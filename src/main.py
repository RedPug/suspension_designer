print("Starting...")

import os

from suspension_designer.document import Document
from suspension_designer.graphics import MainWindow
from PySide6.QtWidgets import QApplication
from suspension_designer.settings import SettingsManager

SettingsManager.read()

app = QApplication([])
window = MainWindow()
window.resize(900, 600)
window.show()

files = SettingsManager.get("last_opened_files")
if files:
    for file in files:
        if not os.path.exists(file):
            print(f"Warning: Last opened file does not exist: {file}")
            files.remove(file)

    for file in files:
        print(f"Loading last opened file: {file}")
        doc = Document.load(file)
        window.document_manager.add_document(doc, select=True)

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