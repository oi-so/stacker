from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from ..constants import FrameType
from ...io.image_data import AstroImage

class ProjectTree(QTreeWidget):
    frame_type_selected = Signal(object)

    def __init__(self):
        super().__init__()

        self.setHeaderHidden(True)

        self._items: dict[FrameType, QTreeWidgetItem] = {}
        self._item_to_type: dict[QTreeWidgetItem, FrameType] = {}
        self.reference_item: QTreeWidgetItem | None = None

        self._build_tree()
        self.itemClicked.connect(self._on_item_clicked)


    def _build_tree(self) -> None:
        root = QTreeWidgetItem(["Project"])
        self.addTopLevelItem(root)

        self.reference_item = QTreeWidgetItem(["⭐ Reference: (None)"])

        for frame_type in FrameType:
            item = QTreeWidgetItem([f"{frame_type.ja_name} (0)"])

            root.addChild(item)
            if frame_type == FrameType.LIGHT:
                item.addChild(self.reference_item)
                item.setExpanded(True)

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

    def set_reference(self, astro_image: AstroImage | None) -> None:
        self.reference_item.takeChildren()

        if astro_image is None:
            return

        child = QTreeWidgetItem(
            [astro_image.info.path.name]
        )

        self.reference_item.addChild(child)
        self.reference_item.setExpanded(True)

    def update_reference_image_display(self, image: AstroImage | None) -> None:
        if self.reference_item:
            if image:
                # AstroImage の構造に合わせて名前を取得 (例: image.info.path.name)
                name = image.info.path.name if hasattr(image, 'info') else "Unknown"
                self.reference_item.setText(0, f"⭐ Reference: {name}")
            else:
                self.reference_item.setText(0, "⭐ Reference: (None)")
