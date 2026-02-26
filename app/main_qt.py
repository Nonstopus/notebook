from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .services import tasks as task_service
from .storage import DB_NAME

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QInputDialog,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - runtime guard for optional GUI dependency
    raise SystemExit(
        "PySide6 не установлен. Установите зависимости: pip install -r requirements.txt"
    ) from exc


DB_PATH = Path(DB_NAME)


class TaskQtWindow(QMainWindow):
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self._tasks_cache = []
        task_service.init_db(self.db_path)

        self.setWindowTitle("Task Tracker Desktop (Qt)")
        self.resize(640, 480)
        self._build_ui()
        self.refresh_tasks()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.tasks_list = QListWidget(self)
        self.tasks_list.itemDoubleClicked.connect(lambda _: self.toggle_task())
        layout.addWidget(self.tasks_list)

        actions = QHBoxLayout()

        add_btn = QPushButton("Добавить", self)
        add_btn.clicked.connect(self.add_task)
        actions.addWidget(add_btn)

        toggle_btn = QPushButton("Готово/Не готово", self)
        toggle_btn.clicked.connect(self.toggle_task)
        actions.addWidget(toggle_btn)

        delete_btn = QPushButton("Удалить", self)
        delete_btn.clicked.connect(self.delete_task)
        actions.addWidget(delete_btn)

        refresh_btn = QPushButton("Обновить", self)
        refresh_btn.clicked.connect(self.refresh_tasks)
        actions.addWidget(refresh_btn)

        layout.addLayout(actions)
        self.setCentralWidget(central)

    def refresh_tasks(self) -> None:
        self.tasks_list.clear()
        self._tasks_cache = task_service.list_tasks(self.db_path)
        for task in self._tasks_cache:
            progress = task_service.subtask_progress(self.db_path, task.id)
            reminder_flag = " ⏰" if task.reminder_datetime else ""
            prefix = "📁 " if progress[1] > 0 else ""
            label = (
                f"[{'✓' if task.is_done else ' '}] {prefix}{task.title}{reminder_flag} "
                f"({progress[0]}/{progress[1]}, subtasks: {progress[1]})"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.tasks_list.addItem(item)

    def _selected_task(self):
        row = self.tasks_list.currentRow()
        if row < 0 or row >= len(self._tasks_cache):
            return None
        return self._tasks_cache[row]

    def add_task(self) -> None:
        title, ok = QInputDialog.getText(self, "Новая задача", "Введите название задачи")
        if not ok:
            return

        cleaned_title = title.strip()
        if not cleaned_title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название задачи")
            return

        task_service.create_task(self.db_path, cleaned_title)
        self.refresh_tasks()

    def toggle_task(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для обновления")
            return

        updated = task_service.update_task(self.db_path, task.id, is_done=not task.is_done)
        if updated:
            self.refresh_tasks()

    def delete_task(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для удаления")
            return

        answer = QMessageBox.question(self, "Удалить задачу", f"Удалить '{task.title}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return

        task_service.delete_task(self.db_path, task.id)
        self.refresh_tasks()


def main() -> int:
    app = QApplication(sys.argv)
    window = TaskQtWindow(DB_PATH)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
