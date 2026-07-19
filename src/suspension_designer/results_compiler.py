from __future__ import annotations

from dataclasses import dataclass, field
from math import floor
from typing import Any, Sequence
from uuid import UUID

import numpy as np

from suspension_designer.model_variables import DisplacementVariable, DistanceVariable
from suspension_designer.motion import MotionData, MotionVariableData
from suspension_designer.scene import SceneState
from suspension_designer.solver import SolverResult, SolverState, solve_system


@dataclass
class ResultsCompilationStep:
    """One simulated step of a compiled motion profile."""

    time: float
    solver_result: SolverResult
    solved_scene_state: SceneState
    variable_values: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResultsCompilation:
    """Tabular output for a compiled motion profile."""

    times: list[float]
    variable_columns: list[str]
    rows: list[dict[str, Any]]
    precision_digits: int
    steps: list[ResultsCompilationStep] = field(default_factory=list)
    

    def to_dict(self) -> dict:
        return {
            "times": self.times,
            "variable_columns": self.variable_columns,
            "rows": self.rows,
            "steps": [
                {
                    "time": step.time,
                    "solver_result": step.solver_result.to_dict(),
                    "variable_values": step.variable_values,
                }
                for step in self.steps
            ],
        }

    def to_table(self) -> tuple[list[str], list[list[str]]]:
        base_header = ["time", "solver_error", "iterations", "did_converge"]
        headers = base_header + self.variable_columns

        table_rows = []
        for row in self.rows:
            values = [str(row.get(header)) for header in headers[:len(base_header)]]
            values.extend([f'{row.get(header):.{self.precision_digits}f}' for header in headers[len(base_header):]])

            table_rows.append(values)

        return headers, table_rows


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

    def compile(self) -> ResultsCompilation:
        """Run the solver at each time step and collect values for all model variables."""

        motion_profile = MotionData.from_dict(self.motion_profile.to_dict())
        motion_profile.sync_from_scene_state(self.scene_state)

        times = self.get_times()
        variable_columns = self._build_variable_columns()

        rows: list[dict[str, Any]] = []
        steps: list[ResultsCompilationStep] = []

        total_steps = len(times)
        current_step = 0

        for time_value in times:
            current_step += 1

            solver_result = self._solve_at_time(motion_profile.variables, float(time_value))
            solved_scene_state = build_solved_scene_state(self.scene_state, solver_result)
            variable_values = self._evaluate_model_variables(solver_result)

            rows.append({
                "time": float(time_value),
                "solver_error": float(solver_result.error),
                "iterations": int(solver_result.iterations),
                "did_converge": bool(solver_result.did_converge),
                **variable_values,
            })

            steps.append(
                ResultsCompilationStep(
                    time=float(time_value),
                    solver_result=solver_result,
                    solved_scene_state=solved_scene_state,
                    variable_values=variable_values,
                )
            )

            print(f"Completed {current_step}/{total_steps}")



        return ResultsCompilation(
            times=[float(t) for t in times],
            variable_columns=variable_columns,
            rows=rows,
            steps=steps,
            precision_digits=solver_result.precision_digits
        )

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

def build_solved_scene_state(scene_state: SceneState, result: SolverResult) -> SceneState:
    """Generates a new SceneState with solved node positions applied."""

    solved_scene = SceneState.from_dict(scene_state.to_dict())
    solved_scene.is_editable = False

    for node in solved_scene.nodes:
        node.locked_plane = None

    positions = get_solved_node_positions(result)

    for i, position in enumerate(positions):
        if 0 <= i < len(solved_scene.nodes):
            solved_scene.nodes[i].world_position = position

    return solved_scene
