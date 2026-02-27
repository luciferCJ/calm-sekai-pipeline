"""
CalmSekai Pipeline — image_gen.py
Step 2: Still image generation.

Primary provider  : DALL-E 3 (OpenAI)
Fallback provider : Fal.ai  (flux-lora with anime LoRA)

Public entry point:
    generate_image(concept: dict) -> Path

The function reads concept["image_prompt"] and concept["id"], calls the
configured primary provider, automatically retries then falls back to the
secondary provider on failure, saves the result to images/{concept_id}.png,
and updates the concept status to "image_done".
"""

import time
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI
import fal_client

import config
from concept import update_concept_status

logger = config.logger.getChild("image_gen")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_ANIME_STYLE_SUFFIX = (
    "anime realism style, cinematic composition, soft natural lighting, "
    "ultra-detailed, 9:16 portrait orientation, no motion blur, no text, no logos"
)


# ---------------------------------------------------------------------------
# Internal: image download helper
# ---------------------------------------------------------------------------

def _download_image(url: str, dest: Path) -> Path:
    """
    Stream-download an image from a CDN URL and save it to dest.

    Args:
        url:  Full HTTPS URL returned by the image generation API.
        dest: Destination Path (should end in .png or .jpg).

    Returns:
        dest — the saved file path.

    Raises:
        httpx.HTTPStatusError: On non-2xx HTTP responses.
        OSError: If the file cannot be written.
    """
    logger.info("Downloading image → %s", dest.name)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=8192):
                f.write(chunk)

    logger.info("Image saved — %s (%.1f KB)", dest.name, dest.stat().st_size / 1024)
    return dest


# ---------------------------------------------------------------------------
# Provider: DALL-E 3
# ---------------------------------------------------------------------------

def _generate_dalle3(prompt: str, concept_id: str, aspect_ratio: str = "9:16") -> Path:
    """
    Generate one image with DALL-E 3 and save it to images/{concept_id}.png.

    Args:
        prompt:     The image_prompt string from the concept JSON.
        concept_id: UUID of the concept — used as the filename.

    Returns:
        Path to the saved PNG file.

    Raises:
        RuntimeError: If OPENAI_API_KEY is not configured.
        Exception:    Propagated from the OpenAI SDK on API error.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    full_prompt = f"{prompt}. {_ANIME_STYLE_SUFFIX}"

    logger.info("[DALL-E 3] Generating image for concept %s", concept_id)
    logger.debug("[DALL-E 3] Prompt: %s", full_prompt[:120])

    ar_cfg   = config.ASPECT_RATIO_CONFIG.get(aspect_ratio, config.ASPECT_RATIO_CONFIG["9:16"])
    img_size = ar_cfg["image_size"]

    response = client.images.generate(
        model="dall-e-3",
        prompt=full_prompt,
        n=1,
        size=img_size,
        quality="hd",
        style="natural",                 # less vivid, more painterly/realistic
        response_format="url",
    )

    image_url = response.data[0].url
    revised   = response.data[0].revised_prompt
    logger.info("[DALL-E 3] Revised prompt: %s", (revised or "")[:80])

    dest = config.IMAGES_DIR / f"{concept_id}.png"
    return _download_image(image_url, dest)


# ---------------------------------------------------------------------------
# Provider: Fal.ai (flux-lora + anime LoRA)
# ---------------------------------------------------------------------------

def _generate_falai(prompt: str, concept_id: str, aspect_ratio: str = "9:16") -> Path:
    """
    Generate one image with fal.ai (flux-lora + anime LoRA) and save it
    to images/{concept_id}.png.

    Requires:
        FAL_KEY        — set in .env
        FAL_ANIME_LORA_URL — public URL to a .safetensors anime LoRA file

    Returns:
        Path to the saved PNG file.

    Raises:
        RuntimeError: If FAL_KEY or FAL_ANIME_LORA_URL are not configured.
    """
    if not config.FAL_KEY:
        raise RuntimeError("FAL_KEY is not set.")
    if not config.FAL_ANIME_LORA_URL:
        raise RuntimeError(
            "FAL_ANIME_LORA_URL is not set. "
            "Provide a public URL to an anime LoRA .safetensors file in .env."
        )

    import os
    os.environ["FAL_KEY"] = config.FAL_KEY  # fal_client reads from env

    full_prompt = f"{prompt}. {_ANIME_STYLE_SUFFIX}"
    logger.info("[Fal.ai] Generating image for concept %s", concept_id)
    logger.debug("[Fal.ai] Prompt: %s", full_prompt[:120])

    ar_cfg   = config.ASPECT_RATIO_CONFIG.get(aspect_ratio, config.ASPECT_RATIO_CONFIG["9:16"])
    fal_size = ar_cfg["fal_image_size"]

    result = fal_client.subscribe(
        config.FAL_ANIME_MODEL,          # default: "fal-ai/flux-lora"
        arguments={
            "prompt": full_prompt,
            "loras": [
                {
                    "path":  config.FAL_ANIME_LORA_URL,
                    "scale": 1.0,
                }
            ],
            "num_images": 1,
            "image_size": fal_size,
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "output_format": "png",
            "enable_safety_checker": True,
        },
        with_logs=False,
    )

    image_url = result["images"][0]["url"]
    dest = config.IMAGES_DIR / f"{concept_id}.png"
    return _download_image(image_url, dest)


# ---------------------------------------------------------------------------
# Provider dispatch table
# ---------------------------------------------------------------------------

_PROVIDERS = {
    "dalle3": _generate_dalle3,
    "falai":  _generate_falai,
}

_FALLBACK = {
    "dalle3": "falai",
    "falai":  "dalle3",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_image(concept: dict) -> Path:
    """
    Generate a still image for the given concept.

    Tries the configured IMAGE_PROVIDER first. On failure retries up to
    API_MAX_RETRIES times, then automatically attempts the fallback provider.
    Saves the result to images/{concept_id}.png and updates concept status
    to "image_done".

    Args:
        concept: Concept dict loaded from concepts/{uuid}.json.
                 Must contain "id" and "image_prompt".

    Returns:
        Path to the saved image file.

    Raises:
        RuntimeError: If both primary and fallback providers fail entirely.
    """
    concept_id   = concept["id"]
    prompt       = concept.get("image_prompt", "")
    aspect_ratio = concept.get("aspect_ratio", "9:16")

    if not prompt:
        raise ValueError(f"Concept {concept_id} has no image_prompt.")

    primary_key  = config.IMAGE_PROVIDER
    fallback_key = _FALLBACK.get(primary_key)

    # Try primary provider with retries
    primary_path = _try_provider(primary_key, prompt, concept_id, aspect_ratio)
    if primary_path:
        update_concept_status(concept_id, "image_done")
        return primary_path

    # Primary exhausted — attempt fallback
    if fallback_key:
        logger.warning(
            "Primary image provider '%s' failed. Attempting fallback '%s'.",
            primary_key, fallback_key,
        )
        fallback_path = _try_provider(fallback_key, prompt, concept_id, aspect_ratio)
        if fallback_path:
            update_concept_status(concept_id, "image_done")
            return fallback_path

    raise RuntimeError(
        f"Image generation failed for concept {concept_id} — "
        f"both '{primary_key}' and '{fallback_key}' providers exhausted."
    )


def _try_provider(
    provider_key: str,
    prompt: str,
    concept_id: str,
    aspect_ratio: str = "9:16",
) -> Optional[Path]:
    """
    Attempt image generation with a named provider, retrying on failure.

    Returns:
        Path on success, None if all retries are exhausted.
    """
    fn = _PROVIDERS.get(provider_key)
    if fn is None:
        logger.error("Unknown image provider '%s' — skipping.", provider_key)
        return None

    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            logger.info(
                "[%s] Attempt %d/%d — concept %s",
                provider_key, attempt, config.API_MAX_RETRIES, concept_id,
            )
            path = fn(prompt, concept_id, aspect_ratio)
            logger.info("[%s] Success — %s", provider_key, path.name)
            return path

        except Exception as exc:
            logger.warning(
                "[%s] Attempt %d/%d failed: %s",
                provider_key, attempt, config.API_MAX_RETRIES, exc,
            )
            if attempt < config.API_MAX_RETRIES:
                logger.info("Retrying in %ds...", config.API_RETRY_DELAY)
                time.sleep(config.API_RETRY_DELAY)

    return None


# ---------------------------------------------------------------------------
# CLI helper — run directly to test image generation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json, sys

    if len(sys.argv) < 2:
        print("Usage: python image_gen.py <concept_id>")
        print("       (concept must already exist in concepts/ folder)")
        sys.exit(1)

    from concept import load_concept
    cid = sys.argv[1]
    c   = load_concept(cid)

    print(f"Generating image for: {c['theme']} / {c['emotion']}")
    p = generate_image(c)
    print(f"Saved: {p}")
