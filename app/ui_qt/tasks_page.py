from __future__ import annotations

from pathlib import Path

from app.main_qt import TaskQtWindow


class TasksPage(TaskQtWindow):
    """Обновлённый экран задач как самостоятельная страница UI."""

    def __init__(self, db_path: Path):
        super().__init__(db_path)
