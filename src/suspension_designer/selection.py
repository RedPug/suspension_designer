from uuid import UUID, uuid4

from PySide6.QtCore import (QObject, Signal)

from suspension_designer.properties import Property

class Selectable(QObject):
    did_change = Signal()

    def __init__(self, name:str, *, id: UUID = None):
        super().__init__()
        self._name = name
        self._id = id if id is not None else uuid4()
    
    @property
    def id(self):
        return self._id
    
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = str(value)
        self.did_change.emit()

    def get_property_list(self) -> dict[str, list[Property]]:
        return {}

class SelectionManager(QObject):
    selection_changed = Signal()  # Signal to emit when selection changes

    def __init__(self):
        super().__init__()

        self._selected_object: Selectable = None
        self._subselections: list[Selectable] = []

        # self.selection_changed.connect(lambda: print(f"Selection changed to: {self._selected_object}"))

    def on_selection_modified(self):
        self._update_subselections()
        self.selection_changed.emit()

    def _update_subselections(self):
        if self._selected_object is None:
            self._subselections = []
        else:
            if hasattr(self._selected_object, 'get_subselections'):
                self._subselections = self._selected_object.get_subselections()
            else:
                self._subselections = []

    def set_selected(self, item: Selectable):
        if self._selected_object == item:
            return  # No change in selection
        
        if self._selected_object is not None:
            self._selected_object.did_change.disconnect(self.on_selection_modified)

        self._selected_object = item

        if self._selected_object is not None:
            self._selected_object.did_change.connect(self.on_selection_modified)

        # self._update_subselections()

        self.on_selection_modified()

    def get_selected(self) -> Selectable:
        return self._selected_object

    @property
    def subselections(self) -> list[Selectable]:
        return self._subselections