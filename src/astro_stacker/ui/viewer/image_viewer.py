from PySide6.QtWidgets import QGraphicsView, QGraphicsScene


class ImageViewer(QGraphicsView):

    def __init__(self):
        super().__init__()

        self.scene = QGraphicsScene()
        self.setScene(self.scene)