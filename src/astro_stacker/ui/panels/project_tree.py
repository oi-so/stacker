from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem


class ProjectTree(QTreeWidget):
    category_selected = Signal(str)

    def __init__(self):
        super().__init__()

        self.setHeaderHidden(True)

        self._items: dict[str, QTreeWidgetItem] = {}

        self._build_tree()

        self.itemClicked.connect(self._on_item_clicked)

    def _build_tree(self) -> None:
        root = QTreeWidgetItem(["Project"])
        self.addTopLevelItem(root)

        categories = [
            ("lights", "Lights"),
            ("darks", "Darks"),
            ("flats", "Flats"),
            ("biases", "Biases"),
            ("flat_darks", "Flat Darks"),
            ("results", "Results"),
        ]

        for key, label in categories:
            item = QTreeWidgetItem([f"{label} (0)"])

            root.addChild(item)

            self._items[key] = item

        root.setExpanded(True)

    def set_count(self, category: str, count: int) -> None:
        labels = {
            "lights": "Lights",
            "darks": "Darks",
            "flats": "Flats",
            "biases": "Biases",
            "flat_darks": "Flat Darks",
            "results": "Results",
        }

        item = self._items[category]

        item.setText(
            0,
            f"{labels[category]} ({count})"
        )

    def _on_item_clicked(
        self,
        item: QTreeWidgetItem,
        column: int
    ) -> None:
        for key, tree_item in self._items.items():
            if item is tree_item:
                self.category_selected.emit(key)
                return