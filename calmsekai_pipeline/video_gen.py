"""
CalmSekai Pipeline — video_gen.py
Step 3: Image → Video generation.

Uses an adapter pattern — swap the video provider by changing VIDEO_PROVIDER
in .env without touching any other code.

Supported providers
-------------------
  "grok"   — xAI Grok  (grok-imagine-video)          ← fully implemented
  "runway" — Runway ML  (Gen-3 Alpha / Gen-4)         ← stub, ready to fill
  "kling"  — Kling AI   (Kling 1.x)                   ← stub, ready to fill

Public entry point
------------------
    generate_video(concept: dict) -> Path
"""

import base64
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import httpx

import config
from concept import update_concept_status

logger = config.logger.getChild("video_gen")

# ---------------------------------------------------------------------------
# Shared: video download helper
# ---------------------------------------------------------------------------
_VIDEO_MAX_POLL_SECONDS = 600   # give up after 10 minutes


def _download_video(url: str, dest: Path) -> Path:
    """
    Stream-download a video from a CDN URL and save it to dest.
    Video URLs returned by Grok are ephemeral — call this immediately.

    Returns:
        dest — the saved file path.
    """
    logger.info("Downloading video → %s", dest.name)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=65536):
                f.write(chunk)

    size_mb = dest.stat().st_size / (1024 * 1024)
    logger.info("Video saved — %s (%.1f MB)", dest.name, size_mb)
    return dest


def _image_to_data_uri(image_path: Path) -> str:
    """
    Read a local image and return a base64 data URI string.
    Accepted by the Grok image_url parameter when the image is local.
    """
    suffix = image_path.suffix.lower()
    mime   = "image/png" if suffix == ".png" else "image/jpeg"
    data   = image_path.read_bytes()
    b64    = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# Adapter base class
# ---------------------------------------------------------------------------

class BaseVideoAdapter(ABC):
    """
    Abstract interface for all video-generation providers.
    Each concrete adapter must implement generate().
    """

    @abstractmethod
    def generate(
        self,
        image_path: Path,
        motion_instruction: str,
        concept_id: str,
    ) -> Path:
        """
        Generate a video from a source image.

        Args:
            image_path:         Path to the source still image (PNG/JPG).
            motion_instruction: Natural-language description of the desired motion.
            concept_id:         UUID — used as the output filename.

        Returns:
            Path to the saved .mp4 file.
        """


# ---------------------------------------------------------------------------
# Grok (xAI) adapter — fully implemented
# ---------------------------------------------------------------------------

class GrokVideoAdapter(BaseVideoAdapter):
    """
    Video generation via xAI Grok using the grok-imagine-video model.

    API flow:
        1. POST /v1/videos/generations  →  { request_id }
        2. GET  /v1/videos/{request_id} →  { status, video: { url } }
        3. Download video.url immediately (ephemeral link)
    """

    _BASE_URL = "https://api.x.ai/v1"
    _MODEL    = "grok-imagine-video"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {config.XAI_API_KEY}",
            "Content-Type": "application/json",
        }

    def _submit_job(
        self,
        image_data_uri: str,
        prompt: str,
    ) -> str:
        """
        Submit a video generation job.

        Returns:
            request_id string.

        Raises:
            httpx.HTTPStatusError: On API error.
            KeyError: If response lacks request_id.
        """
        payload = {
            "model":        self._MODEL,
            "prompt":       prompt,
            "image_url":    image_data_uri,
            "duration":     config.VIDEO_DURATION,       # 10 seconds
            "aspect_ratio": config.VIDEO_ASPECT_SHORTS,  # "9:16"
            "resolution":   config.VIDEO_RESOLUTION,     # "720p"
        }

        logger.info("[Grok] Submitting video generation job...")
        with httpx.Client(timeout=30) as client:
            r = client.post(
                f"{self._BASE_URL}/videos/generations",
                headers=self._headers(),
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

        request_id = data["request_id"]
        logger.info("[Grok] Job submitted — request_id=%s", request_id)
        return request_id

    def _poll_job(self, request_id: str) -> str:
        """
        Poll the job until status == "done" or timeout/expiry.

        Returns:
            The ephemeral video URL.

        Raises:
            RuntimeError: If the job expires or times out.
        """
        url      = f"{self._BASE_URL}/videos/{request_id}"
        deadline = time.monotonic() + _VIDEO_MAX_POLL_SECONDS
        attempt  = 0

        while time.monotonic() < deadline:
            attempt += 1
            with httpx.Client(timeout=30) as client:
                r = client.get(url, headers=self._headers())
                data = r.json()

            logger.info("[Grok] Poll #%d — HTTP %d", attempt, r.status_code)

            # Grok signals completion via HTTP status code, not a body field:
            #   202 Accepted  → still generating, keep polling
            #   200 OK        → done, response body contains video data
            if r.status_code == 200:
                # Body may or may not contain a "status" field depending on
                # API version — check for video URL directly.
                video_url = (data.get("video") or {}).get("url")
                if video_url:
                    logger.info("[Grok] Generation complete — video URL received")
                    return video_url

                # Fallback: honour explicit status field if present
                status = data.get("status", "")
                if status == "expired":
                    raise RuntimeError(
                        f"Grok video job {request_id} expired before completing."
                    )
                # If 200 but no video URL yet, fall through and keep polling
                logger.warning("[Grok] HTTP 200 but no video URL in response — retrying")

            elif r.status_code == 202:
                pass  # still pending — normal

            else:
                r.raise_for_status()  # unexpected status → raise

            time.sleep(config.VIDEO_POLL_INTERVAL)

        raise RuntimeError(
            f"Grok video job {request_id} timed out after {_VIDEO_MAX_POLL_SECONDS}s."
        )

    def generate(
        self,
        image_path: Path,
        motion_instruction: str,
        concept_id: str,
    ) -> Path:
        if not config.XAI_API_KEY:
            raise RuntimeError("XAI_API_KEY is not set.")
        if not image_path.exists():
            raise FileNotFoundError(f"Source image not found: {image_path}")

        logger.info(
            "[Grok] Starting image→video for concept %s  image=%s",
            concept_id, image_path.name,
        )

        image_data_uri = _image_to_data_uri(image_path)
        request_id     = self._submit_job(image_data_uri, motion_instruction)
        video_url      = self._poll_job(request_id)

        dest = config.VIDEOS_DIR / f"{concept_id}.mp4"
        return _download_video(video_url, dest)


# ---------------------------------------------------------------------------
# Runway ML adapter — stub (implement when you have API access)
# ---------------------------------------------------------------------------

class RunwayVideoAdapter(BaseVideoAdapter):
    """
    Stub for Runway ML Gen-3 / Gen-4.

    To implement:
    1. Add RUNWAY_API_KEY to config.py and .env
    2. Implement generate() using Runway's REST API
    3. Update _ADAPTERS below
    """

    def generate(
        self,
        image_path: Path,
        motion_instruction: str,
        concept_id: str,
    ) -> Path:
        raise NotImplementedError(
            "Runway ML adapter is not yet implemented. "
            "Set VIDEO_PROVIDER=grok in .env to use Grok instead."
        )


# ---------------------------------------------------------------------------
# Kling AI adapter — stub (implement when you have API access)
# ---------------------------------------------------------------------------

class KlingVideoAdapter(BaseVideoAdapter):
    """
    Stub for Kling AI (Kuaishou).

    To implement:
    1. Add KLING_API_KEY to config.py and .env
    2. Implement generate() using Kling's REST API
    3. Update _ADAPTERS below
    """

    def generate(
        self,
        image_path: Path,
        motion_instruction: str,
        concept_id: str,
    ) -> Path:
        raise NotImplementedError(
            "Kling AI adapter is not yet implemented. "
            "Set VIDEO_PROVIDER=grok in .env to use Grok instead."
        )


# ---------------------------------------------------------------------------
# Adapter registry — add new providers here
# ---------------------------------------------------------------------------

_ADAPTERS: dict[str, type[BaseVideoAdapter]] = {
    "grok":   GrokVideoAdapter,
    "runway": RunwayVideoAdapter,
    "kling":  KlingVideoAdapter,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_video(concept: dict) -> Path:
    """
    Generate a 10-second video clip from the concept's source image.

    Uses the VIDEO_PROVIDER configured in .env. Retries up to
    API_MAX_RETRIES times on failure, then raises RuntimeError.

    Args:
        concept: Concept dict loaded from concepts/{uuid}.json.
                 Must contain "id" and "video_motion_instruction".
                 Source image must already exist at images/{id}.png
                 (i.e. image generation step must have completed).

    Returns:
        Path to the saved .mp4 file in videos/.

    Raises:
        RuntimeError: If the provider fails after all retries.
        FileNotFoundError: If the source image does not exist.
    """
    concept_id         = concept["id"]
    motion_instruction = concept.get("video_motion_instruction", "")

    if not motion_instruction:
        raise ValueError(f"Concept {concept_id} has no video_motion_instruction.")

    image_path = config.concept_paths(concept_id)["image"]
    if not image_path.exists():
        raise FileNotFoundError(
            f"Source image not found for concept {concept_id}. "
            "Run image generation first."
        )

    provider_key = config.VIDEO_PROVIDER
    adapter_cls  = _ADAPTERS.get(provider_key)
    if adapter_cls is None:
        raise ValueError(
            f"Unknown VIDEO_PROVIDER '{provider_key}'. "
            f"Supported: {list(_ADAPTERS.keys())}"
        )

    adapter = adapter_cls()
    last_error: Exception = RuntimeError("No attempts made")

    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            logger.info(
                "Video generation attempt %d/%d — provider=%s  concept=%s",
                attempt, config.API_MAX_RETRIES, provider_key, concept_id,
            )
            path = adapter.generate(image_path, motion_instruction, concept_id)
            update_concept_status(concept_id, "video_done")
            logger.info("Video generation complete — %s", path.name)
            return path

        except (FileNotFoundError, ValueError, NotImplementedError):
            # Non-retriable errors — raise immediately
            raise
        except Exception as exc:
            logger.warning(
                "Video generation attempt %d/%d failed: %s",
                attempt, config.API_MAX_RETRIES, exc,
            )
            last_error = exc
            if attempt < config.API_MAX_RETRIES:
                logger.info("Retrying in %ds...", config.API_RETRY_DELAY)
                time.sleep(config.API_RETRY_DELAY)

    raise RuntimeError(
        f"Video generation failed for concept {concept_id} after "
        f"{config.API_MAX_RETRIES} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from concept import load_concept

    if len(sys.argv) < 2:
        print("Usage: python video_gen.py <concept_id>")
        print("       (concept must exist and image must already be generated)")
        sys.exit(1)

    cid = sys.argv[1]
    c   = load_concept(cid)
    print(f"Generating video for: {c['theme']} / {c['emotion']}")
    p = generate_video(c)
    print(f"Saved: {p}")
