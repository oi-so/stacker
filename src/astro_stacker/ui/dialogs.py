from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from ..io.image_manager import ImageManager
from ..project.project import Project
from ..project.settings import (
    AlignmentMode,
    AlignmentStrategy,
    BoundaryMode,
    FrameSelectionMode,
    GroundSource,
    HDRStopAfter,
    NightscapeOutput,
    ReferenceMode,
    StackingMethod,
)
from .moving_object_dialog import MovingObjectSettingsDialog


class AlignmentSettingsDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.settings = QSettings("AstroStacker", "AstroStacker")
        self.setWindowTitle("位置合わせ設定")
        layout = QFormLayout(self)

        self.timing = QComboBox()
        self.timing.addItems(["位置合わせ前", "位置合わせ後"])
        self.timing.setCurrentIndex(0 if project.settings.alignment.calibrate_before_align else 1)
        layout.addRow("キャリブレーション", self.timing)

        self.use_dark = QCheckBox("Dark")
        self.use_bias = QCheckBox("Bias")
        self.use_flat = QCheckBox("Flat")
        self.use_flat_dark = QCheckBox("FlatDark")
        for key, box in [
            ("calibration/use_darks", self.use_dark),
            ("calibration/use_biases", self.use_bias),
            ("calibration/use_flats", self.use_flat),
            ("calibration/use_flat_darks", self.use_flat_dark),
        ]:
            box.setChecked(getattr(project.settings.calibration, key.split("/")[1]))
        calibration_box = QGroupBox()
        calibration_layout = QHBoxLayout(calibration_box)
        for box in (self.use_dark, self.use_bias, self.use_flat, self.use_flat_dark):
            calibration_layout.addWidget(box)
        layout.addRow("使用フレーム", calibration_box)

        self.mode_all = QRadioButton("全て位置合わせ")
        self.mode_new = QRadioButton("未位置合わせ画像のみ追加")

        sessions = project.get_alignment_sessions()
        has_session = len(sessions) == 1
        self.mode_new.setEnabled(has_session)
        if project.settings.alignment.mode == "new_only" and has_session:
            self.mode_new.setChecked(True)
        else:
            self.mode_all.setChecked(True)

        mode_box = QGroupBox()
        mode_layout = QVBoxLayout(mode_box)
        mode_layout.addWidget(self.mode_all)
        mode_layout.addWidget(self.mode_new)

        layout.addRow("位置合わせ対象", mode_box)

        self.reference = QComboBox()
        self.reference.addItems(["自動（中央）", "自動（最高品質）", "手動選択"])
        self.reference.setCurrentIndex(list(ReferenceMode).index(project.settings.alignment.reference_mode))

        self.manual_reference = QComboBox()
        for frame in project.light_frames:
            if not frame.info.enabled: continue
            self.manual_reference.addItem(
                frame.info.path.name,
                frame
            )
        self.manual_reference.setEnabled(False)
        self.reference.currentIndexChanged.connect(self._update_reference_widgets)

        if project.reference_image:
            if project.reference_image.info.enabled:
                self.reference.setCurrentIndex(2)
                index = self.manual_reference.findData(project.reference_image)
                if index >= 0:
                    self.manual_reference.setCurrentIndex(index)
            elif not project.reference_image.info.enabled:
                if list(ReferenceMode).index(project.settings.alignment.reference_mode) == 2:
                    self.reference.setCurrentIndex(0)


        layout.addRow("参照画像", self.reference)
        layout.addRow("手動参照画像", self.manual_reference)

        self.sigma = QDoubleSpinBox()
        self.sigma.setRange(3.0, 10.0)
        self.sigma.setSingleStep(0.5)
        self.sigma.setValue(project.settings.alignment.sigma)
        layout.addRow("星検出感度 sigma", self.sigma)

        self.max_stars = QSpinBox()
        self.max_stars.setRange(20, 5000)
        self.max_stars.setValue(project.settings.alignment.max_stars)
        layout.addRow("最大星数", self.max_stars)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_reference_widgets(self):
        manual = (self.reference.currentIndex() == 2)
        self.manual_reference.setEnabled(manual)

    def accept(self) -> None:
        alignment = self.project.settings.alignment
        calibration = self.project.settings.calibration
        alignment.calibrate_before_align = self.timing.currentIndex() == 0
        modes = [ReferenceMode.MIDDLE, ReferenceMode.BEST, ReferenceMode.MANUAL]
        alignment.reference_mode = (modes[self.reference.currentIndex()])
        if alignment.reference_mode == ReferenceMode.MANUAL:
            self.project.set_reference_image(self.manual_reference.currentData())
        alignment.sigma = self.sigma.value()
        alignment.max_stars = self.max_stars.value()
        calibration.use_darks = self.use_dark.isChecked()
        calibration.use_biases = self.use_bias.isChecked()
        calibration.use_flats = self.use_flat.isChecked()
        calibration.use_flat_darks = self.use_flat_dark.isChecked()
        alignment.mode = (AlignmentMode.ALL if self.mode_all.isChecked() else AlignmentMode.NEW_ONLY)


        self.settings.setValue("alignment/calibrate_before", alignment.calibrate_before_align)
        self.settings.setValue("alignment/reference", self.reference.currentIndex())
        self.settings.setValue("alignment/sigma", alignment.sigma)
        self.settings.setValue("alignment/max_stars", alignment.max_stars)
        self.settings.setValue("calibration/use_darks", calibration.use_darks)
        self.settings.setValue("calibration/use_biases", calibration.use_biases)
        self.settings.setValue("calibration/use_flats", calibration.use_flats)
        self.settings.setValue("calibration/use_flat_darks", calibration.use_flat_darks)
        self.settings.setValue("alignment/mode", alignment.mode.value,)
        super().accept()


class StackingSettingsDialog(QDialog):
    def __init__(
        self,
        project: Project,
        manager: ImageManager,
        parent=None,
        use_aligned_image: bool | None = None,
    ):
        super().__init__(parent)
        self.project = project
        self.manager = manager
        self.settings = QSettings("AstroStacker", "AstroStacker")
        self.setWindowTitle("スタック設定")
        layout = QFormLayout(self)
        self.method = QComboBox()
        for method in StackingMethod:
            self.method.addItem(method.show_name, method)
        current = project.settings.light_frame.method
        self.method.setCurrentIndex(self.method.findData(current))
        self.method.setToolTip(
            "Average: 高速な平均 / Median: 外れ値に強い中央値 / Add: 加算\n"
            "Sigma Clipping: σで外れ値を除外\n"
            "比較明・比較暗: 各画素・チャンネルの最大値・最小値\n"
            "最大・最小除外平均: 各画素で最大・最小を1個ずつ除いて平均（3枚以上）"
        )
        layout.addRow("スタック方法", self.method)


        use_alignment = project.settings.use_alignment
        alignment_mode_box = QGroupBox("使用する画像")
        alignment_mode_layout = QVBoxLayout(alignment_mode_box)
        self.alignment_group = QButtonGroup(self)
        self.use_alignment_btn = QRadioButton("アライメント後画像を使う")
        self.not_use_alignment_btn = QRadioButton("アライメント前画像を使う")
        self.alignment_group.addButton(self.use_alignment_btn)
        self.alignment_group.addButton(self.not_use_alignment_btn)
        if use_aligned_image is None:
            if use_alignment:
                self.use_alignment_btn.setChecked(True)
            else:
                self.not_use_alignment_btn.setChecked(True)
        else:
            if use_aligned_image:
                self.use_alignment_btn.setChecked(True)
            else:
                self.not_use_alignment_btn.setChecked(True)

        alignment_mode_layout.addWidget(self.use_alignment_btn)
        alignment_mode_layout.addWidget(self.not_use_alignment_btn)
        layout.addRow(alignment_mode_box)

        basis_box = QGroupBox("スタック基準")
        basis_layout = QVBoxLayout(basis_box)
        self.basis_group = QButtonGroup(self)
        self.star_basis_btn = QRadioButton("恒星基準")
        self.moving_basis_btn = QRadioButton("移動天体基準（彗星・小惑星など）")
        self.basis_group.addButton(self.star_basis_btn)
        self.basis_group.addButton(self.moving_basis_btn)
        if project.settings.moving_object.enabled:
            self.moving_basis_btn.setChecked(True)
        else:
            self.star_basis_btn.setChecked(True)
        self.moving_settings_button = QPushButton("赤経・赤緯 / カタログ / Plate Solve 設定...")
        self.moving_settings_button.clicked.connect(self._show_moving_object_settings)
        basis_layout.addWidget(self.star_basis_btn)
        basis_layout.addWidget(self.moving_basis_btn)
        basis_layout.addWidget(self.moving_settings_button)
        layout.addRow(basis_box)

        self.moving_basis_btn.toggled.connect(self._update_moving_widgets)
        self.use_alignment_btn.toggled.connect(self._update_moving_widgets)
        self._update_moving_widgets()


        self.sigma_group = QGroupBox("Sigma Clipping 設定")
        sigma_layout = QFormLayout(self.sigma_group)

        self.sigma = QDoubleSpinBox()
        self.sigma.setRange(0.5, 10.0)
        self.sigma.setValue(project.settings.light_frame.sigma)
        sigma_layout.addRow("Sigma", self.sigma)
        self.iterations = QSpinBox()
        self.iterations.setRange(1, 10)
        self.iterations.setValue(project.settings.light_frame.iterations)
        sigma_layout.addRow("繰り返し", self.iterations)

        self.method.currentIndexChanged.connect(self._update_sigma_widgets)
        self._update_sigma_widgets()

        layout.addRow(self.sigma_group)

        weighting = QGroupBox("正規化・品質")
        weighting_layout = QFormLayout(weighting)
        self.use_masks = QCheckBox("位置合わせ後の無効領域を除外")
        self.use_masks.setChecked(project.settings.light_frame.use_weight_masks)
        self.use_quality_weights = QCheckBox("品質重みを使用（完全除外とは別）")
        self.use_quality_weights.setChecked(project.settings.light_frame.use_quality_weights)
        self.exposure_normalization = QCheckBox("露出時間で正規化（線形画像向け）")
        self.exposure_normalization.setChecked(
            project.settings.light_frame.exposure_normalization
        )
        self.background_normalization = QComboBox()
        self.background_normalization.addItem("なし", "none")
        self.background_normalization.addItem("Median", "median")
        self.background_normalization.addItem("Robust", "robust")
        background = project.settings.light_frame.background_normalization
        self.background_normalization.setCurrentIndex(
            max(0, self.background_normalization.findData(background))
        )
        weighting_layout.addRow(self.use_masks)
        weighting_layout.addRow(self.use_quality_weights)
        weighting_layout.addRow(self.exposure_normalization)
        weighting_layout.addRow("背景正規化", self.background_normalization)
        layout.addRow(weighting)

        selection = QGroupBox("フレーム選別")
        selection_layout = QFormLayout(selection)
        self.selection_mode = QComboBox()
        for label, mode in (
            ("全画像", FrameSelectionMode.ALL),
            ("上位 %", FrameSelectionMode.TOP_PERCENT),
            ("上位 n 枚", FrameSelectionMode.TOP_COUNT),
            ("Score閾値以上", FrameSelectionMode.SCORE_THRESHOLD),
            ("手動", FrameSelectionMode.MANUAL),
        ):
            self.selection_mode.addItem(label, mode)
        current_selection = project.settings.processing.frame_selection
        self.selection_mode.setCurrentIndex(self.selection_mode.findData(current_selection.mode))
        self.selection_value = QDoubleSpinBox()
        self.selection_value.setRange(0, 100000)
        self.selection_value.setValue(current_selection.value)
        selection_layout.addRow("方式", self.selection_mode)
        selection_layout.addRow("値", self.selection_value)
        layout.addRow(selection)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        if self.moving_basis_btn.isChecked():
            if not self.use_alignment_btn.isChecked():
                QMessageBox.warning(
                    self,
                    "移動天体スタック",
                    "移動天体基準スタックでは、アライメント後画像を使用してください。",
                )
                return
            if len(self.project.settings.moving_object.anchors) < 2:
                QMessageBox.warning(
                    self,
                    "移動天体スタック",
                    "移動天体設定から手入力座標またはカタログ天体を設定してください。",
                )
                return
        methods = list(StackingMethod.__members__.values())
        self.project.settings.light_frame.method = methods[self.method.currentIndex()]
        self.project.settings.light_frame.sigma = self.sigma.value()
        self.project.settings.light_frame.iterations = self.iterations.value()
        self.project.settings.light_frame.use_weight_masks = self.use_masks.isChecked()
        self.project.settings.light_frame.use_quality_weights = self.use_quality_weights.isChecked()
        self.project.settings.light_frame.exposure_normalization = (
            self.exposure_normalization.isChecked()
        )
        self.project.settings.light_frame.background_normalization = (
            self.background_normalization.currentData()
        )
        self.project.settings.processing.frame_selection.mode = self.selection_mode.currentData()
        self.project.settings.processing.frame_selection.value = self.selection_value.value()
        self.settings.setValue("stacking/method", self.project.settings.light_frame.method)
        self.settings.setValue("stacking/sigma", self.sigma.value())
        self.settings.setValue("stacking/iterations", self.iterations.value())
        self.project.settings.use_alignment = self.use_alignment_btn.isChecked()
        self.project.settings.moving_object.enabled = self.moving_basis_btn.isChecked()
        self.settings.setValue("stacking/use_alignment", self.use_alignment_btn.isChecked())
        super().accept()

    def _show_moving_object_settings(self) -> None:
        if not self.project.light_frames:
            QMessageBox.information(self, "移動天体スタック", "ライトフレームを追加してください。")
            return
        if not any(frame.info.enabled for frame in self.project.light_frames):
            QMessageBox.information(
                self, "移動天体スタック", "有効なライトフレームがありません。"
            )
            return
        MovingObjectSettingsDialog(self.project, self.manager, self).exec()

    def _update_moving_widgets(self) -> None:
        moving = self.moving_basis_btn.isChecked()
        self.moving_settings_button.setEnabled(moving)
        if moving:
            self.use_alignment_btn.setChecked(True)
            self.not_use_alignment_btn.setEnabled(False)
        else:
            self.not_use_alignment_btn.setEnabled(True)

    def _update_sigma_widgets(self):
        method = self.method.currentData()
        enabled = method == StackingMethod.SIGMA_CLIP
        self.sigma_group.setEnabled(enabled)


class SaveDialog(QDialog):
    def __init__(self, default_folder: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("保存")
        layout = QFormLayout(self)
        self.format = QComboBox()
        self.format.addItems(["FITS", "TIFF", "PNG", "JPEG"])
        layout.addRow("保存形式", self.format)
        self.bit_depth = QComboBox()
        self.bit_depth.addItems(["16", "32 float"])
        layout.addRow("保存ビット", self.bit_depth)
        self.comment = QTextEdit()
        self.comment.setPlaceholderText("任意の出力コメント（撮影条件の集計に追記）")
        self.comment.setMaximumHeight(90)
        layout.addRow("EXIFコメント", self.comment)
        self.quality = QSpinBox()
        self.quality.setRange(0, 100)
        self.quality.setValue(90)
        layout.addRow("JPEG品質", self.quality)

        row = QHBoxLayout()
        self.path = QLineEdit(str(default_folder / "stacked.fits"))
        browse = QPushButton("参照")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path)
        row.addWidget(browse)
        layout.addRow("保存場所", row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        suffix = self.format.currentText().lower().replace("jpeg", "jpg")
        path, _ = QFileDialog.getSaveFileName(self, "保存", self.path.text(), f"{self.format.currentText()} (*.{suffix})")
        if path:
            self.path.setText(path)

    def selected(self) -> tuple[Path, dict]:
        suffix = self.format.currentText().lower().replace("jpeg", "jpg")
        path = Path(self.path.text())
        if path.suffix == "":
            path = path.with_suffix("." + suffix)
        return path, {
            "bit_depth": 32 if self.bit_depth.currentIndex() == 1 else 16,
            "quality": self.quality.value(),
            "comment": self.comment.toPlainText(),
        }


class HDRSettingsDialog(QDialog):
    def __init__(self, project: Project, default_folder: Path, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("HDR")
        layout = QFormLayout(self)
        self.auto_group = QCheckBox("EXIF撮影条件で自動グループ化")
        self.auto_group.setChecked(project.settings.processing.hdr.auto_group)
        frames = [frame for frame in project.light_frames if frame.info.enabled]
        self.manual_groups = QLineEdit(
            ",".join(
                project.settings.processing.hdr.manual_groups.get(
                    str(frame.info.path), str(index + 1)
                )
                for index, frame in enumerate(frames)
            )
        )
        self.manual_groups.setPlaceholderText("フレーム順のグループID（例: 1,1,2,2）")
        self.manual_groups.setEnabled(not self.auto_group.isChecked())
        self.auto_group.toggled.connect(
            lambda checked: self.manual_groups.setEnabled(not checked)
        )
        self.stop_after = QComboBox()
        self.stop_after.addItem("露出別Stackを保存して終了", HDRStopAfter.EXPOSURE_STACKS)
        self.stop_after.addItem("HDR Mergeまで", HDRStopAfter.MERGE)
        self.stop_after.addItem("Tone Mappingまで", HDRStopAfter.TONE_MAP)
        self.stop_after.setCurrentIndex(
            self.stop_after.findData(project.settings.processing.hdr.stop_after)
        )
        self.tone_mapping = QComboBox()
        self.tone_mapping.addItem("Global", "global")
        self.tone_mapping.addItem("Local", "local")
        self.tone_mapping.addItem("Log", "log")
        self.tone_mapping.setCurrentIndex(
            max(0, self.tone_mapping.findData(project.settings.processing.hdr.tone_mapping))
        )
        self.local_scale = QDoubleSpinBox()
        self.local_scale.setRange(0.5, 1024)
        self.local_scale.setValue(project.settings.processing.hdr.local_scale)
        self.detail_strength = QDoubleSpinBox()
        self.detail_strength.setRange(0, 4)
        self.detail_strength.setSingleStep(0.1)
        self.detail_strength.setValue(project.settings.processing.hdr.detail_strength)
        self.format = QComboBox()
        for label, suffix in (("FITS", ".fits"), ("TIFF", ".tiff"), ("PNG", ".png"), ("JPEG", ".jpg")):
            self.format.addItem(label, suffix)
        self.output = QLineEdit(str(default_folder / "hdr"))
        browse = QPushButton("参照")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.output)
        row.addWidget(browse)
        layout.addRow(self.auto_group)
        layout.addRow("手動グループ", self.manual_groups)
        layout.addRow("実行範囲", self.stop_after)
        layout.addRow("Tone Mapping", self.tone_mapping)
        layout.addRow("Local scale", self.local_scale)
        layout.addRow("Detail strength", self.detail_strength)
        layout.addRow("保存形式", self.format)
        layout.addRow("出力フォルダ", row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "HDR出力フォルダ", self.output.text())
        if folder:
            self.output.setText(folder)

    def accept(self):
        settings = self.project.settings.processing.hdr
        settings.auto_group = self.auto_group.isChecked()
        if not settings.auto_group:
            frames = [frame for frame in self.project.light_frames if frame.info.enabled]
            labels = [value.strip() for value in self.manual_groups.text().split(",")]
            if len(labels) != len(frames) or any(not value for value in labels):
                QMessageBox.warning(
                    self,
                    "HDR手動グループ",
                    f"有効フレーム{len(frames)}枚分のグループIDをカンマ区切りで指定してください。",
                )
                return
            settings.manual_groups = {
                str(frame.info.path): label
                for frame, label in zip(frames, labels, strict=True)
            }
        settings.stop_after = self.stop_after.currentData()
        settings.tone_mapping = self.tone_mapping.currentData()
        settings.local_scale = self.local_scale.value()
        settings.detail_strength = self.detail_strength.value()
        super().accept()

    def selected(self):
        return Path(self.output.text()), self.format.currentData()


class TimelapseSettingsDialog(QDialog):
    def __init__(self, project: Project, default_folder: Path, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("タイムラプス用n枚スタック")
        layout = QFormLayout(self)
        settings = project.settings.processing.timelapse
        self.window = QSpinBox()
        self.window.setRange(1, 10000)
        self.window.setValue(settings.window_size)
        self.step = QSpinBox()
        self.step.setRange(1, 10000)
        self.step.setValue(settings.step)
        self.partial = QCheckBox("最後の端数グループも出力")
        self.partial.setChecked(settings.include_partial)
        self.alignment = QComboBox()
        self.alignment.addItem("位置合わせなし", AlignmentStrategy.NONE)
        self.alignment.addItem("全画像を共通星座標へ位置合わせ", AlignmentStrategy.STAR_GLOBAL)
        self.alignment.setCurrentIndex(max(0, self.alignment.findData(settings.alignment)))
        self.format = QComboBox()
        for label, suffix in (("FITS", ".fits"), ("TIFF", ".tiff"), ("PNG", ".png"), ("JPEG", ".jpg")):
            self.format.addItem(label, suffix)
        self.output = QLineEdit(str(default_folder / "timelapse"))
        browse = QPushButton("参照")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.output)
        row.addWidget(browse)
        layout.addRow("Window size", self.window)
        layout.addRow("Step", self.step)
        layout.addRow(self.partial)
        layout.addRow("Alignment", self.alignment)
        layout.addRow("保存形式", self.format)
        layout.addRow("出力フォルダ", row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "タイムラプス出力フォルダ", self.output.text()
        )
        if folder:
            self.output.setText(folder)

    def accept(self):
        settings = self.project.settings.processing.timelapse
        settings.window_size = self.window.value()
        settings.step = self.step.value()
        settings.include_partial = self.partial.isChecked()
        settings.alignment = self.alignment.currentData()
        super().accept()

    def selected(self):
        return Path(self.output.text()), self.format.currentData()


class NightscapeSettingsDialog(QDialog):
    def __init__(self, project: Project, default_folder: Path, parent=None, suggestion=None):
        super().__init__(parent)
        self.project = project
        settings = project.settings.processing.nightscape
        self.setWindowTitle("新星景")
        layout = QFormLayout(self)
        self.output_mode = QComboBox()
        for label, value in (
            ("星空素材だけ", NightscapeOutput.SKY_ONLY),
            ("地上素材だけ", NightscapeOutput.GROUND_ONLY),
            ("マスクだけ", NightscapeOutput.MASK_ONLY),
            ("星空・地上・マスク素材", NightscapeOutput.MATERIALS),
            ("最終合成まで", NightscapeOutput.FINAL),
        ):
            self.output_mode.addItem(label, value)
        self.output_mode.setCurrentIndex(self.output_mode.findData(settings.output))
        self.ground_source = QComboBox()
        self.ground_source.addItem("星空と同じ画像から生成", GroundSource.SAME_FRAMES)
        self.ground_source.addItem("別撮り画像を使用", GroundSource.SEPARATE_FRAMES)
        self.ground_source.setCurrentIndex(self.ground_source.findData(settings.ground_source))
        self.ground_paths = QLineEdit()
        self.ground_paths.setReadOnly(True)
        ground_browse = QPushButton("別撮り画像を選択")
        ground_browse.clicked.connect(self._browse_ground)
        ground_row = QHBoxLayout()
        ground_row.addWidget(self.ground_paths)
        ground_row.addWidget(ground_browse)
        self.boundary = QComboBox()
        self.boundary.addItem("地上を完全にマスク", BoundaryMode.GROUND_MASK)
        self.boundary.addItem("光害フレームで滑らかに合成", BoundaryMode.LIGHT_POLLUTION)
        self.boundary.addItem("ユーザー作成マスク", BoundaryMode.USER_MASK)
        self.boundary.setCurrentIndex(self.boundary.findData(settings.boundary_mode))
        self.user_mask_path = QLineEdit()
        mask_browse = QPushButton("マスク選択")
        mask_browse.clicked.connect(self._browse_mask)
        mask_row = QHBoxLayout()
        mask_row.addWidget(self.user_mask_path)
        mask_row.addWidget(mask_browse)
        self.star_alignment = QCheckBox("星空を恒星基準で処理")
        self.star_alignment.setChecked(settings.star_alignment)
        self.ground_alignment = QCheckBox("地上固定Alignment + Stack")
        self.ground_alignment.setChecked(settings.ground_alignment)
        self.star_protection = QCheckBox("地平線境界の星を保護")
        self.star_protection.setChecked(settings.use_star_mask)
        self.split_mode = QComboBox()
        self.split_mode.addItem("分割なし", "none")
        self.split_mode.addItem("反転候補から自動提案", "auto")
        self.split_mode.addItem("手動分割", "manual")
        self.split_mode.setCurrentIndex(max(0, self.split_mode.findData(settings.split_mode)))
        self.split_index = QSpinBox()
        self.split_index.setRange(0, max(0, len(project.light_frames) - 1))
        self.split_index.setValue(settings.split_index)
        self.suggestion = QLabel("自動分割候補: 解析結果なし")
        self.suggestion.setWordWrap(True)
        if suggestion is not None:
            points = ", ".join(str(value) for value in suggestion.split_indices) or "なし"
            self.suggestion.setText(
                f"自動分割候補: {points} / 信頼度 {suggestion.confidence:.0%} / "
                f"{suggestion.reason}。候補を採用せず手動分割へ変更できます。"
            )
            if suggestion.split_indices and settings.split_index == 0:
                self.split_index.setValue(suggestion.split_indices[0])
        self.feather = QDoubleSpinBox()
        self.feather.setRange(0, 256)
        self.feather.setValue(settings.feather)
        self.blur_scale = QDoubleSpinBox()
        self.blur_scale.setRange(0.1, 1024)
        self.blur_scale.setValue(settings.blur_scale)
        self.transition_width = QDoubleSpinBox()
        self.transition_width.setRange(0.1, 1024)
        self.transition_width.setValue(settings.transition_width)
        self.background_strength = QDoubleSpinBox()
        self.background_strength.setRange(0, 4)
        self.background_strength.setSingleStep(0.05)
        self.background_strength.setValue(settings.background_strength)
        self.format = QComboBox()
        for label, suffix in (("FITS", ".fits"), ("TIFF", ".tiff"), ("PNG", ".png"), ("JPEG", ".jpg")):
            self.format.addItem(label, suffix)
        self.output = QLineEdit(str(default_folder / "nightscape"))
        output_browse = QPushButton("参照")
        output_browse.clicked.connect(self._browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output)
        output_row.addWidget(output_browse)
        layout.addRow("作成内容", self.output_mode)
        layout.addRow("地上画像", self.ground_source)
        layout.addRow("別撮り地上", ground_row)
        layout.addRow("境界処理", self.boundary)
        layout.addRow("ユーザーマスク", mask_row)
        layout.addRow(self.star_alignment)
        layout.addRow(self.ground_alignment)
        layout.addRow(self.star_protection)
        layout.addRow("時間グループ", self.split_mode)
        layout.addRow(self.suggestion)
        layout.addRow("手動分割位置", self.split_index)
        layout.addRow("Feather", self.feather)
        layout.addRow("光害 Blur scale", self.blur_scale)
        layout.addRow("境界 Transition width", self.transition_width)
        layout.addRow("背景強度", self.background_strength)
        layout.addRow("保存形式", self.format)
        layout.addRow("出力フォルダ", output_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_ground(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "別撮り地上画像")
        if paths:
            self.ground_paths.setText(";".join(paths))

    def _browse_mask(self):
        path, _ = QFileDialog.getOpenFileName(self, "ユーザー作成マスク")
        if path:
            self.user_mask_path.setText(path)

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "新星景出力", self.output.text())
        if path:
            self.output.setText(path)

    def accept(self):
        settings = self.project.settings.processing.nightscape
        settings.output = self.output_mode.currentData()
        settings.ground_source = self.ground_source.currentData()
        settings.boundary_mode = self.boundary.currentData()
        settings.star_alignment = self.star_alignment.isChecked()
        settings.ground_alignment = self.ground_alignment.isChecked()
        settings.use_star_mask = self.star_protection.isChecked()
        settings.split_mode = self.split_mode.currentData()
        settings.split_index = self.split_index.value()
        settings.feather = self.feather.value()
        settings.blur_scale = self.blur_scale.value()
        settings.transition_width = self.transition_width.value()
        settings.background_strength = self.background_strength.value()
        if settings.ground_source == GroundSource.SEPARATE_FRAMES and not self.ground_paths.text():
            QMessageBox.warning(self, "新星景", "別撮り地上画像を選択してください。")
            return
        if settings.boundary_mode == BoundaryMode.USER_MASK and not self.user_mask_path.text():
            QMessageBox.warning(self, "新星景", "ユーザー作成マスクを選択してください。")
            return
        super().accept()

    def selected(self):
        ground = [Path(value) for value in self.ground_paths.text().split(";") if value]
        mask = Path(self.user_mask_path.text()) if self.user_mask_path.text() else None
        return Path(self.output.text()), self.format.currentData(), ground, mask


class ParallelSettingsDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle("並列処理")
        layout = QFormLayout(self)
        self.workers = QSpinBox()
        self.workers.setRange(0, 256)
        self.workers.setSpecialValueText("自動（CPU・空きメモリから決定）")
        self.workers.setValue(project.settings.processing.parallel_workers)
        layout.addRow("最大ワーカー数", self.workers)
        note = QLabel(
            "0では処理ごとにCPU数と空きメモリから安全な並列度を決定します。"
            "結果順序は入力順に固定され、メモリ不足時は逐次処理へ縮退します。"
        )
        note.setWordWrap(True)
        layout.addRow(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        self.project.settings.processing.parallel_workers = self.workers.value()
        super().accept()


class ErrorDialog(QMessageBox):
    @classmethod
    def show_exception(cls, parent, title: str, exc: BaseException) -> None:
        box = cls(parent)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle(title)
        box.setText(str(exc))
        details = QTextEdit()
        details.setPlainText("".join(traceback.format_exception(exc)))
        box.setDetailedText(details.toPlainText())
        box.exec()


def show_language_restart(parent) -> None:
    QMessageBox.information(parent, "言語", "言語設定は次回起動時に反映されます。")
