"""
CalmSekai Pipeline — seo.py
Step 6: SEO metadata generation via GPT-4o.

Generates YouTube-ready title, description, and hashtags tailored to the
CalmSekai brand aesthetic. Output is saved to metadata/{concept_id}.json.

Public entry points:
    generate_seo(concept: dict) -> dict
    save_metadata(concept: dict, seo: dict) -> Path
    load_metadata(concept_id: str) -> dict
    update_metadata_field(concept_id: str, field: str, value) -> None
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

import config
from concept import update_concept_status

logger = config.logger.getChild("seo")

# ---------------------------------------------------------------------------
# Brand SEO constants — always-included tags
# ---------------------------------------------------------------------------
BRAND_TAGS = [
    "calmsekai",
    "anime aesthetic",
    "healing video",
    "anime realism",
    "atmospheric anime",
    "calm anime",
]

BROAD_TAGS = [
    "shorts",
    "youtube shorts",
    "anime",
    "lofi",
    "chill",
    "relaxing",
    "study with me",
    "anime wallpaper",
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the YouTube SEO strategist for CalmSekai, a short-form anime aesthetic
channel producing healing, atmospheric videos. Your output is used directly as
YouTube metadata — it must be high quality, authentic, and follow the exact
JSON schema below.

OUTPUT RULES:
- Output ONLY valid JSON. No markdown. No extra text before or after.
- Follow the exact schema — no extra fields, no missing fields.

SCHEMA:
{
  "title": "<string>",
  "description": "<string>",
  "hashtags": ["<string>", ...],
  "tags": ["<string>", ...]
}

TITLE RULES:
- Maximum 60 characters (YouTube truncates beyond this)
- Evokes the feeling — poetic, not descriptive
- Examples of good titles:
    "Where Forest Spirits Rest"
    "Rain Against Warm Windows"
    "A Soul That Chose the Sea"
    "The Night That Stayed Quiet"
- Never use: ALL CAPS, excessive punctuation, generic words like "aesthetic video"
- No emojis unless one fits perfectly and is used sparingly (max 1)

DESCRIPTION RULES:
- 3 to 4 sentences total
- Healing, introspective tone — reads like a short poem or mood caption
- Weave in 2–3 keywords naturally (do not keyword-stuff)
- Final sentence: a soft invitation to stay, subscribe, or return
- Example:
    "Some moments ask nothing of you — just to breathe and be still. A spirit
    rests where the old forest meets the last light of day. These are the hours
    that remind you healing is already happening. Stay a while."
- Never mention "YouTube", "watch", "click", or "like and subscribe" explicitly

HASHTAG RULES:
- Return exactly 18 hashtags in the "hashtags" array (with # prefix)
- Mix:
    4–5  brand/niche tags  (#calmsekai, #animeaesthetic, #healingvideo, etc.)
    6–7  mid-reach tags    (specific to the concept theme)
    5–6  broad tags        (#shorts, #anime, #lofi, #chill, etc.)
- Always include: #calmsekai, #youtubeshorts, #animerealism

TAGS RULES:
- "tags" array is the same content as "hashtags" but WITHOUT the # prefix
- Lowercase, no special characters except spaces and hyphens
- YouTube API will use this array directly
"""


def _build_user_prompt(concept: dict) -> str:
    """Build the GPT-4o user message from concept fields."""
    scenes = "\n".join(
        f"  Scene {s['scene']}: {s['description']}"
        for s in concept.get("scene_structure", [])
    )
    return (
        f"Generate YouTube SEO metadata for this CalmSekai video concept:\n\n"
        f"Theme: {concept.get('theme', '')}\n"
        f"Emotion: {concept.get('emotion', '')}\n"
        f"Format: {concept.get('format', '')}\n"
        f"Scene structure:\n{scenes}\n"
        f"Audio mood: {concept.get('audio_mood', '')}\n\n"
        f"Make the title and description feel like they belong to this specific "
        f"concept — not generic. The hashtags should reflect the theme naturally."
    )


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def generate_seo(concept: dict) -> dict:
    """
    Generate YouTube SEO metadata for the given concept using GPT-4o.

    Args:
        concept: Concept dict (must contain theme, emotion, scene_structure,
                 audio_mood, and id).

    Returns:
        SEO dict with keys: title, description, hashtags, tags, concept_id,
        created_at.

    Raises:
        RuntimeError: If OPENAI_API_KEY is unset or all retries fail.
        ValueError:   If GPT-4o returns an invalid JSON structure.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client      = OpenAI(api_key=config.OPENAI_API_KEY)
    user_prompt = _build_user_prompt(concept)
    concept_id  = concept["id"]

    logger.info("Generating SEO metadata for concept %s", concept_id)

    last_error: Exception = RuntimeError("No attempts made")

    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.8,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            raw = response.choices[0].message.content
            seo = json.loads(raw)
            _validate_seo(seo)

            # Ensure brand tags are always present
            seo = _enforce_brand_tags(seo)

            # Attach pipeline metadata
            seo["concept_id"] = concept_id
            seo["created_at"] = datetime.now(timezone.utc).isoformat()

            logger.info(
                "SEO generated — title=%r  hashtags=%d",
                seo["title"], len(seo["hashtags"]),
            )
            return seo

        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Attempt %d/%d — invalid SEO JSON: %s",
                           attempt, config.API_MAX_RETRIES, exc)
            last_error = exc
        except Exception as exc:
            logger.warning("Attempt %d/%d — API error: %s",
                           attempt, config.API_MAX_RETRIES, exc)
            last_error = exc

        if attempt < config.API_MAX_RETRIES:
            time.sleep(config.API_RETRY_DELAY)

    raise RuntimeError(
        f"SEO generation failed after {config.API_MAX_RETRIES} attempts: {last_error}"
    )


def _validate_seo(seo: dict) -> None:
    """Raise ValueError if required fields are missing or invalid."""
    required = ["title", "description", "hashtags", "tags"]
    missing  = [f for f in required if f not in seo]
    if missing:
        raise ValueError(f"SEO JSON missing required fields: {missing}")

    title = seo.get("title", "")
    if len(title) > 100:
        raise ValueError(f"Title too long ({len(title)} chars): {title!r}")

    if not isinstance(seo.get("hashtags"), list):
        raise ValueError("hashtags must be a list")
    if not isinstance(seo.get("tags"), list):
        raise ValueError("tags must be a list")


def _enforce_brand_tags(seo: dict) -> dict:
    """
    Guarantee that core brand hashtags are present regardless of what
    GPT-4o generated. Appends any missing ones without duplicating.
    """
    required_hashtags = {"#calmsekai", "#youtubeshorts", "#animerealism"}

    current_hashtags = {h.lower() for h in seo["hashtags"]}
    for tag in required_hashtags:
        if tag not in current_hashtags:
            seo["hashtags"].append(tag)
            seo["tags"].append(tag.lstrip("#"))
            logger.debug("Enforced missing brand tag: %s", tag)

    return seo


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_metadata(concept: dict, seo: dict) -> Path:
    """
    Write the SEO metadata to metadata/{concept_id}.json.
    Also stores a snapshot of the concept fields used to generate it.

    Updates concept status to "seo_done".

    Returns:
        Path to the saved JSON file.
    """
    concept_id = concept["id"]
    path       = config.METADATA_DIR / f"{concept_id}.json"

    # Store both SEO fields and the source concept snapshot
    payload = {
        **seo,
        "concept_snapshot": {
            "theme":   concept.get("theme"),
            "emotion": concept.get("emotion"),
            "format":  concept.get("format"),
        },
    }

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Metadata saved — %s", path.name)

    update_concept_status(concept_id, "seo_done")
    return path


def load_metadata(concept_id: str) -> dict:
    """
    Load SEO metadata from metadata/{concept_id}.json.

    Raises:
        FileNotFoundError: If no metadata exists for this concept ID.
    """
    path = config.METADATA_DIR / f"{concept_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No metadata found for concept id={concept_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def update_metadata_field(concept_id: str, field: str, value) -> None:
    """
    Update a single field in the metadata JSON on disk.
    Used by the dashboard when the user edits title, description, or hashtags.

    Args:
        concept_id: UUID of the concept.
        field:      Key to update (e.g. "title", "description", "hashtags").
        value:      New value for the field.
    """
    meta = load_metadata(concept_id)
    meta[field] = value
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = config.METADATA_DIR / f"{concept_id}.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Metadata field '%s' updated for concept %s", field, concept_id)


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from concept import load_concept

    if len(sys.argv) < 2:
        print("Usage: python seo.py <concept_id>")
        sys.exit(1)

    cid = sys.argv[1]
    c   = load_concept(cid)

    print(f"Generating SEO for: {c['theme']} / {c['emotion']}")
    seo  = generate_seo(c)
    path = save_metadata(c, seo)

    print(f"\nSaved to: {path}")
    print(f"\nTitle:       {seo['title']}")
    print(f"Description: {seo['description'][:80]}...")
    print(f"Hashtags ({len(seo['hashtags'])}): {' '.join(seo['hashtags'][:5])} ...")
