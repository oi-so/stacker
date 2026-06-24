from __future__ import annotations

from pathlib import Path
import traceback

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QRadioButton,
    QVBoxLayout,
    QButtonGroup
)

from ..project.project import Project
from ..project.settings import AlignmentMode, ReferenceMode


class AlignmentSettingsDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.settings = QSettings("AstroStacker", "AstroStacker")
        self.setWindowTitle("位置合わせ設定")
        layout = QFormLayout(self)

        self.timing = QComboBox()
        self.timing.addItems(["位置合わせ前", "位置合わせ後"])
        self.timing.setCurrentIndex(0 if self.settings.value("alignment/calibrate_before", True, bool) else 1)
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
            box.setChecked(self.settings.value(key, True, bool))
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
        if self.settings.value("alignment/mode", "all") == "new_only" and has_session:
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
        self.reference.setCurrentIndex(self.settings.value("alignment/reference", 0, int))

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
                if self.settings.value("alignment/reference", 0, int) == 2:
                    self.reference.setCurrentIndex(0)


        layout.addRow("参照画像", self.reference)
        layout.addRow("手動参照画像", self.manual_reference)

        self.sigma = QDoubleSpinBox()
        self.sigma.setRange(3.0, 10.0)
        self.sigma.setSingleStep(0.5)
        self.sigma.setValue(self.settings.value("alignment/sigma", 5.0, float))
        layout.addRow("星検出感度 sigma", self.sigma)

        self.max_stars = QSpinBox()
        self.max_stars.setRange(20, 5000)
        self.max_stars.setValue(self.settings.value("alignment/max_stars", 500, int))
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
    def __init__(self, project: Project, parent=None, use_aligned_image: bool | None = None):
        super().__init__(parent)
        self.project = project
        self.settings = QSettings("AstroStacker", "AstroStacker")
        self.setWindowTitle("スタック設定")
        layout = QFormLayout(self)
        self.method = QComboBox()
        self.method.addItems(["Mean", "Median", "Sigma Clipping", "Add"])
        methods = ["mean", "median", "sigma_clip", "add"]
        current = self.settings.value("stacking/method", project.settings.light_frame.method)
        self.method.setCurrentIndex(methods.index(current) if current in methods else 0)
        layout.addRow("スタック方法", self.method)


        use_alignment = self.settings.value(
            "stacking/use_alignment",
            project.settings.use_alignment,
            type=bool,
        )
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


        self.sigma = QDoubleSpinBox()
        self.sigma.setRange(0.5, 10.0)
        self.sigma.setValue(self.settings.value("stacking/sigma", 3.0, float))
        layout.addRow("Sigma", self.sigma)
        self.iterations = QSpinBox()
        self.iterations.setRange(1, 10)
        self.iterations.setValue(self.settings.value("stacking/iterations", 1, int))
        layout.addRow("繰り返し", self.iterations)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        methods = ["mean", "median", "sigma_clip", "add"]
        self.project.settings.light_frame.method = methods[self.method.currentIndex()]
        self.project.settings.light_frame.sigma = self.sigma.value()
        self.project.settings.light_frame.iterations = self.iterations.value()
        self.settings.setValue("stacking/method", self.project.settings.light_frame.method)
        self.settings.setValue("stacking/sigma", self.sigma.value())
        self.settings.setValue("stacking/iterations", self.iterations.value())
        self.project.settings.use_alignment = self.use_alignment_btn.isChecked()
        self.settings.setValue("stacking/use_alignment", self.use_alignment_btn.isChecked())
        super().accept()


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
        }


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
