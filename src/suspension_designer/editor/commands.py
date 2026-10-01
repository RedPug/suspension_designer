from abc import abstractmethod

from typing import TYPE_CHECKING

from suspension_designer.editor.keybinds import Keybinds

# Prevent circular imports during runtime type checking
if TYPE_CHECKING:
    from suspension_designer.graphics.document import Document, EditorDocument

class Command:
    @abstractmethod
    def execute(self, document: 'Document'):
        pass

    @abstractmethod
    def undo(self, document: 'Document'):
        pass

class StateChangingCommand(Command):
    def execute(self, document: 'EditorDocument'):
        self._previous_state = document.scene_state.copy()

    def undo(self, document: 'EditorDocument'):
        document.scene_state.restore(self._previous_state)


class ModifyElementCommand(StateChangingCommand):
    def __init__(self, element_id, property_name, value):
        self._element_id = element_id
        self._property_name = property_name
        self._new_value = value

    def execute(self, document: 'EditorDocument'):
        super().execute(document)

        element = document.scene_state.get_element_by_id(self._element_id, force_refresh=True)
        if element:
            # print("Modifying element", self._element_id, "property", self._property_name, "to", self._new_value)
            setattr(element, self._property_name, self._new_value)
            # print("Element modified:", element)
        else:
            print("Element not found:", self._element_id)

class CommandFactory:
    def __init__(self, cls, **kwargs):
        self.cls = cls
        self.kwargs = kwargs

    def create(self, **kwargs):
        return self.cls(**self.kwargs, **kwargs)

Keybinds.UNDO.key_pressed.connect(lambda: CommandManager.current.undo())
Keybinds.REDO.key_pressed.connect(lambda: CommandManager.current.redo())

class CommandManager:
    current: 'CommandManager' = None
    MAX_UNDO_STACK_SIZE = 100

    def __init__(self, document: 'Document'):
        self.document = document
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []

    def set_active(self):
        print(f"Setting active CommandManager for document: {self.document}")
        CommandManager.current = self

    def execute_command(self, command: Command):
        print(f"Executing command: {command.__class__.__name__}")

        command.execute(self.document)

        self.undo_stack.append(command)
        if len(self.undo_stack) > self.MAX_UNDO_STACK_SIZE:
            self.undo_stack.pop(0)

        self.redo_stack.clear()
        print("Clearing redo stack")

    def undo(self):
        if len(self.undo_stack) > 0:
            print("Undoing command")
            command = self.undo_stack.pop()
            command.undo(self.document)
            self.redo_stack.append(command)
            if len(self.redo_stack) > self.MAX_UNDO_STACK_SIZE:
                self.redo_stack.pop(0)
        else:
            print("Undo stack is empty, nothing to undo")

    def redo(self):
        if len(self.redo_stack) > 0:
            print("Redoing command")
            command = self.redo_stack.pop()
            print(f"Executing command: {command.__class__.__name__}")
            command.execute(self.document)
            self.undo_stack.append(command)
            if len(self.undo_stack) > self.MAX_UNDO_STACK_SIZE:
                self.undo_stack.pop(0)
        else:
            print("Redo stack is empty, nothing to redo")