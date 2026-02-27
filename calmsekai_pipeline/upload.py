"""
CalmSekai Pipeline — upload.py
Step 8: YouTube upload via YouTube Data API v3.

Authentication uses OAuth2 with a locally cached token so the browser
authorization only happens once. After that, uploads run headlessly.

Prerequisites:
  1. Create a project at https://console.cloud.google.com
  2. Enable the YouTube Data API v3
  3. Create OAuth2 credentials (Desktop App) → download client_secret.json
  4. Set YOUTUBE_CLIENT_SECRET_PATH in .env to point to that file
  5. Run once interactively: python upload.py <concept_id>
     → browser opens for Google sign-in → token saved → done

Public entry point:
    upload_video(concept: dict) -> str   (returns YouTube video URL)
"""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import googleapiclient.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config
from concept import update_concept_status
from seo import load_metadata

logger = config.logger.getChild("upload")

# ---------------------------------------------------------------------------
# OAuth2 configuration
# ---------------------------------------------------------------------------

_SCOPES      = ["https://www.googleapis.com/auth/youtube.upload"]
_TOKEN_PATH  = config.ROOT_DIR / "youtube_token.json"
_API_SERVICE = "youtube"
_API_VERSION = "v3"

# YouTube category IDs
CATEGORY_PEOPLE_AND_BLOGS = "22"
CATEGORY_ENTERTAINMENT    = "24"

# Upload chunk size — 8 MB gives a good balance of speed vs. memory
_CHUNK_SIZE = 8 * 1024 * 1024


# ---------------------------------------------------------------------------
# OAuth2 authentication
# ---------------------------------------------------------------------------

def _get_youtube_service():
    """
    Return an authenticated YouTube API service object.

    On first call: opens a browser window for Google sign-in, then saves
    the token to youtube_token.json for all future calls.

    On subsequent calls: loads the cached token and silently refreshes it
    if expired. No browser interaction required.

    Raises:
        FileNotFoundError: If client_secret.json does not exist.
        RuntimeError: If authentication fails.
    """
    secret_path = config.YOUTUBE_CLIENT_SECRET_PATH
    if not secret_path.exists():
        raise FileNotFoundError(
            f"YouTube client_secret.json not found at: {secret_path}\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )

    creds = None

    # Load cached token if it exists
    if _TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
            logger.info("Loaded cached OAuth2 token from %s", _TOKEN_PATH.name)
        except Exception as exc:
            logger.warning("Cached token unreadable (%s) — will re-authenticate", exc)
            creds = None

    # Refresh expired token silently
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("OAuth2 token refreshed")
            _save_token(creds)
        except Exception as exc:
            logger.warning("Token refresh failed (%s) — will re-authenticate", exc)
            creds = None

    # Full OAuth2 flow (opens browser on first run)
    if not creds or not creds.valid:
        logger.info("Starting OAuth2 browser flow…")
        flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), _SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        _save_token(creds)
        logger.info("OAuth2 authorization complete")

    return build(_API_SERVICE, _API_VERSION, credentials=creds)


def _save_token(creds: Credentials) -> None:
    """Persist the OAuth2 token to disk."""
    _TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    logger.debug("OAuth2 token saved → %s", _TOKEN_PATH.name)


# ---------------------------------------------------------------------------
# Request body builder
# ---------------------------------------------------------------------------

def _build_video_body(concept: dict, meta: dict) -> dict:
    """
    Build the YouTube API videos.insert() request body.

    Description format:
        <meta description>

        <hashtags joined by spaces>

    Hashtags appended at the end of the description is how YouTube
    renders them as clickable tags on Shorts.

    Args:
        concept: Concept dict (used for fallback title if meta is incomplete).
        meta:    SEO metadata dict from metadata/{uuid}.json.

    Returns:
        YouTube API snippet + status body dict.
    """
    title       = meta.get("title", f"{concept['theme']} — CalmSekai")[:100]
    description = meta.get("description", "")
    hashtags    = meta.get("hashtags", [])
    tags        = meta.get("tags", [])

    # Append hashtags to description so YouTube renders them as links
    if hashtags:
        description = f"{description}\n\n{' '.join(hashtags)}"

    return {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  CATEGORY_PEOPLE_AND_BLOGS,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":           "public",
            "selfDeclaredMadeForKids": False,
            "madeForKids":             False,
        },
    }


# ---------------------------------------------------------------------------
# Resumable upload with progress logging
# ---------------------------------------------------------------------------

def _upload_with_progress(youtube, body: dict, final_path: Path) -> str:
    """
    Upload a video file using YouTube's resumable upload protocol.

    Logs progress after each chunk. Retries up to 3 times on transient
    HTTP errors (5xx, 403 rate limit).

    Args:
        youtube:    Authenticated YouTube service object.
        body:       videos.insert() request body (snippet + status).
        final_path: Path to the .mp4 file to upload.

    Returns:
        The YouTube video ID (e.g. "dQw4w9WgXcQ").

    Raises:
        RuntimeError: If upload fails after retries.
        googleapiclient.errors.HttpError: On unrecoverable API errors.
    """
    media = MediaFileUpload(
        str(final_path),
        mimetype="video/mp4",
        chunksize=_CHUNK_SIZE,
        resumable=True,
    )

    insert_request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=True,
        stabilize=False,
    )

    logger.info("Starting YouTube upload — file=%s (%.1f MB)",
                final_path.name, final_path.stat().st_size / (1024 * 1024))

    response   = None
    error_count = 0
    max_errors  = 5

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info("Upload progress: %d%%", pct)
        except googleapiclient.errors.HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and error_count < max_errors:
                error_count += 1
                logger.warning("Transient upload error (%d) — retrying… [%d/%d]",
                               exc.resp.status, error_count, max_errors)
                import time; time.sleep(2 ** error_count)
            else:
                raise

    video_id = response["id"]
    logger.info("Upload complete — video_id=%s", video_id)
    return video_id


# ---------------------------------------------------------------------------
# Post-upload archiving
# ---------------------------------------------------------------------------

def _save_upload_record(concept_id: str, video_id: str) -> None:
    """
    Write an upload record to uploaded/{concept_id}/upload_record.json
    and copy the final video + metadata JSON there for archiving.

    Original files in finals/ and metadata/ are left in place so the
    dashboard preview continues to work.
    """
    uploaded_dir = config.UPLOADED_DIR / concept_id
    uploaded_dir.mkdir(parents=True, exist_ok=True)

    video_url = f"https://www.youtube.com/shorts/{video_id}"

    record = {
        "concept_id":  concept_id,
        "video_id":    video_id,
        "video_url":   video_url,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    record_path = uploaded_dir / "upload_record.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    # Copy final video + metadata for archival
    paths = config.concept_paths(concept_id)
    for src_key, dest_name in (
        ("final",         f"{concept_id}.mp4"),
        ("metadata_json", f"{concept_id}_metadata.json"),
        ("concept_json",  f"{concept_id}_concept.json"),
    ):
        src = paths[src_key]
        if src.exists():
            shutil.copy2(src, uploaded_dir / dest_name)

    logger.info("Upload record saved → %s", record_path)
    logger.info("YouTube Shorts URL: %s", video_url)


def _append_video_url_to_metadata(concept_id: str, video_id: str) -> None:
    """
    Add video_id and video_url fields to the existing metadata JSON
    so the dashboard can display a link to the published Short.
    """
    from seo import update_metadata_field
    video_url = f"https://www.youtube.com/shorts/{video_id}"
    try:
        update_metadata_field(concept_id, "video_id",  video_id)
        update_metadata_field(concept_id, "video_url", video_url)
    except FileNotFoundError:
        pass  # metadata might not exist if SEO was skipped


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def upload_video(concept: dict) -> str:
    """
    Upload the assembled final video to YouTube as a Short.

    Requires:
        - finals/{concept_id}.mp4 must exist (assembly_done)
        - metadata/{concept_id}.json should exist (seo_done)
        - YOUTUBE_CLIENT_SECRET_PATH must point to a valid client_secret.json
        - Google OAuth2 authorization (browser prompt on first run only)

    Args:
        concept: Concept dict loaded from concepts/{uuid}.json.

    Returns:
        YouTube Shorts URL (https://www.youtube.com/shorts/{video_id}).

    Raises:
        FileNotFoundError: If final video or client_secret.json not found.
        RuntimeError: On upload failure.
    """
    concept_id = concept["id"]
    paths      = config.concept_paths(concept_id)
    final_path = paths["final"]

    # --- Validate final video exists ---
    if not final_path.exists():
        raise FileNotFoundError(
            f"Final video not found for concept {concept_id}. "
            "Run assembly first."
        )

    # --- Load SEO metadata (warn but don't fail if missing) ---
    try:
        meta = load_metadata(concept_id)
    except FileNotFoundError:
        logger.warning(
            "No SEO metadata found for concept %s — "
            "using concept fields as fallback title.", concept_id
        )
        meta = {
            "title":       f"{concept['theme']} — CalmSekai",
            "description": f"{concept['emotion'].capitalize()}. A CalmSekai short.",
            "hashtags":    ["#calmsekai", "#youtubeshorts", "#animerealism"],
            "tags":        ["calmsekai", "youtube shorts", "anime realism"],
        }

    logger.info(
        "Uploading concept %s — title=%r", concept_id, meta.get("title", "")
    )

    # --- Build request body ---
    body = _build_video_body(concept, meta)

    # --- Authenticate ---
    youtube = _get_youtube_service()

    # --- Upload ---
    video_id = _upload_with_progress(youtube, body, final_path)

    # --- Post-upload bookkeeping ---
    _save_upload_record(concept_id, video_id)
    _append_video_url_to_metadata(concept_id, video_id)
    update_concept_status(concept_id, "uploaded")

    video_url = f"https://www.youtube.com/shorts/{video_id}"
    logger.info("Concept %s successfully uploaded → %s", concept_id, video_url)
    return video_url


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python upload.py <concept_id>")
        print()
        print("On first run, a browser window will open for Google sign-in.")
        print("After that, uploads run headlessly using the cached token.")
        sys.exit(1)

    from concept import load_concept
    cid = sys.argv[1]
    c   = load_concept(cid)

    print(f"Uploading: {c['theme']} / {c['emotion']}")
    url = upload_video(c)
    print(f"\nPublished: {url}")
