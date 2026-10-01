from PySide6.QtCore import (QObject, Qt, Signal)

class Keybind(QObject):
    key_pressed = Signal()

    def __init__(self, key: int, ctrl: bool = False, alt: bool = False, shift: bool = False):
        super().__init__()

        self.key = key
        self.ctrl = ctrl
        self.alt = alt
        self.shift = shift

    def handle_event(self, event):
        if self.matches(event):
            self.key_pressed.emit()
            return True
        return False

    def matches(self, event) -> bool:
        if event.key() != self.key:
            return False

        expected_modifiers = Qt.NoModifier
        if self.ctrl:
            expected_modifiers |= Qt.ControlModifier
        if self.alt:
            expected_modifiers |= Qt.AltModifier
        if self.shift:
            expected_modifiers |= Qt.ShiftModifier

        return event.modifiers() == expected_modifiers

class Keybinds:
    UNDO = Keybind(Qt.Key.Key_Z, ctrl=True)
    REDO = Keybind(Qt.Key.Key_Z, ctrl=True, shift=True)
    SAVE = Keybind(Qt.Key.Key_S, ctrl=True)
    SAVE_ALL = Keybind(Qt.Key.Key_S, ctrl=True, shift=True)
    CLOSE_DOCUMENT = Keybind(Qt.Key.Key_W, ctrl=True)

    @classmethod
    def all(cls):
        return (
            value
            for value in vars(cls).values()
            if isinstance(value, Keybind)
        )