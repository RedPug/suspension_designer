from uuid import UUID

from PySide6.QtCore import (QAbstractItemModel, QModelIndex, Qt)

from suspension_designer.editor.scene import SceneState


class TreeItem:
    def __init__(self, name: str, *, parent=None, can_rename: bool = ..., can_select: bool = True, id=...):
        assert isinstance(id, UUID) and can_select or not can_select, "ID must be a UUID instance if the item is selectable"

        self.name = name
        self.parent = parent
        self.children = []
        self.can_rename = can_rename
        self.can_select = can_select
        self.id = id

    def add_child(self, child: 'TreeItem'):
        child.parent = self
        self.children.append(child)

    def child(self,row):
        return self.children[row]
    
    def child_count(self):
        return len(self.children)
    
    def row(self):
        if self.parent is None:
            return 0
        return self.parent.children.index(self)
    
class SceneTreeModel(QAbstractItemModel):
    def __init__(self, document, parent=None):
        super().__init__(parent)

        self.document = document

        self._build_tree()

    def _build_tree(self):
        self.root = TreeItem("Root!", can_select=False)

        scene: SceneState = self.document.scene_state

        # self.root.add_child(TreeItem("Scene", data=self.document))

        nodes = TreeItem("Nodes", can_select=False)
        groups = TreeItem("Groups", can_select=False)
        planes = TreeItem("Reference Planes", can_select=False)
        model_variables = TreeItem("Model Variables", can_select=False)

        self.root.add_child(nodes)
        self.root.add_child(groups)
        self.root.add_child(planes)
        self.root.add_child(model_variables)

        for node in scene.nodes:
            nodes.add_child(TreeItem(node.name, id=node.id))

        for group in scene.groups:
            groups.add_child(TreeItem(group.name, id=group.id))

        for plane in scene.reference_planes:
            planes.add_child(TreeItem(plane.name, id=plane.id))

        for element in scene.model_variables:
            model_variables.add_child(TreeItem(element.name, id=element.id))

    # ---------- Required Qt methods ----------

    def columnCount(self, parent):
        return 1

    def rowCount(self, parent):
        if not parent.isValid():
            item = self.root
        else:
            item = parent.internalPointer()

        return item.child_count()

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self.root
        else:
            parent_item = parent.internalPointer()

        child = parent_item.child(row)

        return self.createIndex(row, column, child)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        child = index.internalPointer()
        parent = child.parent

        if parent is None or parent == self.root:
            return QModelIndex()

        return self.createIndex(parent.row(), 0, parent)

    def data(self, index, role):
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.DisplayRole:
            return item.name

        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags

        item: TreeItem = index.internalPointer()

        flags = Qt.ItemIsEnabled

        if item.can_select:
            flags |= Qt.ItemIsSelectable

        return flags