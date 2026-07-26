from dataclasses import dataclass
from time import perf_counter

import numpy as np
from numba import float64, int32, typed, types, njit
from typing import Any, Literal

from suspension_designer.math import get_rotation_matrix_from_quaternion, mat_mat, mat_t_vec, mat_vec
from suspension_designer.model_variables import DisplacementVariable, DistanceVariable
from suspension_designer.motion import MotionVariableData
from suspension_designer.scene import SceneState

# used for some typing, defines a contiguous (C) array rather than default (A)
array_1d_c = types.Array(dtype=float64, ndim=1, layout='C')

@dataclass
class SolverResult:
    node_positions: np.ndarray
    error: float
    errors: np.ndarray
    iterations: int
    epsilon: float
    did_converge: bool
    time: float

    @property
    def precision_digits(self):
        return int(np.floor(-np.log10(self.epsilon)))

    def __str__(self):
        return f"SolverResult(error={self.error:.6f}, iterations={self.iterations}, did_converge={self.did_converge}, time={self.time:.4f}s)"

@njit(cache=True)
def _get_node_pos(nodes, group_pos, group_rot, node_index: int, group_index: int) -> np.ndarray:
    return group_pos[group_index] + mat_vec(group_rot[group_index], nodes[node_index])

@njit(cache=True)
def _drag_group_by_point(
                            group_pos: np.ndarray,
                            group_rot: list[np.ndarray],
                            group_center: list[np.ndarray],
                            group_index: int,
                            point: np.ndarray,
                            delta: np.ndarray,
                            rotation_strength: float = 0.5
                            ):
        """Moves a point in the group by the given delta, and updates the group's position and rotation accordingly.
        Rotates about the rotation_center instead of the origin.
        The new global position of `point` within the group will be `point + delta` after the drag.

        Args:
            point (np.ndarray): The global position of the point to move.
            delta (np.ndarray): The 3D vector representing the movement delta.
        """
        # if self.is_static:
        #     print(f"Warning: Attempting to drag static group {self.name}. Ignoring.")
        #     return
        
        local_point = mat_t_vec(group_rot[group_index], point - group_pos[group_index])

        _drag_group_by_local_point(group_pos, group_rot, group_center, group_index, local_point, delta, rotation_strength)

@njit(cache=True)
def _drag_group_by_local_point(
                                group_pos: np.ndarray,
                                group_rot: list[np.ndarray],
                                group_center: list[np.ndarray],
                                group_index: int,
                                local_point: np.ndarray,
                                global_delta: np.ndarray,
                                rotation_strength: float = 0.5
                                ):
        # print(f"Dragging group {self.name} by local point {local_point} with global delta {global_delta}, with center {self.rotation_center}")
        
        # "drag" the group by the point for a displacement delta
        # Convert the world point into the group's local frame

        # inv_rot_matrix = self.group_rot[group_index].T.copy()  # Transpose of rotation matrix is its inverse for rotation

        # # Transform the delta into local frame
        local_delta = mat_t_vec(group_rot[group_index], global_delta)

        # # target local point after the drag
        target_local = local_point + local_delta

        # Determine rotation that maps local_point -> target_local (rotate about rotation_center)
        a = local_point - group_center[group_index]
        b = target_local - group_center[group_index]

        ax, ay, az = a
        bx, by, bz = b

        dot = ax*bx + ay*by + az*bz

        cross = np.array([
            ay*bz - az*by,
            az*bx - ax*bz,
            ax*by - ay*bx
        ])*rotation_strength

        na2: float = ax*ax + ay*ay + az*az
        nb2: float = bx*bx + by*by + bz*bz

        q_rot = np.array([1.0, 0.0, 0.0, 0.0])

        if na2 > 1e-16 and nb2 > 1e-16:
            w = np.sqrt(na2 * nb2) + dot
            q_rot = np.array([w, cross[0], cross[1], cross[2]])
            q_rot /= np.linalg.norm(q_rot)
        else:
            print(f"Warning: Division by zero in rotation computation for group {group_index}")

        rot_to_apply = get_rotation_matrix_from_quaternion(q_rot)
        new_rotation_matrix = mat_mat(group_rot[group_index], rot_to_apply)
        
        rotated = mat_vec(new_rotation_matrix, local_point)

        global_point = group_pos[group_index] + mat_vec(group_rot[group_index], local_point)
        
        new_position = global_point + global_delta - rotated
        group_pos[group_index] = new_position

        group_rot[group_index] = new_rotation_matrix

@njit(cache=True)
def _raw_solve( nodes: np.ndarray[tuple[Any, Literal[3]]],
                node_parents: list[list[int]],
                group_pos: np.ndarray,
                group_rot: list[np.ndarray],
                group_center: list[np.ndarray],
                group_static: list[bool],
                linkages: list[tuple[int, int, float]],
                displacements: list[tuple[int, np.ndarray, np.ndarray]],
                easing_factor,
                max_iterations,
                epsilon,
                rotation_strength):
    """Recompute the positions of all linkages based on their connected nodes."""

    did_converge = False
    errors = []

    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        error = 0.0

        # apply displacements
        for n, start, disp in displacements:
            node_pos = _get_node_pos(nodes, group_pos, group_rot, n, node_parents[n][0])
            total_delta = start + disp - node_pos
            disp_dir = disp / np.linalg.norm(disp) if np.linalg.norm(disp) > 1e-8 else np.array([0.0, 0.0, 0.0])
            
            correction = disp_dir * np.dot(total_delta, disp_dir)

            # Match solver.py behavior: apply displacement through a single parent group's local point.
            g = node_parents[n][0]
            _drag_group_by_local_point(group_pos, group_rot, group_center, g, nodes[n], correction*easing_factor, rotation_strength=rotation_strength)

            error = max(error, np.linalg.norm(correction))

        # apply linkages
        for n1, n2, target_distance in linkages:
            g1 = node_parents[n1][0]
            g2 = node_parents[n2][0]
            p1 = _get_node_pos(nodes, group_pos, group_rot, n1, g1)
            p2 = _get_node_pos(nodes, group_pos, group_rot, n2, g2)

            distance = np.linalg.norm(p2 - p1)
            if distance < 1e-12:
                correction = np.array([0.0, 0.0, 0.0])
            else:
                correction = (1 - target_distance/distance) * (p1 - p2)

            static1 = group_static[g1]
            static2 = group_static[g2]
            if not static1 and not static2:
                _drag_group_by_point(group_pos, group_rot, group_center, g1, p1, -correction*0.5*easing_factor, rotation_strength=rotation_strength)
                _drag_group_by_point(group_pos, group_rot, group_center, g2, p2, correction*0.5*easing_factor, rotation_strength=rotation_strength)
            elif not static1:
                # Only g2 is static
                _drag_group_by_point(group_pos, group_rot, group_center, g1, p1, -correction*easing_factor, rotation_strength=rotation_strength)
            elif not static2:
                # Only g1 is static
                _drag_group_by_point(group_pos, group_rot, group_center, g2, p2, correction*easing_factor, rotation_strength=rotation_strength)
            else:
                print(f"Warning: Both nodes in linkage are static. Skipping correction.")

            error = max(error, np.linalg.norm(correction))

        # Constrain each node's parent groups pairwise (once per pair).
        # This matches solver.py behavior where shared-node consistency is encoded
        # via one zero-distance linkage per duplicate-node pair.
        for i in range(len(nodes)):
            parents_i = node_parents[i]
            for j in range(len(parents_i)):
                for k in range(j + 1, len(parents_i)):
                    g1 = parents_i[j]
                    g2 = parents_i[k]
                    p1 = _get_node_pos(nodes, group_pos, group_rot, i, g1)
                    p2 = _get_node_pos(nodes, group_pos, group_rot, i, g2)

                    correction = p1 - p2

                    static1 = group_static[g1]
                    static2 = group_static[g2]
                    if not static1 and not static2:
                        _drag_group_by_point(group_pos, group_rot, group_center, g1, p1, -correction*0.5*easing_factor, rotation_strength=rotation_strength)
                        _drag_group_by_point(group_pos, group_rot, group_center, g2, p2, correction*0.5*easing_factor, rotation_strength=rotation_strength)
                    elif not static1:
                        # Only g2 is static
                        _drag_group_by_point(group_pos, group_rot, group_center, g1, p1, -correction*easing_factor, rotation_strength=rotation_strength)
                    elif not static2:
                        # Only g1 is static
                        _drag_group_by_point(group_pos, group_rot, group_center, g2, p2, correction*easing_factor, rotation_strength=rotation_strength)

                    error = max(error, np.linalg.norm(correction))


        errors.append(error)

        if error < epsilon:
            did_converge = True
            break

    positions = np.zeros(nodes.shape)
    for i in range(len(nodes)):
        n = 0
        for g in node_parents[i]:
            positions[i] += _get_node_pos(nodes, group_pos, group_rot, i, g)
            n += 1
        positions[i] /= n

    # print(f"Reached max iterations with error: {error:.6f}")
    # return positions, np.array(errors), iterations, did_converge

    return (
            positions,
            errors,
            iterations,
            epsilon,
            did_converge)


class Solver:
    def __init__(self,
                nodes: np.ndarray[tuple[Any, Literal[3]]],
                node_parents: list[list[int]],
                linkages: list[tuple[int, int, float]],
                displacements: list[tuple[int, np.ndarray, np.ndarray]]
                ):
    
            assert len(nodes) == len(node_parents), "Number of nodes and node_parents must match"
    
            self.nodes = nodes
            self.node_parents = node_parents
    
            # add 1 to account for 0-based indexing
            num_groups = max([max(parents) for parents in node_parents]) + 1
    
            self.group_pos = np.zeros((num_groups, 3))
    
            # local rotation point of each group
            self.group_center = np.zeros((num_groups, 3))
            num_nodes_in_group = np.zeros(num_groups, dtype=np.int32)
            for i in range(len(nodes)):
                for j in node_parents[i]:
                    self.group_center[j] += nodes[i]
                    num_nodes_in_group[j] += 1
    
            for i in range(num_groups):
                self.group_center[i] = self.group_center[i] / num_nodes_in_group[i] if num_nodes_in_group[i] > 0 else np.zeros(3)
    
            # list of 3x3 rotation matrices
            self.group_rot = np.zeros((num_groups, 3, 3), dtype=np.float64)
            for i in range(num_groups):
                self.group_rot[i] = np.eye(3)
    
            self.group_static = np.array([False for _ in range(num_groups)])
            self.group_static[0] = True  # Mark the first group as static
    
            self.linkages = linkages
            self.displacements = displacements

    def solve(self, *, easing_factor=1.4, max_iterations=1000, epsilon=(1e-8)/2, rotation_strength=0.5) -> SolverResult:
        t0 = perf_counter()
        result_tuple = _raw_solve(
            self.nodes,
            self.node_parents,
            self.group_pos,
            self.group_rot,
            self.group_center,
            self.group_static,
            self.linkages,
            self.displacements,
            easing_factor,
            max_iterations,
            epsilon,
            rotation_strength)
        t1 = perf_counter()
        time = t1 - t0

        positions, errors, iterations, epsilon, did_converge = result_tuple
        return SolverResult(
            node_positions=positions,
            errors=errors,
            error=errors[-1],
            iterations=iterations,
            epsilon=epsilon,
            time=time,
            did_converge=did_converge
        )


    @staticmethod
    def from_connections(
        nodes: np.ndarray,
        node_groups: list[list[int]],
        links: list[tuple[int, int, float]],
        displacements: list[tuple[int, np.ndarray]],
    ) -> "Solver":
        n_nodes = np.ascontiguousarray(nodes)

        parents = typed.List.empty_list(types.ListType(int32))
        for _ in range(len(nodes)):
            parents.append(typed.List.empty_list(types.int32))
            
        for i, group in enumerate(node_groups):
            for node in group:
                parents[node].append(int32(i))

        disps = typed.List.empty_list(types.Tuple((int32, array_1d_c, array_1d_c)))
        for disp in displacements:
            start = np.ascontiguousarray(n_nodes[disp[0]])
            disp_vec = np.ascontiguousarray(disp[1])
            disps.append((int32(disp[0]), start, disp_vec))

        typed_links = typed.List.empty_list(types.Tuple((int32, int32, float64)))
        for link in links:
            typed_links.append((int32(link[0]), int32(link[1]), float64(link[2])))

        # print(f"Created solver with:\nnodes\n{nodes}\nparents\n{parents}\ndisplacements\n{disp}")


        return Solver(
            nodes=n_nodes,
            node_parents=parents,
            linkages=typed_links,
            displacements=disps,
        )

    
def solve_at_time(motion_variables: list[MotionVariableData], time_value: float, scene_state: SceneState, **solver_kwargs: dict) -> SolverResult:
    """Build a solver state for the requested time and solve it without console output."""
    t0 = perf_counter()

    nodes = np.array([node.world_position for node in scene_state.nodes])
    groups = [[scene_state.nodes.index(node) for node in group.nodes] for group in scene_state.groups]

    displacements: list[tuple[int, np.ndarray]] = []
    links: list[tuple[int, int, float]] = []
    motion_variables_by_id = {variable.id: variable for variable in motion_variables}

    for element in scene_state.model_variables:
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
                displacements.append((scene_state.nodes.index(node), variable.get_displacement(sampled_value)))
        elif isinstance(variable, DistanceVariable):
            node_a = variable.node_a
            node_b = variable.node_b
            if node_a is not None and node_b is not None:
                links.append((scene_state.nodes.index(node_a), scene_state.nodes.index(node_b), sampled_value))

    t1 = perf_counter()
    # print(f"Time taken to prepare solver state: {t1 - t0:.6f} seconds")

    solver = Solver.from_connections(
        nodes=nodes,
        node_groups=groups,
        displacements=displacements,
        links=links,
    )

    # solver_state = SolverState.from_connections(
    #     nodes=nodes,
    #     node_groups=groups,
    #     displacements=displacements,
    #     extra_links=links,
    # )


    t2 = perf_counter()
    # print(f"Time taken to create solver state: {t2 - t1:.6f} seconds")

    result = solver.solve(**solver_kwargs)
    # result = solve_system(solver_state, **solver_kwargs)

    t3 = perf_counter()
    # print(f"Time taken to solve system: {t3 - t2:.6f} seconds")

    return result