import os

from suspension_designer.document import Document
from suspension_designer.graphics import MainWindow
from PySide6.QtWidgets import QApplication
from suspension_designer.settings import SettingsManager


if __name__ == "__main__":

    print("Starting...")

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