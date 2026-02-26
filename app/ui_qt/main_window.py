from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget

from .boards_page import BoardsPage
from .tasks_page import TasksPage


class MainWindow(QMainWindow):
    SETTINGS_ORG = "notebook"
    SETTINGS_APP = "task-tracker-qt"
    SETTINGS_TAB_KEY = "main/active_tab"

    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self.settings = QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)

        self.tasks_page = TasksPage(db_path)
        self.boards_page = BoardsPage(db_path)

        self.tabs = QTabWidget(self)
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.tabs.addTab(self.tasks_page, "Задачи")
        self.tabs.addTab(self.boards_page, "Канбан")
        self.tabs.currentChanged.connect(self._persist_active_tab)

        self.setWindowTitle("Task Tracker Desktop (Qt)")
        self.resize(1180, 700)
        self.setCentralWidget(self.tabs)

        self._setup_shortcuts()
        self._restore_active_tab()

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.tabs.setCurrentIndex(0))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.tabs.setCurrentIndex(1))
        QShortcut(QKeySequence("Ctrl+Tab"), self, activated=self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, activated=self._prev_tab)

    def _next_tab(self) -> None:
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % self.tabs.count())

    def _prev_tab(self) -> None:
        self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % self.tabs.count())

    def _persist_active_tab(self, index: int) -> None:
        self.settings.setValue(self.SETTINGS_TAB_KEY, index)
        if self.tabs.currentWidget() is self.boards_page:
            self.boards_page.refresh_boards()

    def _restore_active_tab(self) -> None:
        raw_index = self.settings.value(self.SETTINGS_TAB_KEY, 0)
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            index = 0
        index = max(0, min(index, self.tabs.count() - 1))
        self.tabs.setCurrentIndex(index)

    def closeEvent(self, event) -> None:
        self._persist_active_tab(self.tabs.currentIndex())
        super().closeEvent(event)
