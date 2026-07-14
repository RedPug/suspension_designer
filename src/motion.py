from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
	QAbstractItemView,
	QHeaderView,
	QHBoxLayout,
	QLabel,
	QPushButton,
	QSplitter,
	QTableWidget,
	QTableWidgetItem,
	QVBoxLayout,
	QWidget,
)

from src.model_variables import ModelVariableElement
from src.scene import SceneState


@dataclass
class MotionStepData:
	step: float
	value: Optional[float] = None

	@staticmethod
	def from_dict(data: dict) -> "MotionStepData":
		step = data.get("step", 0.0)
		value = data.get("value")

		try:
			step = float(step)
		except (TypeError, ValueError):
			step = 0.0

		try:
			value = None if value in (None, "") else float(value)
		except (TypeError, ValueError):
			value = None

		return MotionStepData(step=step, value=value)

	def to_dict(self) -> dict:
		return {
			"step": self.step,
			"value": self.value,
		}


@dataclass
class MotionVariableData:
	id: str
	name: str
	is_input: bool = False
	value: Optional[float] = None
	points: list[MotionStepData] = field(default_factory=list)
	model_variable: Any = field(default=None, repr=False, compare=False)

	@classmethod
	def from_model_variable(cls, model_variable) -> "MotionVariableData":
		try:
			value = float(model_variable.variable.evaluate())
		except Exception:
			value = None

		return cls(
			id=str(model_variable.id),
			name=model_variable.name,
			is_input=False,
			value=value,
			model_variable=model_variable,
		)

	@staticmethod
	def from_dict(data: dict) -> "MotionVariableData":
		points_data = data.get("points", data.get("steps", []))

		return MotionVariableData(
			id=str(data.get("id", "")),
			name=data.get("name", ""),
			is_input=bool(data.get("is_input", False)),
			value=data.get("value"),
			points=[MotionStepData.from_dict(point) for point in points_data],
		)

	def to_dict(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"is_input": self.is_input,
			"value": self.value,
			"points": [point.to_dict() for point in self.points],
		}

	def sample_at(self, t: float = 0.0) -> Optional[float]:
		if self.points:
			ordered_points = sorted(self.points, key=lambda point: point.step)

			if t <= ordered_points[0].step:
				return ordered_points[0].value

			if t >= ordered_points[-1].step:
				return ordered_points[-1].value

			for left_point, right_point in zip(ordered_points, ordered_points[1:]):
				if left_point.step <= t <= right_point.step:
					if left_point.value is None or right_point.value is None:
						return None

					span = right_point.step - left_point.step
					if span == 0:
						return right_point.value

					blend = (t - left_point.step) / span
					return left_point.value + (right_point.value - left_point.value) * blend

		return self.value


class MotionData:
	def __init__(self, variables: list[MotionVariableData] | None = None):
		self.variables = list(variables or [])

	@classmethod
	def from_scene_state(cls, scene_state: SceneState) -> "MotionData":
		return cls([
			MotionVariableData.from_model_variable(variable)
			for variable in scene_state.model_variables
		])

	@staticmethod
	def from_dict(data: dict | None) -> "MotionData":
		if not data:
			return MotionData()

		variables = data.get("variables", [])
		return MotionData([
			MotionVariableData.from_dict(variable_data)
			for variable_data in variables
		])

	def to_dict(self) -> dict:
		return {
			"variables": [variable.to_dict() for variable in self.variables]
		}

	def sync_from_scene_state(self, scene_state: SceneState):
		variables_by_id = {variable.id: variable for variable in self.variables}
		synced_variables: list[MotionVariableData] = []

		for model_variable in scene_state.model_variables:
			variable_data = variables_by_id.get(str(model_variable.id))
			if variable_data is None:
				variable_data = MotionVariableData.from_model_variable(model_variable)
			else:
				try:
					variable_data.value = float(model_variable.variable.evaluate())
				except Exception:
					variable_data.value = None
				variable_data.name = model_variable.name
				variable_data.model_variable = model_variable

			variable_data.model_variable = model_variable
			synced_variables.append(variable_data)

		self.variables = synced_variables

	def get_variable_by_id(self, variable_id: str) -> MotionVariableData | None:
		for variable in self.variables:
			if variable.id == str(variable_id):
				return variable
		return None


class MotionTrendCanvas(FigureCanvas):
	def __init__(self, parent=None):
		self.figure = Figure(figsize=(5.0, 3.2), tight_layout=True)
		self.axes = self.figure.add_subplot(111)
		super().__init__(self.figure)
		self.setParent(parent)
		self.setMinimumHeight(220)

	def show_placeholder(self, message: str):
		self.axes.clear()
		self.axes.set_axis_off()
		self.axes.text(0.5, 0.5, message, ha="center", va="center", transform=self.axes.transAxes)
		self.draw_idle()

	def plot_points(self, variable_name: str, points: list[MotionStepData]):
		self.axes.clear()
		self.axes.set_axis_on()

		if not points:
			self.show_placeholder(f"No step data for {variable_name}")
			return

		ordered_points = sorted(points, key=lambda point: point.step)
		filtered_points = [point for point in ordered_points if point.value is not None]

		if not filtered_points:
			self.show_placeholder(f"No numeric values for {variable_name}")
			return

		x_values = [point.step for point in filtered_points]
		y_values = [point.value for point in filtered_points]

		self.axes.plot(x_values, y_values, marker="o", linewidth=1.8)
		self.axes.set_title(variable_name)
		self.axes.set_xlabel("Step #")
		self.axes.set_ylabel("Value")
		self.axes.grid(True, alpha=0.28)
		self.draw_idle()


class MotionTableWidget(QWidget):
	def __init__(
		self,
		motion_data: MotionData,
		scene_state: SceneState | None = None,
		selection_manager=None,
		solve_callback: Callable[[], None] | None = None,
		parent=None,
	):
		super().__init__(parent)

		self.motion_data = motion_data
		self.scene_state = scene_state
		self.selection_manager = selection_manager
		self.solve_callback = solve_callback
		self._updating_variable_table = False
		self._updating_step_table = False
		self._scene_state_connection = None

		main_layout = QVBoxLayout(self)
		main_layout.setContentsMargins(0, 0, 0, 0)
		main_layout.setSpacing(8)

		button_row = QHBoxLayout()
		button_row.setContentsMargins(12, 12, 12, 0)
		button_row.addStretch(1)

		self.solve_button = QPushButton("Solve")
		self.solve_button.clicked.connect(self._on_solve_clicked)
		button_row.addWidget(self.solve_button)
		main_layout.addLayout(button_row)

		splitter = QSplitter(Qt.Horizontal, self)
		splitter.setChildrenCollapsible(False)
		main_layout.addWidget(splitter)

		self.variable_table = QTableWidget(splitter)
		self.variable_table.setColumnCount(3)
		self.variable_table.setHorizontalHeaderLabels(["Name", "Input", "Value"])
		self.variable_table.setSelectionBehavior(QAbstractItemView.SelectRows)
		self.variable_table.setSelectionMode(QAbstractItemView.SingleSelection)
		self.variable_table.verticalHeader().setVisible(False)
		self.variable_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
		self.variable_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
		self.variable_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
		self.variable_table.itemChanged.connect(self._on_variable_item_changed)
		self.variable_table.itemSelectionChanged.connect(self._on_variable_selection_changed)

		right_panel = QWidget(splitter)
		right_layout = QVBoxLayout(right_panel)
		right_layout.setContentsMargins(12, 12, 12, 12)
		right_layout.setSpacing(10)

		self.selection_label = QLabel("Select a model variable to edit its motion trend")
		selection_font = self.selection_label.font()
		selection_font.setBold(True)
		self.selection_label.setFont(selection_font)
		right_layout.addWidget(self.selection_label)

		self.plot_canvas = MotionTrendCanvas(right_panel)
		right_layout.addWidget(self.plot_canvas)

		step_label = QLabel("Step Trend Data")
		step_font = step_label.font()
		step_font.setBold(True)
		step_label.setFont(step_font)
		right_layout.addWidget(step_label)

		self.step_table = QTableWidget(right_panel)
		self.step_table.setColumnCount(2)
		self.step_table.setHorizontalHeaderLabels(["Step #", "Value"])
		self.step_table.setSelectionBehavior(QAbstractItemView.SelectRows)
		self.step_table.setSelectionMode(QAbstractItemView.SingleSelection)
		self.step_table.verticalHeader().setVisible(False)
		self.step_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
		self.step_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
		self.step_table.itemChanged.connect(self._on_step_item_changed)
		right_layout.addWidget(self.step_table, 1)

		splitter.addWidget(self.variable_table)
		splitter.addWidget(right_panel)
		splitter.setStretchFactor(0, 1)
		splitter.setStretchFactor(1, 2)

		if self.scene_state is not None:
			self.scene_state.scene_changed.connect(self.refresh)
			self._scene_state_connection = self.scene_state.scene_changed

		if self.selection_manager is not None:
			self.selection_manager.selection_changed.connect(self._on_selection_manager_changed)

		self.refresh()

	def _on_solve_clicked(self):
		if self.solve_callback is None:
			return

		self.solve_callback()

	def set_scene_state(self, scene_state: SceneState | None):
		if self.scene_state is scene_state:
			return

		if self._scene_state_connection is not None:
			try:
				self._scene_state_connection.disconnect(self.refresh)
			except Exception:
				pass
			self._scene_state_connection = None

		self.scene_state = scene_state

		if self.scene_state is not None:
			self.scene_state.scene_changed.connect(self.refresh)
			self._scene_state_connection = self.scene_state.scene_changed

		self.refresh()

	def refresh(self):
		if self.scene_state is not None:
			self.motion_data.sync_from_scene_state(self.scene_state)

		if self.selection_manager is not None and self._selected_variable_data() is None and self.motion_data.variables:
			self.selection_manager.set_selected(self.motion_data.variables[0].model_variable)
			return

		self._refresh_variable_table()
		self._refresh_selected_variable_panel()

	def _selected_variable_data(self) -> MotionVariableData | None:
		if self.selection_manager is None:
			return None

		selected = self.selection_manager.get_selected()
		if selected is None:
			return None

		selected_id = str(getattr(selected, "id", ""))
		for variable_data in self.motion_data.variables:
			if variable_data.model_variable is selected or variable_data.id == selected_id:
				return variable_data

		return None

	def _refresh_variable_table(self):
		selected_data = self._selected_variable_data()
		selected_id = selected_data.id if selected_data is not None else None

		self._updating_variable_table = True
		self.variable_table.blockSignals(True)
		self.variable_table.setRowCount(len(self.motion_data.variables))

		for row, variable_data in enumerate(self.motion_data.variables):
			name_item = QTableWidgetItem(variable_data.name)
			name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

			input_item = QTableWidgetItem()
			input_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
			input_item.setCheckState(Qt.Checked if variable_data.is_input else Qt.Unchecked)

			value_text = "" if variable_data.value is None else str(variable_data.value)
			value_item = QTableWidgetItem(value_text)
			value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
			value_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

			self.variable_table.setItem(row, 0, name_item)
			self.variable_table.setItem(row, 1, input_item)
			self.variable_table.setItem(row, 2, value_item)

			if selected_id is not None and variable_data.id == selected_id:
				self.variable_table.selectRow(row)

		self.variable_table.blockSignals(False)
		self._updating_variable_table = False

	def _refresh_selected_variable_panel(self):
		selected_data = self._selected_variable_data()

		if selected_data is None:
			self.selection_label.setText("Select a model variable to edit its motion trend")
			self.step_table.blockSignals(True)
			self.step_table.setRowCount(0)
			self.step_table.blockSignals(False)
			self.plot_canvas.show_placeholder("No model variable selected")
			return

		self.selection_label.setText(f"Editing: {selected_data.name}")
		self._load_step_table(selected_data)
		self.plot_canvas.plot_points(selected_data.name, selected_data.points)

	def _load_step_table(self, selected_data: MotionVariableData):
		ordered_points = sorted(selected_data.points, key=lambda point: point.step)
		selected_data.points = list(ordered_points)

		self._updating_step_table = True
		self.step_table.blockSignals(True)
		self.step_table.setRowCount(len(ordered_points) + 1)

		for row, point in enumerate(ordered_points):
			step_item = QTableWidgetItem(str(point.step))
			step_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)

			value_text = "" if point.value is None else str(point.value)
			value_item = QTableWidgetItem(value_text)
			value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)

			self.step_table.setItem(row, 0, step_item)
			self.step_table.setItem(row, 1, value_item)

		self._set_blank_step_row(len(ordered_points))
		self.step_table.blockSignals(False)
		self._updating_step_table = False

	def _set_blank_step_row(self, row: int):
		self.step_table.setItem(row, 0, QTableWidgetItem(""))
		self.step_table.setItem(row, 1, QTableWidgetItem(""))

	def _on_selection_manager_changed(self):
		if self._updating_variable_table or self._updating_step_table:
			return

		self._refresh_variable_table()
		self._refresh_selected_variable_panel()

	def _on_variable_selection_changed(self):
		if self._updating_variable_table or self.selection_manager is None:
			return

		selected_indexes = self.variable_table.selectionModel().selectedRows()
		if not selected_indexes:
			self.selection_manager.set_selected(None)
			return

		row = selected_indexes[0].row()
		if 0 <= row < len(self.motion_data.variables):
			self.selection_manager.set_selected(self.motion_data.variables[row].model_variable)

	def _on_variable_item_changed(self, item: QTableWidgetItem):
		if self._updating_variable_table or item.column() != 1:
			return

		row = item.row()
		if 0 <= row < len(self.motion_data.variables):
			self.motion_data.variables[row].is_input = item.checkState() == Qt.Checked

	def _on_step_item_changed(self, item: QTableWidgetItem):
		if self._updating_step_table:
			return

		selected_data = self._selected_variable_data()
		if selected_data is None:
			return

		updated_points: list[MotionStepData] = []
		for row in range(self.step_table.rowCount()):
			step_item = self.step_table.item(row, 0)
			value_item = self.step_table.item(row, 1)

			step_text = step_item.text().strip() if step_item is not None else ""
			value_text = value_item.text().strip() if value_item is not None else ""

			if not step_text and not value_text:
				continue

			if not step_text or not value_text:
				continue

			try:
				step_value = float(step_text)
				trend_value = float(value_text)
			except ValueError:
				continue

			updated_points.append(MotionStepData(step=step_value, value=trend_value))

		selected_data.points = sorted(updated_points, key=lambda point: point.step)
		self.plot_canvas.plot_points(selected_data.name, selected_data.points)

		last_row = self.step_table.rowCount() - 1
		if last_row >= 0:
			last_step_item = self.step_table.item(last_row, 0)
			last_value_item = self.step_table.item(last_row, 1)
			last_step_text = last_step_item.text().strip() if last_step_item is not None else ""
			last_value_text = last_value_item.text().strip() if last_value_item is not None else ""

			if last_step_text and last_value_text:
				self._updating_step_table = True
				self.step_table.blockSignals(True)
				self.step_table.setRowCount(self.step_table.rowCount() + 1)
				self._set_blank_step_row(self.step_table.rowCount() - 1)
				self.step_table.blockSignals(False)
				self._updating_step_table = False
