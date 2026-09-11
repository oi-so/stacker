"""Portable project manifests; image pixels remain in their original files."""

from pathlib import Path

from ..io.history import restore_plate_cache, save_history
from ..io.image_data import AlignmentData, AstroImage, TransformData
from .codec import fingerprint, read_document, write_document
from .project import Project, ProjectSettings

CATEGORIES = ("lights", "darks", "flats", "flat_darks", "biases")


def frame_groups(project):
    return {
        "lights": project.light_frames,
        **{name: getattr(project.calibration_frames, name) for name in CATEGORIES[1:]},
    }


def save_project(project: Project, path: Path):
    path = path.resolve()
    sources = {
        frame.info.path.resolve() for frames in frame_groups(project).values() for frame in frames
    }
    if path in sources or (project.output_path and path == project.output_path.resolve()):
        raise ValueError("画像ファイルをプロジェクトで上書きできません。別の名前を選んでください。")
    groups = {}
    for category, frames in frame_groups(project).items():
        groups[category] = []
        for frame in frames:
            try:
                signature = getattr(frame, "_source_fingerprint", None) or fingerprint(
                    frame.info.path
                )
            except OSError:
                signature = None
            cached = getattr(frame, "_plate_solve_cache", None)
            groups[category].append(
                {
                    "info": frame.info,
                    "fingerprint": signature,
                    "alignment": getattr(frame, "_alignment_context", None),
                    "plate_solve": (
                        {"settings": cached[0][1], "result": cached[1]} if cached else None
                    ),
                }
            )
    output_signature = None
    if project.output_path and project.output_path.exists():
        output_signature = fingerprint(project.output_path)
    data = {
        "name": path.stem,
        "groups": groups,
        "settings": project.settings,
        "reference": project.reference_image.info.path if project.reference_image else None,
        "sessions": project.alignment_sessions,
        "session": project.current_alignment_session_id,
        "signature": project.alignment_signature,
        "output": project.output_path,
        "output_fingerprint": output_signature,
        "result_metadata": project.result.metadata,
        "view": project.view_state,
        "notes": project.notes,
    }
    write_document(path, "astro-stacker-project", data)
    project.project_path = path
    project.project_name = path.stem
    for frames in frame_groups(project).values():
        for frame in frames:
            save_history(frame)


def load_project(path: Path):
    """Return (project, warnings). Do not replace the active project on failure."""
    from ..io.loader import load_image, load_info

    path = path.resolve()
    data = read_document(path, "astro-stacker-project")
    if not isinstance(data, dict) or not isinstance(data.get("settings"), ProjectSettings):
        raise TypeError("プロジェクト設定が不正です。")
    view = data.get("view", {})
    if not isinstance(view, dict) or view.get("category", "lights") not in CATEGORIES:
        raise ValueError("表示設定が不正です。")
    if not isinstance(data.get("notes", ""), str):
        raise TypeError("プロジェクトのメモが不正です。")
    if "zoom" in view:
        import math

        if len(view["zoom"]) != 6 or not all(
            isinstance(v, (int, float)) and math.isfinite(v) for v in view["zoom"]
        ):
            raise ValueError("ズーム設定が不正です。")
    if "scroll" in view and (
        len(view["scroll"]) != 2 or not all(isinstance(v, int) for v in view["scroll"])
    ):
        raise ValueError("スクロール設定が不正です。")
    from ..core.provider import PreviewSettings

    preview = PreviewSettings(**view.get("preview", {}))
    if not isinstance(preview.binning, int) or preview.binning < 1:
        raise ValueError("プレビュー縮小率が不正です。")
    if not all(name in data["groups"] for name in CATEGORIES):
        raise ValueError("プロジェクトの画像分類が不足しています。")
    project = Project(
        project_name=data["name"],
        project_path=path,
        settings=data["settings"],
        view_state=data.get("view", {}),
        notes=data.get("notes", ""),
    )
    warnings = []
    changed = False
    for category, entries in data["groups"].items():
        if category not in CATEGORIES:
            raise ValueError("Unknown frame category")
        frames = []
        for entry in entries:
            frame = AstroImage(entry["info"])
            source = frame.info.path
            if source in project.known_paths:
                raise ValueError(f"画像が重複しています: {source}")
            try:
                current = fingerprint(source)
            except OSError:
                current = None
            if current is None:
                warnings.append(f"見つからない画像（使用を解除）: {source}")
                frame.info.enabled = False
                changed = True
                frame.info.wcs = None
            elif current != entry["fingerprint"]:
                warnings.append(f"変更された画像（解析情報を破棄）: {source}")
                enabled = frame.info.enabled
                frame = load_info(source)
                frame.info.enabled = enabled
                changed = True
            else:
                frame._source_fingerprint = current
                context = entry.get("alignment")
                if context:
                    frame._alignment_context = context
                restore_plate_cache(frame, entry.get("plate_solve"))
            if current is not None and not hasattr(frame, "_source_fingerprint"):
                frame._source_fingerprint = current
            frames.append(frame)
            project.known_paths.add(source)
        if category == "lights":
            project.light_frames = frames
        else:
            setattr(project.calibration_frames, category, frames)
    project.reference_image = next(
        (f for f in project.light_frames if f.info.path == data["reference"]), None
    )
    project.alignment_sessions = data["sessions"]
    project.current_alignment_session_id = data["session"]
    project.alignment_signature = data["signature"]
    if changed:
        # Reference or calibration changes can invalidate every matrix, even
        # when most light files are unchanged. Keep the session log for review.
        project.alignment_signature = None
        project.current_alignment_session_id = None
        for frames in frame_groups(project).values():
            for frame in frames:
                frame.info.transform = TransformData()
                frame.info.alignment_data = AlignmentData()
                frame.info.alignment_session_id = None
                if hasattr(frame, "_alignment_context"):
                    del frame._alignment_context
    project.result.metadata = data.get("result_metadata", {})
    output = data.get("output")
    if output:
        try:
            if fingerprint(output) != data.get("output_fingerprint"):
                raise ValueError("内容が変更されています")
            project.result.stacked_image = load_image(load_info(output))
            project.output_path = output
        except (OSError, ValueError) as exc:
            warnings.append(f"スタック結果を復元できません: {output} ({exc})")
    return project, warnings
