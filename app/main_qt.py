from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .models import (
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    ItemKind,
    TreeItemRef,
)
from .services import tasks as task_service
from .storage import DB_NAME

try:
    from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, Signal
    from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QPainter, QPen, QPolygonF
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QComboBox,
        QDateTimeEdit,
        QDialog,
        QFormLayout,
        QFrame,
        QFileDialog,
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
        QTextEdit,
        QToolBar,
        QPushButton,
        QSplitter,
        QSizePolicy,
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
ROLE_PRIORITY = Qt.ItemDataRole.UserRole + 7
ROLE_DEADLINE_COLOR = Qt.ItemDataRole.UserRole + 8

TOKENS = {
    "colors": {
        "bg": "#FFFFFF",
        "bg_subtle": "#F7F9FC",
        "border": "#D2DCE8",
        "text_primary": "#1F2933",
        "text_secondary": "#5D6A79",
        "text_meta": "#7A8798",
        "progress_bg": "#DCE3EA",
        "progress_fill": "#4E8F75",
        "danger": "#BE2D2D",
        "focus": "#364B63",
    },
    "radii": {"card": 10, "chip": 8},
}

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

PRIORITY_LABELS = {
    PRIORITY_LOW: "Низкий",
    PRIORITY_MEDIUM: "Средний",
    PRIORITY_HIGH: "Высокий",
    PRIORITY_CRITICAL: "Критичный",
}
LABEL_TO_PRIORITY = {label: value for value, label in PRIORITY_LABELS.items()}


def _priority_to_label(priority: str) -> str:
    return PRIORITY_LABELS.get(priority, PRIORITY_LABELS[PRIORITY_MEDIUM])


def _label_to_priority(label: str) -> str:
    return LABEL_TO_PRIORITY.get(label, PRIORITY_MEDIUM)


class TaskCardDelegate(QStyledItemDelegate):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._density = "comfortable"

    def set_density(self, density: str) -> None:
        self._density = density

    def sizeHint(self, option, index):
        base_height = 84 if self._density == "compact" else 110
        return QSize(option.rect.width(), base_height)

    def _meta_section_rects(self, content_rect: QRectF) -> list[QRectF]:
        column_gap = 0.0
        narrow_breakpoint = 320.0

        if content_rect.width() <= narrow_breakpoint:
            first_row_height = 28.0
            second_row_top = content_rect.top() + 32.0
            first_row_width = max(0.0, content_rect.width() - 12.0)
            first_col_width = first_row_width / 2
            second_col_width = first_row_width - first_col_width
            return [
                QRectF(content_rect.left(), content_rect.top(), first_col_width, first_row_height),
                QRectF(content_rect.left() + first_col_width + 12.0, content_rect.top(), second_col_width, first_row_height),
                QRectF(content_rect.left(), second_row_top, content_rect.width(), 28.0),
            ]

        stretches = [2, 1, 1]
        total_gap = column_gap * (len(stretches) - 1)
        available_width = max(0.0, content_rect.width() - total_gap)
        total_stretch = sum(stretches)

        rects: list[QRectF] = []
        x_cursor = content_rect.left()
        for index, stretch in enumerate(stretches):
            if total_stretch == 0:
                width = 0.0
            elif index == len(stretches) - 1:
                width = content_rect.right() - x_cursor
            else:
                width = round(available_width * stretch / total_stretch)
            rects.append(QRectF(x_cursor, content_rect.top(), max(0.0, width), content_rect.height()))
            x_cursor += width + column_gap
        return rects

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        card_rect = option.rect.adjusted(8, 6, -8, -6)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)

        background = QColor(TOKENS["colors"]["bg"])
        border = QColor(TOKENS["colors"]["border"])
        if hovered:
            background = QColor(TOKENS["colors"]["bg_subtle"])
            border = QColor("#AAB9CA")
        if selected:
            background = QColor(SELECTED_BG_COLOR)
            border = QColor(SELECTED_BORDER_COLOR)

        painter.setBrush(background)
        painter.setPen(QPen(border, 1.4))
        painter.drawRoundedRect(card_rect, TOKENS["radii"]["card"], TOKENS["radii"]["card"])
        if focused:
            painter.setPen(QPen(QColor(TOKENS["colors"]["focus"]), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card_rect.adjusted(2, 2, -2, -2), 6, 6)

        text_color = QColor(SELECTED_TEXT_COLOR if selected else TOKENS["colors"]["text_primary"])
        meta_color = QColor("#2B3A48" if selected else TOKENS["colors"]["text_secondary"])
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
        progress_rect = QRectF(left + 16, top + 40, card_rect.width() - 140, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(TOKENS["colors"]["progress_bg"]))
        painter.drawRoundedRect(progress_rect, 4, 4)
        painter.setBrush(QColor(TOKENS["colors"]["progress_fill"]))
        painter.drawRoundedRect(
            QRectF(progress_rect.left(), progress_rect.top(), progress_rect.width() * progress / 100.0, progress_rect.height()),
            4,
            4,
        )

        sections = [
            {
                "label": "Срок",
                "value": str(index.data(ROLE_DEADLINE) or "—"),
                "color": QColor(index.data(ROLE_DEADLINE_COLOR) or text_color.name()),
                "allow_elide": True,
            },
            {
                "label": "Подзадачи",
                "value": str(index.data(ROLE_SUBTASKS) or 0),
                "color": text_color,
                "allow_elide": False,
            },
            {
                "label": "Приоритет",
                "value": str(index.data(ROLE_PRIORITY) or "Обычный"),
                "color": text_color,
                "allow_elide": True,
            },
        ]
        meta_row_rect = QRectF(left + 16, top + 50, card_rect.width() - 32, 44)
        section_rects = self._meta_section_rects(meta_row_rect)
        cell_padding_x = 8.0
        label_height = 13.0
        value_height = 18.0
        cell_inner_gap = 3.0
        label_font = painter.font()
        label_font.setPointSizeF(max(8.0, label_font.pointSizeF() - 1.0))
        label_font.setBold(False)
        value_font = painter.font()
        value_font.setPointSizeF(max(9.0, value_font.pointSizeF()))
        value_font.setBold(True)
        separator_color = QColor(TOKENS["colors"]["border"])

        for section_index, section in enumerate(sections):
            cell_rect = section_rects[section_index]
            available_width = max(0.0, cell_rect.width() - 2 * cell_padding_x)
            label_rect = QRectF(cell_rect.left() + cell_padding_x, cell_rect.top(), available_width, label_height)
            value_rect = QRectF(
                cell_rect.left() + cell_padding_x,
                cell_rect.top() + label_height + cell_inner_gap,
                available_width,
                value_height,
            )

            painter.setFont(label_font)
            painter.setPen(meta_color)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, section["label"])

            painter.setFont(value_font)
            painter.setPen(section["color"])
            if section["allow_elide"]:
                elided_value = painter.fontMetrics().elidedText(
                    section["value"],
                    Qt.TextElideMode.ElideRight,
                    max(0, int(value_rect.width())),
                )
            else:
                elided_value = section["value"]
            painter.drawText(value_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_value)

            if section_index < len(sections) - 1 and meta_row_rect.width() > 320:
                painter.setPen(QPen(separator_color, 1))
                painter.drawLine(
                    QPointF(cell_rect.right(), cell_rect.top() + 2),
                    QPointF(cell_rect.right(), cell_rect.bottom() - 2),
                )

        badge_x = card_rect.right() - 12
        for text, color in reversed(index.data(ROLE_BADGES) or []):
            badge_width = max(40, len(text) * 7 + 14)
            badge_rect = QRectF(badge_x - badge_width, top + 1, badge_width, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(badge_rect, TOKENS["radii"]["chip"], TOKENS["radii"]["chip"])
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
            badge_x -= badge_width + 6

        if hovered:
            action_bg = QColor("#E2E9F2")
            action_fg = QColor("#243447")
            quick_actions = ["✓", "✎", "🗑"]
            action_x = card_rect.right() - 104
            for glyph in quick_actions:
                quick_rect = QRectF(action_x, top + 34, 28, 20)
                painter.setBrush(action_bg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(quick_rect, 6, 6)
                painter.setPen(action_fg)
                painter.drawText(quick_rect, Qt.AlignmentFlag.AlignCenter, glyph)
                action_x += 32
        painter.restore()


class TaskTreeWidget(QTreeWidget):
    quick_action_requested = Signal(str)
    subtasks_reordered = Signal(int, list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._hover_item: Optional[QTreeWidgetItem] = None

    def _action_regions(self, item: QTreeWidgetItem) -> Dict[str, QRectF]:
        rect = self.visualItemRect(item).adjusted(8, 6, -8, -6)
        y = rect.top() + 34
        return {
            "done": QRectF(rect.right() - 104, y, 28, 20),
            "edit": QRectF(rect.right() - 72, y, 28, 20),
            "delete": QRectF(rect.right() - 40, y, 28, 20),
        }

    def mouseMoveEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is not self._hover_item:
            self._hover_item = item
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover_item = None
        self.viewport().update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        item = self.itemAt(event.pos())
        if item is not None:
            point = QPointF(event.pos())
            for action, rect in self._action_regions(item).items():
                if rect.contains(point):
                    self.setCurrentItem(item)
                    self.quick_action_requested.emit(action)
                    return
        super().mousePressEvent(event)

    def dropEvent(self, event) -> None:
        super().dropEvent(event)
        parent = self.currentItem().parent() if self.currentItem() is not None else None
        if parent is None:
            return
        parent_ref = parent.data(0, ROLE_ITEM_REF)
        if not isinstance(parent_ref, TreeItemRef) or parent_ref.kind != ItemKind.TASK:
            return

        ordered_subtask_ids = []
        for index in range(parent.childCount()):
            child = parent.child(index)
            child_ref = child.data(0, ROLE_ITEM_REF)
            if isinstance(child_ref, TreeItemRef) and child_ref.kind == ItemKind.SUBTASK:
                ordered_subtask_ids.append(child_ref.id)

        if ordered_subtask_ids:
            self.subtasks_reordered.emit(parent_ref.id, ordered_subtask_ids)


class GraphEdgeItem(QGraphicsLineItem):
    def __init__(self, source_item: "GraphNodeItem", target_item: "GraphNodeItem", relation_type: str):
        super().__init__()
        self.source_item = source_item
        self.target_item = target_item
        self.relation_type = relation_type
        self.setZValue(-1)
        self._arrow_points = (QPointF(), QPointF(), QPointF())
        self._apply_style()
        self.update_position()

    def _apply_style(self) -> None:
        if self.relation_type == "hierarchy":
            pen = QPen(QColor("#2D9D5B"), 2)
        elif self.relation_type == "subtask_dependency":
            pen = QPen(QColor("#9A4DFF"), 2)
            pen.setStyle(Qt.PenStyle.DotLine)
        else:
            pen = QPen(QColor("#435A78"), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)

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

        arrow_size = 10.0
        left = QPointF(
            end.x() - ux * arrow_size - uy * (arrow_size * 0.5),
            end.y() - uy * arrow_size + ux * (arrow_size * 0.5),
        )
        right = QPointF(
            end.x() - ux * arrow_size + uy * (arrow_size * 0.5),
            end.y() - uy * arrow_size - ux * (arrow_size * 0.5),
        )
        self._arrow_points = (end, left, right)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        painter.save()
        painter.setPen(self.pen())
        painter.setBrush(QBrush(self.pen().color()))
        end, left, right = self._arrow_points
        painter.drawPolygon(QPolygonF([end, left, right]))
        painter.restore()


class GraphNodeItem(QGraphicsEllipseItem):
    def __init__(self, dialog: "TaskGraphDialog", node_id: str, title: str, *, is_subtask: bool = False):
        super().__init__(0, 0, NODE_WIDTH, NODE_HEIGHT)
        self.dialog = dialog
        self.node_id = node_id
        self.edges = []

        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setBrush(QBrush(QColor("#F5FBF7") if is_subtask else Qt.GlobalColor.white))
        self.setFlags(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable
        )

        label = QGraphicsSimpleTextItem(title, self)
        label.setPos(12, NODE_HEIGHT / 2 - 10)

    def scene_center(self) -> QPointF:
        return self.scenePos() + QPointF(NODE_WIDTH / 2, NODE_HEIGHT / 2)

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
            self.dialog.persist_layout(self.node_id, result)
        return result


class TaskGraphDialog(QDialog):
    RELATION_ALL = "Все связи"
    RELATION_HIERARCHY = "Только иерархия"
    RELATION_DEPENDENCY = "Только зависимости"

    def __init__(self, db_path: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.db_path = db_path
        self._node_items: Dict[str, GraphNodeItem] = {}
        self._graph_links: set[Tuple[str, str, str]] = set()
        self._last_fingerprint: Optional[
            Tuple[
                Tuple[int, ...],
                Tuple[Tuple[int, int], ...],
                Tuple[Tuple[int, int], ...],
                Tuple[Tuple[int, int, str], ...],
            ]
        ] = None

        self.setWindowTitle("Граф задач")
        self.resize(1000, 680)
        self._build_ui()
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(1200)
        self._sync_timer.timeout.connect(self._refresh_if_data_changed)
        self._sync_timer.start()
        self.refresh_graph(force=True)

    @staticmethod
    def _task_node_id(task_id: int) -> str:
        return f"task:{task_id}"

    @staticmethod
    def _subtask_node_id(subtask_id: int) -> str:
        return f"subtask:{subtask_id}"

    def _current_fingerprint(self):
        all_tasks = task_service.list_tasks(self.db_path)
        dependencies = task_service.list_task_links(self.db_path)
        subtask_dependencies = task_service.list_subtask_links(self.db_path)
        hierarchy: list[tuple[int, int]] = []
        for task in all_tasks:
            for subtask in task_service.list_subtasks(self.db_path, task.id):
                hierarchy.append((task.id, subtask.id))
        return (
            tuple(sorted(task.id for task in all_tasks)),
            tuple(sorted(dependencies)),
            tuple(sorted(hierarchy)),
            tuple(sorted(subtask_dependencies)),
        )

    def _refresh_if_data_changed(self) -> None:
        current = self._current_fingerprint()
        if current != self._last_fingerprint:
            self.refresh_graph(force=True)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        add_link_btn = QPushButton("Создать связь", self)
        add_link_btn.clicked.connect(self.add_link)
        controls.addWidget(add_link_btn)

        remove_link_btn = QPushButton("Удалить связь", self)
        remove_link_btn.clicked.connect(self.remove_link)
        controls.addWidget(remove_link_btn)

        controls.addWidget(QLabel("Показать", self))
        self.relation_filter = QComboBox(self)
        self.relation_filter.addItems([self.RELATION_ALL, self.RELATION_HIERARCHY, self.RELATION_DEPENDENCY])
        self.relation_filter.currentIndexChanged.connect(self.refresh_graph)
        controls.addWidget(self.relation_filter)

        refresh_btn = QPushButton("Обновить", self)
        refresh_btn.clicked.connect(self.refresh_graph)
        controls.addWidget(refresh_btn)

        controls.addStretch(1)
        layout.addLayout(controls)

        legend = QFrame(self)
        legend_layout = QHBoxLayout(legend)
        legend_layout.setContentsMargins(8, 6, 8, 6)
        hierarchy_legend = QLabel("━━ Иерархия task → subtask", legend)
        hierarchy_legend.setStyleSheet("color: #2D9D5B;")
        task_dependency_legend = QLabel("- - - task → task", legend)
        task_dependency_legend.setStyleSheet("color: #435A78;")
        subtask_dependency_legend = QLabel("⋯⋯⋯ subtask → subtask", legend)
        subtask_dependency_legend.setStyleSheet("color: #9A4DFF;")
        legend_layout.addWidget(hierarchy_legend)
        legend_layout.addSpacing(20)
        legend_layout.addWidget(task_dependency_legend)
        legend_layout.addSpacing(20)
        legend_layout.addWidget(subtask_dependency_legend)
        legend_layout.addStretch(1)
        layout.addWidget(legend)

        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 1600, 1100)

        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        layout.addWidget(self.view)

    def refresh_graph(self, force: bool = False) -> None:
        self.scene.clear()
        self._node_items.clear()

        all_tasks = task_service.list_tasks(self.db_path)
        layouts = task_service.get_task_layouts(self.db_path)
        task_dependency_links = {
            (self._task_node_id(source), self._task_node_id(target), "task_dependency")
            for source, target in task_service.list_task_links(self.db_path)
        }
        subtask_dependency_links = {
            (self._subtask_node_id(source), self._subtask_node_id(target), "subtask_dependency")
            for source, target, _ in task_service.list_subtask_links(self.db_path)
        }
        hierarchy_links = set()

        for index, task in enumerate(all_tasks):
            node_id = self._task_node_id(task.id)
            node = GraphNodeItem(self, node_id, f"#{task.id} {task.title}")
            x, y = layouts.get(task.id, (80.0 + (index % 5) * 230.0, 80.0 + (index // 5) * 140.0))
            node.setPos(float(x), float(y))
            self.scene.addItem(node)
            self._node_items[node_id] = node

            subtasks = task_service.list_subtasks(self.db_path, task.id)
            for sub_index, subtask in enumerate(subtasks):
                subtask_node_id = self._subtask_node_id(subtask.id)
                sub_node = GraphNodeItem(self, subtask_node_id, f"↳ #{subtask.id} {subtask.title}", is_subtask=True)
                sx = float(x) + 70.0 + ((sub_index % 2) * 190.0)
                sy = float(y) + 110.0 + (sub_index * 85.0)
                sub_node.setPos(sx, sy)
                self.scene.addItem(sub_node)
                self._node_items[subtask_node_id] = sub_node
                hierarchy_links.add((node_id, subtask_node_id, "hierarchy"))

        self._graph_links = task_dependency_links | subtask_dependency_links | hierarchy_links
        selected_filter = self.relation_filter.currentText()
        for source_id, target_id, relation_type in sorted(self._graph_links):
            if selected_filter == self.RELATION_HIERARCHY and relation_type != "hierarchy":
                continue
            if selected_filter == self.RELATION_DEPENDENCY and relation_type == "hierarchy":
                continue

            source_node = self._node_items.get(source_id)
            target_node = self._node_items.get(target_id)
            if not source_node or not target_node:
                continue
            edge = GraphEdgeItem(source_node, target_node, relation_type)
            self.scene.addItem(edge)
            source_node.edges.append(edge)
            target_node.edges.append(edge)

        self._last_fingerprint = self._current_fingerprint()

    def persist_layout(self, node_id: str, position: QPointF) -> None:
        if not node_id.startswith("task:"):
            return
        task_id = int(node_id.split(":", maxsplit=1)[1])
        task_service.set_task_layout(self.db_path, task_id, position.x(), position.y())

    def _pick_task_id(self, title: str, options: list[Tuple[int, str]]) -> Optional[int]:
        labels = [f"#{task_id} {task_title}" for task_id, task_title in options]
        selected, ok = QInputDialog.getItem(self, title, "Выберите задачу", labels, 0, False)
        if not ok:
            return None
        index = labels.index(selected)
        return options[index][0]

    def add_link(self) -> None:
        link_kind, ok = QInputDialog.getItem(
            self,
            "Тип связи",
            "Выберите тип",
            ["task → task", "subtask → subtask"],
            0,
            False,
        )
        if not ok:
            return

        if link_kind == "task → task":
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
        else:
            subtasks = []
            for task in task_service.list_tasks(self.db_path):
                for subtask in task_service.list_subtasks(self.db_path, task.id):
                    subtasks.append((subtask.id, f"#{subtask.id} {subtask.title} (task #{task.id})"))
            if len(subtasks) < 2:
                QMessageBox.information(self, "Недостаточно подзадач", "Нужно минимум две подзадачи")
                return

            source_id = self._pick_task_id("Источник связи", subtasks)
            if source_id is None:
                return
            target_options = [pair for pair in subtasks if pair[0] != source_id]
            target_id = self._pick_task_id("Цель связи", target_options)
            if target_id is None:
                return
            created = task_service.create_subtask_link(self.db_path, source_id, target_id)

        if not created:
            QMessageBox.warning(
                self,
                "Связь не создана",
                "Проверьте, что связь не дублируется и не образует цикл.",
            )
            return
        self.refresh_graph(force=True)

    def remove_link(self) -> None:
        task_links = [("task", source, target) for source, target in task_service.list_task_links(self.db_path)]
        subtask_links = [
            ("subtask", source, target)
            for source, target, _ in task_service.list_subtask_links(self.db_path)
        ]
        links = sorted(task_links + subtask_links)
        if not links:
            QMessageBox.information(self, "Нет связей", "Удалять пока нечего")
            return

        link_labels = [
            f"{kind}: {source} -> {target}" for kind, source, target in links
        ]
        selected, ok = QInputDialog.getItem(self, "Удалить связь", "Выберите связь", link_labels, 0, False)
        if not ok:
            return

        index = link_labels.index(selected)
        kind, source_id, target_id = links[index]
        if kind == "task":
            task_service.delete_task_link(self.db_path, source_id, target_id)
        else:
            task_service.delete_subtask_link(self.db_path, source_id, target_id)
        self.refresh_graph(force=True)


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
        self._is_refreshing_tree = False
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
        self.tasks_list = TaskTreeWidget(self)
        self.tasks_list.setHeaderHidden(True)
        self.tasks_list.setColumnCount(1)
        self.tasks_list.itemSelectionChanged.connect(self.on_selection_changed)
        self.tasks_list.itemChanged.connect(self._on_tree_item_changed)
        self.tasks_list.itemActivated.connect(self._open_selected_item_card)
        self.tasks_list.quick_action_requested.connect(self._handle_quick_action)
        self.tasks_list.subtasks_reordered.connect(self._on_subtasks_reordered)
        self.tasks_list.setMouseTracking(True)
        self.tasks_list.setAllColumnsShowFocus(True)
        self.tasks_list.setWordWrap(False)
        self.tasks_list.setIndentation(26)
        self.tasks_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tasks_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tasks_list.customContextMenuRequested.connect(self._show_task_context_menu)
        self.task_delegate = TaskCardDelegate(self.tasks_list)
        self.tasks_list.setItemDelegate(self.task_delegate)
        left_layout.addWidget(self.tasks_list)

        self.empty_state_label = QLabel(self)
        self.empty_state_label.setWordWrap(True)
        self.empty_state_label.setText(
            "Пока нет задач. Нажмите «Новая задача», чтобы создать первую карточку.\n"
            "Подсказка: для быстрого редактирования используйте двойной клик по заголовку."
        )
        self.empty_state_label.hide()
        left_layout.addWidget(self.empty_state_label)

        left_actions = QHBoxLayout()
        add_btn = QPushButton("Новая задача", self)
        add_btn.clicked.connect(self.add_task)
        left_actions.addWidget(add_btn)

        add_subtask_btn = QPushButton("Подзадача", self)
        add_subtask_btn.clicked.connect(self.add_subtask)
        left_actions.addWidget(add_subtask_btn)

        self.complete_btn = QPushButton("Переключить выполнение", self)
        self.complete_btn.clicked.connect(self.toggle_selected_done)
        left_actions.addWidget(self.complete_btn)

        self.delete_btn = QPushButton("Удалить", self)
        self.delete_btn.clicked.connect(self.delete_task)
        left_actions.addWidget(self.delete_btn)

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
        self.breadcrumbs_label.setWordWrap(False)
        self.breadcrumbs_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        right_layout.addWidget(self.breadcrumbs_label)

        form = QFormLayout()
        self.title_input = QLineEdit(self)
        form.addRow("Заголовок", self.title_input)

        self.status_checkbox = QCheckBox("Задача выполнена", self)
        form.addRow("Статус", self.status_checkbox)

        self.priority_input = QComboBox(self)
        self.priority_input.addItems(list(PRIORITY_LABELS.values()))
        form.addRow("Приоритет", self.priority_input)

        self.reminder_input = QDateTimeEdit(self)
        self.reminder_input.setCalendarPopup(True)
        self.reminder_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        form.addRow("Напоминание", self.reminder_input)

        self.has_due_checkbox = QCheckBox("Установить дедлайн", self)
        self.has_due_checkbox.setChecked(False)
        form.addRow("Дедлайн", self.has_due_checkbox)

        self.due_input = QDateTimeEdit(self)
        self.due_input.setCalendarPopup(True)
        self.due_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.due_input.setEnabled(False)
        self.has_due_checkbox.toggled.connect(self.due_input.setEnabled)
        form.addRow("Дата и время дедлайна", self.due_input)

        self.note_toolbar = QToolBar("Форматирование", self)
        self._build_note_toolbar()
        right_layout.addWidget(self.note_toolbar)

        self.note_input = QTextEdit(self)
        self.note_input.setPlaceholderText("Заметка (поддерживает форматирование)")
        self.note_input.setFixedHeight(180)
        form.addRow("Заметка", self.note_input)
        right_layout.addLayout(form)

        right_layout.addWidget(QLabel("Вложения", self))
        self.attachments_list = QListWidget(self)
        self.attachments_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        right_layout.addWidget(self.attachments_list)
        attachments_actions = QHBoxLayout()
        add_attachment_btn = QPushButton("Прикрепить файл", self)
        add_attachment_btn.clicked.connect(self.add_attachment)
        attachments_actions.addWidget(add_attachment_btn)
        open_attachment_btn = QPushButton("Открыть", self)
        open_attachment_btn.clicked.connect(self.open_selected_attachment)
        attachments_actions.addWidget(open_attachment_btn)
        remove_attachment_btn = QPushButton("Удалить", self)
        remove_attachment_btn.clicked.connect(self.delete_selected_attachment)
        attachments_actions.addWidget(remove_attachment_btn)
        right_layout.addLayout(attachments_actions)

        card_actions = QHBoxLayout()
        self.save_card_btn = QPushButton("Сохранить", self)
        self.save_card_btn.clicked.connect(self.save_selected_task)
        card_actions.addWidget(self.save_card_btn)

        clear_reminder_btn = QPushButton("Очистить напоминание", self)
        clear_reminder_btn.clicked.connect(self.clear_selected_reminder)
        card_actions.addWidget(clear_reminder_btn)

        clear_due_btn = QPushButton("Очистить дедлайн", self)
        clear_due_btn.clicked.connect(self.clear_selected_due)
        card_actions.addWidget(clear_due_btn)

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

    def _build_note_toolbar(self) -> None:
        bold_action = QAction("Ж", self)
        bold_action.triggered.connect(lambda: self.note_input.setFontWeight(700 if self.note_input.fontWeight() < 700 else 400))
        self.note_toolbar.addAction(bold_action)

        italic_action = QAction("К", self)
        italic_action.triggered.connect(lambda: self.note_input.setFontItalic(not self.note_input.fontItalic()))
        self.note_toolbar.addAction(italic_action)

        underline_action = QAction("Ч", self)
        underline_action.triggered.connect(lambda: self.note_input.setFontUnderline(not self.note_input.fontUnderline()))
        self.note_toolbar.addAction(underline_action)

        self.note_toolbar.addSeparator()

        bullet_action = QAction("• Список", self)
        bullet_action.triggered.connect(lambda: self.note_input.insertHtml("<ul><li></li></ul>"))
        self.note_toolbar.addAction(bullet_action)

        numbered_action = QAction("1. Список", self)
        numbered_action.triggered.connect(lambda: self.note_input.insertHtml("<ol><li></li></ol>"))
        self.note_toolbar.addAction(numbered_action)

        self.note_toolbar.addSeparator()

        h_action = QAction("H2", self)
        h_action.triggered.connect(lambda: self._wrap_selection_with_tag("h2"))
        self.note_toolbar.addAction(h_action)

        quote_action = QAction("Цитата", self)
        quote_action.triggered.connect(lambda: self._wrap_selection_with_tag("blockquote"))
        self.note_toolbar.addAction(quote_action)

    def _wrap_selection_with_tag(self, tag: str) -> None:
        cursor = self.note_input.textCursor()
        selected = cursor.selectedText().strip()
        if not selected:
            selected = "Текст"
        cursor.insertHtml(f"<{tag}>{selected}</{tag}>")

    def _apply_density(self) -> None:
        density = "compact" if self.density_mode.currentText().lower().startswith("compact") else "comfortable"
        self.task_delegate.set_density(density)
        self.tasks_list.doItemsLayout()
        self.tasks_list.viewport().update()

    def _run_ui_flow(
        self,
        *,
        busy_widget: Optional[QWidget],
        operation: Callable[[], object],
        on_success: Callable[[object], None],
        error_message: str,
    ) -> bool:
        if busy_widget is not None:
            busy_widget.setEnabled(False)

        try:
            payload = operation()
        except task_service.DeadlineValidationError as exc:
            QMessageBox.warning(self, "Ошибка валидации", str(exc))
            return False
        except Exception:
            QMessageBox.warning(self, "Ошибка", error_message)
            return False
        finally:
            if busy_widget is not None:
                busy_widget.setEnabled(True)

        if payload is None or payload is False:
            QMessageBox.warning(self, "Ошибка", error_message)
            return False

        on_success(payload)
        return True

    def clear_search(self) -> None:
        self.search_input.setText("")
        self.status_filter.setCurrentIndex(0)
        self.subtasks_filter.setCurrentIndex(0)
        self.sort_mode.setCurrentIndex(0)
        self.refresh_tasks()

    def refresh_tasks(self) -> None:
        self._is_refreshing_tree = True
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
        now = datetime.now()
        for task in self._tasks_cache:
            done_subtasks, total_subtasks = progress_map[task.id]
            percent = int((done_subtasks / total_subtasks) * 100) if total_subtasks else 0
            due_value = task.due_datetime or task.reminder_datetime
            deadline = "—"
            deadline_color = TOKENS["colors"]["text_primary"]
            if due_value:
                if not task.is_done and due_value < now:
                    overdue_days = max(1, (now - due_value).days + 1)
                    deadline = f"Просрочено {overdue_days}д"
                    deadline_color = TOKENS["colors"]["danger"]
                else:
                    deadline = due_value.strftime("%d.%m %H:%M")
            priority_label = _priority_to_label(task.priority)
            meta = f"ID #{task.id} · {done_subtasks}/{total_subtasks} выполнено"

            root_item = QTreeWidgetItem([task.title])
            root_item.setData(0, ROLE_ITEM_REF, TreeItemRef(kind=ItemKind.TASK, id=task.id, level=0))
            root_item.setData(0, ROLE_META, meta)
            root_item.setData(0, ROLE_PROGRESS, percent)
            root_item.setData(0, ROLE_DEADLINE, deadline)
            root_item.setData(0, ROLE_DEADLINE_COLOR, deadline_color)
            root_item.setData(0, ROLE_SUBTASKS, total_subtasks)
            root_item.setData(0, ROLE_DONE, task.is_done)
            root_item.setData(0, ROLE_PRIORITY, priority_label)
            root_item.setToolTip(
                0,
                "\n".join(
                    [
                        f"Срок: {deadline}",
                        f"Подзадачи: {total_subtasks}",
                        f"Приоритет: {priority_label}",
                    ]
                ),
            )
            root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsEditable)

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
                child_priority_label = _priority_to_label(subtask.priority)
                child.setData(0, ROLE_PRIORITY, child_priority_label)
                child.setData(0, ROLE_DEADLINE_COLOR, TOKENS["colors"]["text_primary"])
                child.setToolTip(
                    0,
                    "\n".join(
                        [
                            f"Срок: {child.data(0, ROLE_DEADLINE)}",
                            "Подзадачи: 0",
                            f"Приоритет: {child_priority_label}",
                        ]
                    ),
                )
                child.setData(0, ROLE_BADGES, [("SUB", "#6A7A8D")])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)
                root_item.addChild(child)

        self.tasks_list.expandAll()
        if selected_ref is not None:
            self._select_item_in_tree(selected_ref)
        elif self.tasks_list.topLevelItemCount() > 0:
            self.tasks_list.setCurrentItem(self.tasks_list.topLevelItem(0))
        else:
            self._clear_card()
        self._is_refreshing_tree = False
        self._update_empty_state(query)

    def _on_subtasks_reordered(self, task_id: int, ordered_subtask_ids: List[int]) -> None:
        task_service.bulk_reorder_subtasks(self.db_path, task_id, ordered_subtask_ids)
        self.refresh_tasks()

    def _update_empty_state(self, query: str) -> None:
        empty = self.tasks_list.topLevelItemCount() == 0
        if not empty:
            self.empty_state_label.hide()
            return
        if query:
            self.empty_state_label.setText("По запросу ничего не найдено. Попробуйте изменить фильтр или строку поиска.")
        else:
            self.empty_state_label.setText(
                "Пока нет задач. Нажмите «Новая задача», чтобы создать первую карточку.\n"
                "Подсказка: Tab/Shift+Tab и стрелки работают для навигации по списку."
            )
        self.empty_state_label.show()

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
        self.has_due_checkbox.setChecked(False)
        self.due_input.setDateTime(datetime.now())
        self.note_input.setHtml("")
        self.priority_input.setCurrentText("Средний")
        self.attachments_list.clear()

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
            self.note_input.setHtml(subtask.note or "")
            self.reminder_input.setDateTime(subtask.reminder_datetime or datetime.now())
            self.has_due_checkbox.setChecked(subtask.due_datetime is not None)
            self.due_input.setDateTime(subtask.due_datetime or datetime.now())
            self.priority_input.setCurrentText(_priority_to_label(subtask.priority))
            self._load_attachments("subtask", subtask.id)
            return

        task = self._selected_task()
        if task is None:
            self._clear_card()
            return
        self.breadcrumbs_label.setText(task.title)
        self.title_input.setText(task.title)
        self.status_checkbox.setText("Задача выполнена")
        self.status_checkbox.setChecked(task.is_done)
        self.note_input.setHtml(task.note or "")
        self.reminder_input.setDateTime(task.reminder_datetime or datetime.now())
        self.has_due_checkbox.setChecked(task.due_datetime is not None)
        self.due_input.setDateTime(task.due_datetime or datetime.now())
        self.priority_input.setCurrentText(_priority_to_label(task.priority))
        self._load_attachments("task", task.id)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._is_refreshing_tree or column != 0:
            return
        item_ref = item.data(0, ROLE_ITEM_REF)
        if not isinstance(item_ref, TreeItemRef):
            return
        new_title = item.text(0).strip().replace("↳ ", "")
        if not new_title:
            QMessageBox.information(self, "Пустой заголовок", "Введите название")
            self.refresh_tasks()
            return
        if item_ref.kind == ItemKind.SUBTASK:
            self._run_ui_flow(
                busy_widget=self.tasks_list,
                operation=lambda: task_service.update_subtask(self.db_path, item_ref.id, title=new_title),
                on_success=lambda updated: (
                    self.refresh_tasks(),
                    self._focus_subtask_in_tree(updated.task_id, updated.id),
                ),
                error_message="Не удалось обновить подзадачу. Попробуйте снова.",
            )
            return
        self._run_ui_flow(
            busy_widget=self.tasks_list,
            operation=lambda: task_service.update_task(self.db_path, item_ref.id, title=new_title),
            on_success=lambda updated: (self.refresh_tasks(), self._select_task_in_tree(updated.id)),
            error_message="Не удалось обновить задачу. Попробуйте снова.",
        )

    def _load_attachments(self, entity_type: str, entity_id: int) -> None:
        self.attachments_list.clear()
        for attachment in task_service.list_attachments(self.db_path, entity_type=entity_type, entity_id=entity_id):
            size_kb = max(1, math.ceil(attachment.size / 1024))
            item = QListWidgetItem(
                f"{attachment.original_name} ({attachment.mime}, {size_kb} KB)",
                self.attachments_list,
            )
            item.setData(Qt.ItemDataRole.UserRole, attachment.id)

    def add_attachment(self) -> None:
        item_ref = self._selected_item_ref()
        if item_ref is None:
            QMessageBox.information(self, "Выберите элемент", "Сначала выберите задачу или подзадачу")
            return

        path_text, _ = QFileDialog.getOpenFileName(self, "Выберите файл")
        if not path_text:
            return

        entity_type = "subtask" if item_ref.kind == ItemKind.SUBTASK else "task"
        entity_id = item_ref.id
        try:
            task_service.create_attachment(self.db_path, entity_type=entity_type, entity_id=entity_id, source_path=Path(path_text))
        except task_service.AttachmentValidationError as exc:
            QMessageBox.warning(self, "Ошибка вложения", str(exc))
            return
        except task_service.AttachmentStorageError as exc:
            QMessageBox.warning(self, "Файл недоступен", str(exc))
            return

        self._load_attachments(entity_type, entity_id)

    def _selected_attachment_id(self) -> Optional[int]:
        item = self.attachments_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, int) else None

    def open_selected_attachment(self) -> None:
        attachment_id = self._selected_attachment_id()
        if attachment_id is None:
            QMessageBox.information(self, "Открыть вложение", "Выберите вложение из списка")
            return
        attachment = task_service.get_attachment(self.db_path, attachment_id)
        if attachment is None:
            QMessageBox.warning(self, "Ошибка", "Вложение не найдено")
            return
        target = Path(attachment.file_path)
        if not target.exists():
            QMessageBox.warning(self, "Файл отсутствует", f"Файл не найден: {target}")
            return
        if not os.access(target, os.R_OK):
            QMessageBox.warning(self, "Файл недоступен", f"Нет доступа к файлу: {target}")
            return
        QDesktopServices.openUrl(target.as_uri())

    def delete_selected_attachment(self) -> None:
        attachment_id = self._selected_attachment_id()
        if attachment_id is None:
            QMessageBox.information(self, "Удалить вложение", "Выберите вложение из списка")
            return
        if not task_service.delete_attachment(self.db_path, attachment_id):
            QMessageBox.warning(self, "Ошибка", "Не удалось удалить вложение")
            return
        self.on_selection_changed()

    def _handle_quick_action(self, action: str) -> None:
        if action == "done":
            self.toggle_selected_done()
        elif action == "delete":
            self.delete_task()
        elif action == "edit":
            item = self.tasks_list.currentItem()
            if item:
                self.tasks_list.editItem(item, 0)

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
        due_datetime = self.due_input.dateTime().toPython() if self.has_due_checkbox.isChecked() else None
        note = self.note_input.toHtml()
        done = self.status_checkbox.isChecked()
        priority = _label_to_priority(self.priority_input.currentText())

        if item_ref.kind == ItemKind.SUBTASK:
            self._run_ui_flow(
                busy_widget=self.save_card_btn,
                operation=lambda: task_service.update_subtask(
                    self.db_path,
                    item_ref.id,
                    title=title,
                    is_done=done,
                    reminder_datetime=reminder,
                    due_datetime=due_datetime,
                    note=note,
                    priority=priority,
                ),
                on_success=lambda updated: (
                    self.refresh_tasks(),
                    self._focus_subtask_in_tree(updated.task_id, updated.id),
                ),
                error_message="Не удалось сохранить подзадачу. Проверьте данные и попробуйте снова.",
            )
            return

        self._run_ui_flow(
            busy_widget=self.save_card_btn,
            operation=lambda: task_service.update_task(
                self.db_path,
                item_ref.id,
                title=title,
                is_done=done,
                reminder_datetime=reminder,
                due_datetime=due_datetime,
                note=note,
                priority=priority,
            ),
            on_success=lambda updated: (self.refresh_tasks(), self._select_task_in_tree(updated.id)),
            error_message="Не удалось сохранить задачу. Проверьте данные и попробуйте снова.",
        )

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

    def toggle_selected_done(self) -> None:
        subtask_id = self._selected_subtask_id()
        if subtask_id is not None:
            current = task_service.get_subtask(self.db_path, subtask_id)
            if not current:
                QMessageBox.warning(self, "Ошибка", "Подзадача не найдена. Обновите список.")
                self.refresh_tasks()
                return
            self._run_ui_flow(
                busy_widget=self.complete_btn,
                operation=lambda: task_service.update_subtask(self.db_path, subtask_id, is_done=not current.is_done),
                on_success=lambda updated: (
                    self.refresh_tasks(),
                    self._focus_subtask_in_tree(updated.task_id, updated.id),
                ),
                error_message="Не удалось обновить статус подзадачи. Попробуйте снова.",
            )
            return

        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу или подзадачу")
            return

        self._run_ui_flow(
            busy_widget=self.complete_btn,
            operation=lambda: task_service.update_task(self.db_path, task.id, is_done=not task.is_done),
            on_success=lambda updated: (self.refresh_tasks(), self._select_task_in_tree(updated.id)),
            error_message="Не удалось обновить статус задачи. Попробуйте снова.",
        )

    def mark_selected_done(self) -> None:
        self.toggle_selected_done()

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

    def clear_selected_due(self) -> None:
        item_ref = self._selected_item_ref()
        if item_ref is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу или подзадачу для обновления")
            return
        if item_ref.kind == ItemKind.SUBTASK:
            updated = task_service.update_subtask(self.db_path, item_ref.id, due_datetime=None)
            if not updated:
                QMessageBox.warning(self, "Ошибка", "Не удалось очистить дедлайн подзадачи")
                return
            self.refresh_tasks()
            self._focus_subtask_in_tree(updated.task_id, updated.id)
            return

        task_service.update_task(self.db_path, item_ref.id, due_datetime=None)
        self.refresh_tasks()
        self._select_task_in_tree(item_ref.id)

    def delete_task(self) -> None:
        subtask_id = self._selected_subtask_id()
        if subtask_id is not None:
            answer = QMessageBox.question(self, "Удалить подзадачу", "Удалить выбранную подзадачу?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._run_ui_flow(
                busy_widget=self.delete_btn,
                operation=lambda: task_service.delete_subtask(self.db_path, subtask_id),
                on_success=lambda _result: self.refresh_tasks(),
                error_message="Не удалось удалить подзадачу. Попробуйте снова.",
            )
            return

        task = self._selected_task()
        if task is None:
            QMessageBox.information(self, "Выберите задачу", "Выберите задачу для удаления")
            return

        answer = QMessageBox.question(self, "Удалить задачу", f"Удалить '{task.title}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._run_ui_flow(
            busy_widget=self.delete_btn,
            operation=lambda: task_service.delete_task(self.db_path, task.id),
            on_success=lambda _result: self.refresh_tasks(),
            error_message="Не удалось удалить задачу. Попробуйте снова.",
        )

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
        mark_done_action = menu.addAction("Переключить выполнение")
        delete_action = menu.addAction("Удалить")
        menu.addSeparator()
        convert_action = menu.addAction("Сделать подзадачей…")
        chosen = menu.exec(self.tasks_list.viewport().mapToGlobal(pos))
        if chosen == create_task_action:
            self.add_task()
        if chosen == create_subtask_action:
            self.add_subtask()
        if chosen == mark_done_action:
            self.toggle_selected_done()
        if chosen == delete_action:
            self.delete_task()
        if chosen == convert_action:
            self.convert_task_to_subtask()

    def open_graph_mode(self) -> None:
        dialog = TaskGraphDialog(self.db_path, self)
        dialog.exec()
        self.refresh_tasks()


def main() -> int:
    from .ui_qt.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow(DB_PATH)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
