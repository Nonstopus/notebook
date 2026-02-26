from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


PRIORITY_LOW = "low"
PRIORITY_MEDIUM = "medium"
PRIORITY_HIGH = "high"
PRIORITY_CRITICAL = "critical"
ALLOWED_PRIORITIES = (
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_HIGH,
    PRIORITY_CRITICAL,
)


@dataclass
class Task:
    id: int
    title: str
    is_done: bool
    created_at: datetime
    updated_at: datetime
    reminder_datetime: Optional[datetime]
    due_datetime: Optional[datetime]
    note: Optional[str]
    priority: str


@dataclass
class Subtask:
    id: int
    task_id: int
    position: int
    title: str
    is_done: bool
    created_at: datetime
    updated_at: datetime
    reminder_datetime: Optional[datetime]
    due_datetime: Optional[datetime]
    note: Optional[str]
    priority: str


class ItemKind(str, Enum):
    TASK = "task"
    SUBTASK = "subtask"


@dataclass(frozen=True)
class TreeItemRef:
    kind: ItemKind
    id: int
    level: int
    parent_task_id: Optional[int] = None


@dataclass
class TaskLink:
    id: int
    from_task_id: int
    to_task_id: int
    link_type: str
    created_at: datetime


@dataclass
class Board:
    id: int
    name: str
    created_at: datetime
    updated_at: datetime


@dataclass
class BoardColumn:
    id: int
    board_id: int
    name: str
    position: int
    wip_limit: Optional[int]


@dataclass
class BoardItem:
    id: int
    board_id: int
    task_id: int
    column_id: int
    position: int


@dataclass
class Attachment:
    id: int
    entity_type: str
    entity_id: int
    file_path: str
    original_name: str
    mime: str
    size: int
    created_at: datetime
