import os
import threading
import numpy as np

from PySide6.QtWidgets import QApplication

from suspension_designer.graphics.document import Document
from suspension_designer.editor.graphics import MainWindow
from suspension_designer.settings import SettingsManager
from suspension_designer.solver.solver import Solver

def _background_compiler_warmup():
    """Trigger compilation on a secondary thread with dummy data."""
    try:
        # 1. Create a minimal dummy dataset matching your exact structure shapes
        dummy_nodes = np.array([[0,0,0],[1,0,0]], dtype=np.float64)
        dummy_groups = [[0,1]]
        dummy_linkages = []
        dummy_displacements = []
        
        # 2. Instantiate and run the solver once
        solver = Solver.from_connections(
            dummy_nodes, dummy_groups, dummy_linkages, dummy_displacements
        )
        # This will silently compile the class methods in the background
        solver.solve(max_iterations=1)
        print("Numba Solver background compilation complete!")
    except Exception as e:
        print(f"Failed to background compile: {e}")


if __name__ == "__main__":

    print("Starting...")

    # --- Call this right when your application main() starts up ---
    warmup_thread = threading.Thread(target=_background_compiler_warmup, daemon=True)
    warmup_thread.start()

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

    app.exec()