from uuid import uuid4
import json
import os
import csv

import numpy as np

from PySide6.QtCore import (
    QAbstractItemModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QClipboard, QKeySequence

from suspension_designer.rendering import Viewport3D
from suspension_designer.results_compiler import ResultsCompilation
from suspension_designer.selection import SelectionManager

class CopyableTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

    def keyPressEvent(self, event):
        # Override Ctrl+C for copying table values to clipboard
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection_to_clipboard()
        else:
            super().keyPressEvent(event)

    def copy_selection_to_clipboard(self):
        selection = self.selectedRanges()
        if not selection:
            return

        text_parts = []
        
        for range_obj in selection:
            # 1. Extract and append headers for the selected columns
            header_values = []
            for c in range(range_obj.leftColumn(), range_obj.rightColumn() + 1):
                header_item = self.horizontalHeaderItem(c)
                # Fallback to column index number if no explicit header text is set
                header_text = header_item.text() if header_item else f"Column {c+1}"
                header_values.append(header_text)
            
            text_parts.append("\t".join(header_values))

            # 2. Extract and append the corresponding row data
            for r in range(range_obj.topRow(), range_obj.bottomRow() + 1):
                row_values = []
                for c in range(range_obj.leftColumn(), range_obj.rightColumn() + 1):
                    item = self.item(r, c)
                    row_values.append(item.text() if (item and item.text()) else "")
                
                text_parts.append("\t".join(row_values))

        # Join everything with newlines and send to system clipboard
        text_data = "\n".join(text_parts) + "\n"
        QApplication.clipboard().setText(text_data)

class ResultViewer:
    def __init__(self, compilation: ResultsCompilation, selection_manager: SelectionManager):
        self.compilation = compilation
        self.selection_manager = selection_manager
        self.scene_state = self.compilation.base_scene.strip_reference() if self.compilation is not None else None
        self.scene_state.is_editable = False

        self.viewport = None
        self.table_widget = None
        self.step_slider = None
        self.step_label = None
        self.widget = None

    def _get_node_positions(self, index: int):
        steps = self.compilation.steps
        if 0 <= index < len(steps):
            return np.asarray(steps[index].node_positions)
        
        raise IndexError("Step index out of bounds")
    
    def _update_scene_to_time(self, index: int):
        node_positions = self._get_node_positions(index)
        self.scene_state.update_node_positions(node_positions)
        self.scene_state.did_change.emit()

    def _update_step_label(self, index: int | None = None):
        if self.step_label is None or self.compilation is None:
            return

        steps = self.compilation.steps
        if not steps:
            self.step_label.setText("No simulation steps available")
            return

        if index is None:
            index = self.step_slider.value() if self.step_slider is not None else 0

        step = steps[index]
        self.step_label.setText(f"Step {index + 1} / {len(steps)} | t = {step.time:.3f}")

    def _on_step_changed(self, index: int):
        if self.compilation is None or not self.compilation.steps:
            return

        self._update_scene_to_time(index)
        self._update_step_label(index)

    def get_widget(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        if self.compilation is None:
            layout.addWidget(QLabel("No results available."))
            self.widget = widget
            return self.widget

        if self.compilation is not None:
            splitter = QSplitter(Qt.Orientation.Horizontal, widget)
            splitter.setChildrenCollapsible(False)
            layout.addWidget(splitter)

            headers, table_rows = self.compilation.to_table()

            left_panel = QWidget(splitter)
            left_layout = QVBoxLayout(left_panel)
            left_layout.setContentsMargins(0, 0, 0, 0)
            left_layout.setSpacing(6)
            left_layout.addWidget(QLabel("Compilation Results"))

            table = CopyableTableWidget(left_panel)
            table.setColumnCount(len(headers))
            table.setRowCount(len(table_rows))
            table.setHorizontalHeaderLabels(headers)
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
            table.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

            for row_index, row in enumerate(table_rows):
                for column_index, value in enumerate(row):
                    table.setItem(row_index, column_index, QTableWidgetItem("" if value is None else str(value)))

            table.resizeColumnsToContents()

            self.table_widget = table
            left_layout.addWidget(table)

            right_panel = QWidget(splitter)
            right_layout = QVBoxLayout(right_panel)
            right_layout.setContentsMargins(0, 0, 0, 0)
            right_layout.setSpacing(6)

            self.step_label = QLabel("Step 1 / 1")
            right_layout.addWidget(self.step_label)

            self.step_slider = QSlider(Qt.Orientation.Horizontal, right_panel)
            self.step_slider.setSingleStep(1)
            self.step_slider.setPageStep(1)
            self.step_slider.setTracking(True)
            step_count = len(self.compilation.steps)
            if step_count > 0:
                self.step_slider.setRange(0, step_count - 1)
                self.step_slider.valueChanged.connect(self._on_step_changed)
            else:
                self.step_slider.setRange(0, 0)
                self.step_slider.setEnabled(False)
            right_layout.addWidget(self.step_slider)

            self.viewport = Viewport3D(scene_state=self.scene_state, selection_manager=self.selection_manager)
            right_layout.addWidget(self.viewport, 1)

            splitter.addWidget(left_panel)
            splitter.addWidget(right_panel)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)

            if step_count > 0:
                self._update_scene_to_time(0)
                self.step_slider.setValue(0)
                self._update_step_label(0)
        else:
            layout.addWidget(QLabel(str(self.solver_result)))

        self.widget = widget
        return self.widget