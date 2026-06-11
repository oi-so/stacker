from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from enum import StrEnum

class FrameType(StrEnum):
    LIGHT = "lights"
    DARK = "darks"
    FLAT = "flats"
    FLAT_DARK = "flat_darks"
    BIAS = "biases"

    @property
    def label(self) -> str:
        return {
            FrameType.LIGHT: "Lights",
            FrameType.DARK: "Darks",
            FrameType.FLAT: "Flats",
            FrameType.FLAT_DARK: "Flat Darks",
            FrameType.BIAS: "Biases",
        }[self]


class ProjectTree(QTreeWidget):
    category_selected = Signal(str)
    frame_type_selected = Signal(FrameType)

    def __init__(self):
        super().__init__()

        self.setHeaderHidden(True)

        self._items: dict[str, QTreeWidgetItem] = {}

        self._build_tree()

        self.itemClicked.connect(self._on_item_clicked)
        self._item_to_type = {}


    def _build_tree(self) -> None:
        root = QTreeWidgetItem(["Project"])
        self.addTopLevelItem(root)

        for frame_type in FrameType:
            item = QTreeWidgetItem([f"{frame_type.label} (0)"])

            root.addChild(item)

            self._items[frame_type] = item

        root.setExpanded(True)

    def set_count(self, category: FrameType, count: int) -> None:
        item = self._items[category]

        item.setText(
            0,
            f"{category.label} ({count})"
        )

    def _on_item_clicked(
        self,
        item: QTreeWidgetItem,
    ) -> None:
        for frame_type, tree_item in self._items.items():
            if item is tree_item:
                self.category_selected.emit(frame_type)
                return