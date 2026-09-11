"""Small per-image sidecars. Source pixels are never changed."""

import logging
from copy import deepcopy
from dataclasses import replace

from ..project.codec import fingerprint, read_document, write_document
from .image_data import AlignmentData, AstroImage, TransformData

logger = logging.getLogger(__name__)


def history_path(path):
    return path.with_name(path.name + ".astrostacker.json")


def valid_dependencies(context):
    try:
        return all(fingerprint(path) == signature for path, signature in context["dependencies"])
    except OSError:
        return False


def save_history(frame: AstroImage):
    try:
        signature = fingerprint(frame.info.path)
        if getattr(frame, "_source_fingerprint", signature) != signature:
            logger.warning("変更された画像の古い履歴は保存しません: %s", frame.info.path)
            return
        data = {
            "fingerprint": signature,
            "info": frame.info,
            "alignment": getattr(frame, "_alignment_context", None),
        }
        cached = getattr(frame, "_plate_solve_cache", None)
        if cached:
            data["plate_solve"] = {"settings": cached[0][1], "result": cached[1]}
        write_document(history_path(frame.info.path), "astro-stacker-image", data)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("画像履歴を保存できません: %s (%s)", frame.info.path, exc)


def load_history(path):
    try:
        data = read_document(history_path(path), "astro-stacker-image")
        if data["fingerprint"] != fingerprint(path):
            return None
        frame = AstroImage(
            replace(data["info"], path=path, enabled=True, capture_time_override_utc=None)
        )
        frame._source_fingerprint = data["fingerprint"]
        context = data.get("alignment")
        if context and valid_dependencies(context):
            frame._alignment_context = context
        else:
            frame.info.transform = TransformData()
            frame.info.alignment_data = AlignmentData()
            frame.info.alignment_session_id = None
        restore_plate_cache(frame, data.get("plate_solve"))
        return frame
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        # Corrupt optional history must not block the source image.
        logger.warning("画像履歴を無視します: %s (%s)", path, exc)
        return None


def restore_plate_cache(frame, saved):
    if saved:
        from .image_manager import ImageManager

        frame._plate_solve_cache = (
            (ImageManager.cache_key(frame), saved["settings"]),
            saved["result"],
        )
        frame.info.wcs = saved["result"].wcs.deepcopy()


def save_alignment_history(project):
    try:
        dependencies = []
        if project.reference_image:
            path = project.reference_image.info.path
            dependencies.append((path, fingerprint(path)))
        for name in ("darks", "flats", "flat_darks", "biases"):
            for frame in getattr(project.calibration_frames, name):
                if frame.info.enabled:
                    dependencies.append((frame.info.path, fingerprint(frame.info.path)))
        session = project.alignment_sessions.get(project.current_alignment_session_id)
        context = {
            "session": session,
            "dependencies": dependencies,
            "settings": deepcopy(project.settings.alignment),
            "calibration": deepcopy(project.settings.calibration),
        }
        for frame in project.light_frames:
            if frame.info.alignment_session_id == project.current_alignment_session_id:
                frame._alignment_context = context
                save_history(frame)
    except OSError as exc:
        logger.warning("位置合わせ履歴を保存できません: %s", exc)


def adopt_alignment_history(project):
    """Reuse only a coherent group with its original reference and calibration."""
    contexts = [getattr(f, "_alignment_context", None) for f in project.light_frames]
    contexts = [c for c in contexts if c and c["session"]]
    if not contexts:
        return
    for context in contexts:
        session = context["session"]
        project.alignment_sessions[session.session_id] = session
    groups = project.get_alignment_sessions()
    if len(groups) != 1 or any(
        not f.info.is_aligned for f in project.light_frames if f.info.enabled
    ):
        return
    context = contexts[0]
    reference = next(
        (f for f in project.light_frames if f.info.path == context["session"].reference_path), None
    )
    if reference is None or not valid_dependencies(context):
        return
    # A calibrated transform must not silently apply to a different calibration.
    has_calibration = any(
        getattr(project.calibration_frames, n) for n in ("darks", "flats", "flat_darks", "biases")
    )
    if has_calibration or len(context["dependencies"]) > 1:
        return
    project.settings.alignment = context["settings"]
    project.settings.calibration = context["calibration"]
    project.current_alignment_session_id = context["session"].session_id
    project.set_reference_image(reference)
    project.alignment_signature = project.make_alignment_signature()
