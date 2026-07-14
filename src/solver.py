from typing import List, Optional

import numpy as np
from dataclasses import dataclass
import time

from src.model_variables import DisplacementVariable, DistanceVariable
from src.scene import SceneState
from src.motion import MotionVariableData
from src.math import get_rotation_matrix_from_quaternion, mult_quaternions


@dataclass
class SolverResult:
    system_state: 'SolverState'
    error: float
    errors: np.ndarray
    iterations: int
    did_converge: bool
    time: float

    def __str__(self):
        return f"SolverResult(error={self.error:.6f}, iterations={self.iterations}, did_converge={self.did_converge}, time={self.time:.4f}s)"

class Node:

    def __init__(self, name: str, index: int, local_position: np.ndarray, parent_group: Optional['RigidGroup'] = None):
        self.name = name
        self.index = index
        self.local_position = local_position
        self.parent_group = parent_group

    def copy(self) -> 'Node':
        """Creates a copy of this node with the same name, index, and local position, but no parent group."""
        return Node(name=self.name, index=self.index, local_position=np.copy(self.local_position), parent_group=None)

    def get_world_position(self) -> np.ndarray:
        return self.parent_group.position + self.parent_group.rotation_matrix @ self.local_position

class RigidGroup:
    def __init__(self, name: str, nodes: list[Node], position: np.ndarray, rotation: np.ndarray, is_static=False, color: Optional[str] = None):
        self.name: str = name
        self.is_static: bool = is_static
        self.color: Optional[str] = color

        for node in nodes:
            # print(f"Assigning node {node.name} to group {name}")
            node.parent_group = self

        self.nodes: list[Node] = nodes
        self.position: np.ndarray = position
        self.rotation: np.ndarray = rotation
        self.rotation_matrix: np.ndarray = get_rotation_matrix_from_quaternion(self.rotation)

        self.rotation_center = self.recompute_center()

    def recompute_center(self)-> np.ndarray:
        return np.mean([node.local_position for node in self.nodes], axis=0)
    
    def drag_by_point(self, point: np.ndarray, delta: np.ndarray, rotation_strength: float = 0.5):
        """Moves a point in the group by the given delta, and updates the group's position and rotation accordingly.
        Rotates about the rotation_center instead of the origin.
        The new global position of `point` within the group will be `point + delta` after the drag.

        Args:
            point (np.ndarray): The global position of the point to move.
            delta (np.ndarray): The 3D vector representing the movement delta.
        """
        if self.is_static:
            print(f"Warning: Attempting to drag static group {self.name}. Ignoring.")
            return
        
        local_point = self.rotation_matrix.T @ (point - self.position)

        self.drag_by_local_point(local_point, delta, rotation_strength)

    def drag_by_local_point(self, local_point: np.ndarray, global_delta: np.ndarray, rotation_strength: float = 0.5):
        # print(f"Dragging group {self.name} by local point {local_point} with global delta {global_delta}, with center {self.rotation_center}")
        
        # "drag" the group by the point for a displacement delta
        # Convert the world point into the group's local frame

        inv_rot_matrix = self.rotation_matrix.T  # Transpose of rotation matrix is its inverse for rotation

        # # Transform the delta into local frame
        local_delta = inv_rot_matrix @ global_delta

        # # target local point after the drag
        target_local = local_point + local_delta

        # Determine rotation that maps local_point -> target_local (rotate about rotation_center)
        a = local_point - self.rotation_center
        b = target_local - self.rotation_center

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
            print("Warning: One of the vectors for rotation is too small, skipping rotation.")

        new_rotation = mult_quaternions(self.rotation, q_rot)

        # compute new position so that rotated local_point sits at point + delta

        self.rotation = new_rotation
        new_rotation_matrix = get_rotation_matrix_from_quaternion(new_rotation)

        rotated = new_rotation_matrix @ local_point

        global_point = self.position + self.rotation_matrix @ local_point
        
        new_position = global_point + global_delta - rotated
        self.position = new_position

        self.rotation_matrix = new_rotation_matrix

    def copy(self) -> 'RigidGroup':
        """Creates a deep copy of this group and its nodes, with new unique IDs."""
        new_nodes = [node.copy() for node in self.nodes]
        new_group = RigidGroup(
            name=self.name,
            nodes=new_nodes,
            position=np.copy(self.position),
            rotation=self.rotation.copy(),
            is_static=self.is_static,
            color=self.color
        )
        return new_group

class CorrectionProvider:
    def solve_for_correction(self) -> np.ndarray:
        """Returns a 3D vector representing the correction to apply to a node to satisfy a constraint."""
        raise NotImplementedError("Subclasses should implement this method.")

class Linkage:
    def __init__(self, name: str, node1: Node, node2: Node, target_distance: Optional[float] = None):
        self.name = name
        self.node1 = node1
        self.node2 = node2
        self.target_distance = target_distance if target_distance is not None else np.linalg.norm(node2.get_world_position() - node1.get_world_position())

    def solve_for_correction(self) -> np.ndarray:
        """Solves for the delta (N2-N1) that would satisfy the linkage constraint.

        Returns:
            np.ndarray: a 3D vector representing the correction to add to node2 to satisfy the linkage constraint.
        """
        distance = np.linalg.norm(self.node2.get_world_position() - self.node1.get_world_position())
        if distance < 1e-11:
            return np.array([0.0, 0.0, 0.0])
        
        return (1 - self.target_distance/distance) * (self.node1.get_world_position() - self.node2.get_world_position())


class SolverState:
    def __init__(self, groups: list[RigidGroup], linkages: list[Linkage], displacements: list[tuple[Node, np.ndarray, np.ndarray]] = []):
        self.groups = groups
        self.linkages = linkages
        self.displacements = displacements  # List of tuples (Node, initial, delta)

    # def get_node_by_id(self, node_id: int) -> Optional[Node]:
    #     for group in self.groups:
    #         for node in group.nodes:
    #             if node.id == node_id:
    #                 return node
    #     return None
    
    def to_dict(self):
        return {
            'groups': [
                {
                    'name': group.name,
                    'is_static': group.is_static,
                    'color': group.color,
                    'position': group.position.tolist(),
                    'rotation': group.rotation.tolist(),
                    'nodes': [
                        {
                            'name': node.name,
                            'local_position': node.local_position.tolist()
                        }
                        for node in group.nodes
                    ]
                }
                for group in self.groups
            ],
            'linkages': [
                {
                    'name': linkage.name,
                    'node1_id': linkage.node1.id,
                    'node2_id': linkage.node2.id,
                    'target_distance': linkage.target_distance
                }
                for linkage in self.linkages
            ],
            'displacements': [
                {
                    'node_id': node.id,
                    'displacement': delta.tolist()
                }
                for node, initial, delta in self.displacements
            ]
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'SolverState':
        groups_data = data['groups']
        linkages_data = data['linkages']
        displacements_data = data['displacements']
        groups = []
        node_mapping = {}

        for group_data in groups_data:
            nodes = []
            for node_data in group_data['nodes']:
                node = Node(
                    name=node_data['name'],
                    local_position=np.array(node_data['local_position'], dtype=float)
                )
                nodes.append(node)
                node_mapping[node.id] = node
            
            group = RigidGroup(
                name=group_data['name'],
                is_static=group_data['is_static'],
                color=group_data['color'],
                position=np.array(group_data['position'], dtype=float),
                rotation=np.array(group_data['rotation'], dtype=float),
                nodes=nodes
            )
            groups.append(group)

        linkages = []
        for linkage_data in linkages_data:
            node1 = node_mapping.get(linkage_data['node1_id'])
            node2 = node_mapping.get(linkage_data['node2_id'])
            if node1 is None or node2 is None:
                print(f"Warning: Linkage {linkage_data['name']} references missing nodes. Skipping.")
                continue
            linkage = Linkage(
                name=linkage_data['name'],
                node1=node1,
                node2=node2,
                target_distance=linkage_data['target_distance']
            )
            linkages.append(linkage)

        displacements = []
        for displacement_data in displacements_data:
            node = node_mapping.get(displacement_data['node_id'])
            if node is None:
                print(f"Warning: Displacement references missing node. Skipping.")
                continue
            displacement = np.array(displacement_data['displacement'], dtype=float)
            displacements.append((node, displacement))

        return SolverState(groups=groups, linkages=linkages, displacements=displacements)

    def copy(self) -> 'SolverState':
        """Creates a deep copy of the system state, with new group and node instances."""
        group_copy = [group.copy() for group in self.groups]

        # Create a mapping from original nodes to copied nodes for linkage reconstruction
        node_mapping = {}
        for original_group, copied_group in zip(self.groups, group_copy):
            for original_node, copied_node in zip(original_group.nodes, copied_group.nodes):
                node_mapping[original_node] = copied_node

        # Reconstruct linkages with copied nodes
        linkage_copy = []
        for linkage in self.linkages:
            new_linkage = Linkage(
                name = linkage.name,
                node1 = node_mapping[linkage.node1],
                node2 = node_mapping[linkage.node2],
                target_distance = linkage.target_distance
            )
            linkage_copy.append(new_linkage)

        displacement_copy = [(node_mapping[node], np.copy(pos), np.copy(disp)) for node, pos, disp in self.displacements]

        return SolverState(groups=group_copy, linkages=linkage_copy, displacements=displacement_copy)

    @staticmethod
    def from_connections(nodes: np.ndarray, node_groups: list[list[int]], displacements: list[tuple[int, np.ndarray]], extra_links: list[tuple[int, int, float]]) -> 'SolverState':
        """Utility function to create a system state from a list of nodes and their connections.

        Args:
            nodes (np.ndarray): An array of Node objects with global positions defined.
            node_groups (List[List[int]]): A list of lists, where each list contains the indices of nodes that belong to the same group.
            displacements (List[Tuple[int, np.ndarray]]): A list of tuples, where each tuple contains a node index and an array of displacement values.
            extra_links (List[Tuple[int, int, float]]): A list of tuples, where each tuple contains two node indices and a target distance.

        Returns:
            SolverState: A new SolverState object with one RigidGroup containing all nodes and Linkages defined by the connections.
        """
        groups: list[RigidGroup] = []

        all_nodes = []

        # create a list, where each entry is a new list of all the nodes in the same spot.
        duplicate_nodes: list[list[Node]] = [[] for _ in range(len(nodes))]

        for i in range(len(node_groups)):
            node_group = node_groups[i]
            group_nodes = [
                Node(name=f"node_{i}", index=i, local_position=nodes[i]) for i in node_group
                ]

            all_nodes.extend(group_nodes)
            for original_idx, node in zip(node_group, group_nodes):
                duplicate_nodes[original_idx].append(node)

            group = RigidGroup(
                name=f"group_{len(groups)}",
                nodes=group_nodes,
                position=np.array([0.0, 0.0, 0.0]),
                rotation=np.array([1.0, 0.0, 0.0, 0.0]),
                is_static=i==0,  # Make the first group static as a reference frame
            )
            groups.append(group)

        linkages: List[Linkage] = []

        # link all nodes in the same spot together with 0 distance linkage.
        for arr in duplicate_nodes:
            for i in range(len(arr)):
                for j in range(i+1, len(arr)):
                    linkages.append(Linkage(name=f"linkage_{len(linkages)}", node1=arr[i], node2=arr[j]))


        # add extra links
        for node1_idx, node2_idx, target_distance in extra_links:
            if 0 <= node1_idx < len(duplicate_nodes) and 0 <= node2_idx < len(duplicate_nodes):
                linkages.append(Linkage(name=f"linkage_{len(linkages)}", node1=duplicate_nodes[node1_idx][0], node2=duplicate_nodes[node2_idx][0], target_distance=target_distance))


        disp: list[tuple[Node, np.ndarray, np.ndarray]] = []
        for node_idx, delta in displacements:
            
            if node_idx < 0 or node_idx >= len(duplicate_nodes):
                print(f"Warning: Displacement references invalid node index {node_idx}. Skipping.")
                continue
            # for node in duplicate_nodes[node_idx]:
            delta = np.array(delta)
            node = duplicate_nodes[node_idx][0]
            node_pos = node.get_world_position()
            disp.append((node, node_pos, delta))

        return SolverState(groups=groups, linkages=linkages, displacements=disp)


def _apply_linkages(system_state: SolverState, easing_factor, max_iterations, epsilon, rotation_strength):
    """Recompute the positions of all linkages based on their connected nodes."""
    print("applying linkages with displacements:", system_state.displacements)
    did_converge = False
    errors = []

    iterations = 0
    while iterations < max_iterations:
        iterations += 1
        error = 0.0

        # apply displacements
        for node, start, disp in system_state.displacements:
            node_pos = node.get_world_position()
            total_delta = start + disp - node_pos
            disp_dir = disp / np.linalg.norm(disp) if np.linalg.norm(disp) > 1e-8 else np.array([0.0, 0.0, 0.0])
            
            correction = disp_dir * np.dot(total_delta, disp_dir)

            node.parent_group.drag_by_local_point(node.local_position, correction*easing_factor, rotation_strength=rotation_strength)

            error = max(error, np.linalg.norm(correction))

        # apply linkages
        for linkage in system_state.linkages:
            n1 = linkage.node1
            n2 = linkage.node2
            correction = linkage.solve_for_correction()

            if n1.parent_group.is_static and n2.parent_group.is_static:
                print(f"Warning: Both nodes in linkage {linkage.name} are static. Skipping correction.")
                continue


            if n1.parent_group.is_static:
                n2.parent_group.drag_by_local_point(n2.local_position, correction*easing_factor, rotation_strength=rotation_strength)
            elif n2.parent_group.is_static:
                n1.parent_group.drag_by_local_point(n1.local_position, -correction*easing_factor, rotation_strength=rotation_strength)
            else:
                n1.parent_group.drag_by_local_point(n1.local_position, -correction*0.5*easing_factor, rotation_strength=rotation_strength)
                n2.parent_group.drag_by_local_point(n2.local_position, correction*0.5*easing_factor, rotation_strength=rotation_strength)

            error = max(error, np.linalg.norm(correction))


        errors.append(error)

        if error < epsilon:
            # print(f'Converged in {iterations} iterations with error: {error:.6}')
            did_converge = True
            break
        
    # print(f"Reached max iterations with error: {error:.6f}")
    return np.array(errors), iterations, did_converge

def solve_system(system_state: SolverState, easing_factor=1.4, max_iterations=1000, epsilon=(1e-5)/2, rotation_strength=0.5)-> SolverResult:
    """Iteratively solve for the positions of all groups based on the linkage constraints.

    Args:
        system_state (SolverState): The system state containing groups and linkages.
        easing_factor (float, optional): A factor to control the step size of corrections. Stable 0 < easing_factor < 2.0.
        max_iterations (int, optional): Maximum number of iterations to prevent infinite loops. Defaults to 1000.
        rotation_strength (float, optional): A factor to control the strength of rotation corrections. Defaults to 1.0.
    """

    system_copy = system_state.copy()
    t0 = time.perf_counter()
    errors, iterations, did_converge = _apply_linkages(system_copy, easing_factor=easing_factor, max_iterations=max_iterations, epsilon=epsilon, rotation_strength=rotation_strength)
    t1 = time.perf_counter()

    # print(f"T:{t1-t0:.4f},iterations:{iterations}, easing:{easing_factor:.4f}")

    # print(f"Solved system in {t1-t0:.4f} seconds")

    return SolverResult(system_state=system_copy, error=errors[-1], errors=errors, iterations=iterations, time=t1-t0, did_converge=did_converge)


def solve(scene_state: SceneState, motion_variables: list[MotionVariableData], t: float = 0.0, **kwargs) -> SolverResult:
    current_state = scene_state

    nodes = np.array([n.world_position for n in current_state.nodes])

    groups = [[current_state.nodes.index(n) for n in group.nodes] for group in current_state.groups]

    displacements: list[tuple[int, np.ndarray]] = []
    motion_variables_by_id = {variable.id: variable for variable in motion_variables}

    print("model_variables:", current_state.model_variables)

    for element in current_state.model_variables:
        variable = element.variable

        motion_variable = motion_variables_by_id.get(str(variable.id))
        if motion_variable is None or not motion_variable.is_input:
            continue

        sampled_value = motion_variable.sample_at(t)
        if sampled_value is None:
            print(f"Skipping variable {variable.name} at time {t} because it has no sampled value.")
            continue

        if isinstance(variable, DisplacementVariable):
            node = variable.node
            if node is not None:
                displacements.append((current_state.nodes.index(node), variable.get_displacement(sampled_value)))
            
            else:
                print(f"Skipping variable {variable.name} at time {t} because its node is None.")
    
    links: list[Linkage] = []
    for variable in current_state.model_variables:
        motion_variable = motion_variables_by_id.get(str(variable.id))
        if motion_variable is None or not motion_variable.is_input:
            continue

        sampled_value = motion_variable.sample_at(t)
        if sampled_value is None:
            print(f"Skipping variable {variable.name} at time {t} because it has no sampled value.")
            continue

        if isinstance(variable, DistanceVariable):
            node1 = current_state.nodes.index(variable.node1)
            node2 = current_state.nodes.index(variable.node2)
            if node1 is not None and node2 is not None:
                links.append((node1, node2, sampled_value))

    print("about to run solver with displacements:", displacements)
    solver_state = SolverState.from_connections(
        nodes=nodes,
        node_groups=groups,
        displacements=displacements,
        extra_links=links)
    
    solver_state.groups[0].locked = True
    
    result = solve_system(solver_state, **kwargs)
    print(result)

    return result