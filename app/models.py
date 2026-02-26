from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


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
