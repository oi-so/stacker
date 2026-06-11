from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

plugin_path = Path(
    ".venv/lib/python3.12/site-packages/PySide6/Qt/plugins"
).resolve()

QCoreApplication.setLibraryPaths([str(plugin_path)])

app = QApplication([])

print("OK")