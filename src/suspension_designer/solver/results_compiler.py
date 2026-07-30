from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, wait
import multiprocessing
from dataclasses import dataclass, field
from math import ceil, floor
import os
import pickle
import threading
import threading
from time import perf_counter, time, sleep
from typing import Any, Callable, Sequence
from uuid import UUID

import numpy as np

from PySide6.QtCore import QObject, QTimer, Signal, Signal

from suspension_designer.solver.model_variables import DisplacementVariable, DistanceVariable
from suspension_designer.solver.motion import MotionData, MotionVariableData
from suspension_designer.editor.scene import SceneState
from suspension_designer.solver.solver import solve_at_time, SolverResult


@dataclass
class ResultsCompilationStep:
    """One simulated step of a compiled motion profile."""

    time: float
    error: float
    iterations: int
    epsilon: float
    did_converge: bool
    node_positions: np.ndarray
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


def _evaluate_model_variables(result: SolverResult, scene_state: SceneState, variable_names: list[str]) -> dict[str, float]:
    """Evaluate all model variables against the solved scene state."""

    evaluated_values: dict[str, float] = {}

    position_id_map = get_position_id_map(result, scene_state)

    for column_name, model_variable in zip(variable_names, scene_state.model_variables):
        try:
            value = float(model_variable.variable.evaluate(position_id_map))
            evaluated_values[column_name] = value
        except Exception:
            evaluated_values[column_name] = None

    return evaluated_values


@dataclass
class StepCompilationData:
    times: np.ndarray
    motion_profile: MotionData
    variable_columns: list[str]
    scene_state_dict: dict
    solver_kwargs: dict

def _compile_step_task(data: StepCompilationData):
    t_start = perf_counter()
    scene_state = SceneState.from_dict(data.scene_state_dict)

    steps = []
    precision_digits = 16

    cum_solver_time = 0.0
    cum_eval_time = 0.0

    for time in data.times:
        t0 = perf_counter()
        solver_result = solve_at_time(data.motion_profile.variables, time, scene_state, **data.solver_kwargs)
        t1 = perf_counter()
        cum_solver_time += t1 - t0

        t0 = perf_counter()
        variable_value_dict = _evaluate_model_variables(solver_result, scene_state, data.variable_columns)
        variable_values = [variable_value_dict[col] for col in data.variable_columns]

        step = (
            ResultsCompilationStep(
                time=time,
                error=solver_result.error,
                iterations=solver_result.iterations,
                epsilon=solver_result.epsilon,
                did_converge=solver_result.did_converge,
                node_positions=solver_result.node_positions,
                variable_values=variable_values,
            )
        )

        precision_digits = min(precision_digits, solver_result.precision_digits)

        steps.append(step)

        t1 = perf_counter()
        cum_eval_time += t1 - t0

    t_end = perf_counter()
    return steps, precision_digits, (cum_solver_time, cum_eval_time, t_end - t_start)


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
        variable_names = self._build_variable_columns()

        steps: list[ResultsCompilationStep] = []

        total_steps = len(times)
        current_step = 0

        precision_digits = 16

        progress_index = 0
        PROGRESS_TEXT = "1....2....3....4....5....6....7....8....9....!"

        # print("Solving: ", end="", flush=True)
        print("Solving...")

        solving_time_sum = 0.0

        scene_state_dict = self.scene_state.to_dict()

        t0 = perf_counter()

        copy_motion_profile = MotionData.from_dict(motion_profile.to_dict())

        SYNCHRONOUS = True
        MAX_WORKERS = 4

        chunk_size = max(40, ceil(len(times) / MAX_WORKERS))

        step_data = [
            StepCompilationData(
                times = times[i:i + chunk_size],
                motion_profile = copy_motion_profile,
                variable_columns = variable_names,
                scene_state_dict = scene_state_dict,
                solver_kwargs = self.solver_kwargs
            )
            for i in range(0, len(times), chunk_size)
        ]

        print("time ranges:")
        for data in step_data:
            print(f"  {data.times[0]} to {data.times[-1]}")

        if SYNCHRONOUS:
            data = StepCompilationData(
                times=times,
                motion_profile=copy_motion_profile,
                variable_columns=variable_names,
                scene_state_dict=scene_state_dict,
                solver_kwargs=self.solver_kwargs
            )
            some_steps, precision, output_times = _compile_step_task(data)
            print("Solver time: {:.3f} seconds, eval time: {:.3f} seconds, total time: {:.3f} seconds".format(output_times[0], output_times[1], output_times[2]))
            steps.extend(some_steps)
            precision_digits = min(precision_digits, precision)
        else:
            with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
                t01 = perf_counter()
                futures = [
                    executor.submit(_compile_step_task, data)
                    for data in step_data
                ]

                print(f"Submitted {len(futures)} futures, with {len(executor._processes)} processors", flush=True)
                t02 = perf_counter()
                print(f"Time to submit futures: {t02 - t01:.3f} seconds")

                wait(futures)
                t03 = perf_counter()
                print(f"Time to wait for futures: {t03 - t02:.3f} seconds")

                print("Done waiting for futures...", flush=True)
                for future in futures:
                    print("Processing future result...", flush=True)
                    try:
                        some_steps, precision, times = future.result()
                        print("Solver time: {:.3f} seconds, eval time: {:.3f} seconds, total time: {:.3f} seconds".format(times[0], times[1], times[2]))
                        steps.extend(some_steps)
                        precision_digits = min(precision_digits, precision)
                    except Exception as e:
                        print(f"Error processing future result: {e}")
                        continue
                t04 = perf_counter()
                print(f"Time to process all future results: {t04 - t03:.3f} seconds")

        steps.sort(key=lambda x: x.time)

        t1 = perf_counter()
        print("\nDone compiling results in {:.3f} seconds ({:.3f} solving)".format(t1 - t0, solving_time_sum))

        
        return variable_names, steps, precision_digits

    def compile(self, completed: Callable[[ResultsCompilation], None]):
        bridge = ThreadBridge()
        bridge.compilation_ready.connect(completed)

        def func():
            variable_names, steps, precision_digits = self._compile()
            result = ResultsCompilation(
                base_scene=self.scene_state,
                variable_names=variable_names,
                steps=steps,
                precision_digits=precision_digits
            )
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

def get_position_id_map(result: SolverResult, scene_state: SceneState) -> dict[UUID, np.ndarray]:
    """Creates a map of node indices to their solved positions."""

    position_id_map: dict[UUID, np.ndarray] = {}
    positions = result.node_positions

    for i in range(len(positions)):
        position_id_map[scene_state.nodes[i].id] = positions[i]

    return position_id_map
