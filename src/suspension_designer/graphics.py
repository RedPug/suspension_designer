import numpy as np

from PySide6.QtCore import QPoint, Qt, Signal

from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMenuBar,
    QStatusBar,
    QTabBar,
    QToolBar,
    QWidget,
    QVBoxLayout,
    QStackedWidget
)

from PySide6.QtGui import QAction, QMouseEvent
from PySide6.QtCore import QByteArray

from suspension_designer.structures import EditorNode, NodeGroup, ReferencePlane
from suspension_designer.model_variables import ModelVariableElement
from suspension_designer.document import Document, DocumentManager
from suspension_designer.rendering import Camera, Viewport3D
from suspension_designer.docks import PropertiesDock, TreeDock

class TabBar(QTabBar):
    def __init__(self, main_window: 'MainWindow', document_manager: DocumentManager):
        super().__init__(main_window)
        self.main_window = main_window

        self.document_manager = document_manager

        self.setExpanding(False)
        self.setTabsClosable(True)

        self.tabCloseRequested.connect(self.close_tab)
        self.currentChanged.connect(self.on_tab_changed)
        # self.tabSelectionFinalized.connect(self.on_tab_changed)

        self.document_manager.document_added.connect(self.on_doc_added)
        self.document_manager.document_removed.connect(self.on_doc_removed)
        self.document_manager.document_changed.connect(self.on_doc_changed)

    def on_doc_added(self, document: Document):
        # supress changes to prevent tab being selected before it has data.
        self.blockSignals(True)
        index = self.addTab(document.name)
        self.setTabData(index, document)
        self.blockSignals(False)

        # this is the first tab to be added, select it.
        if index == 0 and self.count() == 1:
            self.setCurrentIndex(0)
        

        self.main_window.stack.addWidget(document.create_widget())

        self.setCurrentIndex(index)
        
        

    def on_doc_removed(self, document: Document):
        for index in range(self.count()):
            if self.tabData(index) == document:
                self.removeTab(index)
                self.main_window.stack.removeWidget(document.widget)
                break
        
    def on_doc_changed(self, document: Document):
        index = 0
        while index < self.count():
            if self.tabData(index) == document:
                break
            index = index + 1

        self.setTabText(index, document.name)

    def on_tab_changed(self, index):
        # print(f"Tab changed to index: {index}")
        doc = self.tabData(index)
        if doc is None:
            if index >= 0:
                print("Error: document does not exist for the selected tab {}.".format(index))
                print("tabs count: {}, tabs:".format(self.count()))
                for i in range(self.count()):
                    print(f"  {i}: {self.tabText(i)}")
            return
        
        self.document_manager.select_document(doc)
        
        self.main_window.stack.setCurrentWidget(doc.widget)
        # Implement your logic to switch the view here
        # For example, you might want to update the viewport to show the selected scene

    def close_tab(self, index):
        print(f"Closing tab at index: {index}")
        doc = self.tabData(index)
        self.document_manager.remove_document(doc)
        # Implement your logic to close the tab here


class ToolBar(QToolBar):
    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)

        self.editor_action = QAction("Editor", self)
        self.result_action = QAction("Result", self)

        self.addAction(self.editor_action)
        self.addAction(self.result_action)

        self.editor_action.triggered.connect(self.to_editor)
        self.result_action.triggered.connect(self.to_result)

    def to_editor(self):
        print("Switching to editor mode")
        # self.statusBar().showMessage("Editor mode")
        # self.plotter.add_text("Editor", font_size=10)

    def to_result(self):
        print("Switching to result mode")
        # self.statusBar().showMessage("Result mode")
        # self.plotter.add_text("Result", font_size=10)

class MenuBar(QMenuBar):
    def __init__(self, parent, docks: list[QDockWidget], document_manager: DocumentManager):
        super().__init__(parent)

        self.main_window: QMainWindow = parent
        self.document_manager = document_manager
        self._dock_widgets = {dock.dock_key: dock for dock in docks}
        self._dock_actions = {}
        self._active_document: Document | None = None
        self._restoring_docks = False

        self._project_path = None

        file_menu = self.addMenu("File")

        new_menu = file_menu.addMenu("New")

        new_editor_action = new_menu.addAction("Geometry Editor")
        new_editor_action.triggered.connect(lambda: self.document_manager.create_new_editor_document())
        new_motion_action = new_menu.addAction("Motion")
        new_motion_action.triggered.connect(lambda: self.document_manager.create_new_motion_document())

        save_action = file_menu.addAction("Save")
        save_action.triggered.connect(self.document_manager.save_current)
        save_as_action = file_menu.addAction("Save as")
        save_as_action.triggered.connect(self.document_manager.save_current_as)
        save_all_action = file_menu.addAction("Save All")
        save_all_action.triggered.connect(self.document_manager.save_all)
        load_action = file_menu.addAction("Load")
        load_action.triggered.connect(self.document_manager.load)


        view_menu = self.addMenu("View")

        dock_menu = view_menu.addMenu("Docks")
        # actions
        for dock in docks:
            toggle_action = dock.toggleViewAction()
            self._dock_actions[dock.dock_key] = toggle_action
            dock_menu.addAction(toggle_action)

            dock.visibilityChanged.connect(self._on_dock_visibility_changed)
            dock.dockLocationChanged.connect(self._on_dock_location_changed)

        self.document_manager.selection_changed.connect(self.sync_docks)
        self.sync_docks(self.document_manager.current_document)

        view_menu.addSeparator()

        perspective_action = QAction("Perspective", self, checkable=True, checked=False)
        perspective_action.toggled.connect(self.toggle_perspective)
        view_menu.addAction(perspective_action)
        
        view_direction_menu = view_menu.addMenu("View Direction")
        view_direction_menu.addAction("Front").triggered.connect(lambda: self.set_view_direction(np.array([0, 0, 1])))
        view_direction_menu.addAction("Right").triggered.connect(lambda: self.set_view_direction(np.array([1, 0, 0])))
        view_direction_menu.addAction("Top").triggered.connect(lambda: self.set_view_direction(np.array([0, 1, 0])))
        view_direction_menu.addAction("Back").triggered.connect(lambda: self.set_view_direction(np.array([0, 0, -1])))
        view_direction_menu.addAction("Left").triggered.connect(lambda: self.set_view_direction(np.array([-1, 0, 0])))
        view_direction_menu.addAction("Bottom").triggered.connect(lambda: self.set_view_direction(np.array([0, -1, 0])))
        view_direction_menu.addSeparator()
        view_direction_menu.addAction("Isometric").triggered.connect(lambda: self.set_view_direction(np.array([1,1,1]), up=np.array([0, 1, 0])))
        view_direction_menu.addAction("Dimetric").triggered.connect(lambda: self.set_view_direction(np.array([0.333,0.333,0.882]), up=np.array([0, 1, 0])))
        view_direction_menu.addAction("Trimetric").triggered.connect(lambda: self.set_view_direction(np.array([0.393, 0.518, 0.761]), up=np.array([0, 1, 0])))


        add_menu = self.addMenu("Add")
        add_menu.addAction("Node").triggered.connect(lambda: self.add_node())
        add_menu.addAction("Plane").triggered.connect(lambda: self.add_reference_plane())
        add_menu.addAction("Group").triggered.connect(lambda: self.add_group())
        add_menu.addAction("Variable").triggered.connect(lambda: self.add_model_variable())


        solve_menu = self.addMenu("Solve")
        solve_menu.addAction("Solve System").triggered.connect(self.solve_system)

    def save_as_scene(self):
        pass

    def save_scene(self):
        self.document_manager.s
        pass

    def sync_docks(self, document: Document | None):
        self._save_active_dock_state()
        self._active_document = document

        if document is None:
            required_docks = set()
        else:
            required = document.required_docks()
            if isinstance(required, str):
                required_docks = {required}
            else:
                required_docks = set(required)

        self._restoring_docks = True

        for dock_key, dock in self._dock_widgets.items():
            allowed = dock_key in required_docks
            dock.setVisible(allowed)

            action = self._dock_actions.get(dock_key)
            if action is not None:
                action.setEnabled(allowed)
                action.setVisible(allowed)

        if document is not None and document.dock_layout_state:
            self.main_window.restoreState(document.dock_layout_state_bytes())

        self._restoring_docks = False

    def _save_active_dock_state(self):
        if self._restoring_docks:
            return

        if self._active_document is None:
            return

        self._active_document.set_dock_layout_state(self.main_window.saveState())

    def _on_dock_visibility_changed(self, _visible: bool):
        self._save_active_dock_state()

    def _on_dock_location_changed(self, *args):
        self._save_active_dock_state()

    def load_scene(self):
        pass

    def toggle_perspective(self, checked):
        self.document_manager.current_document.viewport.camera.perspective = checked

    def set_view_direction(self, direction, up=np.array([0, 1, 0])):
        self.document_manager.current_document.viewport.camera.set_view_direction(direction, up)

    def add_node(self):
        self.document_manager.current_document.scene_state.add_node(EditorNode(name="New Node", world_position=np.array([0.0, 0.0, 0.0])))
    
    def add_reference_plane(self):
        self.document_manager.current_document.scene_state.add_reference_plane(ReferencePlane(name="New Plane", p0=np.array([0.0, 0.0, 0.0]), p1=np.array([1.0, 0.0, 0.0]), p2=np.array([0.0, 1.0, 0.0]), mode="containing"))

    def add_group(self):
        self.document_manager.current_document.scene_state.add_group(NodeGroup(name="New Group", nodes=[]))

    def add_model_variable(self):
        self.document_manager.current_document.scene_state.add_model_variable(ModelVariableElement())



    def solve_system(self):
        print("Solving system...")
        result = self.document_manager.current_document.scene_manager.solve_system()
        if result.did_converge:
            print(f"System solved in {result.iterations} iterations with error {result.error:.6f}.")
            self.parent().status_bar.showMessage(f"System solved in {result.iterations} iterations with error {result.error:.6f}.", 5000)
        else:
            print(f"System did not converge after {result.iterations} iterations. Final error: {result.error:.6f}.")
            self.parent().status_bar.showMessage(f"System did not converge after {result.iterations} iterations. Final error: {result.error:.6f}.", 5000)

class StatusBar(QStatusBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.showMessage("Ready")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Suspension Designer Super Ultra Pro Max Deluxe Edition")

        container = QWidget()
        layout = QVBoxLayout(container)

        self.stack = QStackedWidget()

        self.document_manager = DocumentManager()

        self.workspaceBar = TabBar(self, self.document_manager)
        
        layout.addWidget(self.workspaceBar)
        layout.addWidget(self.stack)

        self.setCentralWidget(container)

        # self.setDockOptions(
        #     QMainWindow.DockOption.AnimatedDocks | 
        #     QMainWindow.DockOption.AllowNestedDocks | 
        #     QMainWindow.DockOption.AllowTabbedDocks
        # )

        # all_docks = [
        #     (PropertiesDock(self, self.scene_manager), Qt.RightDockWidgetArea),
        #     (SceneTreeDock(self, self.scene_manager), Qt.LeftDockWidgetArea)
        # ]

        # for dock_widget, location in all_docks:
        #     if location is not None:
        #         self.addDockWidget(location, dock_widget)
        #     else:
        #         self.addDockWidget(Qt.LeftDockWidgetArea, dock_widget)
        #         dock_widget.hide()  # start hidden

        self.tree_dock = TreeDock(self, document_manager=self.document_manager)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.tree_dock)

        self.property_dock = PropertiesDock(self, document_manager=self.document_manager)
        self.addDockWidget(Qt.RightDockWidgetArea, self.property_dock)

        self.tree_dock.hide()
        self.property_dock.hide()

        # self.toolbar = ToolBar(self)
        # self.addToolBar(self.toolbar)

        self.menu_bar = MenuBar(self,
            docks=[self.tree_dock, self.property_dock],
            document_manager=self.document_manager
        )
        self.setMenuBar(self.menu_bar)

        self.status_bar = StatusBar(self)
        self.setStatusBar(self.status_bar)

    def keyPressEvent(self, event):
        key = event.key()
        ctrl = event.modifiers() & Qt.ControlModifier
        shift = event.modifiers() & Qt.ShiftModifier
        # print(f"Key pressed: {event.key()}, modifiers: {event.modifiers()}")
        if key == Qt.Key.Key_S and ctrl:
            if shift:
                print("Ctrl+Shift+S pressed: Save all scenes")
                self.document_manager.save_all()
            else:
                print("Ctrl+S pressed: Save scene")
                self.document_manager.save_current()
        elif key == Qt.Key.Key_W and ctrl:
            self.document_manager.remove_document(self.document_manager.current_document)
        else:
            super().keyPressEvent(event)


    def closeEvent(self, event):
        print("Closing application and cleaning up resources...")
        # self.scene.plotter.clear()
        # self.scene.plotter.Finalize()
        # self.scene.plotter.interactor.Finalize()
        # self.scene.plotter.close()
        

        super().closeEvent(event)