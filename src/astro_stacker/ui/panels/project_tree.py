from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from ..constants import FrameType

class ProjectTree(QTreeWidget):
    frame_type_selected = Signal(object)

    def __init__(self):
        super().__init__()

        self.setHeaderHidden(True)

        self._items: dict[FrameType, QTreeWidgetItem] = {}
        self._item_to_type: dict[QTreeWidgetItem, FrameType] = {}

        self._build_tree()
        self.itemClicked.connect(self._on_item_clicked)


    def _build_tree(self) -> None:
        root = QTreeWidgetItem(["Project"])
        self.addTopLevelItem(root)

        for frame_type in FrameType:
            item = QTreeWidgetItem([f"{frame_type.ja_name} (0)"])

            root.addChild(item)

            self._items[frame_type] = item
            self._item_to_type[item] = frame_type

        root.setExpanded(True)

    def set_count(self, category: FrameType, count: int) -> None:
        item = self._items[category]

        item.setText(
            0,
            f"{category.ja_name} ({count})"
        )

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:

        frame_type = self._item_to_type.get(item)

        if frame_type is not None:
            self.frame_type_selected.emit(frame_type)
