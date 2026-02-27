"""
CalmSekai Pipeline — dashboard/main.py
FastAPI backend serving the review dashboard and all pipeline API routes.

Run with:
    cd calmsekai_pipeline
    python -m uvicorn dashboard.main:app --reload --host 127.0.0.1 --port 8000

Or directly:
    python dashboard/main.py
"""

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

try:
    import tkinter
    import tkinter.filedialog
    _TKINTER_AVAILABLE = True
except ImportError:
    _TKINTER_AVAILABLE = False

_TK_LOCK = threading.Lock()

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Add the pipeline root to sys.path so we can import pipeline modules
# ---------------------------------------------------------------------------
_PIPELINE_ROOT = Path(__file__).resolve().parent.parent
if str(_PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PIPELINE_ROOT))

import config  # noqa: E402  (must come after sys.path insertion)

logger = config.logger.getChild("dashboard")

# ---------------------------------------------------------------------------
# Thumbnails folder (created on startup)
# ---------------------------------------------------------------------------
THUMBNAILS_DIR = config.ROOT_DIR / "thumbnails"
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Supported audio file extensions for local audio browser
# ---------------------------------------------------------------------------
AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CalmSekai Pipeline Dashboard",
    description="Review, assemble, and upload CalmSekai videos",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # local only — no security concern
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Background job manager
# ---------------------------------------------------------------------------

class JobManager:
    """
    Tracks long-running pipeline stages in background threads.
    One job per concept at a time. Thread-safe via a lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self, concept_id: str, stage: str, fn, *args) -> None:
        """
        Start fn(*args) in a daemon thread tagged with concept_id + stage.

        Raises:
            ValueError: If a job is already running for this concept.
        """
        with self._lock:
            existing = self._jobs.get(concept_id)
            if existing and existing["thread"].is_alive():
                raise ValueError(
                    f"Stage '{existing['stage']}' is already running for concept {concept_id}."
                )

        def _run() -> None:
            try:
                fn(*args)
            except Exception as exc:
                logger.error("Background job failed [%s/%s]: %s", concept_id, stage, exc)
                with self._lock:
                    self._jobs[concept_id]["error"] = str(exc)
            finally:
                with self._lock:
                    self._jobs[concept_id]["running"] = False

        thread = threading.Thread(target=_run, daemon=True, name=f"{concept_id[:8]}-{stage}")
        with self._lock:
            self._jobs[concept_id] = {
                "stage":   stage,
                "thread":  thread,
                "running": True,
                "error":   None,
            }
        thread.start()
        logger.info("Started background job: concept=%s  stage=%s", concept_id, stage)

    def status(self, concept_id: str) -> Optional[dict]:
        """Return job status dict or None if no job ever started."""
        with self._lock:
            job = self._jobs.get(concept_id)
            if not job:
                return None
            return {
                "stage":   job["stage"],
                "running": job["thread"].is_alive(),
                "error":   job["error"],
            }


jobs = JobManager()


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------

class GenerateConceptRequest(BaseModel):
    theme:   Optional[str] = None
    emotion: Optional[str] = None
    format_: Optional[str] = None   # "shorts_10s" | "shorts_30s"


class AssembleRequest(BaseModel):
    audio_path:     str           # absolute path to local audio file
    breathing_zoom: bool = True


class MetadataUpdateRequest(BaseModel):
    field: str    # "title" | "description" | "hashtags" | "tags"
    value: Any    # str for title/description, list for hashtags/tags


class AudioFolderRequest(BaseModel):
    folder: str   # absolute path to local audio folder


class ConceptUpdateRequest(BaseModel):
    theme:                    Optional[str]  = None
    emotion:                  Optional[str]  = None
    format:                   Optional[str]  = None
    image_prompt:             Optional[str]  = None
    video_motion_instruction: Optional[str]  = None
    audio_mood:               Optional[str]  = None
    scene_structure:          Optional[list] = None


class PromptUpdateRequest(BaseModel):
    prompt: str   # new system prompt, or "" to reset to default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_concept(concept_id: str) -> dict:
    """Load concept or raise 404."""
    from concept import load_concept
    try:
        return load_concept(concept_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Concept not found: {concept_id}")


def _extract_thumbnail(concept_id: str) -> Path:
    """
    Extract the first frame of the final video as a JPEG thumbnail.
    Caches to thumbnails/{concept_id}.jpg — re-extracts only if stale.
    """
    final_path = config.concept_paths(concept_id)["final"]
    thumb_path = THUMBNAILS_DIR / f"{concept_id}.jpg"

    if not final_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Final video not found. Run assembly first.",
        )

    # Re-extract only if thumbnail is older than the final video
    if thumb_path.exists() and thumb_path.stat().st_mtime >= final_path.stat().st_mtime:
        return thumb_path

    cmd = [
        config.FFMPEG_PATH,
        "-y",
        "-i", str(final_path),
        "-vframes", "1",
        "-q:v", "2",          # high quality JPEG
        str(thumb_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not thumb_path.exists():
        raise HTTPException(status_code=500, detail="Thumbnail extraction failed.")

    return thumb_path


# ===========================================================================
# API Routes — Concepts
# ===========================================================================

@app.get("/api/concepts")
def list_concepts_route():
    """Return all concepts sorted newest first."""
    from concept import list_concepts
    return list_concepts()


@app.post("/api/concepts/generate", status_code=201)
def generate_concept_route(body: GenerateConceptRequest = GenerateConceptRequest()):
    """Generate a new concept via GPT-4o and save it."""
    from concept import generate_concept, save_concept
    try:
        concept = generate_concept(
            theme=body.theme,
            emotion=body.emotion,
            format_=body.format_,
        )
        save_concept(concept)
        return concept
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/concepts/{concept_id}")
def get_concept_route(concept_id: str):
    """Return a single concept by UUID."""
    return _require_concept(concept_id)


@app.patch("/api/concepts/{concept_id}")
def update_concept_route(concept_id: str, body: ConceptUpdateRequest):
    """
    Update editable content fields of a concept (theme, emotion, image_prompt, etc.).
    Status and pipeline metadata are never modified by this endpoint.
    """
    _require_concept(concept_id)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided.")
    try:
        from concept import update_concept_fields
        return update_concept_fields(concept_id, fields)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/concepts/{concept_id}/approve")
def approve_concept_route(concept_id: str):
    """Mark concept as approved — pipeline can proceed."""
    _require_concept(concept_id)
    from concept import approve_concept
    approve_concept(concept_id)
    return {"status": "approved"}


@app.post("/api/concepts/{concept_id}/reject")
def reject_concept_route(concept_id: str):
    """Mark concept as rejected."""
    _require_concept(concept_id)
    from concept import reject_concept
    reject_concept(concept_id)
    return {"status": "rejected"}


# ===========================================================================
# API Routes — System prompts
# ===========================================================================

@app.get("/api/prompts/concept")
def get_concept_prompt():
    """Return the currently active GPT-4o system prompt for concept generation."""
    from concept import load_concept_prompt
    return {"prompt": load_concept_prompt()}


@app.patch("/api/prompts/concept")
def update_concept_prompt(body: PromptUpdateRequest):
    """
    Save a custom system prompt for concept generation.
    Pass prompt="" to reset to the built-in default.
    """
    from concept import save_concept_prompt
    save_concept_prompt(body.prompt)
    return {"detail": "Prompt saved." if body.prompt.strip() else "Prompt reset to default."}


# ===========================================================================
# API Routes — Pipeline execution (background jobs)
# ===========================================================================

@app.post("/api/concepts/{concept_id}/run/image", status_code=202)
def run_image_route(concept_id: str):
    """
    Start image generation in the background.
    Concept must be approved. Poll GET /api/concepts/{id} for status updates.
    """
    concept = _require_concept(concept_id)
    if concept["status"] not in ("approved",):
        raise HTTPException(
            status_code=409,
            detail=f"Concept must be 'approved' to generate image. Current: {concept['status']}",
        )
    try:
        from image_gen import generate_image
        jobs.start(concept_id, "image", generate_image, concept)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"detail": "Image generation started", "concept_id": concept_id}


@app.post("/api/concepts/{concept_id}/run/video", status_code=202)
def run_video_route(concept_id: str):
    """
    Start video generation in the background.
    Image must exist (status: image_done).
    """
    concept = _require_concept(concept_id)
    if concept["status"] not in ("image_done",):
        raise HTTPException(
            status_code=409,
            detail=f"Image must be done before generating video. Current: {concept['status']}",
        )
    try:
        from video_gen import generate_video
        jobs.start(concept_id, "video", generate_video, concept)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"detail": "Video generation started", "concept_id": concept_id}


@app.post("/api/concepts/{concept_id}/run/seo", status_code=202)
def run_seo_route(concept_id: str):
    """
    Generate SEO metadata in the background.
    Can run as soon as concept is approved.
    """
    concept = _require_concept(concept_id)

    def _run_seo(c: dict) -> None:
        from seo import generate_seo, save_metadata
        seo_data = generate_seo(c)
        save_metadata(c, seo_data)

    try:
        jobs.start(concept_id, "seo", _run_seo, concept)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"detail": "SEO generation started", "concept_id": concept_id}


@app.post("/api/concepts/{concept_id}/run/assemble", status_code=202)
def run_assemble_route(concept_id: str, body: AssembleRequest):
    """
    Start FFmpeg assembly in the background.
    Video must exist (status: video_done).
    audio_path must be an absolute path to a local audio file.
    """
    concept = _require_concept(concept_id)
    if concept["status"] not in ("video_done", "assembly_done", "seo_done"):
        raise HTTPException(
            status_code=409,
            detail=f"Video must be done before assembling. Current: {concept['status']}",
        )

    audio = Path(body.audio_path)
    if not audio.exists():
        raise HTTPException(status_code=400, detail=f"Audio file not found: {audio}")

    try:
        from assembly import assemble
        jobs.start(
            concept_id, "assemble",
            assemble, concept, audio, body.breathing_zoom,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"detail": "Assembly started", "concept_id": concept_id}


@app.post("/api/concepts/{concept_id}/run/audio", status_code=202)
def run_audio_route(concept_id: str):
    """
    Generate AI music for this concept via Suno API (background job).
    Requires SUNO_API_KEY to be configured.
    Concept must be at video_done, assembly_done, or seo_done stage.
    Returns the deterministic audio path immediately (for polling / UI display).
    """
    if not config.SUNO_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="SUNO_API_KEY is not configured. Add it to .env and restart the server.",
        )

    concept = _require_concept(concept_id)
    if concept["status"] not in ("video_done", "assembly_done", "seo_done"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Concept must be at video_done, assembly_done, or seo_done to generate audio. "
                f"Current: {concept['status']}"
            ),
        )

    audio_path = config.concept_paths(concept_id)["audio"]

    try:
        from audio_gen import generate_audio
        jobs.start(concept_id, "audio", generate_audio, concept)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "detail": "Audio generation started",
        "concept_id": concept_id,
        "audio_path": str(audio_path),
    }


@app.get("/api/concepts/{concept_id}/audio/info")
def get_audio_info(concept_id: str):
    """
    Check whether Suno-generated audio exists for this concept.
    Returns {"exists": bool, "path": str|null, "name": str|null, "size_kb": float|null}.
    Called on ReviewView mount to restore Suno tab state across sessions.
    """
    audio_path = config.concept_paths(concept_id)["audio"]
    if audio_path.exists() and audio_path.stat().st_size > 0:
        return {
            "exists":   True,
            "path":     str(audio_path),
            "name":     audio_path.name,
            "size_kb":  round(audio_path.stat().st_size / 1024, 1),
        }
    return {"exists": False, "path": None, "name": None, "size_kb": None}


# ===========================================================================
# API Routes — Job status
# ===========================================================================

@app.get("/api/jobs/{concept_id}")
def get_job_status(concept_id: str):
    """
    Check whether a background pipeline job is currently running.
    Returns null if no job has been started for this concept.
    """
    status = jobs.status(concept_id)
    if status is None:
        return JSONResponse(content=None)
    return status


# ===========================================================================
# API Routes — Metadata (SEO)
# ===========================================================================

@app.get("/api/concepts/{concept_id}/metadata")
def get_metadata_route(concept_id: str):
    """Return saved SEO metadata for a concept."""
    from seo import load_metadata
    try:
        return load_metadata(concept_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Metadata not found. Run SEO generation first.")


@app.patch("/api/concepts/{concept_id}/metadata")
def update_metadata_route(concept_id: str, body: MetadataUpdateRequest):
    """Update a single metadata field (used by dashboard editor)."""
    from seo import update_metadata_field
    try:
        update_metadata_field(concept_id, body.field, body.value)
        return {"detail": f"Field '{body.field}' updated"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Metadata not found.")


# ===========================================================================
# API Routes — Media files
# ===========================================================================

@app.get("/api/concepts/{concept_id}/image")
def serve_image(concept_id: str):
    """Serve the generated still image."""
    path = config.concept_paths(concept_id)["image"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found. Run image generation first.")
    return FileResponse(path, media_type="image/png")


@app.get("/api/concepts/{concept_id}/video/raw")
def serve_raw_video(concept_id: str):
    """Serve the raw Grok-generated video (before assembly)."""
    path = config.concept_paths(concept_id)["video"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Raw video not found.")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/concepts/{concept_id}/video/final")
def serve_final_video(concept_id: str):
    """Serve the assembled final video (video + audio + fades)."""
    path = config.concept_paths(concept_id)["final"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Final video not found. Run assembly first.")
    return FileResponse(path, media_type="video/mp4")


@app.get("/api/concepts/{concept_id}/thumbnail")
def serve_thumbnail(concept_id: str):
    """
    Serve or generate a JPEG thumbnail (first frame of the final video).
    Cached — regenerated only when the final video is newer.
    """
    thumb = _extract_thumbnail(concept_id)
    return FileResponse(thumb, media_type="image/jpeg")


# ===========================================================================
# API Routes — Audio browser + native folder picker
# ===========================================================================

@app.post("/api/browse/folder")
def browse_folder():
    """
    Open the OS native folder picker dialog and return the selected path.
    Uses tkinter on the server (works because the server runs locally).
    Returns {"path": "C:/..."} or {"path": null} if the user cancelled.
    """
    if not _TKINTER_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail="tkinter is not available on this server. Type the folder path manually.",
        )
    with _TK_LOCK:
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = tkinter.filedialog.askdirectory(title="Select audio folder")
        root.destroy()

    return {"path": folder if folder else None}


@app.post("/api/suno/callback", include_in_schema=False)
async def suno_callback(request: Request):
    """
    No-op webhook receiver for Suno's callBackUrl requirement.
    Suno will POST here when generation is done, but we rely on polling
    (GET /api/v1/generate/record-info) — this endpoint just returns 200.
    """
    return {"ok": True}


@app.get("/api/audio/list")
def list_audio_files(folder: str):
    """
    List audio files in the given local folder path.
    Query param: ?folder=C:/path/to/my/music

    Returns a list of {name, path, ext} objects.
    """
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {folder}")

    files = [
        {
            "name": f.name,
            "path": str(f),          # full absolute path — sent back for assembly
            "ext":  f.suffix.lower(),
            "size_kb": round(f.stat().st_size / 1024, 1),
        }
        for f in sorted(folder_path.iterdir())
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    ]

    return {"folder": str(folder_path), "files": files}


# ===========================================================================
# API Routes — YouTube upload (delegates to upload.py)
# ===========================================================================

@app.post("/api/concepts/{concept_id}/upload", status_code=202)
def upload_to_youtube(concept_id: str):
    """
    Trigger YouTube upload for an assembled, SEO-packaged concept.
    Runs in the background — poll concept status for 'uploaded'.
    """
    concept = _require_concept(concept_id)
    if concept["status"] not in ("seo_done", "assembly_done"):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Concept must have 'seo_done' or 'assembly_done' status to upload. "
                f"Current: {concept['status']}"
            ),
        )

    def _run_upload(c: dict) -> None:
        from upload import upload_video
        upload_video(c)

    try:
        jobs.start(concept_id, "upload", _run_upload, concept)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"detail": "Upload started", "concept_id": concept_id}


# ===========================================================================
# Serve Vue.js SPA
# ===========================================================================

# Serve built Vue app from dashboard/frontend/dist/ if it exists
_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
_FRONTEND_DEV  = Path(__file__).parent / "frontend"

if _FRONTEND_DIST.exists():
    # Production: serve built assets
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Catch-all: return index.html for client-side routing."""
        index = _FRONTEND_DIST / "index.html"
        if not index.exists():
            return JSONResponse({"detail": "Frontend not built. Run: cd dashboard/frontend && npm run build"}, status_code=503)
        return FileResponse(index)

else:
    @app.get("/", include_in_schema=False)
    def serve_placeholder():
        return JSONResponse({
            "detail": "Frontend not built yet.",
            "instructions": [
                "cd calmsekai_pipeline/dashboard/frontend",
                "npm install",
                "npm run build",
                "Then restart this server.",
            ],
            "api_docs": "http://127.0.0.1:8000/docs",
        })


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    uvicorn.run(
        "dashboard.main:app",
        host=config.DASHBOARD_HOST,
        port=config.DASHBOARD_PORT,
        reload=True,
        reload_dirs=[str(_PIPELINE_ROOT)],
        log_level="info",
    )
