from abc import ABC, abstractmethod
from time import perf_counter
from functools import partial

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt, Signal

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDockWidget,
    QFormLayout,
    QFrame, 
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeView,
    QWidget,
    QVBoxLayout
)

from PySide6.QtGui import QBrush, QColor

from suspension_designer.properties import GroupEditor, Property
from suspension_designer.document import (
    DOCK_PROPERTIES,
    DOCK_TREE,
    Document,
    DocumentManager,
    EditorDocument,
)

class TreeDock(QDockWidget):
    dock_key = DOCK_TREE
    
    def __init__(self, parent, document_manager: DocumentManager):
        super().__init__("Tree", parent)
        self.setObjectName("treeDock")

        self.document_manager = document_manager

        self.current_doc = None

        self.document_manager.selection_changed.connect(self.setDocument)

        self.tree = QTreeView(self)

        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)

        # self.objectSelected.connect(lambda obj: print(f"Selected object: {str(obj)}"))

        self.setWidget(self.tree)

    def _onSelectionChanged(self, selected, deselected):
        indexes = selected.indexes()

        if not indexes:
            self.document_manager.current_document.selection_manager.set_selected(None)
            return

        item = indexes[0].internalPointer()

        self.document_manager.current_document.selection_manager.set_selected(item.data)

    def setDocument(self, document: Document):
        """Switch to displaying a different document."""
        if document == self.current_doc:
            return

        if self.current_doc:
            self.current_doc.did_change.disconnect(self.refreshTree)
            self.current_doc.selection_manager.selection_changed.disconnect(self.restoreSelection)

        self.current_doc = document

        if document is None:
            self.tree.setModel(None)
            return
        
        document.selection_manager.selection_changed.connect(
            self.restoreSelection
        )

        document.did_change.connect(self.refreshTree)



        self.tree.setModel(document.create_tree_model())

        # Optional
        self.tree.expandToDepth(1)

        if self.tree.model() is None:
            return

        self.tree.selectionModel().selectionChanged.connect(
            self._onSelectionChanged
        )
        self.restoreSelection()

    def refreshTree(self):
        document = self.document_manager.current_document

        if document is None:
            self.tree.setModel(None)
            return
        
        if self.tree.model() is None:
            return

        self.tree.setModel(document.create_tree_model())

        self.tree.selectionModel().selectionChanged.connect(
            self._onSelectionChanged
        )

        self.tree.expandToDepth(1)

        self.restoreSelection()

    def restoreSelection(self):
        if self.tree.model() is None:
            return

        selected = self.document_manager.current_document.selection_manager.get_selected()

        if selected is None:
            self.tree.setCurrentIndex(QModelIndex())
            return

        index = self.findIndexForObject(selected)

        if index.isValid():
            self.tree.setCurrentIndex(index)
        else:
            print(f"Could not find index for selected object: {selected}, {index}")


    def findIndexForObject(self, obj, parent=QModelIndex()):
        if self.tree.model() is None:
            return QModelIndex()
        
        model = self.tree.model()

        for row in range(model.rowCount(parent)):
            index = model.index(row, 0, parent)

            item = index.internalPointer()

            if item.data is obj:
                return index

            child = self.findIndexForObject(obj, index)
            if child.isValid():
                return child

        return QModelIndex()

    def currentObject(self):
        """Returns the selected object from the tree."""

        index = self.tree.currentIndex()

        if not index.isValid():
            return None

        item = index.internalPointer()

        return item.data


class PropertiesDock(QDockWidget):
    dock_key = DOCK_PROPERTIES

    def __init__(
        self,
        parent,
        document_manager: DocumentManager,
    ):
        super().__init__("Properties", parent)
        self.setObjectName("propertiesDock")

        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.setMinimumWidth(220)

        self.document_manager = document_manager
        self.document_manager.selection_changed.connect(self.set_document)

        self._selection_manager_changed: Signal = None

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.setWidget(scroll)

        # Content widget inside scroll area
        self.content = QWidget()
        self.content.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )
        scroll.setWidget(self.content)

        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(6, 6, 6, 6)
        self.layout.setSpacing(8)

        self.build_table()

    def set_document(self, document: Document):
        """Switch to displaying a different document."""

        if document is None:
            self.content.setEnabled(False)
            return
        
        if self._selection_manager_changed is not None:
            self._selection_manager_changed.disconnect(self.on_selection_changed)
            self._selection_manager_changed = None

        self._selection_manager_changed = document.selection_manager.selection_changed
        
        self._selection_manager_changed.connect(
            self.on_selection_changed
        )

        self.content.setEnabled(True)

        self.build_table()

    # ---------------------------------------------------------

    def clear_layout(self):
        while self.layout.count():
            item = self.layout.takeAt(0)

            if widget := item.widget():
                widget.deleteLater()

            elif child_layout := item.layout():
                self._delete_layout(child_layout)

    def _delete_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)

            if widget := item.widget():
                widget.deleteLater()

            elif child := item.layout():
                self._delete_layout(child)

        layout.deleteLater()

    # ---------------------------------------------------------

    def build_table(self):
        self.clear_layout()
        if self.document_manager.current_document is None:
            return

        selected = self.document_manager.current_document.selection_manager.get_selected()
        if selected is None:
            return

        for section_name, props in selected.get_property_list().items():

            self.add_section(section_name)

            form = QFormLayout()
            form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)

            self.layout.addLayout(form)

            for prop in props:
                self.add_property(form, prop)

        if isinstance(self.document_manager.current_document, EditorDocument) and self.document_manager.current_document.scene_state.is_editable:
            self.layout.addWidget(QPushButton("Delete", clicked=lambda: self.document_manager.current_document.scene_state.delete_element(selected)))

        self.layout.addStretch()

    # ---------------------------------------------------------

    def add_section(self, title):
        label = QLabel(title)

        font = label.font()
        font.setBold(True)
        label.setFont(font)

        self.layout.addWidget(label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)

        self.layout.addWidget(line)

    # ---------------------------------------------------------

    def add_property(self, form, prop: Property):
        editor = prop.create_editor(self.content)

        try:
            prop.editor.disconnect()
        except Exception:
            pass

        prop.connect_changed(
            partial(self.on_property_changed, prop)
        )

        scene_state = self.document_manager.current_document.scene_state
        
        prop.refresh(scene_state)
        
        editor.setEnabled(prop.editable and scene_state.is_editable)

        form.addRow(prop.name, editor)

    # ---------------------------------------------------------

    def on_property_changed(self, prop: Property):
        if hasattr(self.document_manager.current_document, 'scene_state'):
            prop.commit(self.document_manager.current_document.scene_state)
        else:
            prop.commit(None)

    # ---------------------------------------------------------

    def on_selection_changed(self):
        self.build_table()