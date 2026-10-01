from abc import abstractmethod

from typing import TYPE_CHECKING

from PySide6.QtCore import (QObject, Signal)

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

class CommandFactory:
    @abstractmethod
    def create(self, value) -> Command:
        pass

class NonLocalCommand(Command):
    def execute(self, document: 'EditorDocument'):
        self._previous_state = document.scene_state.copy()

    def undo(self, document: 'EditorDocument'):
        document.scene_state.restore(self._previous_state)

class NonLocalModifyElementCommand(NonLocalCommand):
    def __init__(self, element_id, property_name, value):
        self._element_id = element_id
        self._property_name = property_name
        self._new_value = value

    def execute(self, document: 'EditorDocument'):
        super().execute(document)

        element = document.scene_state.get_element_by_id(self._element_id)
        if element:
            # print("Modifying element", self._element_id, "property", self._property_name, "to", self._new_value)
            setattr(element, self._property_name, self._new_value)
            # print("Element modified:", element)
        else:
            print("Element not found:", self._element_id)

class NonLocalModifyElementCommandFactory(CommandFactory):
    def __init__(self, element_id, property_name):
        self.element_id = element_id
        self.property_name = property_name

    def create(self, value):
        return NonLocalModifyElementCommand(self.element_id, self.property_name, value)

class LocalModifyElementCommand(Command):
    def __init__(self, element_id, property_name, value):
        self._element_id = element_id
        self._property_name = property_name
        self._new_value = value
        self._old_value = ...

    def execute(self, document: 'EditorDocument'):
        element = document.scene_state.get_element_by_id(self._element_id)
        self._old_value = getattr(element, self._property_name)

        if element:
            setattr(element, self._property_name, self._new_value)
        else:
            print("Element not found:", self._element_id)

    def undo(self, document: 'EditorDocument'):
        element = document.scene_state.get_element_by_id(self._element_id)
        if element and self._old_value is not ...:
            setattr(element, self._property_name, self._old_value)

class LocalModifyElementCommandFactory(CommandFactory):
    def __init__(self, element_id, property_name):
        self.element_id = element_id
        self.property_name = property_name

    def create(self, value):
        return LocalModifyElementCommand(self.element_id, self.property_name, value)

Keybinds.UNDO.key_pressed.connect(lambda: CommandManager.current.undo())
Keybinds.REDO.key_pressed.connect(lambda: CommandManager.current.redo())

class CommandManager(QObject):
    did_undo = Signal()

    current: 'CommandManager' = None
    MAX_UNDO_STACK_SIZE = 100

    def __init__(self, document: 'Document'):
        super().__init__()
        self.document = document
        self.undo_stack: list[Command] = []
        self.redo_stack: list[Command] = []

    def set_active(self):
        if CommandManager.current is self:
            return
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

            self.did_undo.emit()
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