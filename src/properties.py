from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from time import perf_counter
from typing import Any, Callable, List, Literal, Optional, Union

from PySide6.QtCore import (QObject, Qt, Signal)
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget


from typing import TYPE_CHECKING

# Prevent circular imports during runtime type checking
if TYPE_CHECKING:
    from src.structures import SceneState, EditorNode


class PropertyType(ABC):

    @abstractmethod
    def create_editor(self, parent):
        ...

    @abstractmethod
    def set_value(self, prop, value):
        ...

    @abstractmethod
    def get_value(self, prop):
        ...

    @abstractmethod
    def connect_changed(self, prop, callback):
        ...


class DropdownPropertyType(PropertyType):
    
    def __init__(self, options_callback: Callable[['SceneState'], dict[str, Any]], default_index: int = 0, default_value: Any = None, tooltips: List[str] = None):
        self.options_callback = options_callback
        self.default_index = default_index
        self.default_value = default_value
        self.tooltips = tooltips

    def create_editor(self, parent):
        return QComboBox(parent)

    def set_value(self, prop, value, scene_state: 'SceneState'):
        editor = prop.editor
        if editor is None:
            return

        editor.blockSignals(True)
        
        options = self.options_callback(scene_state)
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

    def get_value(self, prop, scene_state: 'SceneState'):
        editor = prop.editor
        if editor is None:
            return None

        v = self.options_callback(scene_state).get(editor.currentText(), None)
        return v

    def connect_changed(self, prop, callback):
        editor = prop.editor
        editor.currentIndexChanged.connect(lambda _: callback())

class StringPropertyType(PropertyType):

    def create_editor(self, parent):
        return QLineEdit(parent)

    def set_value(self, prop, value, scene_state: 'SceneState'):
        editor = prop.editor
        if editor is None:
            return

        editor.blockSignals(True)
        editor.setText("" if value is None else str(value))
        editor.blockSignals(False)

    def get_value(self, prop, scene_state: 'SceneState'):
        editor = prop.editor
        if editor is None:
            return ""

        return editor.text()

    def connect_changed(self, prop, callback):
        editor = prop.editor
        editor.editingFinished.connect(callback)


class NumberPropertyType(PropertyType):

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
        return editor

    def set_value(self, prop, value, scene_state: 'SceneState'):
        editor = prop.editor
        if editor is None:
            return

        editor.blockSignals(True)

        if isinstance(editor, QSpinBox):
            editor.setValue(int(value))
        else:
            editor.setValue(float(value) / self.multiplier)

        editor.blockSignals(False)

    def get_value(self, prop, scene_state: 'SceneState'):
        editor = prop.editor
        if editor is None:
            return 0

        return editor.value() * self.multiplier

    def connect_changed(self, prop, callback):
        editor = prop.editor

        def handler(*args):
            callback()

        editor.lineEdit().editingFinished.connect(handler)
        
class Property:
    def __init__(
        self,
        name,
        *,
        type,
        get,
        set = None,
        
    ):
        # self.id = id
        self.name = name

        self._getter = get
        self._setter = set

        self.property_type = type

        self.editor = None

    @property
    def editable(self):
        return self._setter is not None

    def create_editor(self, parent):
        if self.editor is None:
            self.editor = self.property_type.create_editor(parent)
        return self.editor

    def refresh(self, scene_state):
        value = self._getter(scene_state)
        self.property_type.set_value(self, value, scene_state)

    def commit(self, scene_state):
        if self._setter is None:
            return

        value = self.property_type.get_value(self, scene_state)
        self._setter(value, scene_state)

    def connect_changed(self, callback):
        self.property_type.connect_changed(self, callback)

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

class GroupPropertyType(PropertyType):

    def __init__(self, all_nodes_callback: Callable[['SceneState'], list['EditorNode']]):
        self.all_nodes_callback = all_nodes_callback

    def create_editor(self, parent):
        return GroupEditor(parent)

    def set_value(self, prop, value, scene_state: 'SceneState'):
        prop.editor.set_nodes(
            self.all_nodes_callback(scene_state),
            value,
        )

    def get_value(self, prop, scene_state: 'SceneState'):
        return prop.editor.selected_nodes()

    def connect_changed(self, prop, callback):
        prop.editor.valueChanged.connect(callback)