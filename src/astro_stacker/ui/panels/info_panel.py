from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel



class InfoPanel(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Image Info"))
        layout.addStretch()