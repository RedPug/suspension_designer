from PySide6.QtCore import (QAbstractItemModel, QModelIndex, Qt)

from suspension_designer.scene import SceneState


class TreeItem:
    def __init__(self, name: str, data=None, parent=None, *, can_rename: bool = ..., can_select: bool = True):
        self.name = name
        self.data = data
        self.parent = parent
        self.children = []
        self.can_rename = can_rename
        self.can_select = can_select

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
        
        # self.document.selection_manager.selection_changed.connect(self._build_tree)

        self._build_tree()

    def _build_tree(self):
        self.root = TreeItem("Scene")

        scene: SceneState = self.document.scene_state

        nodes = TreeItem("Nodes", can_select=False)
        groups = TreeItem("Groups", can_select=False)
        planes = TreeItem("Reference Planes", can_select=False)
        model_variables = TreeItem("Model Variables", can_select=False)

        self.root.add_child(nodes)
        self.root.add_child(groups)
        self.root.add_child(planes)
        self.root.add_child(model_variables)

        for node in scene.nodes:
            nodes.add_child(TreeItem(node.name, node))

        for group in scene.groups:
            groups.add_child(TreeItem(group.name, group))

        for plane in scene.reference_planes:
            planes.add_child(TreeItem(plane.name, plane))

        for element in scene.model_variables:
            model_variables.add_child(TreeItem(element.name, element))

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