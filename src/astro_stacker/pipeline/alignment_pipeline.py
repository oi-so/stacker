from ..core.frame_provider import FrameProvider
from ..project.project import Project
from ..project.settings import AlignmentSettings, AlignmentMode, ReferenceMode
from ..alignment.aligner import align_catalogs
from ..io.image_data import TransformData, AlignmentData
import os

from concurrent.futures import ThreadPoolExecutor, as_completed
from ..alignment.detection import process_frame

import logging

logger = logging.getLogger(__name__)

cpu = os.cpu_count()
MAX_WORKERS: int | None = cpu - 1 if cpu else None

class AlignmentPipeline:
    def __init__(self, provider: FrameProvider) -> None:
        self.provider = provider


    def run(self, project: Project, settings: AlignmentSettings, progress=None, is_cancelled=None):
        if not project.light_frames:
            raise ValueError("No light frames")
        
        enabled_frames = [
            frame for frame in project.light_frames
            if frame.info.enabled
        ]

        if not enabled_frames:
            raise ValueError("No enabled light frames")

        if settings.reference_mode == ReferenceMode.MIDDLE:
            project.set_reference_image(
                enabled_frames[
                    len(enabled_frames) // 2
                ]
            )

        elif settings.reference_mode == ReferenceMode.MANUAL:
            if (
                project.reference_image is None
                or project.reference_image not in enabled_frames
            ):
                raise ValueError(
                    "参照画像が選択されていません。"
                )

        elif settings.reference_mode == ReferenceMode.BEST:
            raise ValueError(
                "最高品質の参照画像は未実装です。"
            )

        reference = project.reference_image
        if reference is None:
            raise ValueError(
                "参照画像が設定されていません。"
            )

        if settings.mode == AlignmentMode.ALL:
            session_id = (
                project.create_alignment_session()
            )
            frames_to_align = enabled_frames

        else:
            session_id = (
                project.current_alignment_session_id
            )

            if session_id is None:
                session_id = (
                    project.create_alignment_session()
                )

            sessions = (
                project.get_alignment_sessions()
            )

            if len(sessions) > 1:
                raise ValueError(
                    "異なる位置合わせグループが混在しています。\n"
                    "全て位置合わせを実行してください。"
                )

            frames_to_align = [
                frame for frame in enabled_frames
                if frame.info.alignment_session_id != session_id
            ]

        total = len(frames_to_align)

        if total == 0:
            logger.info("No frames need alignment")
            return



        finished = 0
        if reference in frames_to_align:
            finished = 1
            if progress:
                progress("参照画像の星を検出中", finished, total, reference.info.path.name)

        if is_cancelled and is_cancelled():
            return

        reference.info.alignment_session_id = session_id
        reference.info.transform = TransformData()
        reference.info.alignment_data = AlignmentData()
        project.set_reference_image(reference)

        reference_result = process_frame(
            self.provider,
            reference,
            settings.sigma,
            settings.max_stars,
        )

        reference_catalog = reference_result.catalog
        reference_alignment_catalog = reference_result.alignment_catalog

        reference.info.stars.all_stars = reference_catalog
        reference.info.stars.alignment_stars = reference_alignment_catalog
        reference.info.score_data = reference_result.score_data

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
                astro_image = futures[future]

                if is_cancelled and is_cancelled():
                    return

                finished += 1

                if progress:
                    progress("位置合わせ中", finished, total, astro_image.info.path.name)

                try:
                    # ここで例外が発生する可能性（process_frame 内のエラー）をキャッチできるようにする
                    detection = future.result()
                except Exception:
                    logger.exception("星の検出に失敗しました: %s", astro_image.info.path.name)
                    continue

                astro_image.info.stars.all_stars = detection.catalog
                astro_image.info.stars.alignment_stars = detection.alignment_catalog
                astro_image.info.score_data = detection.score_data

                try:
                    result = align_catalogs(
                        reference_alignment_catalog,
                        detection.alignment_catalog,
                    )
                except Exception:
                    logger.exception("Align failed: %s", astro_image.info.path.name)
                    continue

                if result is None:
                    continue

                astro_image.info.transform = result.transform
                astro_image.info.alignment_data = result.info
                astro_image.info.alignment_session_id = session_id

        project.alignment_signature = project.make_alignment_signature()
