from __future__ import annotations

import mimetypes
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from app import storage

from app.models import ALLOWED_PRIORITIES, Attachment, Board, BoardColumn, BoardItem, Subtask, Task


UNSET_DUE_DATETIME = object()
UNSET_BOARD_FIELD = object()
ConvertToSubtaskError = storage.ConvertToSubtaskError
BoardValidationError = storage.BoardValidationError
DeadlineValidationError = storage.DeadlineValidationError
AttachmentValidationError = storage.AttachmentValidationError
AttachmentStorageError = storage.AttachmentStorageError

def _validate_priority(priority: str) -> str:
    normalized = priority.strip().lower()
    if normalized not in ALLOWED_PRIORITIES:
        allowed = "|".join(ALLOWED_PRIORITIES)
        raise ValueError(f"Недопустимый приоритет '{priority}'. Допустимо: {allowed}")
    return normalized


def init_db(db_path: Path) -> None:
    storage.init_db(db_path)


def repair_sanitized_notes(db_path: Path) -> Dict[str, int]:
    return storage.repair_sanitized_notes(db_path)


def create_task(
    db_path: Path,
    title: str,
    reminder_datetime: Optional[datetime] = None,
    due_datetime: Optional[datetime] = None,
    note: Optional[str] = None,
    priority: str = "medium",
) -> Task:
    validated_priority = _validate_priority(priority)
    return storage.create_task(
        db_path,
        title=title,
        reminder_datetime=reminder_datetime,
        due_datetime=due_datetime,
        note=note,
        priority=validated_priority,
    )


def list_tasks(
    db_path: Path,
    search: Optional[str] = None,
    has_reminder: Optional[bool] = None,
    is_done: Optional[bool] = None,
    due_on_date: Optional[date] = None,
    overdue_only: bool = False,
    now: Optional[datetime] = None,
) -> List[Task]:
    return storage.list_tasks(
        db_path,
        search=search,
        has_reminder=has_reminder,
        is_done=is_done,
        due_on_date=due_on_date,
        overdue_only=overdue_only,
        now=now,
    )


def get_task(db_path: Path, task_id: int) -> Optional[Task]:
    return storage.get_task(db_path, task_id)


def update_task(
    db_path: Path,
    task_id: int,
    *,
    title: Optional[str] = None,
    is_done: Optional[bool] = None,
    reminder_datetime: Optional[Optional[datetime]] = None,
    due_datetime: Optional[Optional[datetime]] | object = UNSET_DUE_DATETIME,
    note: Optional[Optional[str]] = None,
    priority: Optional[str] = None,
) -> Optional[Task]:
    kwargs = {
        "title": title,
        "is_done": is_done,
        "reminder_datetime": reminder_datetime,
        "note": note,
    }
    if due_datetime is not UNSET_DUE_DATETIME:
        kwargs["due_datetime"] = due_datetime
    if priority is not None:
        kwargs["priority"] = _validate_priority(priority)
    return storage.update_task(db_path, task_id, **kwargs)


def delete_task(db_path: Path, task_id: int) -> bool:
    return storage.delete_task(db_path, task_id)


def due_reminders(db_path: Path, now: Optional[datetime] = None) -> Iterable[Task]:
    return storage.due_reminders(db_path, now=now)


def create_subtask(
    db_path: Path,
    task_id: int,
    title: str,
    priority: str = "medium",
    due_datetime: Optional[datetime] = None,
) -> Optional[Subtask]:
    validated_priority = _validate_priority(priority)
    return storage.create_subtask(
        db_path,
        task_id,
        title,
        validated_priority,
        due_datetime=due_datetime,
    )


def list_subtasks(db_path: Path, task_id: int) -> List[Subtask]:
    return storage.list_subtasks(db_path, task_id)

def get_subtask(db_path: Path, subtask_id: int) -> Optional[Subtask]:
    return storage.get_subtask(db_path, subtask_id)



def update_subtask(
    db_path: Path,
    subtask_id: int,
    *,
    title: Optional[str] = None,
    is_done: Optional[bool] = None,
    reminder_datetime: Optional[Optional[datetime]] = None,
    due_datetime: Optional[Optional[datetime]] | object = UNSET_DUE_DATETIME,
    note: Optional[Optional[str]] = None,
    priority: Optional[str] = None,
) -> Optional[Subtask]:
    kwargs = {
        "title": title,
        "is_done": is_done,
        "reminder_datetime": reminder_datetime,
        "note": note,
    }
    if due_datetime is not UNSET_DUE_DATETIME:
        kwargs["due_datetime"] = due_datetime
    if priority is not None:
        kwargs["priority"] = _validate_priority(priority)
    return storage.update_subtask(db_path, subtask_id, **kwargs)


def delete_subtask(db_path: Path, subtask_id: int) -> bool:
    return storage.delete_subtask(db_path, subtask_id)


def move_subtask(db_path: Path, subtask_id: int, new_task_id: int) -> Optional[Subtask]:
    return storage.move_subtask(db_path, subtask_id, new_task_id)


def subtask_progress(db_path: Path, task_id: int) -> Tuple[int, int]:
    return storage.subtask_progress(db_path, task_id)

def reorder_subtask(db_path: Path, subtask_id: int, new_position: int) -> List[Subtask]:
    return storage.reorder_subtask(db_path, subtask_id, new_position)


def bulk_reorder_subtasks(db_path: Path, task_id: int, ordered_subtask_ids: List[int]) -> List[Subtask]:
    return storage.bulk_reorder_subtasks(db_path, task_id, ordered_subtask_ids)


def convert_task_to_subtask(db_path: Path, child_task_id: int, parent_task_id: int) -> Optional[Subtask]:
    if child_task_id == parent_task_id:
        raise ConvertToSubtaskError("Нельзя сделать задачу подзадачей самой себя")

    child = storage.get_task(db_path, child_task_id)
    if not child:
        raise ConvertToSubtaskError(f"Задача #{child_task_id} не найдена")

    parent = storage.get_task(db_path, parent_task_id)
    if not parent:
        raise ConvertToSubtaskError(f"Родительская задача #{parent_task_id} не найдена")

    if storage.list_subtasks(db_path, child_task_id):
        raise ConvertToSubtaskError(
            "Нельзя конвертировать задачу с подзадачами: сначала перенесите или удалите её подзадачи"
        )

    links = storage.list_task_links(db_path)
    if any(child_task_id in link for link in links):
        raise ConvertToSubtaskError(
            "Нельзя конвертировать задачу, участвующую в связях графа: сначала удалите связи"
        )

    converted = storage.create_subtask(db_path, parent_task_id, child.title)
    if not converted:
        return None

    if child.is_done:
        converted = storage.update_subtask(db_path, converted.id, is_done=True)
    if not storage.delete_task(db_path, child_task_id):
        storage.delete_subtask(db_path, converted.id)
        return None
    return converted


def create_task_link(
    db_path: Path,
    source_task_id: int,
    target_task_id: int,
    *,
    prevent_cycles: bool = True,
) -> bool:
    return storage.create_task_link(
        db_path,
        source_task_id,
        target_task_id,
        prevent_cycles=prevent_cycles,
    )


def list_task_links(db_path: Path, task_id: Optional[int] = None) -> List[Tuple[int, int]]:
    links = storage.list_task_links(db_path)
    if task_id is None:
        return links
    return [pair for pair in links if task_id in pair]


def list_task_links_with_type(db_path: Path) -> List[Tuple[int, int, str]]:
    return storage.list_task_links_with_type(db_path)


def delete_task_link(db_path: Path, source_task_id: int, target_task_id: int) -> bool:
    return storage.delete_task_link(db_path, source_task_id, target_task_id)


def list_subtask_links(db_path: Path) -> List[Tuple[int, int, str]]:
    return storage.list_subtask_links(db_path)


def create_subtask_link(
    db_path: Path,
    source_subtask_id: int,
    target_subtask_id: int,
    *,
    link_type: str = "depends_on",
    prevent_cycles: bool = True,
) -> bool:
    return storage.create_subtask_link(
        db_path,
        source_subtask_id,
        target_subtask_id,
        link_type=link_type,
        prevent_cycles=prevent_cycles,
    )


def delete_subtask_link(
    db_path: Path,
    source_subtask_id: int,
    target_subtask_id: int,
    *,
    link_type: Optional[str] = None,
) -> bool:
    return storage.delete_subtask_link(
        db_path,
        source_subtask_id,
        target_subtask_id,
        link_type=link_type,
    )


def get_task_layouts(db_path: Path) -> Dict[int, Tuple[float, float]]:
    return storage.get_task_layouts(db_path)


def set_task_layout(db_path: Path, task_id: int, x: float, y: float) -> bool:
    return storage.set_task_layout(db_path, task_id, x, y)



def create_board(db_path: Path, name: str, column_names: Optional[List[str]] = None) -> Board:
    return storage.create_board(db_path, name, column_names)


def list_boards(db_path: Path) -> List[Board]:
    return storage.list_boards(db_path)


def get_board(db_path: Path, board_id: int) -> Optional[Board]:
    return storage.get_board(db_path, board_id)


def update_board(db_path: Path, board_id: int, name: str) -> Optional[Board]:
    return storage.update_board(db_path, board_id, name)


def delete_board(db_path: Path, board_id: int) -> bool:
    return storage.delete_board(db_path, board_id)


def list_board_columns(db_path: Path, board_id: int) -> List[BoardColumn]:
    return storage.list_board_columns(db_path, board_id)


def create_board_column(db_path: Path, board_id: int, name: str, *, wip_limit: Optional[int] = None) -> BoardColumn:
    return storage.create_board_column(db_path, board_id, name, wip_limit=wip_limit)


def update_board_column(
    db_path: Path,
    column_id: int,
    *,
    name: str | object = UNSET_BOARD_FIELD,
    wip_limit: Optional[int] | object = UNSET_BOARD_FIELD,
) -> Optional[BoardColumn]:
    kwargs = {}
    if name is not UNSET_BOARD_FIELD:
        kwargs["name"] = name
    if wip_limit is not UNSET_BOARD_FIELD:
        kwargs["wip_limit"] = wip_limit
    return storage.update_board_column(db_path, column_id, **kwargs)


def rename_board_column(db_path: Path, column_id: int, new_name: str) -> Optional[BoardColumn]:
    return storage.rename_board_column(db_path, column_id, new_name)


def delete_board_column(db_path: Path, column_id: int, target_column_id: int) -> bool:
    return storage.delete_board_column(db_path, column_id, target_column_id)


def reorder_board_columns(db_path: Path, board_id: int, ordered_column_ids: List[int]) -> List[BoardColumn]:
    return storage.reorder_board_columns(db_path, board_id, ordered_column_ids)


def list_board_items(db_path: Path, board_id: int) -> List[BoardItem]:
    return storage.list_board_items(db_path, board_id)


def move_board_item(db_path: Path, board_id: int, task_id: int, column_id: int, position: int) -> BoardItem:
    return storage.move_board_item(db_path, board_id, task_id, column_id, position)


def move_board_item_by_id(db_path: Path, board_item_id: int, column_id: int, position: int) -> BoardItem:
    return storage.move_board_item_by_id(db_path, board_item_id, column_id, position)


def ensure_board_item(db_path: Path, board_id: int, task_id: int) -> Optional[BoardItem]:
    return storage.ensure_board_item(db_path, board_id, task_id)


def create_attachment(db_path: Path, *, entity_type: str, entity_id: int, source_path: Path) -> Attachment:
    guessed_mime = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
    return storage.create_attachment(
        db_path,
        entity_type=entity_type,
        entity_id=entity_id,
        source_path=source_path,
        original_name=source_path.name,
        mime=guessed_mime,
    )


def list_attachments(db_path: Path, *, entity_type: str, entity_id: int) -> List[Attachment]:
    return storage.list_attachments(db_path, entity_type=entity_type, entity_id=entity_id)


def get_attachment(db_path: Path, attachment_id: int) -> Optional[Attachment]:
    return storage.get_attachment(db_path, attachment_id)


def delete_attachment(db_path: Path, attachment_id: int) -> bool:
    return storage.delete_attachment(db_path, attachment_id)
