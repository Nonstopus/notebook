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
        QCheckBox,
        QComboBox,
        QDateTimeEdit,
        QDialog,
        QFormLayout,
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
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QTreeWidget,
        QTreeWidgetItem,
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
        labels = [f"#{task_id} {task_title}" for task_id, task_title in options]
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


class TaskQtWindow(QMainWindow):
    def __init__(self, db_path: Path):
        super().__init__()
        self.db_path = db_path
        self._tasks_cache = []
        self._tasks_by_id: Dict[int, object] = {}
        task_service.init_db(self.db_path)

        self.setWindowTitle("Task Tracker Desktop (Qt)")
        self.resize(980, 560)
        self._build_ui()
        self.refresh_tasks()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

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

        search_row.addWidget(QLabel("Статус", self))
        self.status_filter = QComboBox(self)
        self.status_filter.addItems(["Все", "Активные", "Выполненные"])
        self.status_filter.currentIndexChanged.connect(self.refresh_tasks)
        search_row.addWidget(self.status_filter)

        search_row.addWidget(QLabel("Подзадачи", self))
        self.subtasks_filter = QComboBox(self)
        self.subtasks_filter.addItems(["Все", "Есть подзадачи", "Без подзадач"])
        self.subtasks_filter.currentIndexChanged.connect(self.refresh_tasks)
        search_row.addWidget(self.subtasks_filter)

        search_row.addWidget(QLabel("Сортировка", self))
        self.sort_mode = QComboBox(self)
        self.sort_mode.addItems(
            [
                "Сначала новые",
                "Сначала старые",
                "Статус (активные → выполненные)",
                "Подзадачи (по убыванию)",
            ]
        )
        self.sort_mode.currentIndexChanged.connect(self.refresh_tasks)
        search_row.addWidget(self.sort_mode)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Задачи и подзадачи", self))
        self.tasks_list = QTreeWidget(self)
        self.tasks_list.setHeaderLabels(["Задача", "Прогресс"])
        self.tasks_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.tasks_list.setAlternatingRowColors(True)
        left_layout.addWidget(self.tasks_list)

        left_actions = QHBoxLayout()
        add_btn = QPushButton("Добавить", self)
        add_btn.clicked.connect(self.add_task)
        left_actions.addWidget(add_btn)

        delete_btn = QPushButton("Удалить", self)
        delete_btn.clicked.connect(self.delete_task)
        left_actions.addWidget(delete_btn)

        convert_btn = QPushButton("Сделать подзадачей", self)
        convert_btn.clicked.connect(self.convert_task_to_subtask)
        left_actions.addWidget(convert_btn)

        graph_btn = QPushButton("Граф задач", self)
        graph_btn.clicked.connect(self.open_graph_mode)
        left_actions.addWidget(graph_btn)

        left_layout.addLayout(left_actions)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Карточка задачи", self))

        form = QFormLayout()
        self.title_input = QLineEdit(self)
        form.addRow("Заголовок", self.title_input)

        self.status_checkbox = QCheckBox("Задача выполнена", self)
        form.addRow("Статус", self.status_checkbox)

        self.reminder_input = QDateTimeEdit(self)
        self.reminder_input.setCalendarPopup(True)
        self.reminder_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        form.addRow("Напоминание", self.reminder_input)

        self.note_input = QPlainTextEdit(self)
        self.note_input.setPlaceholderText("Заметка")
        self.note_input.setFixedHeight(140)
        form.addRow("Note", self.note_input)
        right_layout.addLayout(form)

        card_actions = QHBoxLayout()
        save_card_btn = QPushButton("Сохранить", self)
        save_card_btn.clicked.connect(self.save_selected_task)
        card_actions.addWidget(save_card_btn)

        clear_reminder_btn = QPushButton("Очистить напоминание", self)
        clear_reminder_btn.clicked.connect(self.clear_selected_reminder)
        card_actions.addWidget(clear_reminder_btn)

        refresh_btn = QPushButton("Обновить", self)
        refresh_btn.clicked.connect(self.refresh_tasks)
        card_actions.addWidget(refresh_btn)

        right_layout.addLayout(card_actions)
        right_layout.addStretch(1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter)

        self.setCentralWidget(central)

    def clear_search(self) -> None:
        self.search_input.setText("")
        self.status_filter.setCurrentIndex(0)
        self.subtasks_filter.setCurrentIndex(0)
        self.sort_mode.setCurrentIndex(0)
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        selected = self._selected_task_id()
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        status_value = self.status_filter.currentText() if hasattr(self, "status_filter") else "Все"
        is_done_filter = None
        if status_value == "Активные":
            is_done_filter = False
        elif status_value == "Выполненные":
            is_done_filter = True

        all_tasks = task_service.list_tasks(
            self.db_path,
            search=query or None,
            is_done=is_done_filter,
        )
        progress_map = {
            task.id: task_service.subtask_progress(self.db_path, task.id) for task in all_tasks
        }

        subtasks_value = self.subtasks_filter.currentText() if hasattr(self, "subtasks_filter") else "Все"
        if subtasks_value == "Есть подзадачи":
            filtered_tasks = [task for task in all_tasks if progress_map[task.id][1] > 0]
        elif subtasks_value == "Без подзадач":
            filtered_tasks = [task for task in all_tasks if progress_map[task.id][1] == 0]
        else:
            filtered_tasks = all_tasks

        sort_value = self.sort_mode.currentText() if hasattr(self, "sort_mode") else "Сначала новые"
        if sort_value == "Сначала старые":
            filtered_tasks.sort(key=lambda task: task.created_at)
        elif sort_value == "Статус (активные → выполненные)":
            filtered_tasks.sort(key=lambda task: (task.is_done, -task.created_at.timestamp()))
        elif sort_value == "Подзадачи (по убыванию)":
            filtered_tasks.sort(
                key=lambda task: (progress_map[task.id][1], progress_map[task.id][0], task.created_at.timestamp()),
                reverse=True,
            )

        self._tasks_cache = filtered_tasks
        self._tasks_by_id = {task.id: task for task in self._tasks_cache}

        self.tasks_list.clear()
        for task in self._tasks_cache:
            done_subtasks, total_subtasks = progress_map[task.id]
            reminder_flag = "⏰ " if task.reminder_datetime else ""
            subtask_badge = "🧩 " if total_subtasks else ""
            text = f"[{'✓' if task.is_done else ' '}] {subtask_badge}{reminder_flag}{task.title}"
            progress = f"{done_subtasks}/{total_subtasks} · подзадач: {total_subtasks}"
            root_item = QTreeWidgetItem([text, progress])
            root_item.setData(0, Qt.ItemDataRole.UserRole, task.id)
            self.tasks_list.addTopLevelItem(root_item)

            subtasks = task_service.list_subtasks(self.db_path, task.id)
            for subtask in subtasks:
                st_text = f"[{'✓' if subtask.is_done else ' '}] {subtask.title}"
                child = QTreeWidgetItem([st_text, "subtask"])
                child.setDisabled(True)
                root_item.addChild(child)

        self.tasks_list.expandAll()
        if selected is not None:
            self._select_task_in_tree(selected)
        elif self.tasks_list.topLevelItemCount() > 0:
            self.tasks_list.setCurrentItem(self.tasks_list.topLevelItem(0))
        else:
            self._clear_card()

    def _selected_task_id(self) -> Optional[int]:
        item = self.tasks_list.currentItem()
        if not item:
            return None
        task_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(task_id, int):
            return None
        return task_id

    def _select_task_in_tree(self, task_id: int) -> None:
        for index in range(self.tasks_list.topLevelItemCount()):
            item = self.tasks_list.topLevelItem(index)
            if item.data(0, Qt.ItemDataRole.UserRole) == task_id:
                self.tasks_list.setCurrentItem(item)
                return

    def _selected_task(self):
        task_id = self._selected_task_id()
        if task_id is None:
            return None
        return self._tasks_by_id.get(task_id) or task_service.get_task(self.db_path, task_id)

    def _clear_card(self) -> None:
        self.title_input.setText("")
        self.status_checkbox.setChecked(False)
        self.reminder_input.setDateTime(datetime.now())
        self.note_input.setPlainText("")

    def on_selection_changed(self) -> None:
        task = self._selected_task()
        if task is None:
            self._clear_card()
            return
        self.title_input.setText(task.title)
        self.status_checkbox.setChecked(task.is_done)
        self.note_input.setPlainText(task.note or "")
        if task.reminder_datetime:
            self.reminder_input.setDateTime(task.reminder_datetime)
        else:
            self.reminder_input.setDateTime(datetime.now())

    def add_task(self) -> None:
        title, ok = QInputDialog.getText(self, "Новая задача", "Введите название задачи")
        if not ok:
            return

        cleaned_title = title.strip()
        if not cleaned_title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название задачи")
            return

        created = task_service.create_task(self.db_path, cleaned_title)
        self.refresh_tasks()
        self._select_task_in_tree(created.id)

    def save_selected_task(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для редактирования")
            return

        title = self.title_input.text().strip()
        if not title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название задачи")
            return

        reminder = self.reminder_input.dateTime().toPython()
        updated = task_service.update_task(
            self.db_path,
            task.id,
            title=title,
            is_done=self.status_checkbox.isChecked(),
            reminder_datetime=reminder,
            note=self.note_input.toPlainText(),
        )
        if not updated:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить задачу")
            return
        self.refresh_tasks()
        self._select_task_in_tree(task.id)

    def clear_selected_reminder(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для обновления")
            return
        task_service.update_task(self.db_path, task.id, reminder_datetime=None)
        self.refresh_tasks()
        self._select_task_in_tree(task.id)

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
