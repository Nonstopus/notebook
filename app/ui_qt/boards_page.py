from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services import tasks as task_service


class BoardColumnList(QListWidget):
    def __init__(self, column_id: int, on_drop, parent: QWidget | None = None):
        super().__init__(parent)
        self.column_id = column_id
        self._on_drop = on_drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)
        self.setAlternatingRowColors(True)

    def dragEnterEvent(self, event) -> None:
        if event.source() and isinstance(event.source(), QListWidget):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        source_widget = event.source() if isinstance(event.source(), BoardColumnList) else None
        dragged_item = source_widget.currentItem() if source_widget else None
        dragged_board_item_id = None
        if dragged_item is not None:
            dragged_board_item_id = dragged_item.data(Qt.ItemDataRole.UserRole)

        super().dropEvent(event)

        target_position = self.indexAt(event.position().toPoint()).row()
        if target_position < 0:
            target_position = self.count() - 1

        if dragged_board_item_id is not None and target_position >= 0:
            self._on_drop(self.column_id, int(dragged_board_item_id), target_position)


class BoardsPage(QWidget):
    """Экран канбан-досок."""

    def __init__(self, db_path: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.db_path = db_path
        self.board_selector = QComboBox(self)
        self.columns_layout = QHBoxLayout()
        self.column_widgets: dict[int, BoardColumnList] = {}

        self._build_ui()
        self.refresh_boards()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Доска", self))
        root.addWidget(self.board_selector)
        root.addLayout(self.columns_layout)
        self.board_selector.currentIndexChanged.connect(self._render_board)

    def _column(self, title: str, list_widget: QListWidget) -> QVBoxLayout:
        column = QVBoxLayout()
        label = QLabel(title, self)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(label)
        column.addWidget(list_widget)
        return column

    def _active_board_id(self) -> int | None:
        value = self.board_selector.currentData()
        return int(value) if value is not None else None

    def _clear_columns(self) -> None:
        while self.columns_layout.count():
            item = self.columns_layout.takeAt(0)
            child_layout = item.layout()
            if child_layout:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)
                    widget = child_item.widget()
                    if widget:
                        widget.deleteLater()
        self.column_widgets.clear()

    def _render_board(self) -> None:
        board_id = self._active_board_id()
        self._clear_columns()
        if board_id is None:
            return

        columns = task_service.list_board_columns(self.db_path, board_id)
        items = task_service.list_board_items(self.db_path, board_id)
        tasks_by_id = {task.id: task for task in task_service.list_tasks(self.db_path)}

        for column in columns:
            list_widget = BoardColumnList(column.id, self._persist_column_order, self)
            self.column_widgets[column.id] = list_widget
            self.columns_layout.addLayout(self._column(column.name, list_widget))

        for item in items:
            task = tasks_by_id.get(item.task_id)
            if not task or item.column_id not in self.column_widgets:
                continue
            list_item = QListWidgetItem(f"#{task.id} {task.title}")
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
            self.column_widgets[item.column_id].addItem(list_item)

        # Автоматически добавляем неразмещённые задачи в первую колонку доски.
        for task in tasks_by_id.values():
            existing = task_service.ensure_board_item(self.db_path, board_id, task.id)
            if existing and existing.column_id in self.column_widgets:
                already = [
                    self.column_widgets[existing.column_id].item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.column_widgets[existing.column_id].count())
                ]
                if existing.id not in already:
                    item_widget = QListWidgetItem(f"#{task.id} {task.title}")
                    item_widget.setData(Qt.ItemDataRole.UserRole, existing.id)
                    item_widget.setFlags(item_widget.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
                    self.column_widgets[existing.column_id].addItem(item_widget)

    def _persist_column_order(self, target_column_id: int, board_item_id: int, target_position: int) -> None:
        task_service.move_board_item_by_id(self.db_path, board_item_id, target_column_id, target_position)

    def refresh_boards(self) -> None:
        boards = task_service.list_boards(self.db_path)
        if not boards:
            task_service.create_board(self.db_path, "Основная доска", ["К выполнению", "В работе", "Готово"])
            boards = task_service.list_boards(self.db_path)

        current_board_id = self._active_board_id()
        self.board_selector.blockSignals(True)
        self.board_selector.clear()
        selected_index = 0
        for index, board in enumerate(boards):
            self.board_selector.addItem(board.name, board.id)
            if current_board_id == board.id:
                selected_index = index
        self.board_selector.setCurrentIndex(selected_index)
        self.board_selector.blockSignals(False)
        self._render_board()
