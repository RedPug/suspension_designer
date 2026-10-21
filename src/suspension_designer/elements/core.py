from enum import Enum, StrEnum, auto
from time import perf_counter
from typing import Any, Callable, List, Literal, Optional, Union
from uuid import UUID, uuid4

from PySide6.QtCore import (QObject, Signal)

import numpy as np

# from src.solver import SolverState, solve_system, SolverResult
from suspension_designer.editor.commands import CommandFactory, LocalModifyElementCommand, LocalModifyElementCommandFactory, NonLocalModifyElementCommand, NonLocalModifyElementCommandFactory
from suspension_designer.user_interface.properties import DropdownPropertyEditorFactory, GroupPropertyEditorFactory, NumberPropertyEditorFactory, Property, StringPropertyEditorFactory
# from src.scene import SceneState
from suspension_designer.user_interface.selection import Selectable


class EditorElement(Selectable):
    def __init__(self, name: str, *, id: UUID = None):
        super().__init__(name, id=id)

    def fill_references(self, id_to_element: dict[UUID, 'EditorElement']):
        pass

    def to_dict(self) -> dict:
        raise NotImplementedError("to_dict method must be implemented by subclasses of EditorElement.")

    @staticmethod
    def from_dict(data: dict) -> 'EditorElement':
        raise NotImplementedError("from_dict method must be implemented by subclasses of EditorElement.")