from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from .models import ItemKind, TreeItemRef
from .services import tasks as task_service
from .storage import DB_NAME

try:
    from PySide6.QtCore import QPointF, QRectF, QSize, Qt
    from PySide6.QtGui import QBrush, QColor, QPainter, QPen
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
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QSplitter,
        QStyledItemDelegate,
        QStyle,
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
ROLE_ITEM_REF = Qt.ItemDataRole.UserRole
ROLE_META = Qt.ItemDataRole.UserRole + 1
ROLE_PROGRESS = Qt.ItemDataRole.UserRole + 2
ROLE_BADGES = Qt.ItemDataRole.UserRole + 3
ROLE_DEADLINE = Qt.ItemDataRole.UserRole + 4
ROLE_SUBTASKS = Qt.ItemDataRole.UserRole + 5
ROLE_DONE = Qt.ItemDataRole.UserRole + 6

SELECTED_BG_COLOR = "#E8EDF3"
SELECTED_BORDER_COLOR = "#5A6B7D"
SELECTED_TEXT_COLOR = "#1C232B"


def contrast_ratio(foreground: str, background: str) -> float:
    def _hex_to_luminance(value: str) -> float:
        raw = value.lstrip("#")
        rgb = [int(raw[index : index + 2], 16) / 255.0 for index in (0, 2, 4)]
        channels = [
            channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in rgb
        ]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    fg = _hex_to_luminance(foreground)
    bg = _hex_to_luminance(background)
    lighter = max(fg, bg)
    darker = min(fg, bg)
    return (lighter + 0.05) / (darker + 0.05)


SELECTED_TEXT_CONTRAST = contrast_ratio(SELECTED_TEXT_COLOR, SELECTED_BG_COLOR)


class TaskCardDelegate(QStyledItemDelegate):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._density = "comfortable"

    def set_density(self, density: str) -> None:
        self._density = density

    def sizeHint(self, option, index):
        base_height = 76 if self._density == "compact" else 96
        return QSize(option.rect.width(), base_height)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card_rect = option.rect.adjusted(8, 6, -8, -6)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        background = QColor("#FFFFFF")
        border = QColor("#D2DCE8")
        if hovered:
            background = QColor("#F7F9FC")
            border = QColor("#AAB9CA")
        if selected:
            background = QColor(SELECTED_BG_COLOR)
            border = QColor(SELECTED_BORDER_COLOR)

        painter.setBrush(background)
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(card_rect, 8, 8)
        if focused:
            painter.setPen(QPen(QColor("#364B63"), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card_rect.adjusted(2, 2, -2, -2), 6, 6)

        text_color = QColor(SELECTED_TEXT_COLOR if selected else "#1F2933")
        meta_color = QColor("#2B3A48" if selected else "#5D6A79")
        left = card_rect.left() + 12
        top = card_rect.top() + 10

        done = bool(index.data(ROLE_DONE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#2D9D5B" if done else "#D98B2B"))
        painter.drawEllipse(QRectF(left, top + 2, 10, 10))

        title_font = painter.font()
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(QRectF(left + 16, top - 1, card_rect.width() - 40, 22), index.data(Qt.ItemDataRole.DisplayRole) or "")

        meta_font = painter.font()
        meta_font.setBold(False)
        painter.setFont(meta_font)
        painter.setPen(meta_color)
        painter.drawText(QRectF(left + 16, top + 17, card_rect.width() - 40, 18), index.data(ROLE_META) or "")

        progress = int(index.data(ROLE_PROGRESS) or 0)
        progress_rect = QRectF(left + 16, top + 40, card_rect.width() - 52, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#DCE3EA"))
        painter.drawRoundedRect(progress_rect, 4, 4)
        painter.setBrush(QColor("#4E8F75"))
        painter.drawRoundedRect(
            QRectF(progress_rect.left(), progress_rect.top(), progress_rect.width() * progress / 100.0, progress_rect.height()),
            4,
            4,
        )

        sections = [
            ("Статус", "Готово" if done else "В работе"),
            ("Срок", index.data(ROLE_DEADLINE) or "—"),
            ("Подзадачи", str(index.data(ROLE_SUBTASKS) or 0)),
        ]
        x_cursor = left + 16
        for section_index, (label, value) in enumerate(sections):
            painter.setPen(meta_color)
            painter.drawText(QRectF(x_cursor, top + 54, 65, 16), label)
            painter.setPen(text_color)
            painter.drawText(QRectF(x_cursor + 54, top + 54, 90, 16), value)
            x_cursor += 132
            if section_index < len(sections) - 1:
                painter.setPen(QPen(QColor("#C7D2DF"), 1))
                painter.drawLine(int(x_cursor - 10), int(top + 52), int(x_cursor - 10), int(top + 68))

        badge_x = card_rect.right() - 12
        for text, color in reversed(index.data(ROLE_BADGES) or []):
            badge_width = max(40, len(text) * 7 + 14)
            badge_rect = QRectF(badge_x - badge_width, top + 1, badge_width, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(badge_rect, 8, 8)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
            badge_x -= badge_width + 6
        painter.restore()


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


class TaskPickerDialog(QDialog):
    def __init__(self, tasks: list, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tasks = tasks
        self._filtered_tasks = list(tasks)
        self.selected_task_id: Optional[int] = None

        self.setWindowTitle("Выберите родительскую задачу")
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Поиск", self))

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("ID или название")
        self.search_input.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self._accept_item)
        layout.addWidget(self.list_widget)

        actions = QHBoxLayout()
        ok_btn = QPushButton("Выбрать", self)
        ok_btn.clicked.connect(self._accept_current)
        actions.addWidget(ok_btn)

        cancel_btn = QPushButton("Отмена", self)
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(cancel_btn)
        layout.addLayout(actions)

        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search_input.text().strip().lower()
        self._filtered_tasks = []
        self.list_widget.clear()

        for task in self._tasks:
            label = f"#{task.id} {task.title}"
            if query and query not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.list_widget.addItem(item)
            self._filtered_tasks.append(task)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _accept_item(self, item: QListWidgetItem) -> None:
        self.selected_task_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _accept_current(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "Задачи не найдены", "Выберите родительскую задачу из списка")
            return
        self.selected_task_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


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
        self.search_input.textChanged.connect(self.refresh_tasks)
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

        search_row.addWidget(QLabel("Плотность", self))
        self.density_mode = QComboBox(self)
        self.density_mode.addItems(["Compact", "Comfortable"])
        self.density_mode.setCurrentText("Comfortable")
        self.density_mode.currentIndexChanged.connect(self._apply_density)
        search_row.addWidget(self.density_mode)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("Задачи и подзадачи", self))
        self.tasks_list = QTreeWidget(self)
        self.tasks_list.setHeaderHidden(True)
        self.tasks_list.setColumnCount(1)
        self.tasks_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.tasks_list.itemActivated.connect(self._open_selected_item_card)
        self.tasks_list.setMouseTracking(True)
        self.tasks_list.setIndentation(26)
        self.tasks_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tasks_list.customContextMenuRequested.connect(self._show_task_context_menu)
        self.task_delegate = TaskCardDelegate(self.tasks_list)
        self.tasks_list.setItemDelegate(self.task_delegate)
        left_layout.addWidget(self.tasks_list)

        left_actions = QHBoxLayout()
        add_btn = QPushButton("Новая задача", self)
        add_btn.clicked.connect(self.add_task)
        left_actions.addWidget(add_btn)

        add_subtask_btn = QPushButton("Подзадача", self)
        add_subtask_btn.clicked.connect(self.add_subtask)
        left_actions.addWidget(add_subtask_btn)

        complete_btn = QPushButton("Отметить выполненной", self)
        complete_btn.clicked.connect(self.mark_selected_done)
        left_actions.addWidget(complete_btn)

        delete_btn = QPushButton("Удалить", self)
        delete_btn.clicked.connect(self.delete_task)
        left_actions.addWidget(delete_btn)

        convert_btn = QPushButton("Сделать подзадачей…", self)
        convert_btn.clicked.connect(self.convert_task_to_subtask)
        left_actions.addWidget(convert_btn)

        graph_btn = QPushButton("Граф задач", self)
        graph_btn.clicked.connect(self.open_graph_mode)
        left_actions.addWidget(graph_btn)

        left_layout.addLayout(left_actions)

        right_panel = QWidget(self)
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(QLabel("Карточка элемента", self))
        self.breadcrumbs_label = QLabel("—", self)
        right_layout.addWidget(self.breadcrumbs_label)

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
        self._apply_styles()
        self._apply_density()

    def _apply_styles(self) -> None:
        qss_path = Path(__file__).with_name("styles").joinpath("task_list.qss")
        if qss_path.exists():
            self.tasks_list.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _apply_density(self) -> None:
        density = "compact" if self.density_mode.currentText().lower().startswith("compact") else "comfortable"
        self.task_delegate.set_density(density)
        self.tasks_list.doItemsLayout()
        self.tasks_list.viewport().update()

    def clear_search(self) -> None:
        self.search_input.setText("")
        self.status_filter.setCurrentIndex(0)
        self.subtasks_filter.setCurrentIndex(0)
        self.sort_mode.setCurrentIndex(0)
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        selected_ref = self._selected_item_ref()
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
            percent = int((done_subtasks / total_subtasks) * 100) if total_subtasks else 0
            deadline = task.reminder_datetime.strftime("%d.%m %H:%M") if task.reminder_datetime else "—"
            meta = f"ID #{task.id} · {done_subtasks}/{total_subtasks} выполнено"

            root_item = QTreeWidgetItem([task.title])
            root_item.setData(0, ROLE_ITEM_REF, TreeItemRef(kind=ItemKind.TASK, id=task.id, level=0))
            root_item.setData(0, ROLE_META, meta)
            root_item.setData(0, ROLE_PROGRESS, percent)
            root_item.setData(0, ROLE_DEADLINE, deadline)
            root_item.setData(0, ROLE_SUBTASKS, total_subtasks)
            root_item.setData(0, ROLE_DONE, task.is_done)

            badges = []
            if total_subtasks:
                badges.append(("🧩", "#607D8B"))
            if task.reminder_datetime:
                badges.append(("⏰", "#D17C3F"))
            if task.is_done:
                badges.append(("DONE", "#2D9D5B"))
            root_item.setData(0, ROLE_BADGES, badges)
            self.tasks_list.addTopLevelItem(root_item)

            subtasks = task_service.list_subtasks(self.db_path, task.id)
            for subtask in subtasks:
                child = QTreeWidgetItem([f"↳ {subtask.title}"])
                child.setData(0, ROLE_ITEM_REF, TreeItemRef(kind=ItemKind.SUBTASK, id=subtask.id, level=1, parent_task_id=task.id))
                child.setData(0, ROLE_META, f"Подзадача #{subtask.id}")
                child.setData(0, ROLE_PROGRESS, 100 if subtask.is_done else 0)
                child_deadline = subtask.due_datetime or subtask.reminder_datetime
                child.setData(0, ROLE_DEADLINE, child_deadline.strftime("%d.%m %H:%M") if child_deadline else "—")
                child.setData(0, ROLE_SUBTASKS, 0)
                child.setData(0, ROLE_DONE, subtask.is_done)
                child.setData(0, ROLE_BADGES, [("SUB", "#6A7A8D")])
                root_item.addChild(child)

        self.tasks_list.expandAll()
        if selected_ref is not None:
            self._select_item_in_tree(selected_ref)
        elif self.tasks_list.topLevelItemCount() > 0:
            self.tasks_list.setCurrentItem(self.tasks_list.topLevelItem(0))
        else:
            self._clear_card()

    def _selected_item_ref(self) -> Optional[TreeItemRef]:
        item = self.tasks_list.currentItem()
        if item is None:
            return None
        item_ref = item.data(0, ROLE_ITEM_REF)
        return item_ref if isinstance(item_ref, TreeItemRef) else None

    def _selected_task_id(self) -> Optional[int]:
        item_ref = self._selected_item_ref()
        if item_ref is None:
            return None
        if item_ref.kind == ItemKind.TASK:
            return item_ref.id
        return item_ref.parent_task_id

    def _select_task_in_tree(self, task_id: int) -> None:
        self._select_item_in_tree(TreeItemRef(kind=ItemKind.TASK, id=task_id, level=0))

    def _select_item_in_tree(self, item_ref: TreeItemRef) -> None:
        if item_ref.kind == ItemKind.TASK:
            for index in range(self.tasks_list.topLevelItemCount()):
                item = self.tasks_list.topLevelItem(index)
                current_ref = item.data(0, ROLE_ITEM_REF)
                if isinstance(current_ref, TreeItemRef) and current_ref.kind == ItemKind.TASK and current_ref.id == item_ref.id:
                    self.tasks_list.setCurrentItem(item)
                    self.tasks_list.scrollToItem(item)
                    return
            return
        if item_ref.parent_task_id is None:
            return
        self._focus_subtask_in_tree(item_ref.parent_task_id, item_ref.id)

    def _focus_subtask_in_tree(self, parent_task_id: int, subtask_id: int) -> None:
        for index in range(self.tasks_list.topLevelItemCount()):
            parent_item = self.tasks_list.topLevelItem(index)
            parent_ref = parent_item.data(0, ROLE_ITEM_REF)
            if not isinstance(parent_ref, TreeItemRef) or parent_ref.id != parent_task_id:
                continue
            parent_item.setExpanded(True)
            for child_index in range(parent_item.childCount()):
                child_item = parent_item.child(child_index)
                child_ref = child_item.data(0, ROLE_ITEM_REF)
                if isinstance(child_ref, TreeItemRef) and child_ref.kind == ItemKind.SUBTASK and child_ref.id == subtask_id:
                    self.tasks_list.setCurrentItem(child_item)
                    self.tasks_list.scrollToItem(child_item)
                    return
            self.tasks_list.setCurrentItem(parent_item)
            self.tasks_list.scrollToItem(parent_item)
            return

    def _selected_task(self):
        task_id = self._selected_task_id()
        if task_id is None:
            return None
        return self._tasks_by_id.get(task_id) or task_service.get_task(self.db_path, task_id)

    def _selected_subtask(self):
        item_ref = self._selected_item_ref()
        if item_ref is None or item_ref.kind != ItemKind.SUBTASK:
            return None
        return task_service.get_subtask(self.db_path, item_ref.id)

    def _selected_subtask_id(self) -> Optional[int]:
        item_ref = self._selected_item_ref()
        if item_ref and item_ref.kind == ItemKind.SUBTASK:
            return item_ref.id
        return None

    def _clear_card(self) -> None:
        self.breadcrumbs_label.setText("—")
        self.title_input.setText("")
        self.status_checkbox.setText("Элемент выполнен")
        self.status_checkbox.setChecked(False)
        self.reminder_input.setDateTime(datetime.now())
        self.note_input.setPlainText("")

    def _open_selected_item_card(self) -> None:
        self.on_selection_changed()

    def on_selection_changed(self) -> None:
        item_ref = self._selected_item_ref()
        if item_ref is None:
            self._clear_card()
            return

        if item_ref.kind == ItemKind.SUBTASK:
            subtask = self._selected_subtask()
            parent = self._selected_task()
            if subtask is None or parent is None:
                self._clear_card()
                return
            self.breadcrumbs_label.setText(f"{parent.title} > {subtask.title}")
            self.title_input.setText(subtask.title)
            self.status_checkbox.setText("Подзадача выполнена")
            self.status_checkbox.setChecked(subtask.is_done)
            self.note_input.setPlainText(subtask.note or "")
            self.reminder_input.setDateTime(subtask.reminder_datetime or datetime.now())
            return

        task = self._selected_task()
        if task is None:
            self._clear_card()
            return
        self.breadcrumbs_label.setText(task.title)
        self.title_input.setText(task.title)
        self.status_checkbox.setText("Задача выполнена")
        self.status_checkbox.setChecked(task.is_done)
        self.note_input.setPlainText(task.note or "")
        self.reminder_input.setDateTime(task.reminder_datetime or datetime.now())

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
        item_ref = self._selected_item_ref()
        if item_ref is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу или подзадачу для редактирования")
            return

        title = self.title_input.text().strip()
        if not title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название")
            return

        reminder = self.reminder_input.dateTime().toPython()
        note = self.note_input.toPlainText()
        done = self.status_checkbox.isChecked()

        if item_ref.kind == ItemKind.SUBTASK:
            updated = task_service.update_subtask(
                self.db_path,
                item_ref.id,
                title=title,
                is_done=done,
                reminder_datetime=reminder,
                note=note,
            )
            if not updated:
                QMessageBox.warning(self, "Ошибка", "Не удалось сохранить подзадачу")
                return
            self.refresh_tasks()
            self._focus_subtask_in_tree(updated.task_id, updated.id)
            return

        updated = task_service.update_task(
            self.db_path,
            item_ref.id,
            title=title,
            is_done=done,
            reminder_datetime=reminder,
            note=note,
        )
        if not updated:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить задачу")
            return
        self.refresh_tasks()
        self._select_task_in_tree(updated.id)

    def add_subtask(self) -> None:
        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите родительскую задачу")
            return

        title, ok = QInputDialog.getText(self, "Новая подзадача", "Введите название подзадачи")
        if not ok:
            return

        cleaned_title = title.strip()
        if not cleaned_title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название подзадачи")
            return

        created = task_service.create_subtask(self.db_path, task.id, cleaned_title)
        if not created:
            QMessageBox.warning(self, "Ошибка", "Не удалось создать подзадачу")
            return

        self.refresh_tasks()
        self._focus_subtask_in_tree(task.id, created.id)

    def mark_selected_done(self) -> None:
        subtask_id = self._selected_subtask_id()
        if subtask_id is not None:
            updated = task_service.update_subtask(self.db_path, subtask_id, is_done=True)
            if not updated:
                QMessageBox.warning(self, "Ошибка", "Не удалось отметить подзадачу")
                return
            self.refresh_tasks()
            self._focus_subtask_in_tree(updated.task_id, updated.id)
            return

        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу или подзадачу")
            return

        task_service.update_task(self.db_path, task.id, is_done=True)
        self.refresh_tasks()
        self._select_task_in_tree(task.id)

    def clear_selected_reminder(self) -> None:
        item_ref = self._selected_item_ref()
        if item_ref is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу или подзадачу для обновления")
            return
        if item_ref.kind == ItemKind.SUBTASK:
            updated = task_service.update_subtask(self.db_path, item_ref.id, reminder_datetime=None)
            if not updated:
                QMessageBox.warning(self, "Ошибка", "Не удалось очистить напоминание подзадачи")
                return
            self.refresh_tasks()
            self._focus_subtask_in_tree(updated.task_id, updated.id)
            return

        task_service.update_task(self.db_path, item_ref.id, reminder_datetime=None)
        self.refresh_tasks()
        self._select_task_in_tree(item_ref.id)

    def delete_task(self) -> None:
        subtask_id = self._selected_subtask_id()
        if subtask_id is not None:
            answer = QMessageBox.question(self, "Удалить подзадачу", "Удалить выбранную подзадачу?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            task_service.delete_subtask(self.db_path, subtask_id)
            self.refresh_tasks()
            return

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
        if self._selected_subtask_id() is not None:
            QMessageBox.information(
                self,
                "Выберите задачу",
                "Преобразовывать можно только задачи верхнего уровня",
            )
            return

        child_task = self._selected_task()
        if child_task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для преобразования")
            return

        parent_options = [task for task in task_service.list_tasks(self.db_path) if task.id != child_task.id]
        if not parent_options:
            QMessageBox.information(
                self,
                "Недостаточно задач",
                "Нужна хотя бы ещё одна задача, чтобы выбрать родителя",
            )
            return

        dialog = TaskPickerDialog(parent_options, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.selected_task_id is None:
            return

        if dialog.selected_task_id == child_task.id:
            QMessageBox.warning(self, "Ошибка преобразования", "Нельзя сделать задачу подзадачей самой себя")
            return

        if not task_service.get_task(self.db_path, dialog.selected_task_id):
            QMessageBox.warning(self, "Ошибка преобразования", "Родительская задача не найдена")
            return

        try:
            converted = task_service.convert_task_to_subtask(
                self.db_path,
                child_task.id,
                dialog.selected_task_id,
            )
        except task_service.ConvertToSubtaskError as exc:
            QMessageBox.warning(self, "Ошибка преобразования", str(exc))
            return

        if not converted:
            QMessageBox.warning(self, "Ошибка", "Не удалось преобразовать задачу")
            return

        self.refresh_tasks()
        self._focus_subtask_in_tree(dialog.selected_task_id, converted.id)

    def _show_task_context_menu(self, pos) -> None:
        item = self.tasks_list.itemAt(pos)
        if item is None:
            return
        self.tasks_list.setCurrentItem(item)

        menu = QMenu(self)
        create_task_action = menu.addAction("Новая задача")
        create_subtask_action = menu.addAction("Новая подзадача")
        mark_done_action = menu.addAction("Отметить выполненной")
        delete_action = menu.addAction("Удалить")
        menu.addSeparator()
        convert_action = menu.addAction("Сделать подзадачей…")
        chosen = menu.exec(self.tasks_list.viewport().mapToGlobal(pos))
        if chosen == create_task_action:
            self.add_task()
        if chosen == create_subtask_action:
            self.add_subtask()
        if chosen == mark_done_action:
            self.mark_selected_done()
        if chosen == delete_action:
            self.delete_task()
        if chosen == convert_action:
            self.convert_task_to_subtask()

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
