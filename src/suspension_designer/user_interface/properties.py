from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from time import perf_counter
from typing import Any, Callable, List, Literal, Optional, Union

from PySide6.QtCore import (QObject, Qt, Signal)
from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget


from typing import TYPE_CHECKING

from suspension_designer.editor.commands import Command, CommandFactory, CommandManager, NonLocalCommand, NonLocalModifyElementCommand


# Prevent circular imports during runtime type checking
if TYPE_CHECKING:
    from suspension_designer.elements.core import EditorElement
    from suspension_designer.user_interface.document import Document, EditorDocument

class Property:
    def __init__(
        self,
        name: str,
        *,
        prop_editor: PropertyEditorFactory,
        get: Callable[['Document'], Any],
        set: CommandFactory = None,
    ):
        assert isinstance(name, str), "name must be a string"
        assert isinstance(prop_editor, PropertyEditorFactory), "prop_editor must be an instance of PropertyEditorFactory"
        assert isinstance(get, Callable), "get must be a callable"
        assert isinstance(set, (CommandFactory, type(None))), "set must be a CommandFactory or None"

        self.name = name

        self._getter = get
        self._command_factory = set

        self.prop_editor = prop_editor

        self.editor: QWidget = None

    @property
    def editable(self):
        return self._command_factory is not None

    def create_editor(self, parent):
        if self.editor is None:
            self.editor = self.prop_editor.create_editor(parent)
        return self.editor

    def refresh(self, document):
        """Refresh the editor widget with the current value from the document."""
        value = self._getter(document)
        self.prop_editor.set_value(self, value, document)

    def commit(self, document):
        """Commit the current value from the editor widget to the document."""
        if self._command_factory is None:
            return

        value = self.prop_editor.get_value(self, document)
        print("Committing property", self.name, "with value", value)
        command = self._command_factory.create(value=value)
        CommandManager.current.execute_command(command)

    def connect_changed(self, callback):
        self.prop_editor.connect_changed(self, callback)


class PropertyEditorFactory(ABC):

    @abstractmethod
    def create_editor(self, parent: QWidget):
        ...

    @abstractmethod
    def set_value(self, prop: Property, value: Any, document: Document):
        ...

    @abstractmethod
    def get_value(self, prop: Property, document: Document):
        ...

    @abstractmethod
    def connect_changed(self, prop: Property, callback):
        ...


class DropdownPropertyEditorFactory(PropertyEditorFactory):
    
    def __init__(self, options_callback: Callable[[Document], dict[str, Any]], default_index: int = 0, default_value: Any = None, tooltips: List[str] = None):
        self.options_callback = options_callback
        self.default_index = default_index
        self.default_value = default_value
        self.tooltips = tooltips

    def create_editor(self, parent):
        return QComboBox(parent)

    def set_value(self, prop, value, document: Document):
        editor = prop.editor
        if editor is None:
            return

        editor.blockSignals(True)
        
        options = self.options_callback(document)
        keys = list(options.keys())

        # rebuild item options for the combo box
        editor.clear()
        for i in range(len(keys)):
            editor.addItem(keys[i])
            if self.tooltips and i < len(self.tooltips):
                editor.setItemData(i, self.tooltips[i], role=Qt.ToolTipRole)

        # select the correct option from the combo box
        values = list(options.values())
        if value in values:
            index = values.index(value)
            editor.setCurrentIndex(index)
        else:
            if self.default_value is not None and self.default_value in options.values():
                index = values.index(self.default_value)
                editor.setCurrentIndex(index) 
            else:
                editor.setCurrentIndex(self.default_index)  # No selection
        editor.blockSignals(False)

    def get_value(self, prop, document: Document):
        editor = prop.editor
        if editor is None:
            return None

        v = self.options_callback(document).get(editor.currentText(), None)
        return v

    def connect_changed(self, prop, callback):
        editor = prop.editor
        editor.currentIndexChanged.connect(lambda _: callback())

class StringPropertyEditorFactory(PropertyEditorFactory):

    def create_editor(self, parent):
        return QLineEdit(parent)

    def set_value(self, prop, value, document: Document):
        editor = prop.editor
        if editor is None:
            return

        editor.blockSignals(True)
        editor.setText("" if value is None else str(value))
        editor.blockSignals(False)

    def get_value(self, prop, document: Document):
        editor = prop.editor
        if editor is None:
            return ""

        return editor.text()

    def connect_changed(self, prop, callback):
        editor = prop.editor
        editor.editingFinished.connect(callback)


class ButtonPropertyEditorFactory(PropertyEditorFactory):

    def __init__(self, *, checked_text="Shown", unchecked_text="Hidden"):
        self.checked_text = checked_text
        self.unchecked_text = unchecked_text

    def create_editor(self, parent):
        editor = QPushButton(parent)
        editor.setCheckable(True)
        return editor

    def set_value(self, prop, value, document: Document):
        editor = prop.editor
        if editor is None:
            return

        editor.blockSignals(True)
        editor.setChecked(bool(value))
        editor.setText(self.checked_text if value else self.unchecked_text)
        editor.blockSignals(False)

    def get_value(self, prop, document: Document):
        return prop.editor.isChecked()

    def connect_changed(self, prop, callback):
        editor = prop.editor
        def on_toggled(checked):
            editor.setText(self.checked_text if checked else self.unchecked_text)
            callback()

        editor.toggled.connect(on_toggled)


class NumberPropertyEditorFactory(PropertyEditorFactory):

    def __init__(self, *, decimals=2, step=1.0, suffix="", multiplier=1.0):
        self.decimals = decimals
        self.step = step
        self.suffix = suffix
        self.multiplier = multiplier

    def create_editor(self, parent):
        # We decide float vs int lazily based on value later,
        # but default to float editor (more flexible)
        editor = QDoubleSpinBox(parent)
        editor.setDecimals(self.decimals)
        editor.setSingleStep(self.step)
        editor.setRange(-1e12, 1e12)
        editor.setSuffix(self.suffix)
        editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        editor.setFixedWidth(100)
        return editor

    def set_value(self, prop, value, document: Document):
        editor = prop.editor
        if editor is None:
            return

        editor.blockSignals(True)

        try:
            if isinstance(editor, QSpinBox):
                editor.setValue(int(value))
            else:
                editor.setValue(float(value) / self.multiplier)
        except:
            editor.setValue(0)

        editor.blockSignals(False)

    def get_value(self, prop, document: Document):
        editor = prop.editor
        if editor is None:
            return 0

        return editor.value() * self.multiplier

    def connect_changed(self, prop, callback):
        editor = prop.editor

        def handler(*args):
            callback()

        editor.editingFinished.connect(handler)

class GroupEditor(QWidget):
    valueChanged = Signal()

    def __init__(self, parent=None):
        t0 = perf_counter()
        super().__init__(parent)

        self._all_nodes = []
        self._selected_nodes = []

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_add_node)
        self.layout.addWidget(self.combo)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addLayout(self.rows_layout)

        t1 = perf_counter()
        # print(f"GroupEditor.__init__ took {t1-t0:.6f} seconds")

    def set_nodes(self, all_nodes, selected_nodes):
        self._all_nodes = list(all_nodes)
        self._selected_nodes = list(selected_nodes)

        self._rebuild()

    def selected_nodes(self):
        return list(self._selected_nodes)

    def _rebuild(self):
        t0 = perf_counter()
        selected_ids = {node.id for node in self._selected_nodes}

        # Remove old rows
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        # Build dropdown
        self.combo.blockSignals(True)
        self.combo.clear()

        self.combo.addItem("Add node...", None)

        for node in self._all_nodes:
            if node.id not in selected_ids:
                self.combo.addItem(node.name, node)

        self.combo.setCurrentIndex(0)
        self.combo.blockSignals(False)

        # Build rows
        for node in self._selected_nodes:
            row = QWidget()

            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)

            layout.addWidget(QLabel(node.name))
            layout.addStretch()

            remove = QPushButton("✕")
            remove.setMaximumWidth(24)

            remove.clicked.connect(
                lambda checked=False, n=node: self._remove_node(n)
            )

            layout.addWidget(remove)

            self.rows_layout.addWidget(row)

        self.rows_layout.addStretch()

        t1 = perf_counter()
        # print(f"GroupEditor._rebuild took {t1-t0:.6f} seconds")

    def _on_add_node(self, index):
        node = self.combo.itemData(index)

        if node is None:
            return

        self._selected_nodes.append(node)

        self._rebuild()

        self.valueChanged.emit()

    def _remove_node(self, node):
        self._selected_nodes.remove(node)

        self._rebuild()

        self.valueChanged.emit()

class GroupPropertyEditorFactory(PropertyEditorFactory):

    def __init__(self, all_elements_callback: Callable[[Document], list['EditorElement']]):
        self.all_elements_callback = all_elements_callback

    def create_editor(self, parent):
        return GroupEditor(parent)

    def set_value(self, prop, value, document: Document):
        prop.editor.set_nodes(
            self.all_elements_callback(document),
            value,
        )

    def get_value(self, prop, document: Document):
        return prop.editor.selected_nodes()

    def connect_changed(self, prop, callback):
        prop.editor.valueChanged.connect(callback)


class ReferenceGeometryEditor(QWidget):
    valueChanged = Signal()

    def __init__(self, parent=None):
        t0 = perf_counter()
        super().__init__(parent)

        self._all_nodes = []
        self._selected_nodes = []
        self._available_types = []
        self._available_types_callback = None
        self._document = None
        self._literal_factory = None

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.type_combo = QComboBox()
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self.layout.addWidget(self.type_combo)

        self.reference_combo = QComboBox()
        self.reference_combo.currentIndexChanged.connect(self._on_add_reference)
        self.reference_combo.setEnabled(False)
        self.layout.addWidget(self.reference_combo)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addLayout(self.rows_layout)

        t1 = perf_counter()
        # print(f"GroupEditor.__init__ took {t1-t0:.6f} seconds")

    def set_nodes(
        self,
        all_nodes,
        selected_nodes,
        available_types=None,
        available_types_callback=None,
        document=None,
        literal_factory=None,
    ):
        self._all_nodes = list(all_nodes)
        self._selected_nodes = list(selected_nodes)
        self._available_types_callback = available_types_callback
        self._document = document
        self._literal_factory = literal_factory
        if available_types is None:
            available_types = (
                self._node_geometry_type(node) for node in self._all_nodes
            )
        self._available_types = []
        for geometry_type in available_types:
            if geometry_type is not None and geometry_type not in self._available_types:
                self._available_types.append(geometry_type)

        self._rebuild()

    @staticmethod
    def _node_geometry_type(node):
        geometry = getattr(node, "_geometry", None)
        return geometry.__class__ if geometry is not None else None

    def selected_nodes(self):
        return list(self._selected_nodes)

    def _rebuild(self):
        t0 = perf_counter()
        selected_ids = {node.id for node in self._selected_nodes}
        available_types = self._available_types
        if self._available_types_callback is not None:
            available_types = self._available_types_callback(
                self._document,
                self._selected_nodes,
            )

        # Remove old rows
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)

            if item.widget():
                item.widget().deleteLater()

        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem("Add reference...", None)
        selected_types = {
            self._node_geometry_type(node) for node in self._selected_nodes
        }
        has_reference_options = False
        for geometry_type in available_types:
            if (
                geometry_type not in selected_types
                or any(
                    self._node_geometry_type(node) is geometry_type
                    and node.id not in selected_ids
                    for node in self._all_nodes
                )
            ):
                self.type_combo.addItem(
                    f"Existing {self._geometry_display_name(geometry_type)}",
                    (geometry_type, False),
                )
                has_reference_options = has_reference_options or any(
                    self._node_geometry_type(node) is geometry_type
                    and node.id not in selected_ids
                    for node in self._all_nodes
                )
            if self._literal_factory is not None:
                self.type_combo.addItem(
                    f"Raw {self._geometry_display_name(geometry_type)}",
                    (geometry_type, True),
                )
        self.type_combo.setCurrentIndex(0)
        self.type_combo.setEnabled(
            bool(available_types) and (
                has_reference_options
                or self._literal_factory is not None
            )
        )
        self.type_combo.blockSignals(False)

        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        self.reference_combo.addItem("Select reference...", None)
        self.reference_combo.setEnabled(False)
        self.reference_combo.blockSignals(False)

        # Build rows
        for node in self._selected_nodes:
            row = QWidget()

            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            header = QWidget(row)
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)

            geometry_type = self._node_geometry_type(node)
            geometry_name = self._geometry_display_name(geometry_type)
            if getattr(node, "is_literal_geometry", False):
                label = geometry_name
            else:
                label = f"{node.name} [{geometry_name}]" if geometry_type else node.name
            header_layout.addWidget(QLabel(label))
            header_layout.addStretch()

            remove = QPushButton("✕")
            remove.setMaximumWidth(24)

            remove.clicked.connect(
                lambda checked=False, n=node: self._remove_node(n)
            )

            header_layout.addWidget(remove)
            row_layout.addWidget(header)

            if (
                self._literal_factory is not None
                and getattr(node, "is_literal_geometry", False)
            ):
                transform_widget = QWidget(row)
                transform_layout = QVBoxLayout(transform_widget)
                transform_layout.setContentsMargins(20, 0, 0, 0)
                for literal_prop in node.get_transform_property_list():
                    literal_editor = literal_prop.create_editor(transform_widget)
                    literal_prop.refresh(self._document)
                    literal_prop.connect_changed(
                        lambda prop=literal_prop: prop.commit(self._document)
                    )
                    property_row = QWidget(transform_widget)
                    property_layout = QHBoxLayout(property_row)
                    property_layout.setContentsMargins(0, 0, 0, 0                    )
                    property_layout.addWidget(QLabel(literal_prop.name))
                    property_layout.addWidget(literal_editor)
                    transform_layout.addWidget(property_row)
                row_layout.addWidget(transform_widget)

            self.rows_layout.addWidget(row)

        self.rows_layout.addStretch()

        t1 = perf_counter()
        # print(f"GroupEditor._rebuild took {t1-t0:.6f} seconds")

    @staticmethod
    def _geometry_display_name(geometry_type):
        if geometry_type is None:
            return ""
        name = geometry_type.__name__
        return name[:-8] if name.endswith("Geometry") else name

    def _on_type_changed(self, index):
        selection = self.type_combo.itemData(index)
        self.reference_combo.blockSignals(True)
        self.reference_combo.clear()
        self.reference_combo.addItem("Select reference...", None)

        if selection is None:
            self.reference_combo.setEnabled(False)
            self.reference_combo.blockSignals(False)
            return

        geometry_type, is_literal = selection
        if is_literal:
            literal = self._literal_factory(geometry_type)
            self._selected_nodes.append(literal)
            self._rebuild()
            self.valueChanged.emit()
            return

        selected_ids = {node.id for node in self._selected_nodes}
        for node in self._all_nodes:
            if (
                self._node_geometry_type(node) is geometry_type
                and node.id not in selected_ids
            ):
                self.reference_combo.addItem(node.name, node)
        self.reference_combo.setEnabled(self.reference_combo.count() > 1)
        self.reference_combo.blockSignals(False)

    def _on_add_reference(self, index):
        node = self.reference_combo.itemData(index)
        if node is None:
            return

        self._selected_nodes.append(node)
        self._rebuild()
        self.valueChanged.emit()

    def _remove_node(self, node):
        self._selected_nodes.remove(node)

        self._rebuild()

        self.valueChanged.emit()

class ReferenceGeometryPropertyEditorFactory(PropertyEditorFactory, CommandFactory):

    def __init__(
        self,
        all_elements_callback: Callable[[EditorDocument], list['EditorElement']],
        available_types_callback: Callable[[EditorDocument, list['EditorElement']], list[type]],
        element_id,
        literal_factory: Callable[[type], 'EditorElement'],
    ):
        self.all_elements_callback = all_elements_callback
        self.available_types_callback = available_types_callback
        self.element_id = element_id
        self.literal_factory = literal_factory

    def create_editor(self, parent):
        return ReferenceGeometryEditor(parent)

    def set_value(self, prop: Property, value, document: EditorDocument):
        selected = [] if value is None else list(value)
        prop.editor.set_nodes(
            self.all_elements_callback(document),
            selected,
            available_types_callback=self.available_types_callback,
            document=document,
            literal_factory=self.literal_factory,
        )

    def get_value(self, prop, document: EditorDocument):
        return prop.editor.selected_nodes()

    def create(self, value):
        return ReferenceGeometryConstraintCommand(
            self.element_id,
            value,
        )

    def connect_changed(self, prop, callback):
        prop.editor.valueChanged.connect(callback)


class ReferenceGeometryConstraintCommand(NonLocalCommand):
    def __init__(self, element_id, value):
        self.element_id = element_id
        self.value = value

    def execute(self, document):
        super().execute(document)
        from suspension_designer.elements.geometry_builder import GeometryBuilder

        element = document.scene_state.get_element_by_id(self.element_id)
        if element is None:
            raise ValueError(f"Reference geometry element not found: {self.element_id}")

        element._constraints = list(self.value)
        element._update_constraint_set()
        GeometryBuilder(document.scene_state.reference_geometry).rebuild_all_geometry()
        element.did_change.emit()