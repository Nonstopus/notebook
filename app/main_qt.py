from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from .services import tasks as task_service
from .storage import DB_NAME

try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QBrush, QPainter, QPen
    from PySide6.QtWidgets import (
        QApplication,
        QDateTimeEdit,
        QDialog,
        QGraphicsEllipseItem,
        QGraphicsLineItem,
        QGraphicsScene,
        QGraphicsSimpleTextItem,
        QGraphicsView,
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
NODE_WIDTH = 180
NODE_HEIGHT = 70


class GraphEdgeItem(QGraphicsLineItem):
    def __init__(self, source_item: "GraphNodeItem", target_item: "GraphNodeItem"):
        super().__init__()
        self.source_item = source_item
        self.target_item = target_item
        self.setPen(QPen(Qt.GlobalColor.darkGray, 2))
        self.setZValue(-1)
        self.update_position()

    def update_position(self) -> None:
        source = self.source_item.scene_center()
        target = self.target_item.scene_center()

        dx = target.x() - source.x()
        dy = target.y() - source.y()
        length = max(1.0, math.hypot(dx, dy))
        ux = dx / length
        uy = dy / length

        start = QPointF(
            source.x() + ux * (NODE_WIDTH / 2),
            source.y() + uy * (NODE_HEIGHT / 2),
        )
        end = QPointF(
            target.x() - ux * (NODE_WIDTH / 2),
            target.y() - uy * (NODE_HEIGHT / 2),
        )
        self.setLine(start.x(), start.y(), end.x(), end.y())


class GraphNodeItem(QGraphicsEllipseItem):
    def __init__(self, dialog: "TaskGraphDialog", task_id: int, title: str):
        super().__init__(0, 0, NODE_WIDTH, NODE_HEIGHT)
        self.dialog = dialog
        self.task_id = task_id
        self.edges = []

        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setBrush(QBrush(Qt.GlobalColor.white))
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable
        )

        label = QGraphicsSimpleTextItem(f"#{task_id} {title}", self)
        label.setPos(12, NODE_HEIGHT / 2 - 10)

    def scene_center(self) -> QPointF:
        return self.scenePos() + QPointF(NODE_WIDTH / 2, NODE_HEIGHT / 2)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
            self.dialog.persist_layout(self.task_id, result)
        return result


class TaskGraphDialog(QDialog):
    def __init__(self, db_path: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db_path = db_path
        self._node_items: Dict[int, GraphNodeItem] = {}
        self._graph_links: set[Tuple[int, int]] = set()

        self.setWindowTitle("Граф задач")
        self.resize(1000, 680)
        self._build_ui()
        self.refresh_graph()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        add_link_btn = QPushButton("Создать связь", self)
        add_link_btn.clicked.connect(self.add_link)
        controls.addWidget(add_link_btn)

        remove_link_btn = QPushButton("Удалить связь", self)
        remove_link_btn.clicked.connect(self.remove_link)
        controls.addWidget(remove_link_btn)

        refresh_btn = QPushButton("Обновить", self)
        refresh_btn.clicked.connect(self.refresh_graph)
        controls.addWidget(refresh_btn)

        controls.addStretch(1)
        layout.addLayout(controls)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 1600, 1100)

        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        layout.addWidget(self.view)

    def refresh_graph(self) -> None:
        self.scene.clear()
        self._node_items.clear()

        all_tasks = task_service.list_tasks(self.db_path)
        layouts = task_service.get_task_layouts(self.db_path)
        self._graph_links = set(task_service.list_task_links(self.db_path))

        for index, task in enumerate(all_tasks):
            node = GraphNodeItem(self, task.id, task.title)
            x, y = layouts.get(task.id, (80.0 + (index % 5) * 230.0, 80.0 + (index // 5) * 140.0))
            node.setPos(float(x), float(y))
            self.scene.addItem(node)
            self._node_items[task.id] = node

        for source_id, target_id in sorted(self._graph_links):
            source_node = self._node_items.get(source_id)
            target_node = self._node_items.get(target_id)
            if not source_node or not target_node:
                continue
            edge = GraphEdgeItem(source_node, target_node)
            self.scene.addItem(edge)
            source_node.edges.append(edge)
            target_node.edges.append(edge)

    def persist_layout(self, task_id: int, position: QPointF) -> None:
        task_service.set_task_layout(self.db_path, task_id, position.x(), position.y())

    def _pick_task_id(self, title: str, options: list[Tuple[int, str]]) -> Optional[int]:
        labels = [f"#{task_id} {name}" for task_id, name in options]
        selected, ok = QInputDialog.getItem(self, title, "Выберите задачу", labels, 0, False)
        if not ok:
            return None
        index = labels.index(selected)
        return options[index][0]

    def add_link(self) -> None:
        all_tasks = task_service.list_tasks(self.db_path)
        if len(all_tasks) < 2:
            QMessageBox.information(self, "Недостаточно задач", "Нужно минимум две задачи")
            return

        options = [(task.id, task.title) for task in all_tasks]
        source_id = self._pick_task_id("Источник связи", options)
        if source_id is None:
            return

        target_options = [pair for pair in options if pair[0] != source_id]
        target_id = self._pick_task_id("Цель связи", target_options)
        if target_id is None:
            return

        created = task_service.create_task_link(self.db_path, source_id, target_id)
        if not created:
            QMessageBox.warning(
                self,
                "Связь не создана",
                "Проверьте, что связь не дублируется и не образует цикл.",
            )
            return
        self.refresh_graph()

    def remove_link(self) -> None:
        if not self._graph_links:
            QMessageBox.information(self, "Нет связей", "Удалять пока нечего")
            return

        link_labels = [f"{source} -> {target}" for source, target in sorted(self._graph_links)]
        selected, ok = QInputDialog.getItem(self, "Удалить связь", "Выберите связь", link_labels, 0, False)
        if not ok:
            return

        index = link_labels.index(selected)
        source_id, target_id = sorted(self._graph_links)[index]
        task_service.delete_task_link(self.db_path, source_id, target_id)
        self.refresh_graph()


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

        convert_btn = QPushButton("Сделать подзадачей", self)
        convert_btn.clicked.connect(self.convert_task_to_subtask)
        actions.addWidget(convert_btn)

        graph_btn = QPushButton("Граф задач", self)
        graph_btn.clicked.connect(self.open_graph_mode)
        actions.addWidget(graph_btn)

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

    def convert_task_to_subtask(self) -> None:
        child_task = self._selected_task()
        if child_task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для преобразования")
            return

        parent_options = [task for task in self._tasks_cache if task.id != child_task.id]
        if not parent_options:
            QMessageBox.information(
                self,
                "Недостаточно задач",
                "Нужна хотя бы ещё одна задача, чтобы выбрать родителя",
            )
            return

        option_labels = [f"#{task.id} {task.title}" for task in parent_options]
        selected_label, ok = QInputDialog.getItem(
            self,
            "Сделать подзадачей",
            "Выберите родительскую задачу",
            option_labels,
            0,
            False,
        )
        if not ok:
            return

        selected_index = option_labels.index(selected_label)
        parent_task = parent_options[selected_index]
        converted = task_service.convert_task_to_subtask(self.db_path, child_task.id, parent_task.id)
        if not converted:
            QMessageBox.warning(self, "Ошибка", "Не удалось преобразовать задачу")
            return

        self.refresh_tasks()

    def open_graph_mode(self) -> None:
        dialog = TaskGraphDialog(self.db_path, self)
        dialog.exec()
        self.refresh_tasks()


def main() -> int:
    app = QApplication(sys.argv)
    window = TaskQtWindow(DB_PATH)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
