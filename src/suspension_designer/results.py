import numpy as np

from suspension_designer.solver import SolverResult
from suspension_designer.scene import SceneState

def build_solved_scene_state(scene_state: SceneState, result: SolverResult) -> SceneState:
    """Generates a new SceneState, using all the data in the input SceneState,
    but with the nodes moved based on the SolverResult (average of all corresponding node positions)

    Args:
        scene_state (SceneState): The scene to copy, which the data will be put into
        result (SolverResult): The result of the solve that defines new node positions

    Returns:
        SceneState: A scene containing all of the original scene data, but with nodes moved to their solves positions
    """

    solved_scene = SceneState.from_dict(scene_state.to_dict())
    solved_scene.is_editable = False

    # prevent reference planes from doing weird things.
    for node in solved_scene.nodes:
        node.locked_plane = None

    positions_by_index: dict[int, list[np.ndarray]] = {}
    for group in result.system_state.groups:
        for node in group.nodes:
            positions_by_index.setdefault(node.index, []).append(np.array(node.get_world_position(), dtype=float))

    for node_index, positions in positions_by_index.items():
        if 0 <= node_index < len(solved_scene.nodes):
            solved_scene.nodes[node_index].world_position = np.mean(positions, axis=0)

    return solved_scene