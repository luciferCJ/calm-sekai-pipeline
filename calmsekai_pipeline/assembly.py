"""
CalmSekai Pipeline — assembly.py
Step 5: FFmpeg video + audio assembly.

Takes the raw Grok-generated video and a user-selected audio track,
applies fade in/out, optional breathing zoom, enforces 24fps H.264,
and outputs to finals/{concept_id}.mp4.

Public entry point:
    assemble(concept: dict, audio_path: Path, breathing_zoom: bool = True) -> Path
"""

import subprocess
import tempfile
from pathlib import Path

import config
from concept import update_concept_status

logger = config.logger.getChild("assembly")

# ---------------------------------------------------------------------------
# Output specs
# ---------------------------------------------------------------------------
TARGET_W      = 1080
TARGET_H      = 1920
ZOOM_SCALE    = 1.03          # 3% scale-up for breathing zoom composition
VIDEO_FADE_S  = 0.5           # seconds for video fade in/out
AUDIO_FADE_S  = 1.0           # seconds for audio fade in/out


# ---------------------------------------------------------------------------
# ffprobe path helper
# ---------------------------------------------------------------------------

def _ffprobe_path() -> str:
    """
    Derive the ffprobe executable path from config.FFMPEG_PATH.
    Works whether FFMPEG_PATH is "ffmpeg" (on PATH) or a full exe path.
    """
    ffmpeg = config.FFMPEG_PATH
    if ffmpeg.lower().endswith("ffmpeg.exe"):
        return ffmpeg[:-len("ffmpeg.exe")] + "ffprobe.exe"
    # Assume ffmpeg is on PATH — ffprobe should be too
    return "ffprobe"


def _get_video_duration(video_path: Path) -> float:
    """
    Use ffprobe to read the actual duration of a video file in seconds.

    Raises:
        RuntimeError: If ffprobe fails or returns a non-numeric value.
    """
    cmd = [
        _ffprobe_path(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float(result.stdout.strip())
        logger.info("Detected video duration: %.2fs — %s", duration, video_path.name)
        return duration
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise RuntimeError(
            f"ffprobe could not read duration of {video_path}: {exc}\n"
            f"stderr: {getattr(exc, 'stderr', '')}"
        ) from exc


# ---------------------------------------------------------------------------
# FFmpeg filter chain builder
# ---------------------------------------------------------------------------

def _build_filter_complex(
    clip_duration: float,
    fade_duration: float,
    audio_fade_duration: float,
    breathing_zoom: bool,
) -> str:
    """
    Build the FFmpeg -filter_complex string for the assembly.

    Video chain:
      1. fps=24               — enforce frame rate
      2. scale to target      — scale to fill 1080×1920 (or 3% larger for zoom)
      3. crop=1080:1920       — center-crop to exact Shorts dimensions
      4. fade in              — VIDEO_FADE_S fade from black
      5. fade out             — VIDEO_FADE_S fade to black

    Breathing zoom:
      When enabled, the video is scaled to TARGET_W * ZOOM_SCALE by
      TARGET_H * ZOOM_SCALE before cropping to 1080×1920. This tightens
      the composition by 3%, creating a slightly more intimate frame that
      complements the organic motion already present in the Grok video.

    Audio chain:
      1. atrim                — trim to clip_duration (no over-run)
      2. asetpts=PTS-STARTPTS — reset timestamps after trim
      3. afade in             — AUDIO_FADE_S fade in
      4. afade out            — AUDIO_FADE_S fade out

    Returns:
        The complete filter_complex string ready for -filter_complex flag.
    """
    # Video fade out starts this many seconds before the end
    v_fade_out_start = max(0.0, clip_duration - fade_duration)

    # Audio fade out starts 1 audio_fade_duration before end
    a_fade_out_start = max(0.0, clip_duration - audio_fade_duration)

    # Scale dimensions — zoom adds 3% to each axis
    if breathing_zoom:
        scale_w = int(TARGET_W * ZOOM_SCALE) + 1   # slight over to avoid rounding gap
        scale_h = int(TARGET_H * ZOOM_SCALE) + 1
    else:
        scale_w = TARGET_W
        scale_h = TARGET_H

    video_chain = (
        f"[0:v]"
        f"fps=fps={config.OUTPUT_FPS},"
        f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
        f"crop={TARGET_W}:{TARGET_H},"
        f"fade=t=in:st=0:d={fade_duration},"
        f"fade=t=out:st={v_fade_out_start:.3f}:d={fade_duration}"
        f"[vout]"
    )

    audio_chain = (
        f"[1:a]"
        f"atrim=0:{clip_duration:.3f},"
        f"asetpts=PTS-STARTPTS,"
        f"afade=t=in:st=0:d={audio_fade_duration},"
        f"afade=t=out:st={a_fade_out_start:.3f}:d={audio_fade_duration}"
        f"[aout]"
    )

    return f"{video_chain};{audio_chain}"


# ---------------------------------------------------------------------------
# FFmpeg command builder
# ---------------------------------------------------------------------------

def _build_ffmpeg_command(
    video_in: Path,
    audio_in: Path,
    output: Path,
    clip_duration: float,
    breathing_zoom: bool,
) -> list[str]:
    """
    Build the complete FFmpeg command as a list of strings.

    Using a list (not a shell string) avoids all shell-injection risk and
    handles paths with spaces correctly on Windows.

    Output codec settings:
      Video: H.264 (libx264), CRF 18 (visually lossless), slow preset,
             yuv420p pixel format for max compatibility
      Audio: AAC, 192 kbps
      Container: MP4 with +faststart (streaming-ready)
    """
    filter_complex = _build_filter_complex(
        clip_duration=clip_duration,
        fade_duration=VIDEO_FADE_S,
        audio_fade_duration=AUDIO_FADE_S,
        breathing_zoom=breathing_zoom,
    )

    return [
        config.FFMPEG_PATH,
        "-y",                           # overwrite output without asking

        # Inputs
        "-i", str(video_in),            # [0] raw video from Grok
        "-i", str(audio_in),            # [1] user-selected audio

        # Filters
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",

        # Video codec
        "-c:v", "libx264",
        "-preset", "slow",              # better compression, worth the extra time
        "-crf", "18",                   # high quality (0=lossless, 51=worst)
        "-pix_fmt", "yuv420p",          # required for iOS / YouTube compatibility

        # Audio codec
        "-c:a", "aac",
        "-b:a", "192k",

        # Container
        "-movflags", "+faststart",      # move moov atom to front for streaming

        # Duration safety cap — never exceed the source video length
        "-t", f"{clip_duration:.3f}",

        str(output),
    ]


# ---------------------------------------------------------------------------
# FFmpeg runner
# ---------------------------------------------------------------------------

def _run_ffmpeg(cmd: list[str]) -> None:
    """
    Execute the FFmpeg command, stream stderr to the pipeline log.

    Raises:
        RuntimeError: If FFmpeg exits with a non-zero return code.
    """
    logger.info("Running FFmpeg:\n  %s", " ".join(f'"{a}"' if " " in a else a for a in cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.stderr:
        # FFmpeg writes progress to stderr — log at DEBUG level to avoid noise
        for line in result.stderr.splitlines():
            logger.debug("[ffmpeg] %s", line)

    if result.returncode != 0:
        # Log the tail of stderr at ERROR level so the problem is visible
        tail = "\n".join(result.stderr.splitlines()[-20:])
        raise RuntimeError(
            f"FFmpeg exited with code {result.returncode}.\n"
            f"Last output:\n{tail}"
        )

    logger.info("FFmpeg completed successfully")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def assemble(
    concept: dict,
    audio_path: Path,
    breathing_zoom: bool = True,
) -> Path:
    """
    Assemble the final video by merging the Grok video with the selected
    audio track and applying fade effects.

    This is called by the dashboard when the user selects an audio file
    and clicks the assemble button.

    Args:
        concept:        Concept dict loaded from concepts/{uuid}.json.
                        Must contain "id". Source video must exist at
                        videos/{id}.mp4 (video_gen step must be complete).
        audio_path:     Absolute path to the user-selected audio file.
                        Supported formats: any FFmpeg-readable audio
                        (mp3, wav, flac, m4a, aac, ogg, etc.)
        breathing_zoom: When True, scales the video to 103% then center-
                        crops to 1080×1920, tightening the composition.
                        Default True. Set False if the Grok video already
                        feels well-framed.

    Returns:
        Path to the assembled final video in finals/.

    Raises:
        FileNotFoundError: If source video or audio file does not exist.
        RuntimeError: If FFmpeg fails.
    """
    concept_id = concept["id"]
    paths      = config.concept_paths(concept_id)
    video_in   = paths["video"]
    output     = paths["final"]

    # --- Input validation ---
    if not video_in.exists():
        raise FileNotFoundError(
            f"Source video not found for concept {concept_id}. "
            "Run video generation first."
        )
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    logger.info(
        "Assembling concept %s — video=%s  audio=%s  zoom=%s",
        concept_id, video_in.name, audio_path.name, breathing_zoom,
    )

    # --- Detect actual clip duration ---
    clip_duration = _get_video_duration(video_in)

    # --- Build and run FFmpeg ---
    cmd = _build_ffmpeg_command(
        video_in=video_in,
        audio_in=audio_path,
        output=output,
        clip_duration=clip_duration,
        breathing_zoom=breathing_zoom,
    )

    _run_ffmpeg(cmd)

    # --- Confirm output exists ---
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(
            f"FFmpeg completed but output file is missing or empty: {output}"
        )

    size_mb = output.stat().st_size / (1024 * 1024)
    logger.info(
        "Assembly complete — %s (%.1f MB)", output.name, size_mb
    )

    update_concept_status(concept_id, "assembly_done")
    return output


# ---------------------------------------------------------------------------
# Multi-scene project assembly
# ---------------------------------------------------------------------------

def assemble_project(
    project: dict,
    audio_path: Path,
    breathing_zoom: bool = True,
) -> Path:
    """
    Stitch all scene videos for a project into one final video with audio.

    Each scene must have a video at videos/{scene_id}.mp4. Scenes are
    ordered by their 'order' field. The stitched video is saved to
    finals/{project_id}.mp4.

    Args:
        project:        Project dict (from load_project / get_project_with_scenes).
                        Must include 'id', 'aspect_ratio', and 'scenes' list.
        audio_path:     Absolute path to the audio file.
        breathing_zoom: When True, applies 3% breathing zoom to each clip.

    Returns:
        Path to the final assembled video.

    Raises:
        FileNotFoundError: If any scene video or the audio file is missing.
        RuntimeError:      If FFmpeg fails.
    """
    from project import update_project_status

    project_id   = project["id"]
    aspect_ratio = project.get("aspect_ratio", "9:16")
    ar_cfg       = config.ASPECT_RATIO_CONFIG.get(aspect_ratio, config.ASPECT_RATIO_CONFIG["9:16"])
    target_w     = ar_cfg["width"]
    target_h     = ar_cfg["height"]

    scenes = sorted(
        project.get("scenes", []),
        key=lambda s: s.get("order", 999),
    )
    if not scenes:
        raise ValueError(f"Project {project_id} has no scenes.")

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # --- Validate all scene videos exist ---
    scene_videos: list[Path] = []
    for scene in scenes:
        vpath = config.VIDEOS_DIR / f"{scene['id']}.mp4"
        if not vpath.exists():
            raise FileNotFoundError(
                f"Video not found for scene {scene['id']} (order={scene.get('order')}). "
                "Run video generation for all scenes first."
            )
        scene_videos.append(vpath)

    logger.info(
        "Assembling project %s — %d scenes  ar=%s  audio=%s",
        project_id, len(scenes), aspect_ratio, audio_path.name,
    )

    # Use a temp dir for intermediate files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        norm_clips: list[Path] = []

        # --- Pass 1: normalize each clip to target resolution + fps ---
        for i, (scene, vpath) in enumerate(zip(scenes, scene_videos)):
            norm_out = tmp / f"norm_{i:03d}.mp4"

            if breathing_zoom:
                scale_w = int(target_w * ZOOM_SCALE) + 1
                scale_h = int(target_h * ZOOM_SCALE) + 1
            else:
                scale_w = target_w
                scale_h = target_h

            norm_cmd = [
                config.FFMPEG_PATH, "-y",
                "-i", str(vpath),
                "-vf", (
                    f"fps=fps={config.OUTPUT_FPS},"
                    f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
                    f"crop={target_w}:{target_h}"
                ),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",   # strip audio from individual clips
                str(norm_out),
            ]
            _run_ffmpeg(norm_cmd)
            norm_clips.append(norm_out)

        # --- Pass 2: concat normalized clips ---
        concat_list = tmp / "concat_list.txt"
        concat_list.write_text(
            "\n".join(f"file '{p}'" for p in norm_clips),
            encoding="utf-8",
        )

        concat_out = tmp / "concat.mp4"
        concat_cmd = [
            config.FFMPEG_PATH, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(concat_out),
        ]
        _run_ffmpeg(concat_cmd)

        # --- Pass 3: add audio, fades, final encode ---
        total_duration = _get_video_duration(concat_out)
        a_fade_out     = max(0.0, total_duration - AUDIO_FADE_S)
        v_fade_out     = max(0.0, total_duration - VIDEO_FADE_S)

        filter_complex = (
            f"[0:v]"
            f"fade=t=in:st=0:d={VIDEO_FADE_S},"
            f"fade=t=out:st={v_fade_out:.3f}:d={VIDEO_FADE_S}"
            f"[vout];"
            f"[1:a]"
            f"atrim=0:{total_duration:.3f},"
            f"asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={AUDIO_FADE_S},"
            f"afade=t=out:st={a_fade_out:.3f}:d={AUDIO_FADE_S}"
            f"[aout]"
        )

        output = config.FINALS_DIR / f"{project_id}.mp4"
        final_cmd = [
            config.FFMPEG_PATH, "-y",
            "-i", str(concat_out),
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", "libx264",
            "-preset", "slow",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-t", f"{total_duration:.3f}",
            str(output),
        ]
        _run_ffmpeg(final_cmd)

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(
            f"FFmpeg completed but output file is missing or empty: {output}"
        )

    size_mb = output.stat().st_size / (1024 * 1024)
    logger.info("Project assembly complete — %s (%.1f MB)", output.name, size_mb)

    update_project_status(project_id, "assembly_done")
    return output


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from concept import load_concept

    if len(sys.argv) < 3:
        print("Usage: python assembly.py <concept_id> <path/to/audio.mp3>")
        sys.exit(1)

    cid   = sys.argv[1]
    audio = Path(sys.argv[2])
    c     = load_concept(cid)

    print(f"Assembling: {c['theme']} / {c['emotion']}")
    p = assemble(c, audio)
    print(f"Final video: {p}")
