from uuid import uuid4
import json
import os
import csv

import numpy as np

from PySide6.QtCore import (
    QAbstractItemModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    Signal,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QClipboard, QKeySequence


from suspension_designer.properties import Property, StringPropertyType
from suspension_designer.rendering import Viewport3D
from suspension_designer.motion import MotionData, MotionTableWidget
from suspension_designer.solver import SolverResult
from suspension_designer.selection import SelectionManager, Selectable
from suspension_designer.scene import SceneState
from suspension_designer.tree_model import SceneTreeModel
from suspension_designer.results_compiler import ResultsCompilation, ResultsCompiler
from suspension_designer.data_manager import save_csv, save_json, get_filepath



DOCK_TREE = "tree"
DOCK_PROPERTIES = "properties"


class Document(Selectable):
    def __init__(self, name: str, filepath: str = None):
        super().__init__(name)

        self.has_changed = False
        self.did_change.connect(lambda: setattr(self, "has_changed", True))

        self.filepath = filepath

        self.widget = None
        self.document_manager = None

        self.selection_manager = SelectionManager()
        self.dock_layout_state: str | None = None

    def create_tree_model(self) -> QAbstractItemModel:
        return None

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
    
    def get_property_list(self):
        return {
            "Info":[
                Property("ID",
                    get=lambda _: self.id,
                    type=StringPropertyType()
                ),
                Property("Name",
                    get=lambda _: self.name,
                    set=lambda name, _: setattr(self, 'name', name),
                    type=StringPropertyType()
                ),
                Property("Filepath",
                    get=lambda _: self.filepath,
                    type=StringPropertyType()
                ),
            ]
        }
    
    def _save_proj(self, filepath: str, data: dict, type: str) -> tuple[bool, str | None]:
        data = {
            "type": type,
            "name": self.name,
            "id": str(self.id),
            "document_data": data,
        }

        if filepath is not None:
            self.filepath = filepath
            if save_json(filepath, data):
                return True, filepath
            
        return False, None

    def save(self, prompt_user: bool = False) -> tuple[bool, str | None]:
        raise NotImplementedError("Subclasses must implement the save method.")

    @staticmethod
    def load(filepath: str) -> 'Document':
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error occurred while loading document from {filepath}: {e}")
            return None

        type = data.get("type")

        name = data.get("name", "Untitled")

        doc_data = data.get("document_data", data)

        document = None

        if type == "editor":

            scene_state = SceneState.from_dict(doc_data)
            document = EditorDocument(name=name, filepath=filepath, scene=scene_state)

        elif type == "results":
            if "times" in doc_data and "rows" in doc_data:
                compilation = ResultsCompilation(
                    times=doc_data.get("times", []),
                    variable_columns=doc_data.get("variable_columns", []),
                    rows=doc_data.get("rows", []),
                    steps=[],
                )
                document = ResultDocument(name=name, filepath=filepath, compilation=compilation)
        elif type == "motion":
            motion_data = doc_data.get("motion_data")
            document = MotionDocument(
                name=name,
                filepath=filepath,
                motion_data=motion_data,
                editor_filepath=doc_data.get("editor_filepath"),
            )
        else:
            raise ValueError(f"Unknown document type: {type}")
        
        if document is not None:
            return document
        else:
            raise ValueError(f"Failed to create document from filepath: {filepath}")
    
    

class EditorDocument(Document):
    def __init__(self, name: str, filepath: str = None, scene: SceneState = None):
        super().__init__(name, filepath)
        self.scene_state = scene if scene is not None else SceneState()
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
    
    def save(self, prompt_user: bool = False) -> tuple[bool, str | None]:
        # Implement saving logic for the scene document
        data = self.scene_state.to_dict()

        filepath = get_filepath(default_path=self.filepath if not prompt_user else None, prompt="Save Editor Document", filter=["proj"])

        if not filepath:
            return False, None
        
        if self._save_proj(filepath, data, type="editor"):
            return True, filepath
        return False, None


class CopyableTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

    def keyPressEvent(self, event):
        # Override Ctrl+C for copying table values to clipboard
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection_to_clipboard()
        else:
            super().keyPressEvent(event)

    def copy_selection_to_clipboard(self):
        selection = self.selectedRanges()
        if not selection:
            return

        text_parts = []
        
        for range_obj in selection:
            # 1. Extract and append headers for the selected columns
            header_values = []
            for c in range(range_obj.leftColumn(), range_obj.rightColumn() + 1):
                header_item = self.horizontalHeaderItem(c)
                # Fallback to column index number if no explicit header text is set
                header_text = header_item.text() if header_item else f"Column {c+1}"
                header_values.append(header_text)
            
            text_parts.append("\t".join(header_values))

            # 2. Extract and append the corresponding row data
            for r in range(range_obj.topRow(), range_obj.bottomRow() + 1):
                row_values = []
                for c in range(range_obj.leftColumn(), range_obj.rightColumn() + 1):
                    item = self.item(r, c)
                    row_values.append(item.text() if (item and item.text()) else "")
                
                text_parts.append("\t".join(row_values))

        # Join everything with newlines and send to system clipboard
        text_data = "\n".join(text_parts) + "\n"
        QApplication.clipboard().setText(text_data)

class ResultDocument(Document):
    def __init__(self, name: str, filepath: str = None, compilation: ResultsCompilation = None):
        super().__init__(name, filepath)
        self.compilation = compilation
        self.table_widget = None

    def create_widget(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        if self.compilation is None:
            layout.addWidget(QLabel("No results available."))
            self.widget = widget
            return self.widget

        if self.compilation is not None:
            layout.addWidget(QLabel("Compilation Results"))
            headers, table_rows = self.compilation.to_table()

            table = CopyableTableWidget(widget)
            table.setColumnCount(len(headers))
            table.setRowCount(len(table_rows))
            table.setHorizontalHeaderLabels(headers)
            table.verticalHeader().setVisible(False)
            # table.setSelectionBehavior(QAbstractItemView.SelectRows)
            # table.setSelectionMode(QAbstractItemView.SingleSelection)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)

            for row_index, row in enumerate(table_rows):
                for column_index, value in enumerate(row):
                    table.setItem(row_index, column_index, QTableWidgetItem("" if value is None else str(value)))

            self.table_widget = table
            layout.addWidget(table)
        else:
            layout.addWidget(QLabel(str(self.solver_result)))

        self.widget = widget
        return self.widget

    def save(self, prompt_user: bool = False) -> bool:
        # Implement saving logic for the results document
        filepath = get_filepath(default_path=self.filepath if not prompt_user else None, prompt="Save Results", filter=["proj","csv"])
        if not filepath:
            return False, None
        
        ext = os.path.splitext(filepath)[1]
        if ext == ".csv":
            if save_csv(filepath, header=["time"] + self.compilation.variable_columns, rows=self.compilation.rows):
                return True, filepath
        elif ext == ".proj":
            if self.compilation is not None:
                data = {
                    "times": self.compilation.times,
                    "variable_columns": self.compilation.variable_columns,
                    "rows": self.compilation.rows,
                }
            else:
                data = {}
            if self._save_proj(filepath, data, type="results"):
                return True, filepath
        else:
            print(f"Unsupported file format: {ext}")
        return False, None



class MotionDocument(Document):
    def __init__(self, name: str, filepath: str = None, scene_state: SceneState = None, motion_data: MotionData | dict | None = None, editor_filepath: str | None = None):
        super().__init__(name, filepath)
        self.scene_state = scene_state
        self.editor_filepath = editor_filepath

        if isinstance(motion_data, MotionData):
            self.motion_data = motion_data
        else:
            self.motion_data = MotionData.from_dict(motion_data)

        if self.scene_state is not None and not self.motion_data.variables:
            self.motion_data = MotionData.from_scene_state(self.scene_state)

        if self.scene_state is None and self.editor_filepath:
            self.resolve_source_scene_state()

    def resolve_source_scene_state(self):
        if self.document_manager is not None and self.editor_filepath:
            source_document = self.document_manager.get_document_by_filepath(self.editor_filepath)
            if isinstance(source_document, EditorDocument):
                self.scene_state = source_document.scene_state
                return self.scene_state

        if self.editor_filepath and os.path.exists(self.editor_filepath):
            try:
                source_document = Document.load(self.editor_filepath)
            except Exception as error:
                print(f"Failed to load source editor document from '{self.editor_filepath}': {error}")
                return self.scene_state

            if isinstance(source_document, EditorDocument):
                self.scene_state = source_document.scene_state

        return self.scene_state

    def solve_into_result_document(self):
        self.resolve_source_scene_state()

        if self.scene_state is None:
            print("No scene state available to solve.")
            return None

        if self.document_manager is None:
            print("Motion document is not attached to a document manager.")
            return None

        self.motion_data.sync_from_scene_state(self.scene_state)

        compiler = ResultsCompiler(
            self.scene_state,
            self.motion_data,
            start_time=0.0,
            end_time=1.0,
            step=0.01,
        )
        compilation = compiler.compile()

        result_document = ResultDocument(
            name=f"{self.name} Results",
            compilation=compilation,
        )

        self.document_manager.add_document(result_document, select=True)
        return result_document

    def solve_into_editor_document(self):
        return self.solve_into_result_document()

    def sync_from_editor_document(self, editor_document: EditorDocument | None):
        if editor_document is None:
            return

        self.scene_state = editor_document.scene_state
        if self.scene_state is not None:
            self.motion_data.sync_from_scene_state(self.scene_state)

        if self.widget is not None:
            if hasattr(self.widget, "set_scene_state"):
                self.widget.set_scene_state(self.scene_state)
            else:
                self.widget.scene_state = self.scene_state
                self.widget.refresh()

    def create_widget(self):
        self.widget = MotionTableWidget(
            self.motion_data,
            scene_state=self.scene_state,
            selection_manager=self.selection_manager,
            solve_callback=self.solve_into_result_document,
        )
        return self.widget

    def required_docks(self) -> tuple[str, ...]:
        return (DOCK_TREE, DOCK_PROPERTIES)

    def save(self, prompt_user: bool = False) -> tuple[bool, str | None]:
        filepath = get_filepath(default_path=self.filepath if not prompt_user else None, prompt="Save Motion Document", filter=["proj"])

        if not filepath:
            return False, None

        if self.scene_state is not None:
            self.motion_data.sync_from_scene_state(self.scene_state)

        if self._save_proj(
            filepath,
            {
                "motion_data": self.motion_data.to_dict(),
                "editor_filepath": self.editor_filepath,
            },
            type="motion",
        ):
            return True, filepath
        return False, None


class DocumentManager(QObject):
    document_added = Signal(Document)
    document_removed = Signal(Document)

    document_changed = Signal(Document)

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

    def get_document_by_filepath(self, filepath: str):
        if not filepath:
            return None

        normalized_target = os.path.normcase(os.path.abspath(filepath))

        for document in self._documents:
            if not document.filepath:
                continue

            normalized_document_path = os.path.normcase(os.path.abspath(document.filepath))
            if normalized_document_path == normalized_target:
                return document

        return None

    def select_document(self, doc: Document):
        if doc is None:
            self.selected_doc_index = None
            self.selection_changed.emit(None)
        elif doc in self._documents:
            self.selected_doc_index = self._documents.index(doc)

            if isinstance(doc, MotionDocument):
                source_document = self.get_document_by_filepath(doc.editor_filepath)
                if isinstance(source_document, EditorDocument):
                    doc.sync_from_editor_document(source_document)

            self.selection_changed.emit(doc)
        else:
            raise ValueError("Document not found in the manager.")

    def save_all(self):
        for doc in self._documents:
            _, path = doc.save()
            print(f"Saved {doc.name} to {path}")

    def save_current(self):
        if self.selected_doc_index is None:
            print("No document is currently selected.")
            return
        
        current_doc = self._documents[self.selected_doc_index]
        _, path = current_doc.save()
        print(f"Saved {current_doc.name} to {path}")

    def save_current_as(self):
        if self.selected_doc_index is None:
            print("No document is currently selected.")
            return
        
        current_doc = self._documents[self.selected_doc_index]
        _, path = current_doc.save(prompt_user=True)
        print(f"Saved {current_doc.name} to {path}")

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
            if document is not None:
                self.add_document(document)
                self.select_document(document)
                print(f"Loaded document {document.name} from {filepath}")
            else:
                raise ValueError("Failed to load document. The file may be corrupted or of an unsupported type.")
        except Exception as e:
            print(f"Failed to load document: {e}")

    def get_document(self, index):
        if 0 <= index < len(self._documents):
            return self._documents[index]
        raise IndexError("Document index out of range.")

    def add_document(self, document: Document, select=False):
        document.did_change.connect(lambda: self.document_changed.emit(document))

        document.document_manager = self
        self._documents.append(document)
        self.document_added.emit(document)
        if select:
            self.select_document(document)
        
        

    def remove_document(self, document: Document):
        if document not in self._documents:
            raise ValueError("Document not found in the manager.")
        
        document.did_change.disconnect(lambda: self.document_changed.emit(document))
        
        self._documents.remove(document)
        self.document_removed.emit(document)

        document.document_manager = None

        if len(self._documents) > 0:
            self.select_document(self._documents[min(self.selected_doc_index, len(self._documents)-1)])
        else:
            self.select_document(None)

        if document.widget is not None:
            document.widget.deleteLater()  # Ensure the widget is properly deleted
            document.widget = None  # Clear the reference to the widget

    def create_new_editor_document(self, name: str = "New Document"):
        new_doc = EditorDocument(name=name)
        self.add_document(new_doc, select=True)
    
    def create_new_motion_document(self):
        if self.current_document is not None and isinstance(self.current_document, EditorDocument):
            editor_doc = self.current_document
        else:
            editor_doc = next((doc for doc in self._documents if isinstance(doc, EditorDocument)), None)

        if editor_doc is None:
            print("No editor document available to create a motion document from.")
            return

        motion_document = MotionDocument(
        name=f"{editor_doc.name} Motion",
        scene_state=editor_doc.scene_state,
        editor_filepath=editor_doc.filepath,
        )

        self.add_document(motion_document, select=True)
