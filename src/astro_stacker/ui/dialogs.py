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
)

from ..project.project import Project


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

        self.reference = QComboBox()
        self.reference.addItems(["自動=中央", "自動=最高品質", "手動選択"])
        self.reference.setCurrentIndex(self.settings.value("alignment/reference", 0, int))
        layout.addRow("参照画像", self.reference)

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

    def accept(self) -> None:
        alignment = self.project.settings.alignment
        calibration = self.project.settings.calibration
        alignment.calibrate_before_align = self.timing.currentIndex() == 0
        alignment.reference_mode = ["middle", "best", "manual"][self.reference.currentIndex()]
        alignment.sigma = self.sigma.value()
        alignment.max_stars = self.max_stars.value()
        calibration.use_darks = self.use_dark.isChecked()
        calibration.use_biases = self.use_bias.isChecked()
        calibration.use_flats = self.use_flat.isChecked()
        calibration.use_flat_darks = self.use_flat_dark.isChecked()

        self.settings.setValue("alignment/calibrate_before", alignment.calibrate_before_align)
        self.settings.setValue("alignment/reference", self.reference.currentIndex())
        self.settings.setValue("alignment/sigma", alignment.sigma)
        self.settings.setValue("alignment/max_stars", alignment.max_stars)
        self.settings.setValue("calibration/use_darks", calibration.use_darks)
        self.settings.setValue("calibration/use_biases", calibration.use_biases)
        self.settings.setValue("calibration/use_flats", calibration.use_flats)
        self.settings.setValue("calibration/use_flat_darks", calibration.use_flat_darks)
        super().accept()


class StackingSettingsDialog(QDialog):
    def __init__(self, project: Project, parent=None):
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
