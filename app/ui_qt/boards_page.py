from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
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
        self.columns_editor = QListWidget(self)

        self._build_ui()
        self.refresh_boards()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Доска", self))
        top.addWidget(self.board_selector, 1)
        create_board_btn = QPushButton("+ Доска", self)
        delete_board_btn = QPushButton("Удалить доску", self)
        top.addWidget(create_board_btn)
        top.addWidget(delete_board_btn)
        root.addLayout(top)

        editor = QHBoxLayout()
        editor.addWidget(QLabel("Колонки", self))
        self.columns_editor.setMaximumHeight(120)
        editor.addWidget(self.columns_editor, 1)
        add_col_btn = QPushButton("+", self)
        rename_col_btn = QPushButton("Переим.", self)
        delete_col_btn = QPushButton("Удалить", self)
        up_col_btn = QPushButton("↑", self)
        down_col_btn = QPushButton("↓", self)
        for btn in [add_col_btn, rename_col_btn, delete_col_btn, up_col_btn, down_col_btn]:
            editor.addWidget(btn)
        root.addLayout(editor)

        root.addLayout(self.columns_layout)

        self.board_selector.currentIndexChanged.connect(self._render_board)
        create_board_btn.clicked.connect(self._create_board)
        delete_board_btn.clicked.connect(self._delete_board)
        add_col_btn.clicked.connect(self._create_column)
        rename_col_btn.clicked.connect(self._rename_column)
        delete_col_btn.clicked.connect(self._delete_column)
        up_col_btn.clicked.connect(lambda: self._move_column(-1))
        down_col_btn.clicked.connect(lambda: self._move_column(1))

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

    def _current_editor_column_id(self) -> int | None:
        item = self.columns_editor.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
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
        self.columns_editor.clear()
        if board_id is None:
            return

        columns = task_service.list_board_columns(self.db_path, board_id)
        items = task_service.list_board_items(self.db_path, board_id)
        tasks_by_id = {task.id: task for task in task_service.list_tasks(self.db_path)}

        for column in columns:
            editor_item = QListWidgetItem(f"{column.position + 1}. {column.name}")
            editor_item.setData(Qt.ItemDataRole.UserRole, column.id)
            self.columns_editor.addItem(editor_item)

            list_widget = BoardColumnList(column.id, self._persist_column_order, self)
            self.column_widgets[column.id] = list_widget
            self.columns_layout.addLayout(self._column(column.name, list_widget))

        for item in items:
            task = tasks_by_id.get(item.task_id)
            if not task or item.column_id not in self.column_widgets:
                continue
            overdue = task_service.is_overdue(
                due_datetime=task.due_datetime,
                deadline_enabled=task.due_datetime is not None,
                is_done=task.is_done,
                now=datetime.now(),
            )
            title = f"#{task.id} {task.title}"
            if overdue:
                title = f"{title} · ⚠ Просрочено"
            list_item = QListWidgetItem(title)
            list_item.setData(Qt.ItemDataRole.UserRole, item.id)
            list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
            self.column_widgets[item.column_id].addItem(list_item)

        for task in tasks_by_id.values():
            existing = task_service.ensure_board_item(self.db_path, board_id, task.id)
            if existing and existing.column_id in self.column_widgets:
                already = [
                    self.column_widgets[existing.column_id].item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.column_widgets[existing.column_id].count())
                ]
                if existing.id not in already:
                    overdue = task_service.is_overdue(
                        due_datetime=task.due_datetime,
                        deadline_enabled=task.due_datetime is not None,
                        is_done=task.is_done,
                        now=datetime.now(),
                    )
                    title = f"#{task.id} {task.title}"
                    if overdue:
                        title = f"{title} · ⚠ Просрочено"
                    item_widget = QListWidgetItem(title)
                    item_widget.setData(Qt.ItemDataRole.UserRole, existing.id)
                    item_widget.setFlags(item_widget.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
                    self.column_widgets[existing.column_id].addItem(item_widget)

    def _persist_column_order(self, target_column_id: int, board_item_id: int, target_position: int) -> None:
        task_service.move_board_item_by_id(self.db_path, board_item_id, target_column_id, target_position)

    def _create_board(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая доска", "Название доски:")
        if ok and name.strip():
            task_service.create_board(self.db_path, name.strip(), ["К выполнению", "В работе", "Готово"])
            self.refresh_boards()

    def _delete_board(self) -> None:
        board_id = self._active_board_id()
        if board_id is None:
            return
        confirm = QMessageBox.question(self, "Удаление доски", "Удалить текущую доску?")
        if confirm == QMessageBox.StandardButton.Yes:
            task_service.delete_board(self.db_path, board_id)
            self.refresh_boards()

    def _create_column(self) -> None:
        board_id = self._active_board_id()
        if board_id is None:
            return
        name, ok = QInputDialog.getText(self, "Новая колонка", "Название колонки:")
        if ok and name.strip():
            task_service.create_board_column(self.db_path, board_id, name.strip())
            self._render_board()

    def _rename_column(self) -> None:
        column_id = self._current_editor_column_id()
        if column_id is None:
            return
        name, ok = QInputDialog.getText(self, "Переименовать колонку", "Новое название:")
        if ok and name.strip():
            task_service.update_board_column(self.db_path, column_id, name=name.strip())
            self._render_board()

    def _delete_column(self) -> None:
        board_id = self._active_board_id()
        column_id = self._current_editor_column_id()
        if board_id is None or column_id is None:
            return

        columns = task_service.list_board_columns(self.db_path, board_id)
        targets = [col for col in columns if col.id != column_id]
        if not targets:
            QMessageBox.warning(self, "Удаление колонки", "На доске должна остаться хотя бы одна колонка.")
            return

        names = [col.name for col in targets]
        target_name, ok = QInputDialog.getItem(
            self,
            "Удаление колонки",
            "Перенести карточки в колонку:",
            names,
            0,
            False,
        )
        if not ok:
            return

        target = next((col for col in targets if col.name == target_name), None)
        if target is None:
            return
        task_service.delete_board_column(self.db_path, column_id, target.id)
        self._render_board()

    def _move_column(self, delta: int) -> None:
        board_id = self._active_board_id()
        column_id = self._current_editor_column_id()
        if board_id is None or column_id is None:
            return

        columns = task_service.list_board_columns(self.db_path, board_id)
        ids = [col.id for col in columns]
        current_index = ids.index(column_id)
        new_index = current_index + delta
        if new_index < 0 or new_index >= len(ids):
            return
        ids[current_index], ids[new_index] = ids[new_index], ids[current_index]
        task_service.reorder_board_columns(self.db_path, board_id, ids)
        self._render_board()
        self._select_editor_column(column_id)

    def _select_editor_column(self, column_id: int) -> None:
        for index in range(self.columns_editor.count()):
            if self.columns_editor.item(index).data(Qt.ItemDataRole.UserRole) == column_id:
                self.columns_editor.setCurrentRow(index)
                break

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
