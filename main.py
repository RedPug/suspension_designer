import json
import os
# os.environ["QT_QUICK_BACKEND"] = "software" # or force a different backend
# os.environ["QT_OPENGL"] = "software" # or force a different OpenGL implementation

import numpy as np

# from src.scene import Scene
from src.document import Document, EditorDocument
# from src.structures import DisplacementVariable, SceneState, solve
from src.graphics import MainWindow
from PySide6.QtWidgets import QApplication
import matplotlib.pyplot as plt
# from src.math import mult_quaternions, get_rotation_matrix_from_quaternion
from src.document import MotionDocument

# system_state = SolverState(groups=[chassis_group, upright_group, upper_group, lower_group], linkages=linkages1)
nodes = np.array([
    [0.267,0.260,-0.165], # 0
    [0.236,0.110,-0.153], # 1
    [0.240,0.096,0.217], # 2
    [0.245, 0.278, 0.233], # 3
    [0.565, 0.109, -0.005], # 4
    [0.539,0.295,-0.021], # 5
    [0.570, 0.170, 0.075], # 6
    [0.213, 0.155, 0.045], # 7
], dtype=float)

node_groups = [
    [0,1,2,3],  # chassis
    [4,5,6],        # upright
    [0,3,5],          # upper control arm
    [1,2,4],          # lower control arm
    [6,7], # toe rod
]

edges = []
for group in node_groups:
    for i in range(len(group)):
        j = (i + 1) % len(group)
        edges.append((group[i], group[j]))

app = QApplication([])
window = MainWindow()
window.resize(900, 600)
window.show()

if not os.path.exists("./user_data/user_settings.json"):
    with open("./user_data/user_settings.json", "w") as f:
        json.dump({}, f)

with open("./user_data/user_settings.json", "r") as f:
    user_settings = json.load(f)

if user_settings.get("last_opened_files"):
    files = user_settings["last_opened_files"]
    for file in files:
        if not os.path.exists(file):
            print(f"Warning: Last opened file does not exist: {file}")
            files.remove(file)

    for file in files:
        print(f"Loading last opened file: {file}")
        doc = Document.load(file)
        window.document_manager.add_document(doc, select=True)


def open_motion_document_from_default_editor(window: MainWindow):
    editor_document = next(
        (doc for doc in window.document_manager._documents if isinstance(doc, EditorDocument)),
        None,
    )

    if editor_document is None:
        print("No editor document available to create a motion document from.")
        return

    motion_document = MotionDocument(
        name=f"{editor_document.name} Motion",
        scene_state=editor_document.scene_state,
        editor_filepath=editor_document.filepath,
    )
    window.document_manager.add_document(motion_document, select=True)


# open_motion_document_from_default_editor(window)

# doc = Document.load("C:\\Users\\thero\\Downloads\\test4.proj")
# window.document_manager.add_document(doc, select=True)
# window.tree_dock.refreshTree()

# old_scene = window.document_manager.get_document(0).scene_state
# old_scene.add_model_variable(DisplacementVariable(name="Test Variable"))


# window.scene_manager.set_scene(ProjectSerializer.load_scene("C:\\Users\\thero\\Downloads\\test4.proj"))
# window.scene_state.nodes = [EditorNode(name=f"Node {i}", world_position=pos) for i, pos in enumerate(nodes)]
# window.scene_state.edges = np.array(edges, dtype=int)
# window.scene_state.groups = [NodeGroup(name="My Group!", nodes=[window.scene_state.nodes[i] for i in [0,1,2,3]])]
# window.scene_state.add_reference_plane(ReferencePlane(p0=np.array([1.0, 0.0, 0.0]), p1=np.array([0.0, 1.0, 0.0]), p2=np.array([0.0, 0.0, 1.0]), mode="containing"))

# displacements = []
# displacements.append((5, [None, 0.1, None]))  # Move node 5 up by 0.1 in the Y direction


# result = solve(old_scene, displacements=displacements)
# # print(result)

# positions = [[] for _ in range(len(old_scene.nodes))]

# for group in result.system_state.groups:
#     for node in group.nodes:
#         positions[node.index].append(node.get_world_position())

# avg_positions = [np.mean(pos_list, axis=0) for pos_list in positions]

# new_scene = SceneState.from_dict(old_scene.to_dict())
# new_scene.name = "Modified Scene"
# new_scene.is_editable = False

# for i in range(len(avg_positions)):
#     new_scene.nodes[i].world_position = avg_positions[i]

# window.document_manager.add_document(EditorDocument(name="Modified Scene", scene=new_scene))

# print(f"Errors: {result.errors}")

# fig, ax = plt.subplots()

# for easing in np.arange(0.1, 1.6 + 0.1, 0.1):
#     result = window.scene_manager.solve(displacements=displacements, easing_factor=easing, max_iterations=1e4)
#     ax.plot(np.arange(len(result.errors)), result.errors, '-', label=f"Easing: {easing:.2f}")

# ax.set_yscale('log')
# ax.set_xscale('log')
# ax.set_ylabel('Error (log scale)')
# ax.set_xlabel('Iteration')
# ax.set_title('Error Convergence of Fixed Displacement Solver')
# ax.legend()
# ax.grid()
# plt.show()

app.exec()