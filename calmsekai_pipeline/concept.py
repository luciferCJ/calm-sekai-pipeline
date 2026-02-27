"""
CalmSekai Pipeline — concept.py
Step 1: Concept generation via GPT-4.

Generates structured JSON concept cards describing theme, emotion, scene
structure, image prompt, video motion instructions, and audio mood.
Each concept is assigned a UUID and saved to the concepts/ folder.
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openai import OpenAI

import config

logger = config.logger.getChild("concept")

# ---------------------------------------------------------------------------
# Brand constants — rotated themes and allowed formats
# ---------------------------------------------------------------------------
THEMES = [
    "Fairy / Forest Spirits",
    "Sakura / Seasons",
    "Lost Spirits / Wandering Souls",
    "Cozy Interiors / Rainy Windows",
    "Ocean / Water Spirits",
    "Night Sky / Moonlit Scenes",
]

EMOTIONS = [
    "longing",
    "healing",
    "quiet magic",
    "melancholic peace",
    "soft wonder",
    "gentle nostalgia",
]

FORMATS = ["shorts_10s", "shorts_30s"]

# ---------------------------------------------------------------------------
# GPT-4 prompt construction
# ---------------------------------------------------------------------------

_PROMPTS_FILE = config.ROOT_DIR / "prompts.json"

_SYSTEM_PROMPT = """\
You are the creative director for CalmSekai, a YouTube Shorts brand producing
healing, atmospheric anime-realism videos. Your job is to generate a single
video concept as a JSON object — nothing else, no markdown, no explanation.

The aesthetic is: high-detail anime realism, soft cinematic lighting, natural
physics, stillness with subtle organic motion, 9:16 vertical format for Shorts.

The JSON you return MUST follow this exact schema:
{
  "theme": "<one of the CalmSekai themes>",
  "emotion": "<the core feeling the video evokes>",
  "format": "<shorts_10s or shorts_30s>",
  "scene_structure": [
    {"scene": 1, "description": "<establish the world / magic>"},
    {"scene": 2, "description": "<emotional shift or reveal>"},
    {"scene": 3, "description": "<soft resolution or fade>"}
  ],
  "image_prompt": "<detailed DALL-E 3 prompt — anime realism style, cinematic, soft lighting, 9:16 portrait>",
  "video_motion_instruction": "<instruction for the video model — slow organic movement only, no shake, no cuts>",
  "audio_mood": "<description of the music mood to match the emotion — 55–65 BPM, soft piano, ambient pad, no percussion>"
}

Rules for image_prompt:
- Always include: "anime realism style, cinematic composition, soft natural lighting, 9:16 portrait, ultra-detailed"
- Never include: motion blur, action, crowds, text, logos
- Describe one atmospheric scene in high detail

Rules for video_motion_instruction:
- Describe very slow, organic camera or scene movement
- Examples: slow parallax drift, leaves swaying gently, water surface rippling
- Never suggest: cuts, zooms, shake, dramatic movement

Output ONLY valid JSON. No extra text before or after.
"""


def _load_system_prompt() -> str:
    """Return the active system prompt — custom (from prompts.json) or the built-in default."""
    if _PROMPTS_FILE.exists():
        try:
            data = json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
            if data.get("concept_system_prompt"):
                return data["concept_system_prompt"]
        except (KeyError, json.JSONDecodeError):
            pass
    return _SYSTEM_PROMPT


def _build_user_prompt(
    theme: Optional[str],
    emotion: Optional[str],
    format_: Optional[str],
) -> str:
    parts = []
    if theme:
        parts.append(f'Theme: "{theme}"')
    if emotion:
        parts.append(f'Emotion: "{emotion}"')
    if format_:
        parts.append(f'Format: "{format_}"')

    if parts:
        return (
            "Generate a CalmSekai video concept using these parameters:\n"
            + "\n".join(parts)
            + "\n\nFor any parameter not specified above, choose the best fit yourself."
        )
    return (
        "Generate a fresh CalmSekai video concept. "
        "Choose the theme, emotion, and format that feel most cohesive and atmospheric right now."
    )


# ---------------------------------------------------------------------------
# Core generation function
# ---------------------------------------------------------------------------

def generate_concept(
    theme: Optional[str] = None,
    emotion: Optional[str] = None,
    format_: Optional[str] = None,
) -> dict:
    """
    Call GPT-4 to generate a structured video concept.

    Args:
        theme:   Optional theme override (from THEMES list or custom string).
        emotion: Optional emotion override.
        format_: Optional format override — "shorts_10s" or "shorts_30s".

    Returns:
        A concept dict with all required fields plus a UUID and timestamps.

    Raises:
        ValueError: If GPT-4 returns malformed JSON or missing required fields.
        RuntimeError: If all retries are exhausted.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env file."
        )

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    user_prompt = _build_user_prompt(theme, emotion, format_)

    logger.info("Generating concept — theme=%s  emotion=%s  format=%s",
                theme or "auto", emotion or "auto", format_ or "auto")

    last_error: Exception = RuntimeError("No attempts made")

    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _load_system_prompt()},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.9,       # creative variance
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            concept = json.loads(raw)
            _validate_concept(concept)

            # Attach pipeline metadata
            concept["id"]         = str(uuid.uuid4())
            concept["status"]     = "pending_approval"
            concept["created_at"] = datetime.now(timezone.utc).isoformat()

            logger.info("Concept generated — id=%s  theme=%s",
                        concept["id"], concept.get("theme"))
            return concept

        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Attempt %d/%d — invalid concept JSON: %s",
                           attempt, config.API_MAX_RETRIES, exc)
            last_error = exc
        except Exception as exc:
            logger.warning("Attempt %d/%d — API error: %s",
                           attempt, config.API_MAX_RETRIES, exc)
            last_error = exc

        if attempt < config.API_MAX_RETRIES:
            time.sleep(config.API_RETRY_DELAY)

    raise RuntimeError(
        f"Concept generation failed after {config.API_MAX_RETRIES} attempts: {last_error}"
    )


def _validate_concept(concept: dict) -> None:
    """Raise ValueError if any required field is missing."""
    required = [
        "theme",
        "emotion",
        "format",
        "scene_structure",
        "image_prompt",
        "video_motion_instruction",
        "audio_mood",
    ]
    missing = [f for f in required if f not in concept]
    if missing:
        raise ValueError(f"Concept JSON missing required fields: {missing}")

    if not isinstance(concept.get("scene_structure"), list):
        raise ValueError("scene_structure must be a list")

    if concept.get("format") not in FORMATS:
        logger.warning(
            "Unexpected format value '%s' — expected one of %s",
            concept.get("format"), FORMATS,
        )


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def save_concept(concept: dict) -> Path:
    """
    Write concept dict to concepts/{uuid}.json.

    Returns:
        Path to the saved JSON file.
    """
    concept_id = concept["id"]
    path = config.CONCEPTS_DIR / f"{concept_id}.json"
    path.write_text(json.dumps(concept, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Concept saved — %s", path)
    return path


def load_concept(concept_id: str) -> dict:
    """
    Load a concept from disk by its UUID.

    Raises:
        FileNotFoundError: If no concept with that ID exists.
    """
    path = config.CONCEPTS_DIR / f"{concept_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No concept found for id={concept_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def update_concept_status(concept_id: str, status: str) -> None:
    """
    Update the status field of an existing concept on disk.

    Typical status values:
        pending_approval → approved → image_done → video_done →
        assembly_done → seo_done → uploaded
    """
    concept = load_concept(concept_id)
    concept["status"] = status
    concept["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_concept(concept)
    logger.info("Concept %s status → %s", concept_id, status)


def list_concepts() -> list[dict]:
    """
    Return all saved concepts sorted by created_at descending (newest first).
    Used by the dashboard to populate the concept approval screen.
    """
    concepts = []
    for path in config.CONCEPTS_DIR.glob("*.json"):
        try:
            concepts.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read concept file %s: %s", path.name, exc)

    concepts.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return concepts


def approve_concept(concept_id: str) -> None:
    """Mark a concept as approved — pipeline will proceed with it."""
    update_concept_status(concept_id, "approved")


def reject_concept(concept_id: str) -> None:
    """Mark a concept as rejected — it will not be processed."""
    update_concept_status(concept_id, "rejected")


_EDITABLE_FIELDS = {
    "theme", "emotion", "format",
    "image_prompt", "video_motion_instruction",
    "audio_mood", "scene_structure",
}


def update_concept_fields(concept_id: str, fields: dict) -> dict:
    """
    Update editable content fields of a saved concept.

    Only keys present in fields (and in _EDITABLE_FIELDS) are touched.
    Status and pipeline metadata are never overwritten by this function.

    Args:
        concept_id: UUID of the concept to update.
        fields:     Dict of field name → new value.

    Returns:
        The updated concept dict.

    Raises:
        FileNotFoundError: If the concept does not exist.
        ValueError:        If an unrecognised field key is passed.
    """
    unknown = set(fields) - _EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown concept fields: {unknown}")

    concept = load_concept(concept_id)
    for key, value in fields.items():
        concept[key] = value
    concept["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_concept(concept)
    logger.info("Concept %s fields updated: %s", concept_id, list(fields.keys()))
    return concept


def load_concept_prompt() -> str:
    """Return the currently active system prompt (custom or built-in default)."""
    return _load_system_prompt()


def save_concept_prompt(prompt: str) -> None:
    """
    Persist a custom system prompt to prompts.json.

    Passing an empty string clears the override and restores the default.

    Args:
        prompt: The new system prompt text, or "" to reset to default.
    """
    if not prompt.strip():
        # Reset: remove the override
        if _PROMPTS_FILE.exists():
            data = json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
            data.pop("concept_system_prompt", None)
            _PROMPTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Concept system prompt reset to default.")
        return

    # Load existing prompts.json or start fresh
    data = {}
    if _PROMPTS_FILE.exists():
        try:
            data = json.loads(_PROMPTS_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    data["concept_system_prompt"] = prompt
    _PROMPTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Concept system prompt saved to %s", _PROMPTS_FILE.name)


# ---------------------------------------------------------------------------
# CLI helper — run directly to generate a test concept
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Generating test concept...")
    c = generate_concept()
    path = save_concept(c)
    print(f"\nSaved to: {path}")
    print(json.dumps(c, indent=2, ensure_ascii=False))
