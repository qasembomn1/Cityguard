from PySide6.QtCore import QObject,Signal
class BaseStore(QObject):
    changed = Signal()
    error = Signal(str)
    success = Signal(str)

    def emit_success(self, text: str) -> None:
        self.success.emit(text)
        self.changed.emit()

    def emit_error(self, text: str) -> None:
        self.error.emit(text)
