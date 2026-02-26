from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QListWidget, QHBoxLayout, QVBoxLayout, QWidget

from app.services import tasks as task_service


class BoardsPage(QWidget):
    """Экран канбан-досок."""

    def __init__(self, db_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.db_path = db_path
        self.todo_list = QListWidget(self)
        self.in_progress_list = QListWidget(self)
        self.done_list = QListWidget(self)
        self._build_ui()
        self.refresh_boards()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.addLayout(self._column("К выполнению", self.todo_list))
        root.addLayout(self._column("В работе", self.in_progress_list))
        root.addLayout(self._column("Готово", self.done_list))

    def _column(self, title: str, list_widget: QListWidget) -> QVBoxLayout:
        column = QVBoxLayout()
        label = QLabel(title, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(label)
        list_widget.setAlternatingRowColors(True)
        column.addWidget(list_widget)
        return column

    def refresh_boards(self) -> None:
        for widget in (self.todo_list, self.in_progress_list, self.done_list):
            widget.clear()

        all_tasks = task_service.list_tasks(self.db_path)
        for index, task in enumerate(all_tasks):
            if task.is_done:
                self.done_list.addItem(f"#{task.id} {task.title}")
            elif index % 2 == 0:
                self.in_progress_list.addItem(f"#{task.id} {task.title}")
            else:
                self.todo_list.addItem(f"#{task.id} {task.title}")
