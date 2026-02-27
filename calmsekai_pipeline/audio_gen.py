"""
CalmSekai Pipeline — audio_gen.py
Step 4: AI music generation via Suno API.

Generates instrumental ambient music matched to the concept's audio_mood.
Output is saved to audio/{concept_id}.mp3.

Public entry point:
    generate_audio(concept: dict) -> Path

This step is optional — the dashboard also supports picking a local audio
file. Concept status is NOT updated by this module; audio generation is
not a mandatory pipeline stage.
"""

import time
from pathlib import Path

import httpx

import config

logger = config.logger.getChild("audio_gen")

# ---------------------------------------------------------------------------
# Suno API constants
# ---------------------------------------------------------------------------
_SUNO_MODEL             = "V4_5ALL"
_SUNO_MAX_POLL_SECONDS  = 300    # 5 minutes max wait
_SUNO_POLL_INTERVAL     = 5      # seconds between status polls

# Terminal error statuses returned by Suno
_SUNO_ERROR_STATUSES = {
    "CREATE_TASK_FAILED",
    "GENERATE_AUDIO_FAILED",
    "SENSITIVE_WORD_ERROR",
}


# ---------------------------------------------------------------------------
# Mood → Suno style mapping
# ---------------------------------------------------------------------------

def _mood_to_style(audio_mood: str) -> str:
    """
    Convert a concept's audio_mood description to a Suno style string.

    Suno's style field accepts natural language descriptions and tag-style
    keywords mixed together. We derive a base style from keyword matching,
    then append the full audio_mood for extra context.

    Args:
        audio_mood: The audio_mood string from the concept JSON.

    Returns:
        A style string suitable for the Suno API.
    """
    mood_lower = audio_mood.lower()

    if any(k in mood_lower for k in ("piano", "soft piano")):
        base = "ambient lo-fi piano, healing, no percussion"
    elif any(k in mood_lower for k in ("flute", "strings", "orchestral")):
        base = "ambient orchestral meditation, cinematic, no drums"
    elif any(k in mood_lower for k in ("electronic", "synth", "pad")):
        base = "ambient electronic, atmospheric pads, no beats"
    elif any(k in mood_lower for k in ("nature", "forest", "rain", "ocean")):
        base = "ambient nature soundscape, meditative, no percussion"
    else:
        base = "ambient meditation, atmospheric, no percussion"

    return f"{base}, {audio_mood}"


# ---------------------------------------------------------------------------
# Suno API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.SUNO_API_KEY}",
        "Content-Type": "application/json",
    }


def _submit_suno_job(audio_mood: str, theme: str, client: httpx.Client) -> str:
    """
    Submit an instrumental music generation request to Suno.

    Args:
        audio_mood: Concept's audio_mood field.
        theme:      Concept's theme — used as the track title.
        client:     Shared httpx Client for the generation session.

    Returns:
        taskId string for polling.

    Raises:
        RuntimeError: If the API returns an unexpected response.
        httpx.HTTPStatusError: On non-2xx HTTP response.
    """
    # callBackUrl is required by the Suno API even when using polling.
    # We point it at our local dashboard's no-op endpoint; Suno will
    # attempt the callback but we don't rely on it — polling drives us.
    payload = {
        "customMode":   True,
        "instrumental": True,
        "model":        _SUNO_MODEL,
        "style":        _mood_to_style(audio_mood),
        "title":        f"CalmSekai — {theme}",
        "callBackUrl":  (
            f"http://{config.DASHBOARD_HOST}:{config.DASHBOARD_PORT}"
            "/api/suno/callback"
        ),
    }

    logger.info("[Suno] Submitting generation job — style=%s", payload["style"][:60])

    r = client.post(
        f"{config.SUNO_BASE_URL}/api/v1/generate",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    try:
        task_id = data["data"]["taskId"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Suno response missing taskId. Full response: {data}"
        ) from exc

    logger.info("[Suno] Job submitted — taskId=%s", task_id)
    return task_id


def _poll_suno_job(task_id: str, client: httpx.Client) -> str:
    """
    Poll Suno until the track is ready, then return the audio download URL.

    Status progression: PENDING → TEXT_SUCCESS → FIRST_SUCCESS → SUCCESS

    We treat FIRST_SUCCESS the same as SUCCESS: Suno generates two songs
    per request, and FIRST_SUCCESS means the first is ready. Taking it
    immediately avoids waiting for the second and roughly halves wait time.

    Args:
        task_id: The taskId returned by _submit_suno_job.
        client:  Shared httpx Client.

    Returns:
        Direct MP3 download URL (ephemeral — download immediately).

    Raises:
        RuntimeError: On terminal error status or timeout.
    """
    deadline = time.monotonic() + _SUNO_MAX_POLL_SECONDS
    attempt  = 0

    while time.monotonic() < deadline:
        attempt += 1

        r = client.get(
            f"{config.SUNO_BASE_URL}/api/v1/generate/record-info",
            headers=_headers(),
            params={"taskId": task_id},
            timeout=30,
        )
        r.raise_for_status()
        data   = r.json()
        status = (data.get("data") or data).get("status", "PENDING")

        logger.info("[Suno] Poll #%d — status=%s", attempt, status)

        if status in ("FIRST_SUCCESS", "SUCCESS"):
            try:
                suno_data = (data.get("data") or data)["response"]["sunoData"]
                audio_url = suno_data[0]["audioUrl"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(
                    f"Suno {status} but no audioUrl in response: {data}"
                ) from exc
            logger.info("[Suno] Audio ready — url=%s…", audio_url[:80])
            return audio_url

        if status in _SUNO_ERROR_STATUSES:
            raise RuntimeError(
                f"Suno generation failed with status '{status}' "
                f"(taskId={task_id}). Check your prompt for restricted content."
            )

        time.sleep(_SUNO_POLL_INTERVAL)

    raise RuntimeError(
        f"Suno job {task_id} timed out after {_SUNO_MAX_POLL_SECONDS}s."
    )


def _download_audio(url: str, dest: Path) -> Path:
    """
    Stream-download an MP3 from a CDN URL and save it to dest.

    Args:
        url:  Full HTTPS audio URL from Suno.
        dest: Destination path (audio/{concept_id}.mp3).

    Returns:
        dest — the saved file path.
    """
    logger.info("[Suno] Downloading audio → %s", dest.name)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=65536):
                f.write(chunk)

    size_kb = dest.stat().st_size / 1024
    logger.info("[Suno] Audio saved — %s (%.1f KB)", dest.name, size_kb)
    return dest


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_audio(concept: dict) -> Path:
    """
    Generate an instrumental music track for the given concept via Suno API.

    The track is based on concept["audio_mood"] and concept["theme"].
    Saved to audio/{concept_id}.mp3.

    Idempotent: if audio/{concept_id}.mp3 already exists and is non-empty,
    it is returned immediately without making an API call.

    Does NOT update concept status — audio generation is optional and not
    part of the mandatory concept status flow.

    Args:
        concept: Concept dict with "id", "audio_mood", and "theme" fields.

    Returns:
        Path to the saved .mp3 file.

    Raises:
        RuntimeError: If SUNO_API_KEY is not set, or generation fails after retries.
        ValueError:   If concept is missing audio_mood.
    """
    if not config.SUNO_API_KEY:
        raise RuntimeError(
            "SUNO_API_KEY is not set. Add it to your .env file. "
            "You can still use local audio file selection instead."
        )

    concept_id = concept["id"]
    audio_mood = concept.get("audio_mood", "").strip()
    theme      = concept.get("theme", "CalmSekai")

    if not audio_mood:
        raise ValueError(f"Concept {concept_id} has no audio_mood field.")

    dest = config.AUDIO_DIR / f"{concept_id}.mp3"

    # Idempotency check — return cached file if it already exists
    if dest.exists() and dest.stat().st_size > 0:
        logger.info(
            "[Suno] Audio already generated for concept %s — returning cached file.",
            concept_id,
        )
        return dest

    logger.info(
        "[Suno] Starting audio generation — concept=%s  mood=%s",
        concept_id, audio_mood[:60],
    )

    last_error: Exception = RuntimeError("No attempts made")

    with httpx.Client() as client:
        for attempt in range(1, config.API_MAX_RETRIES + 1):
            try:
                logger.info(
                    "[Suno] Attempt %d/%d", attempt, config.API_MAX_RETRIES
                )
                task_id   = _submit_suno_job(audio_mood, theme, client)
                audio_url = _poll_suno_job(task_id, client)
                path      = _download_audio(audio_url, dest)
                logger.info("[Suno] Generation complete — %s", path.name)
                return path

            except Exception as exc:
                logger.warning(
                    "[Suno] Attempt %d/%d failed: %s",
                    attempt, config.API_MAX_RETRIES, exc,
                )
                last_error = exc
                if attempt < config.API_MAX_RETRIES:
                    logger.info("Retrying in %ds…", config.API_RETRY_DELAY)
                    time.sleep(config.API_RETRY_DELAY)

    raise RuntimeError(
        f"Suno audio generation failed after {config.API_MAX_RETRIES} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from concept import load_concept

    if len(sys.argv) < 2:
        print("Usage: python audio_gen.py <concept_id>")
        sys.exit(1)

    cid = sys.argv[1]
    c   = load_concept(cid)
    print(f"Generating audio for: {c['theme']} / {c['audio_mood']}")
    p = generate_audio(c)
    print(f"Saved: {p}")
