from uuid import uuid4
import json

from PySide6.QtCore import (
    QAbstractItemModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Signal,
)
from PySide6.QtWidgets import QFileDialog

from src.rendering import Viewport3D
from src.motion import MotionData, MotionTableWidget
from src.solver import SolverResult
from src.structures import SelectionManager
from src.scene import SceneState
from src.tree_model import SceneTreeModel


DOCK_TREE = "tree"
DOCK_PROPERTIES = "properties"


class Document:
    def __init__(self, name: str, filepath: str = None):
        self.name = name
        self.has_changed = False
        self.filepath = filepath
        self.widget = None
        self.id = uuid4()
        self.selection_manager = SelectionManager()
        self.dock_layout_state: str | None = None

    def create_tree_model(self) -> QAbstractItemModel:
        return None

    def get_properties(self):
        pass

    def get_menus(self):
        pass

    def required_docks(self) -> tuple[str, ...]:
        return tuple()

    def set_dock_layout_state(self, state: QByteArray | str | None):
        if state is None:
            self.dock_layout_state = None
            return

        if isinstance(state, QByteArray):
            self.dock_layout_state = bytes(state.toBase64()).decode("ascii")
            return

        self.dock_layout_state = state

    def dock_layout_state_bytes(self) -> QByteArray:
        if not self.dock_layout_state:
            return QByteArray()

        return QByteArray.fromBase64(self.dock_layout_state.encode("ascii"))

    def create_widget(self):
        raise NotImplementedError("Subclasses must implement the create_widget method.")
    
    def _save(self, filepath: str, data: dict, type: str) -> bool:
        data = {
            "type": type,
            "name": self.name,
            "id": str(self.id),
            "dock_layout_state": self.dock_layout_state,
            **data,
        }

        if filepath is None:
            if self.filepath is None:
                filepath, _ = QFileDialog.getSaveFileName(
                    None,
                    "Save Project",
                    "",
                    "Project Files (*.proj)"
                )
                if not filepath:
                    print("Save operation cancelled.")
                    return False
            else:
                filepath = self.filepath

        self.filepath = filepath

        print(f"Saving document {self.name} to: {filepath}")

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        self.has_changed = False

        return True
    
    def save(self, filepath: str = None):
        raise NotImplementedError("Subclasses must implement the save method.")
    
    @staticmethod
    def load(filepath: str) -> 'Document':
        with open(filepath, "r") as f:
            data = json.load(f)

        type = data.get("type")

        name = data.get("name", "Untitled")

        if type == "editor":
            scene_state = SceneState.from_dict(data)
            document = EditorDocument(name=name, filepath=filepath, scene=scene_state)
        elif type == "results":
            solver_result = SolverResult.from_dict(data)
            document = ResultsDocument(name=name, filepath=filepath, solver_result=solver_result)
        elif type == "motion":
            motion_data = data.get("motion_data", data if "variables" in data else {})
            document = MotionDocument(name=name, filepath=filepath, motion_data=motion_data)
        else:
            raise ValueError(f"Unknown document type: {type}")

        document.set_dock_layout_state(data.get("dock_layout_state"))
        return document
    

class EditorDocument(Document):
    def __init__(self, name: str, filepath: str = None, scene: SceneState = None):
        super().__init__(name, filepath)
        self.scene_state = scene
        self.viewport = None

    def create_tree_model(self) -> QAbstractItemModel:
        return SceneTreeModel(self)

    def required_docks(self) -> tuple[str, ...]:
        return (DOCK_TREE, DOCK_PROPERTIES)

    def create_widget(self):
        # Create a widget to display the scene
        # This could be a custom QWidget that visualizes the scene
        viewport = Viewport3D(scene_state=self.scene_state, selection_manager=self.selection_manager)
        self.viewport = viewport
        self.widget = self.viewport
        return self.widget
    
    def save(self, filepath: str = None):
        # Implement saving logic for the scene document
        data = self.scene_state.to_dict()

        self._save(filepath, data, type="editor")


class ResultsDocument(Document):
    def __init__(self, name: str, filepath: str = None, solver_result: SolverResult = None):
        super().__init__(name, filepath)
        self.solver_result = solver_result

    def create_widget(self):
        pass

    def save(self, filepath: str = None):
        # Implement saving logic for the results document
        self._save(filepath, self.solver_result.to_dict(), type="results")

class MotionDocument(Document):
    def __init__(self, name: str, filepath: str = None, scene_state: SceneState = None, motion_data: MotionData | dict | None = None):
        super().__init__(name, filepath)
        self.scene_state = scene_state
        if isinstance(motion_data, MotionData):
            self.motion_data = motion_data
        else:
            self.motion_data = MotionData.from_dict(motion_data)

        if self.scene_state is not None and not self.motion_data.variables:
            self.motion_data = MotionData.from_scene_state(self.scene_state)

    def create_widget(self):
        self.widget = MotionTableWidget(
            self.motion_data,
            scene_state=self.scene_state,
            selection_manager=self.selection_manager,
        )
        return self.widget

    def required_docks(self) -> tuple[str, ...]:
        return tuple()

    def save(self, filepath: str = None):
        if self.scene_state is not None:
            self.motion_data.sync_from_scene_state(self.scene_state)

        self._save(filepath, {"motion_data": self.motion_data.to_dict()}, type="motion")

class DocumentManager(QObject):
    document_added = Signal(Document)
    document_removed = Signal(Document)

    selection_changed = Signal(Document)

    def __init__(self):
        super().__init__()

        self._documents: list[Document] = []
        
        self.selected_doc_index = None

    @property
    def current_document(self):
        if self.selected_doc_index is not None:
            return self._documents[self.selected_doc_index]
        return None

    def select_document(self, doc: Document):
        if doc is None:
            self.selected_doc_index = None
            self.selection_changed.emit(None)
        elif doc in self._documents:
            self.selected_doc_index = self._documents.index(doc)
            self.selection_changed.emit(doc)
        else:
            raise ValueError("Document not found in the manager.")

    def save_all(self):
        for doc in self._documents:
            doc.save()
            print(f"Saved {doc.name} to {doc.filepath}")

    def save_current(self):
        if self.selected_doc_index is None:
            print("No document is currently selected.")
            return
        
        current_doc = self._documents[self.selected_doc_index]  # Assuming the first document is the current one
        current_doc.save()
        print(f"Saved {current_doc.name} to {current_doc.filepath}")

    def save_current_as(self):
        if self.selected_doc_index is None:
            print("No document is currently selected.")
            return
        
        current_doc = self._documents[self.selected_doc_index]  # Assuming the first document is the current one
        current_doc.filepath = None
        current_doc.save()
        print(f"Saved {current_doc.name} to {current_doc.filepath}")

    def load(self):
        filepath, _ = QFileDialog.getOpenFileName(
            None,
            "Load Project",
            "",
            "Project Files (*.proj)"
        )
        if not filepath:
            print("Load operation cancelled.")
            return
        
        try:
            document = Document.load(filepath)
            self.add_document(document)
            self.select_document(document)
            print(f"Loaded document {document.name} from {filepath}")
        except Exception as e:
            print(f"Failed to load document: {e}")

    def get_document(self, index):
        if 0 <= index < len(self._documents):
            return self._documents[index]
        raise IndexError("Document index out of range.")

    def add_document(self, document: Document, select=False):
        self._documents.append(document)
        self.document_added.emit(document)
        if select:
            self.select_document(document)

    def remove_document(self, document: Document):
        if document not in self._documents:
            raise ValueError("Document not found in the manager.")
        
        self._documents.remove(document)
        self.document_removed.emit(document)

        if len(self._documents) > 0:
            self.select_document(self._documents[min(self.selected_doc_index, len(self._documents)-1)])
        else:
            self.select_document(None)

        if document.widget is not None:
            document.widget.deleteLater()  # Ensure the widget is properly deleted
            document.widget = None  # Clear the reference to the widget