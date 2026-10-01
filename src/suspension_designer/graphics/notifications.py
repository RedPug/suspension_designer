from time import time

from PySide6.QtCore import QObject

from PySide6.QtWidgets import (
    QStatusBar
)

class NotificationManager:
    status_bar = None
    
    @staticmethod
    def bind_status_bar(status_bar: QStatusBar):
        NotificationManager.status_bar = status_bar
