import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QTextCharFormat, QColor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget


class QtLogEmitter(QObject):
    message = Signal(int, str)


class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.emitter = QtLogEmitter()

    def emit(self, record: logging.LogRecord) -> None:
        self.emitter.message.emit(record.levelno, self.format(record))


class LogPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        clear = QPushButton("クリア")
        tools.addStretch()
        tools.addWidget(clear)
        layout.addLayout(tools)

        self.editor = QTextEdit()
        self.editor.setReadOnly(True)
        layout.addWidget(self.editor)
        clear.clicked.connect(self.editor.clear)

    def append_log(self, level: int, text: str) -> None:
        color = QColor(self.palette().color(QPalette.ColorRole.Text))
        if level >= logging.ERROR:
            color = QColor("#ff6b6b")
        elif level >= logging.WARNING:
            color = QColor("#ffd166")

        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text + "\n", fmt)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()

    def log(self, text: str):
        self.append_log(logging.INFO, text)
