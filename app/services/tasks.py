from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from app import storage
from app.models import Subtask, Task


UNSET_DUE_DATETIME = object()
ConvertToSubtaskError = storage.ConvertToSubtaskError


def init_db(db_path: Path) -> None:
    storage.init_db(db_path)


def create_task(
    db_path: Path,
    title: str,
    reminder_datetime: Optional[datetime] = None,
    due_datetime: Optional[datetime] = None,
    note: Optional[str] = None,
) -> Task:
    return storage.create_task(
        db_path,
        title=title,
        reminder_datetime=reminder_datetime,
        due_datetime=due_datetime,
        note=note,
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
) -> Optional[Task]:
    kwargs = {
        "title": title,
        "is_done": is_done,
        "reminder_datetime": reminder_datetime,
        "note": note,
    }
    if due_datetime is not UNSET_DUE_DATETIME:
        kwargs["due_datetime"] = due_datetime
    return storage.update_task(db_path, task_id, **kwargs)


def delete_task(db_path: Path, task_id: int) -> bool:
    return storage.delete_task(db_path, task_id)


def due_reminders(db_path: Path, now: Optional[datetime] = None) -> Iterable[Task]:
    return storage.due_reminders(db_path, now=now)


def create_subtask(db_path: Path, task_id: int, title: str) -> Optional[Subtask]:
    return storage.create_subtask(db_path, task_id, title)


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
) -> Optional[Subtask]:
    kwargs = {
        "title": title,
        "is_done": is_done,
        "reminder_datetime": reminder_datetime,
        "note": note,
    }
    if due_datetime is not UNSET_DUE_DATETIME:
        kwargs["due_datetime"] = due_datetime
    return storage.update_subtask(db_path, subtask_id, **kwargs)


def delete_subtask(db_path: Path, subtask_id: int) -> bool:
    return storage.delete_subtask(db_path, subtask_id)


def subtask_progress(db_path: Path, task_id: int) -> Tuple[int, int]:
    return storage.subtask_progress(db_path, task_id)


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


def create_task_link(db_path: Path, source_task_id: int, target_task_id: int) -> bool:
    return storage.create_task_link(db_path, source_task_id, target_task_id)


def list_task_links(db_path: Path, task_id: Optional[int] = None) -> List[Tuple[int, int]]:
    links = storage.list_task_links(db_path)
    if task_id is None:
        return links
    return [pair for pair in links if task_id in pair]


def delete_task_link(db_path: Path, source_task_id: int, target_task_id: int) -> bool:
    return storage.delete_task_link(db_path, source_task_id, target_task_id)


def get_task_layouts(db_path: Path) -> Dict[int, Tuple[float, float]]:
    return storage.get_task_layouts(db_path)


def set_task_layout(db_path: Path, task_id: int, x: float, y: float) -> bool:
    return storage.set_task_layout(db_path, task_id, x, y)
