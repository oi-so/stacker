import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from ..alignment.aligner import align_catalogs, compose_alignment_transforms
from ..alignment.detection import process_frame
from ..core.frame_provider import FrameProvider
from ..io.image_data import AlignmentData, TransformData
from ..project.project import Project
from ..project.settings import AlignmentMode, AlignmentSettings, ReferenceMode
from ..utils.timer import timer

logger = logging.getLogger(__name__)

cpu = os.cpu_count()
MAX_WORKERS: int | None = cpu - 1 if cpu else None
MAX_NEIGHBOR_REFERENCE_DISTANCE = 10


class AlignmentPipeline:
    def __init__(self, provider: FrameProvider) -> None:
        self.provider = provider

    def run(
        self,
        project: Project,
        settings: AlignmentSettings,
        progress=None,
        is_cancelled=None,
    ) -> None:
        if not project.light_frames:
            raise ValueError("No light frames")

        enabled_frames = [frame for frame in project.light_frames if frame.info.enabled]
        if not enabled_frames:
            raise ValueError("No enabled light frames")

        if settings.reference_mode == ReferenceMode.MIDDLE:
            project.set_reference_image(enabled_frames[len(enabled_frames) // 2])
        elif settings.reference_mode == ReferenceMode.MANUAL:
            if project.reference_image is None or project.reference_image not in enabled_frames:
                raise ValueError("参照画像が選択されていません。")
        elif settings.reference_mode == ReferenceMode.BEST:
            raise ValueError("最高品質の参照画像は未実装です。")

        reference = project.reference_image
        if reference is None:
            raise ValueError("参照画像が設定されていません。")

        if settings.mode == AlignmentMode.ALL:
            session_id = project.create_alignment_session()
            frames_to_align = enabled_frames
        else:
            existing_session_id = project.current_alignment_session_id
            session_id = (
                existing_session_id
                if existing_session_id is not None
                else project.create_alignment_session()
            )

            if len(project.get_alignment_sessions()) > 1:
                raise ValueError(
                    "異なる位置合わせグループが混在しています。\n"
                    "全て位置合わせを実行してください。"
                )

            frames_to_align = [
                frame
                for frame in enabled_frames
                if frame.info.alignment_session_id != session_id
            ]

        if not frames_to_align:
            logger.info("No frames need alignment")
            return

        # Do not allow an old matrix to survive a failed retry.
        for frame in frames_to_align:
            frame.info.alignment_session_id = None
            frame.info.transform = TransformData()
            frame.info.alignment_data = AlignmentData()

        with timer("AlignmentWorkers", True):
            if is_cancelled and is_cancelled():
                return

            reference.info.alignment_session_id = session_id
            reference.info.transform = TransformData(matrix=np.eye(3, dtype=np.float64))
            reference.info.alignment_data = AlignmentData()

            if progress:
                progress("参照画像の星を検出中", 1, max(len(frames_to_align), 1), reference.info.path.name)

            reference_result = process_frame(
                self.provider,
                reference,
                settings.sigma,
                settings.max_stars,
            )
            reference.info.stars.all_stars = reference_result.catalog
            reference.info.score_data = reference_result.score_data

            detected_catalogs = {reference.info.path: reference_result.catalog}
            detection_finished = 1 if reference in frames_to_align else 0

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(
                        process_frame,
                        self.provider,
                        frame,
                        settings.sigma,
                        settings.max_stars,
                    ): frame
                    for frame in frames_to_align
                    if frame is not reference
                }

                for future in as_completed(futures):
                    if is_cancelled and is_cancelled():
                        return

                    frame = futures[future]
                    detection_finished += 1
                    if progress:
                        progress(
                            "星を検出中",
                            detection_finished,
                            len(frames_to_align),
                            frame.info.path.name,
                        )

                    try:
                        detection = future.result()
                    except Exception:
                        logger.exception("星の検出に失敗しました: %s", frame.info.path.name)
                        continue

                    frame.info.stars.all_stars = detection.catalog
                    frame.info.score_data = detection.score_data
                    detected_catalogs[frame.info.path] = detection.catalog

            if is_cancelled and is_cancelled():
                return

            # In NEW_ONLY mode, an already aligned neighboring frame may be the
            # best bridge for newly appended frames.
            for frame in enabled_frames:
                catalog = frame.info.stars.all_stars
                if catalog is not None:
                    detected_catalogs.setdefault(frame.info.path, catalog)

            reference_index = enabled_frames.index(reference)
            frame_indices = {
                frame.info.path: index for index, frame in enumerate(enabled_frames)
            }
            alignment_order = sorted(
                (frame for frame in frames_to_align if frame is not reference),
                key=lambda frame: abs(frame_indices[frame.info.path] - reference_index),
            )

            aligned_frames = {
                frame.info.path: frame
                for frame in enabled_frames
                if frame.info.transform.matrix is not None
                and frame.info.alignment_session_id == session_id
            }
            aligned_frames[reference.info.path] = reference

            aligned_finished = 1 if reference in frames_to_align else 0
            for frame in alignment_order:
                if is_cancelled and is_cancelled():
                    return

                target_catalog = detected_catalogs.get(frame.info.path)
                if target_catalog is None:
                    continue

                aligned_finished += 1
                if progress:
                    progress(
                        "位置合わせ中",
                        aligned_finished,
                        len(frames_to_align),
                        frame.info.path.name,
                    )

                target_index = frame_indices[frame.info.path]
                target_reference_distance = abs(target_index - reference_index)
                neighbor_candidates = [
                    candidate
                    for candidate in aligned_frames.values()
                    if candidate is not reference
                    and abs(frame_indices[candidate.info.path] - reference_index)
                    < target_reference_distance
                    and abs(frame_indices[candidate.info.path] - target_index)
                    <= MAX_NEIGHBOR_REFERENCE_DISTANCE
                    and candidate.info.path in detected_catalogs
                ]
                neighbor_candidates.sort(
                    key=lambda candidate: abs(
                        frame_indices[candidate.info.path] - target_index
                    )
                )

                last_error: Exception | None = None
                for candidate in [reference, *neighbor_candidates]:
                    candidate_catalog = detected_catalogs.get(candidate.info.path)
                    if candidate_catalog is None:
                        continue

                    try:
                        local_result = align_catalogs(candidate_catalog, target_catalog)
                        result_transform = compose_alignment_transforms(
                            local_result.transform,
                            candidate.info.transform,
                        )
                    except Exception as exc:  # noqa: BLE001 - astroalign raises several error types
                        last_error = exc
                        continue

                    frame.info.transform = result_transform
                    frame.info.alignment_data = local_result.info
                    frame.info.alignment_session_id = session_id
                    aligned_frames[frame.info.path] = frame

                    if candidate is not reference:
                        logger.info(
                            "Aligned %s through nearby frame %s",
                            frame.info.path.name,
                            candidate.info.path.name,
                        )
                    break
                else:
                    logger.error(
                        "Align failed after reference and neighbor attempts: %s (%s)",
                        frame.info.path.name,
                        last_error,
                    )

            project.alignment_signature = project.make_alignment_signature()
