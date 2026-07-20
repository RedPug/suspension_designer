from __future__ import annotations

from concurrent.futures import thread
from dataclasses import dataclass, field
from math import floor
import pickle
import threading
import threading
from time import perf_counter, time, sleep
from typing import Any, Callable, Sequence
from uuid import UUID

import numpy as np

from PySide6.QtCore import QObject, QTimer, Signal, Signal

from suspension_designer.model_variables import DisplacementVariable, DistanceVariable
from suspension_designer.motion import MotionData, MotionVariableData
from suspension_designer.scene import SceneState
from suspension_designer.solver import SolverResult, SolverState, solve_system


@dataclass
class ResultsCompilationStep:
    """One simulated step of a compiled motion profile."""

    time: float
    error: float
    iterations: int
    epsilon: float
    did_converge: bool
    node_positions: list[tuple[float, float, float]]
    variable_values: list


@dataclass
class ResultsCompilation:
    """Tabular output for a compiled motion profile."""
    base_scene: SceneState
    steps: list[ResultsCompilationStep]
    variable_names: list[str]
    precision_digits: int
    

    def to_dict(self) -> dict:
        return {
            "precision_digits": self.precision_digits,
            "variable_names": self.variable_names,
            "base_scene": self.base_scene.to_dict(),
            "steps": [
                {
                    "time": step.time,
                    "error": step.error,
                    "iterations": step.iterations,
                    "epsilon": step.epsilon,
                    "did_converge": step.did_converge,
                    "node_positions": step.node_positions,
                    "variable_values": step.variable_values,
                }
                for step in self.steps
            ],
        }
    
    @staticmethod
    def from_dict(data: dict) -> ResultsCompilation:
        return ResultsCompilation(
            precision_digits=data.get("precision_digits"),
            base_scene=SceneState.from_dict(data["base_scene"]),
            variable_names=data.get("variable_names"),
            steps=[
                ResultsCompilationStep(
                    time=step["time"],
                    error=step["error"],
                    iterations=step["iterations"],
                    epsilon=step["epsilon"],
                    did_converge=step["did_converge"],
                    node_positions=step["node_positions"],
                    variable_values=step["variable_values"],
                )
                for step in data["steps"]
            ],
        )


    def to_table(self) -> tuple[list[str], list[list[str]]]:
        base_header = ["time", "solver_error", "iterations", "did_converge"]
        headers = base_header + self.variable_names

        table_rows = []
        for step in self.steps:
            values = [
                step.time,
                step.error,
                step.iterations,
                step.did_converge,
            ]
            values.extend([f'{step.variable_values[i]:.{self.precision_digits}f}' for i in range(len(self.variable_names))])

            table_rows.append(values)

        return headers, table_rows


# 1. Create a lightweight signal bridge
class ThreadBridge(QObject):
    # This signal carries the final object back to the main thread
    compilation_ready = Signal(ResultsCompilation)

class ResultsCompiler:
    """Simulates a motion profile and compiles model-variable values into a table."""

    def __init__(
        self,
        scene_state: SceneState,
        motion_profile: MotionData | Sequence[MotionVariableData],
        *,
        start_time: float = 0.0,
        end_time: float = 1.0,
        step: float = 0.1,
        solver_kwargs: dict[str, Any] | None = None,
    ):
        self.scene_state = scene_state
        if isinstance(motion_profile, MotionData):
            self.motion_profile = motion_profile
        else:
            self.motion_profile = MotionData(list(motion_profile))

        self.start_time = float(start_time)
        self.end_time = float(end_time)
        self.step = float(step)
        self.solver_kwargs = dict(solver_kwargs or {})

    def get_times(self) -> np.ndarray:
        """Returns the time samples used for compilation."""

        return np.round(np.arange(self.start_time, self.end_time + self.step * 0.5, self.step), 10)

    def _compile(self) -> ResultsCompilation:
        """Run the solver at each time step and collect values for all model variables."""

        motion_profile = MotionData.from_dict(self.motion_profile.to_dict())
        motion_profile.sync_from_scene_state(self.scene_state)

        times = self.get_times()
        variable_columns = self._build_variable_columns()

        steps: list[ResultsCompilationStep] = []

        total_steps = len(times)
        current_step = 0

        precision_digits = 16

        progress_index = 0
        PROGRESS_TEXT = "1....2....3....4....5....6....7....8....9....!"

        print("Solving: ", end="", flush=True)

        solving_time_sum = 0.0

        t0 = perf_counter()
        for time_value in times:
            current_step += 1

            solver_result = self._solve_at_time(motion_profile.variables, float(time_value))
            node_positions = get_solved_node_positions(solver_result).tolist()
            variable_value_dict = self._evaluate_model_variables(solver_result)
            variable_values = [variable_value_dict[col] for col in variable_columns]

            solving_time_sum += solver_result.time

            steps.append(
                ResultsCompilationStep(
                    time=time_value,
                    error=solver_result.error,
                    iterations=solver_result.iterations,
                    epsilon=solver_result.epsilon,
                    did_converge=solver_result.did_converge,
                    node_positions=node_positions,
                    variable_values=variable_values,
                )
            )

            precision_digits = min(precision_digits, solver_result.precision_digits)

            # print(f"Completed {current_step}/{total_steps}")
            while progress_index <= (len(PROGRESS_TEXT)-1)*current_step/total_steps:
                print(PROGRESS_TEXT[progress_index], end="", flush=True)
                progress_index += 1

        t1 = perf_counter()
        print("\nDone compiling results in {:.3f} seconds ({:.3f} solving)".format(t1 - t0, solving_time_sum))

        return ResultsCompilation(
            base_scene=self.scene_state,
            variable_names=variable_columns,
            steps=steps,
            precision_digits=precision_digits
        )
    
    def compile(self, completed: Callable[[ResultsCompilation], None]):
        bridge = ThreadBridge()
        bridge.compilation_ready.connect(completed)

        def func():
            result = self._compile()
            bridge.compilation_ready.emit(result)

        thread = threading.Thread(target=func)

        #store bridge so it isn't garbage collected
        thread.bridge = bridge

        thread.start()
        return thread

    def _build_variable_columns(self) -> list[str]:
        columns: list[str] = []
        seen: dict[str, int] = {}

        for variable in self.scene_state.model_variables:
            base_name = variable.name or "Unnamed Variable"
            count = seen.get(base_name, 0)
            seen[base_name] = count + 1

            if count == 0:
                columns.append(base_name)
            else:
                columns.append(f"{base_name} ({str(variable.id)[:8]})")

        return columns

    def _evaluate_model_variables(self, result: SolverResult) -> dict[str, Any]:
        """Evaluate all model variables against the solved scene state."""

        evaluated_values: dict[str, Any] = {}
        columns = self._build_variable_columns()

        position_id_map = get_position_id_map(result, self.scene_state)

        for column_name, model_variable in zip(columns, self.scene_state.model_variables):
            try:
                value = float(model_variable.variable.evaluate(position_id_map))
                evaluated_values[column_name] = value
            except Exception:
                evaluated_values[column_name] = None

        return evaluated_values

    def _solve_at_time(self, motion_variables: list[MotionVariableData], time_value: float) -> SolverResult:
        """Build a solver state for the requested time and solve it without console output."""

        nodes = np.array([node.world_position for node in self.scene_state.nodes])
        groups = [[self.scene_state.nodes.index(node) for node in group.nodes] for group in self.scene_state.groups]

        displacements: list[tuple[int, np.ndarray]] = []
        links: list[tuple[int, int, float]] = []
        motion_variables_by_id = {variable.id: variable for variable in motion_variables}

        for element in self.scene_state.model_variables:
            variable = element.variable

            motion_variable = motion_variables_by_id.get(str(variable.id))
            if motion_variable is None or not motion_variable.is_input:
                continue

            sampled_value = motion_variable.sample_at(time_value)
            if sampled_value is None:
                continue

            if isinstance(variable, DisplacementVariable):
                node = variable.node
                if node is not None:
                    displacements.append((self.scene_state.nodes.index(node), variable.get_displacement(sampled_value)))
            elif isinstance(variable, DistanceVariable):
                node_a = variable.node_a
                node_b = variable.node_b
                if node_a is not None and node_b is not None:
                    links.append((self.scene_state.nodes.index(node_a), self.scene_state.nodes.index(node_b), sampled_value))

        solver_state = SolverState.from_connections(
            nodes=nodes,
            node_groups=groups,
            displacements=displacements,
            extra_links=links,
        )

        return solve_system(solver_state, **self.solver_kwargs)


def get_solved_node_positions(result: SolverResult) -> np.ndarray:
    """Creates a numpy array containing the node positions, ordered by their original index."""

    positions_by_index: dict[int, list[np.ndarray]] = {}
    for group in result.system_state.groups:
        for node in group.nodes:
            positions_by_index.setdefault(node.index, []).append(np.array(node.get_world_position(), dtype=float))

    positions = [np.mean(positions, axis=0) for _, positions in sorted(positions_by_index.items())]

    return np.array(positions)

def get_position_id_map(result: SolverResult, scene_state: SceneState) -> dict[UUID, np.ndarray]:
    """Creates a map of node indices to their solved positions."""

    position_id_map: dict[UUID, np.ndarray] = {}
    positions = get_solved_node_positions(result)

    for i in range(len(positions)):
        position_id_map[scene_state.nodes[i].id] = positions[i]

    return position_id_map
