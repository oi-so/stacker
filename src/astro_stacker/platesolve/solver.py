from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

from ..core.frame_provider import FrameProvider
from ..io.image_data import AstroImage


@dataclass(frozen=True, slots=True)
class PlateSolveSettings:
    executable: str = "solve-field"
    downsample: int = 2
    timeout_seconds: int = 180
    scale_low: float | None = None
    scale_high: float | None = None
    center_ra_deg: float | None = None
    center_dec_deg: float | None = None
    search_radius_deg: float = 8.0
    auto_downsample: bool = True


@dataclass(frozen=True, slots=True)
class PlateSolveResult:
    wcs: WCS
    center_ra_deg: float
    center_dec_deg: float
    pixel_scale_arcsec: float


class AstrometryNetSolver:
    """Run the locally installed Astrometry.net ``solve-field`` command."""

    def solve(
        self,
        frame: AstroImage,
        provider: FrameProvider,
        settings: PlateSolveSettings | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> PlateSolveResult:
        settings = settings or PlateSolveSettings()
        if is_cancelled and is_cancelled():
            raise RuntimeError("Plate Solveをキャンセルしました。")
        token = getattr(provider, "cache_token", None)
        key = (token(frame), settings) if token is not None else None
        cached = getattr(frame, "_plate_solve_cache", None)
        if key is not None and cached is not None and cached[0] == key:
            return replace(cached[1], wcs=cached[1].wcs.deepcopy())
        executable = self._find_executable(settings.executable)
        image = self._as_mono(provider.get_image(frame))

        with tempfile.TemporaryDirectory(prefix="astro-stacker-platesolve-") as directory:
            work_dir = Path(directory)
            input_path = work_dir / "input.fits"
            wcs_path = work_dir / "solution.wcs"
            solved_path = work_dir / "solution.solved"
            fits.writeto(input_path, image, overwrite=True)

            # Let solve-field downsample so its WCS remains in original pixels.
            effective = replace(
                settings,
                downsample=max(
                    settings.downsample,
                    (max(image.shape) + 2047) // 2048 if settings.auto_downsample else 1,
                ),
            )
            command = self._command(executable, input_path, wcs_path, solved_path, effective)
            log_path = work_dir / "solve-field.log"
            with log_path.open("w+", encoding="utf-8") as log_file:
                process = subprocess.Popen(
                    command,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                self._wait(process, settings.timeout_seconds, is_cancelled)
                log_file.seek(0)
                output = log_file.read()

            if process.returncode != 0 or not wcs_path.exists() or not solved_path.exists():
                tail = "\n".join(output.splitlines()[-20:])
                raise RuntimeError(
                    "Plate Solveに失敗しました。Astrometry.netのindexファイルと設定を確認してください。"
                    + (f"\n\nsolve-field output:\n{tail}" if tail else "")
                )

            wcs = WCS(fits.getheader(wcs_path)).celestial
            if not wcs.has_celestial:
                raise RuntimeError("Plate Solveの結果に天球WCSが含まれていません。")

        height, width = image.shape
        ra, dec = wcs.pixel_to_world_values((width - 1) / 2.0, (height - 1) / 2.0)
        scales = np.asarray(proj_plane_pixel_scales(wcs), dtype=np.float64) * 3600.0
        pixel_scale = float(np.mean(np.abs(scales)))
        result = PlateSolveResult(
            wcs=wcs,
            center_ra_deg=float(np.asarray(ra)) % 360.0,
            center_dec_deg=float(np.asarray(dec)),
            pixel_scale_arcsec=pixel_scale,
        )

        if key is not None:
            frame._plate_solve_cache = (key, replace(result, wcs=result.wcs.deepcopy()))
        return result

    @staticmethod
    def _find_executable(value: str) -> str:
        value = value.strip()
        if not value:
            value = "solve-field"
        path = shutil.which(value)
        if path is None:
            raise FileNotFoundError(
                f"solve-fieldが見つかりません: {value}\n"
                "Astrometry.net本体と撮影画角に合うindexファイルをインストールしてください。"
            )
        return path

    @staticmethod
    def _as_mono(image: np.ndarray) -> np.ndarray:
        data = np.asarray(image)
        if data.ndim == 2:
            mono = data
        elif data.ndim == 3 and data.shape[-1] == 1:
            mono = data[..., 0]
        elif data.ndim == 3:
            mono = np.mean(data[..., :3], axis=-1)
        else:
            raise ValueError(f"Plate Solve非対応の画像形状です: {data.shape}")
        mono = np.asarray(mono, dtype=np.float32)
        if not np.all(np.isfinite(mono)):
            mono = np.nan_to_num(mono, copy=True)
        return mono

    @staticmethod
    def _command(
        executable: str,
        input_path: Path,
        wcs_path: Path,
        solved_path: Path,
        settings: PlateSolveSettings,
    ) -> list[str]:
        command = [
            executable,
            "--overwrite",
            "--no-plots",
            "--no-verify",
            "--new-fits",
            "none",
            "--match",
            "none",
            "--rdls",
            "none",
            "--corr",
            "none",
            "--downsample",
            str(max(1, settings.downsample)),
            "--wcs",
            str(wcs_path),
            "--solved",
            str(solved_path),
        ]
        if settings.scale_low is not None and settings.scale_high is not None:
            if not (0.0 < settings.scale_low < settings.scale_high):
                raise ValueError("Plate Solveのピクセルスケール範囲が不正です。")
            command.extend(
                [
                    "--scale-units",
                    "arcsecperpix",
                    "--scale-low",
                    str(settings.scale_low),
                    "--scale-high",
                    str(settings.scale_high),
                ]
            )
        if settings.center_ra_deg is not None and settings.center_dec_deg is not None:
            if not -90.0 <= settings.center_dec_deg <= 90.0:
                raise ValueError("Plate Solveの探索中心赤緯が不正です。")
            if not 0.0 < settings.search_radius_deg <= 180.0:
                raise ValueError("Plate Solveの探索半径が不正です。")
            command.extend(
                [
                    "--ra",
                    str(settings.center_ra_deg % 360.0),
                    "--dec",
                    str(settings.center_dec_deg),
                    "--radius",
                    str(settings.search_radius_deg),
                ]
            )
        command.append(str(input_path))
        return command

    @staticmethod
    def _wait(
        process: subprocess.Popen[str],
        timeout_seconds: int,
        is_cancelled: Callable[[], bool] | None,
    ) -> None:
        deadline = time.monotonic() + max(1, timeout_seconds)
        while process.poll() is None:
            if is_cancelled is not None and is_cancelled():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise RuntimeError("Plate Solveをキャンセルしました。")
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                raise TimeoutError(f"Plate Solveが{timeout_seconds}秒でタイムアウトしました。")
            time.sleep(0.1)
