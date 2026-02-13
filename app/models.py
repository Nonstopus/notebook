from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    title: str
    is_done: bool
    created_at: datetime
    updated_at: datetime


@dataclass
class TaskLink:
    id: int
    from_task_id: int
    to_task_id: int
    link_type: str
    created_at: datetime
