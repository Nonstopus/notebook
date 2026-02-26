from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .services import tasks as task_service
from .storage import DB_NAME

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QDateTimeEdit,
        QDialog,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
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


class TaskDetailDialog(QDialog):
    def __init__(self, db_path: Path, task_id: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db_path = db_path
        self.task_id = task_id
        self._subtasks_cache = []

        self.setWindowTitle("Детали задачи")
        self.resize(520, 420)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Название", self))
        self.title_input = QLineEdit(self)
        title_row.addWidget(self.title_input)
        save_title_btn = QPushButton("Сохранить", self)
        save_title_btn.clicked.connect(self.save_title)
        title_row.addWidget(save_title_btn)
        layout.addLayout(title_row)

        reminder_row = QHBoxLayout()
        reminder_row.addWidget(QLabel("Напоминание", self))
        self.reminder_input = QDateTimeEdit(self)
        self.reminder_input.setCalendarPopup(True)
        self.reminder_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        reminder_row.addWidget(self.reminder_input)

        save_reminder_btn = QPushButton("Сохранить", self)
        save_reminder_btn.clicked.connect(self.save_reminder)
        reminder_row.addWidget(save_reminder_btn)

        clear_reminder_btn = QPushButton("Очистить", self)
        clear_reminder_btn.clicked.connect(self.clear_reminder)
        reminder_row.addWidget(clear_reminder_btn)
        layout.addLayout(reminder_row)

        layout.addWidget(QLabel("Подзадачи", self))
        self.subtasks_list = QListWidget(self)
        self.subtasks_list.itemDoubleClicked.connect(lambda _: self.toggle_subtask())
        layout.addWidget(self.subtasks_list)

        subtask_actions = QHBoxLayout()
        add_subtask_btn = QPushButton("Добавить", self)
        add_subtask_btn.clicked.connect(self.add_subtask)
        subtask_actions.addWidget(add_subtask_btn)

        toggle_subtask_btn = QPushButton("Готово/Не готово", self)
        toggle_subtask_btn.clicked.connect(self.toggle_subtask)
        subtask_actions.addWidget(toggle_subtask_btn)

        delete_subtask_btn = QPushButton("Удалить", self)
        delete_subtask_btn.clicked.connect(self.delete_subtask)
        subtask_actions.addWidget(delete_subtask_btn)

        layout.addLayout(subtask_actions)

    def refresh(self) -> None:
        task = task_service.get_task(self.db_path, self.task_id)
        if not task:
            QMessageBox.warning(self, "Ошибка", "Задача не найдена")
            self.reject()
            return

        self.title_input.setText(task.title)
        if task.reminder_datetime:
            self.reminder_input.setDateTime(task.reminder_datetime)
        else:
            self.reminder_input.setDateTime(datetime.now())

        self.subtasks_list.clear()
        self._subtasks_cache = task_service.list_subtasks(self.db_path, self.task_id)
        for subtask in self._subtasks_cache:
            label = f"[{'✓' if subtask.is_done else ' '}] {subtask.title}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, subtask.id)
            self.subtasks_list.addItem(item)

    def save_title(self) -> None:
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название задачи")
            return
        task_service.update_task(self.db_path, self.task_id, title=title)
        self.refresh()

    def save_reminder(self) -> None:
        reminder = self.reminder_input.dateTime().toPython()
        task_service.update_task(self.db_path, self.task_id, reminder_datetime=reminder)
        self.refresh()

    def clear_reminder(self) -> None:
        task_service.update_task(self.db_path, self.task_id, reminder_datetime=None)
        self.refresh()

    def _selected_subtask(self):
        row = self.subtasks_list.currentRow()
        if row < 0 or row >= len(self._subtasks_cache):
            return None
        return self._subtasks_cache[row]

    def add_subtask(self) -> None:
        title, ok = QInputDialog.getText(self, "Новая подзадача", "Введите название подзадачи")
        if not ok:
            return
        cleaned_title = title.strip()
        if not cleaned_title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название подзадачи")
            return
        task_service.create_subtask(self.db_path, self.task_id, cleaned_title)
        self.refresh()

    def toggle_subtask(self) -> None:
        subtask = self._selected_subtask()
        if subtask is None:
            QMessageBox.information(self, "Выберите подзадачу", "Выберите подзадачу для обновления")
            return
        task_service.update_subtask(self.db_path, subtask.id, is_done=not subtask.is_done)
        self.refresh()

    def delete_subtask(self) -> None:
        subtask = self._selected_subtask()
        if subtask is None:
            QMessageBox.information(self, "Выберите подзадачу", "Выберите подзадачу для удаления")
            return
        answer = QMessageBox.question(self, "Удалить подзадачу", f"Удалить '{subtask.title}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        task_service.delete_subtask(self.db_path, subtask.id)
        self.refresh()


class TaskQtWindow(QMainWindow):
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self._tasks_cache = []
        task_service.init_db(self.db_path)

        self.setWindowTitle("Task Tracker Desktop (Qt)")
        self.resize(760, 520)
        self._build_ui()
        self.refresh_tasks()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Поиск", self))
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Название или заметка")
        self.search_input.returnPressed.connect(self.refresh_tasks)
        search_row.addWidget(self.search_input)

        search_btn = QPushButton("Найти", self)
        search_btn.clicked.connect(self.refresh_tasks)
        search_row.addWidget(search_btn)

        clear_search_btn = QPushButton("Сброс", self)
        clear_search_btn.clicked.connect(self.clear_search)
        search_row.addWidget(clear_search_btn)
        layout.addLayout(search_row)

        self.tasks_list = QListWidget(self)
        self.tasks_list.itemDoubleClicked.connect(lambda _: self.open_task_details())
        layout.addWidget(self.tasks_list)

        actions = QHBoxLayout()

        add_btn = QPushButton("Добавить", self)
        add_btn.clicked.connect(self.add_task)
        actions.addWidget(add_btn)

        detail_btn = QPushButton("Открыть", self)
        detail_btn.clicked.connect(self.open_task_details)
        actions.addWidget(detail_btn)

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

    def clear_search(self) -> None:
        self.search_input.setText("")
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        self.tasks_list.clear()
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        self._tasks_cache = task_service.list_tasks(self.db_path, search=query or None)
        for task in self._tasks_cache:
            done_subtasks, total_subtasks = task_service.subtask_progress(self.db_path, task.id)
            reminder_flag = " ⏰" if task.reminder_datetime else ""
            subtask_badge = ""
            if total_subtasks > 0:
                subtask_badge = f" | подзадачи: {done_subtasks}/{total_subtasks}"
            label = f"[{'✓' if task.is_done else ' '}] {task.title}{reminder_flag}{subtask_badge}"
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

    def open_task_details(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для просмотра")
            return
        dialog = TaskDetailDialog(self.db_path, task.id, self)
        dialog.exec()
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
