"""
CalmSekai Pipeline — project.py
Multi-scene project management.

A "project" is a collection of ordered scenes that together tell a story.
Each scene is stored as a concept JSON in concepts/ with extra fields:
  is_scene: true, project_id, order, duration, aspect_ratio.

This lets image_gen.generate_image(scene) and video_gen.generate_video(scene)
work completely unchanged — they only need id, image_prompt, and
video_motion_instruction.

Public entry points:
    generate_project(title, theme, emotion, aspect_ratio, target_duration) -> dict
    save_project(project) -> Path
    load_project(project_id) -> dict
    list_projects() -> list[dict]
    update_project_status(project_id, status) -> None
    update_project_fields(project_id, fields) -> dict
    add_scene(project_id, scene_data) -> dict
    update_scene_fields(project_id, scene_id, fields) -> dict
    delete_scene(project_id, scene_id) -> None
    load_scene(scene_id) -> dict
"""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from openai import OpenAI

import config

logger = config.logger.getChild("project")

# ---------------------------------------------------------------------------
# GPT-4o project generation prompt
# ---------------------------------------------------------------------------

_PROJECT_SYSTEM_PROMPT = """\
You are the creative director for CalmSekai, a YouTube Shorts brand producing
healing, atmospheric anime-realism videos. Your job is to generate a multi-scene
video project as a JSON object — nothing else, no markdown, no explanation.

The aesthetic is: high-detail anime realism, soft cinematic lighting, natural
physics, stillness with subtle organic motion.

The JSON you return MUST follow this exact schema:
{
  "title": "<evocative short title for the whole story>",
  "audio_mood": "<description of music mood — BPM, instruments, no percussion>",
  "scenes": [
    {
      "order": 1,
      "description": "<brief creative description of this scene's story beat>",
      "image_prompt": "<detailed image generation prompt — anime realism style, cinematic, soft lighting, portrait orientation, ultra-detailed>",
      "video_motion_instruction": "<very slow organic camera or scene movement — no cuts, no shake>",
      "duration": <integer seconds for this scene>
    }
  ]
}

Rules for scenes:
- Generate 3 to 5 scenes that together tell a coherent atmospheric story
- The total duration of all scenes should be close to the requested target_duration
- Scene 1: establish the world and introduce the atmosphere
- Middle scenes: deepen the mood or reveal something quietly magical
- Final scene: soft resolution, fade, sense of peace

Rules for image_prompt:
- Always include: "anime realism style, cinematic composition, soft natural lighting, ultra-detailed, no motion blur, no text, no logos"
- Include the correct orientation hint based on aspect_ratio parameter
- Describe one atmospheric scene in high detail — one location, one moment

Rules for video_motion_instruction:
- Very slow, organic movement only
- Examples: slow parallax drift, leaves swaying gently, water surface rippling, soft light shaft moving
- Never: cuts, zooms, shake, dramatic movement

Rules for audio_mood:
- Describe the single music mood for the whole project
- Format: "55–65 BPM, soft piano, ambient pad, no percussion" style

Output ONLY valid JSON. No extra text before or after.
"""


def _build_project_user_prompt(
    title: str,
    theme: str,
    emotion: str,
    aspect_ratio: str,
    target_duration: int,
) -> str:
    orientation = {
        "9:16": "9:16 portrait orientation",
        "16:9": "16:9 landscape orientation",
        "1:1":  "1:1 square orientation",
    }.get(aspect_ratio, "9:16 portrait orientation")

    return (
        f'Generate a CalmSekai multi-scene video project with these parameters:\n'
        f'Title hint: "{title}"\n'
        f'Theme: "{theme}"\n'
        f'Emotion: "{emotion}"\n'
        f'Aspect ratio: {aspect_ratio} ({orientation})\n'
        f'Target total duration: {target_duration} seconds\n\n'
        f'Remember to include "{orientation}" in every image_prompt.\n'
        f'Make the scenes flow naturally as a story — beginning, middle, end.'
    )


# ---------------------------------------------------------------------------
# Core generation function
# ---------------------------------------------------------------------------

def generate_project(
    title: str,
    theme: str,
    emotion: str,
    aspect_ratio: str = "9:16",
    target_duration: int = 30,
) -> dict:
    """
    Call GPT-4o to generate a multi-scene project with story arc.

    Returns:
        A project dict with id, scene_ids list, and a scenes list with
        scene dicts ready to be saved individually.

    Raises:
        RuntimeError: If API calls fail after retries.
        ValueError: If GPT-4o returns malformed JSON.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    user_prompt = _build_project_user_prompt(
        title, theme, emotion, aspect_ratio, target_duration
    )

    logger.info(
        "Generating project — title=%s  theme=%s  emotion=%s  ar=%s  dur=%ds",
        title, theme, emotion, aspect_ratio, target_duration,
    )

    last_error: Exception = RuntimeError("No attempts made")

    for attempt in range(1, config.API_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _PROJECT_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.9,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            gpt_data = json.loads(raw)
            _validate_project_response(gpt_data)

            project_id = str(uuid.uuid4())
            now        = datetime.now(timezone.utc).isoformat()

            # Build scene dicts (to be saved separately in concepts/)
            scenes     = []
            scene_ids  = []
            for s in gpt_data["scenes"]:
                scene_id = str(uuid.uuid4())
                scene = {
                    "id":                       scene_id,
                    "is_scene":                 True,
                    "project_id":               project_id,
                    "order":                    s["order"],
                    "description":              s.get("description", ""),
                    "image_prompt":             s.get("image_prompt", ""),
                    "video_motion_instruction": s.get("video_motion_instruction", ""),
                    "duration":                 int(s.get("duration", 10)),
                    "aspect_ratio":             aspect_ratio,
                    "status":                   "pending",
                    "created_at":               now,
                }
                scenes.append(scene)
                scene_ids.append(scene_id)

            project = {
                "id":              project_id,
                "title":           gpt_data.get("title", title),
                "theme":           theme,
                "emotion":         emotion,
                "aspect_ratio":    aspect_ratio,
                "target_duration": target_duration,
                "audio_mood":      gpt_data.get("audio_mood", ""),
                "status":          "draft",
                "scene_ids":       scene_ids,
                "created_at":      now,
            }

            # Attach scenes list (caller saves them; not stored in project JSON)
            project["_scenes"] = scenes

            logger.info(
                "Project generated — id=%s  title=%s  scenes=%d",
                project_id, project["title"], len(scenes),
            )
            return project

        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Attempt %d/%d — invalid project JSON: %s",
                           attempt, config.API_MAX_RETRIES, exc)
            last_error = exc
        except Exception as exc:
            logger.warning("Attempt %d/%d — API error: %s",
                           attempt, config.API_MAX_RETRIES, exc)
            last_error = exc

        if attempt < config.API_MAX_RETRIES:
            time.sleep(config.API_RETRY_DELAY)

    raise RuntimeError(
        f"Project generation failed after {config.API_MAX_RETRIES} attempts: {last_error}"
    )


def _validate_project_response(data: dict) -> None:
    """Raise ValueError if GPT-4o response is missing required fields."""
    if "scenes" not in data or not isinstance(data["scenes"], list):
        raise ValueError("Project JSON missing 'scenes' list")
    if not data["scenes"]:
        raise ValueError("Project JSON has empty scenes list")
    for i, s in enumerate(data["scenes"]):
        for field in ("order", "image_prompt", "video_motion_instruction"):
            if field not in s:
                raise ValueError(f"Scene {i} missing required field '{field}'")


# ---------------------------------------------------------------------------
# Project persistence
# ---------------------------------------------------------------------------

def save_project(project: dict) -> Path:
    """
    Write project dict to projects/{project_id}.json.
    The _scenes key (if present) is stripped before saving.
    """
    to_save = {k: v for k, v in project.items() if k != "_scenes"}
    path = config.PROJECTS_DIR / f"{project['id']}.json"
    path.write_text(
        json.dumps(to_save, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Project saved — %s", path)
    return path


def load_project(project_id: str) -> dict:
    """
    Load a project from disk by its UUID.

    Raises:
        FileNotFoundError: If no project with that ID exists.
    """
    path = config.PROJECTS_DIR / f"{project_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No project found for id={project_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_projects() -> list[dict]:
    """Return all saved projects sorted by created_at descending."""
    projects = []
    for path in config.PROJECTS_DIR.glob("*.json"):
        try:
            projects.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read project file %s: %s", path.name, exc)
    projects.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return projects


def update_project_status(project_id: str, status: str) -> None:
    """Update the status field of an existing project on disk."""
    project = load_project(project_id)
    project["status"] = status
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_project(project)
    logger.info("Project %s status → %s", project_id, status)


_PROJECT_EDITABLE_FIELDS = {"title", "audio_mood", "theme", "emotion"}


def update_project_fields(project_id: str, fields: dict) -> dict:
    """
    Update editable content fields of a saved project.
    Status and pipeline metadata are never overwritten by this function.
    """
    unknown = set(fields) - _PROJECT_EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown project fields: {unknown}")
    project = load_project(project_id)
    for key, value in fields.items():
        project[key] = value
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_project(project)
    logger.info("Project %s fields updated: %s", project_id, list(fields.keys()))
    return project


# ---------------------------------------------------------------------------
# Scene persistence (scenes live in concepts/ folder)
# ---------------------------------------------------------------------------

def save_scene(scene: dict) -> Path:
    """Write scene dict to concepts/{scene_id}.json."""
    path = config.CONCEPTS_DIR / f"{scene['id']}.json"
    path.write_text(
        json.dumps(scene, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Scene saved — %s", path)
    return path


def load_scene(scene_id: str) -> dict:
    """
    Load a scene from concepts/{scene_id}.json.

    Raises:
        FileNotFoundError: If no scene with that ID exists.
    """
    path = config.CONCEPTS_DIR / f"{scene_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No scene found for id={scene_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def add_scene(project_id: str, scene_data: Optional[dict] = None) -> dict:
    """
    Add a new blank scene to a project (or add a pre-populated scene_data dict).

    Returns:
        The saved scene dict.
    """
    project = load_project(project_id)
    now     = datetime.now(timezone.utc).isoformat()

    scene_id = str(uuid.uuid4())
    order    = len(project["scene_ids"]) + 1

    scene = {
        "id":                       scene_id,
        "is_scene":                 True,
        "project_id":               project_id,
        "order":                    order,
        "description":              "",
        "image_prompt":             "",
        "video_motion_instruction": "",
        "duration":                 10,
        "aspect_ratio":             project.get("aspect_ratio", "9:16"),
        "status":                   "pending",
        "created_at":               now,
    }

    if scene_data:
        for k, v in scene_data.items():
            if k not in ("id", "is_scene", "project_id", "created_at"):
                scene[k] = v

    save_scene(scene)

    project["scene_ids"].append(scene_id)
    project["updated_at"] = now
    save_project(project)

    logger.info("Scene %s added to project %s (order=%d)", scene_id, project_id, order)
    return scene


_SCENE_EDITABLE_FIELDS = {
    "description", "image_prompt", "video_motion_instruction",
    "duration", "order",
}


def update_scene_fields(project_id: str, scene_id: str, fields: dict) -> dict:
    """
    Update editable fields of a scene.

    Raises:
        FileNotFoundError: If the scene or project doesn't exist.
        ValueError: If an unrecognised field key is passed.
    """
    unknown = set(fields) - _SCENE_EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Unknown scene fields: {unknown}")

    scene = load_scene(scene_id)
    if scene.get("project_id") != project_id:
        raise ValueError(f"Scene {scene_id} does not belong to project {project_id}")

    for key, value in fields.items():
        scene[key] = value
    scene["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_scene(scene)
    logger.info("Scene %s fields updated: %s", scene_id, list(fields.keys()))
    return scene


def update_scene_status(scene_id: str, status: str) -> None:
    """Update the status field of a scene."""
    scene = load_scene(scene_id)
    scene["status"] = status
    scene["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_scene(scene)
    logger.info("Scene %s status → %s", scene_id, status)


def delete_scene(project_id: str, scene_id: str) -> None:
    """
    Remove a scene from the project's scene_ids list and delete its JSON file.
    Re-numbers remaining scenes by their order field.
    """
    project = load_project(project_id)
    if scene_id not in project["scene_ids"]:
        raise ValueError(f"Scene {scene_id} not in project {project_id}")

    project["scene_ids"].remove(scene_id)
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_project(project)

    # Delete the scene JSON
    path = config.CONCEPTS_DIR / f"{scene_id}.json"
    if path.exists():
        path.unlink()

    logger.info("Scene %s deleted from project %s", scene_id, project_id)


def get_project_with_scenes(project_id: str) -> dict:
    """
    Load a project and attach a full 'scenes' list (loaded from disk)
    sorted by order.

    Returns:
        Project dict with an added 'scenes' key.
    """
    project = load_project(project_id)
    scenes  = []
    for sid in project.get("scene_ids", []):
        try:
            scenes.append(load_scene(sid))
        except FileNotFoundError:
            logger.warning("Scene %s referenced in project %s not found", sid, project_id)

    scenes.sort(key=lambda s: s.get("order", 999))
    project["scenes"] = scenes
    return project
