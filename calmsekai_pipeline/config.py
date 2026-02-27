"""
CalmSekai Pipeline — config.py
Central configuration: API keys, paths, and pipeline settings.
All values are loaded from environment variables / .env file.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env from the pipeline root (same directory as this file)
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
load_dotenv(_THIS_DIR / ".env")

# ---------------------------------------------------------------------------
# Root directory
# ---------------------------------------------------------------------------
ROOT_DIR = Path(os.getenv("ROOT_DIR", str(_THIS_DIR)))

# ---------------------------------------------------------------------------
# Folder structure — all paths derived from ROOT_DIR
# ---------------------------------------------------------------------------
IMAGES_DIR   = ROOT_DIR / "images"
VIDEOS_DIR   = ROOT_DIR / "videos"
AUDIO_DIR    = ROOT_DIR / "audio"
FINALS_DIR   = ROOT_DIR / "finals"
METADATA_DIR = ROOT_DIR / "metadata"
UPLOADED_DIR = ROOT_DIR / "uploaded"
CONCEPTS_DIR = ROOT_DIR / "concepts"

# Ensure all directories exist at import time
for _d in (IMAGES_DIR, VIDEOS_DIR, AUDIO_DIR, FINALS_DIR,
           METADATA_DIR, UPLOADED_DIR, CONCEPTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging — pipeline-wide logger writing to pipeline.log + console
# ---------------------------------------------------------------------------
LOG_FILE = ROOT_DIR / "pipeline.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("calmsekai")

# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------
OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
XAI_API_KEY      = os.getenv("XAI_API_KEY", "")       # Grok / xAI
FAL_KEY          = os.getenv("FAL_KEY", "")            # Fal.ai fallback

# Fal.ai model + anime LoRA configuration
# FAL_ANIME_LORA_URL: URL to a .safetensors LoRA weight file hosted publicly.
# Find anime realism LoRAs on Civitai or Hugging Face, copy the direct download URL.
FAL_ANIME_MODEL   = os.getenv("FAL_ANIME_MODEL", "fal-ai/flux-lora")
FAL_ANIME_LORA_URL = os.getenv("FAL_ANIME_LORA_URL", "")  # required for fal.ai fallback

# Suno API (optional — AI music generation; local audio still works without it)
SUNO_API_KEY  = os.getenv("SUNO_API_KEY", "")
SUNO_BASE_URL = os.getenv("SUNO_BASE_URL", "https://api.sunoapi.org")

YOUTUBE_CLIENT_SECRET_PATH = Path(
    os.getenv("YOUTUBE_CLIENT_SECRET_PATH", str(ROOT_DIR / "client_secret.json"))
)

# ---------------------------------------------------------------------------
# Provider selection — change this value to swap video backend
# Supported: "grok" | "runway" | "kling"
# ---------------------------------------------------------------------------
VIDEO_PROVIDER: str = os.getenv("VIDEO_PROVIDER", "grok")

# Supported: "dalle3" | "falai"
IMAGE_PROVIDER: str = os.getenv("IMAGE_PROVIDER", "dalle3")

# ---------------------------------------------------------------------------
# Generation parameters
# ---------------------------------------------------------------------------
IMAGE_SIZE_SHORTS  = "1024x1792"   # 9:16 portrait — DALL-E 3 closest to 9:16
IMAGE_SIZE_WIDE    = "1792x1024"   # 16:9 landscape

VIDEO_ASPECT_SHORTS = "9:16"
VIDEO_ASPECT_WIDE   = "16:9"
VIDEO_DURATION      = 10           # seconds per clip
VIDEO_RESOLUTION    = "720p"

OUTPUT_FPS          = 24
OUTPUT_FORMAT       = "mp4"        # h264 / aac

# ---------------------------------------------------------------------------
# FFmpeg — path to ffmpeg executable
# Set FFMPEG_PATH in .env if ffmpeg is not on your system PATH
# ---------------------------------------------------------------------------
FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "ffmpeg")

# ---------------------------------------------------------------------------
# Dashboard / API server
# ---------------------------------------------------------------------------
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8000"))

# ---------------------------------------------------------------------------
# Retry policy for all API calls
# ---------------------------------------------------------------------------
API_MAX_RETRIES  = 3
API_RETRY_DELAY  = 5   # seconds between retries
VIDEO_POLL_INTERVAL = 10  # seconds between video status polls

# ---------------------------------------------------------------------------
# Startup validation — warn if critical keys are missing
# ---------------------------------------------------------------------------
_REQUIRED = {
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "XAI_API_KEY": XAI_API_KEY,
    "FAL_KEY": FAL_KEY,
}

_missing = [k for k, v in _REQUIRED.items() if not v]
if _missing:
    logger.warning(
        "The following API keys are not set — related pipeline stages will fail: %s",
        ", ".join(_missing),
    )

# Soft warning for optional key — does not block the pipeline
if not SUNO_API_KEY:
    logger.warning(
        "SUNO_API_KEY is not set — Suno AI music generation unavailable. "
        "Local audio file selection will still work."
    )


def concept_paths(concept_id: str) -> dict[str, Path]:
    """
    Return a dict of all paths associated with a given concept UUID.
    Directories are created on first call.
    """
    return {
        "concept_json":  CONCEPTS_DIR  / f"{concept_id}.json",
        "image":         IMAGES_DIR    / f"{concept_id}.png",
        "video":         VIDEOS_DIR    / f"{concept_id}.mp4",
        "audio":         AUDIO_DIR     / f"{concept_id}.mp3",
        "final":         FINALS_DIR    / f"{concept_id}.mp4",
        "metadata_json": METADATA_DIR  / f"{concept_id}.json",
        "uploaded_dir":  UPLOADED_DIR  / concept_id,
    }
