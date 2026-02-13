from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from .models import Subtask, Task

DB_NAME = "data.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def get_conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


def init_db(db_path: Path) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                is_done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reminder_datetime TEXT,
                note TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                is_done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_links (
                source_task_id INTEGER NOT NULL,
                target_task_id INTEGER NOT NULL,
                PRIMARY KEY (source_task_id, target_task_id),
                FOREIGN KEY(source_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(target_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                CHECK (source_task_id != target_task_id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_layout (
                task_id INTEGER PRIMARY KEY,
                x REAL NOT NULL,
                y REAL NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            """
        )


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        is_done=bool(row["is_done"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        reminder_datetime=datetime.fromisoformat(row["reminder_datetime"]) if row["reminder_datetime"] else None,
        note=row["note"],
    )


def _row_to_subtask(row: sqlite3.Row) -> Subtask:
    return Subtask(
        id=row["id"],
        task_id=row["task_id"],
        title=row["title"],
        is_done=bool(row["is_done"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _now() -> str:
    return datetime.utcnow().isoformat()


def create_task(db_path: Path, title: str, reminder_datetime: Optional[datetime] = None, note: Optional[str] = None) -> Task:
    created_at = _now()
    reminder_value = reminder_datetime.isoformat() if reminder_datetime else None
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (title, is_done, created_at, updated_at, reminder_datetime, note)
            VALUES (?, 0, ?, ?, ?, ?)
            """,
            (title, created_at, created_at, reminder_value, note),
        )
        task_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row)


def list_tasks(
    db_path: Path,
    search: Optional[str] = None,
    has_reminder: Optional[bool] = None,
    is_done: Optional[bool] = None,
) -> List[Task]:
    query = "SELECT * FROM tasks"
    clauses: List[str] = []
    values: List[object] = []
    if search:
        clauses.append("(title LIKE ? OR COALESCE(note, '') LIKE ?)")
        pattern = f"%{search}%"
        values.extend([pattern, pattern])
    if has_reminder is not None:
        if has_reminder:
            clauses.append("reminder_datetime IS NOT NULL")
        else:
            clauses.append("reminder_datetime IS NULL")
    if is_done is not None:
        clauses.append("is_done = ?")
        values.append(1 if is_done else 0)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"
    with get_conn(db_path) as conn:
        rows = conn.execute(query, tuple(values)).fetchall()
    return [_row_to_task(row) for row in rows]


def get_task(db_path: Path, task_id: int) -> Optional[Task]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row) if row else None


def update_task(
    db_path: Path,
    task_id: int,
    *,
    title: Optional[str] = None,
    is_done: Optional[bool] = None,
    reminder_datetime: Optional[Optional[datetime]] = None,
    note: Optional[Optional[str]] = None,
) -> Optional[Task]:
    task = get_task(db_path, task_id)
    if not task:
        return None

    updates: List[str] = []
    values: List[object] = []
    if title is not None:
        updates.append("title = ?")
        values.append(title)
    if is_done is not None:
        updates.append("is_done = ?")
        values.append(1 if is_done else 0)
        if is_done:
            updates.append("reminder_datetime = NULL")
    if reminder_datetime is not None:
        updates.append("reminder_datetime = ?")
        values.append(reminder_datetime.isoformat() if reminder_datetime else None)
    if note is not None:
        updates.append("note = ?")
        values.append(note)

    if not updates:
        return task

    updates.append("updated_at = ?")
    values.append(_now())
    values.append(task_id)

    set_clause = ", ".join(updates)
    with get_conn(db_path) as conn:
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", tuple(values))
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row)


def delete_task(db_path: Path, task_id: int) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return cursor.rowcount > 0


def create_subtask(db_path: Path, task_id: int, title: str) -> Optional[Subtask]:
    if not get_task(db_path, task_id):
        return None
    created_at = _now()
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO subtasks (task_id, title, is_done, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?)
            """,
            (task_id, title, created_at, created_at),
        )
        subtask_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
    return _row_to_subtask(row)


def list_subtasks(db_path: Path, task_id: int) -> List[Subtask]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY created_at ASC", (task_id,)
        ).fetchall()
    return [_row_to_subtask(row) for row in rows]


def update_subtask(
    db_path: Path,
    subtask_id: int,
    *,
    title: Optional[str] = None,
    is_done: Optional[bool] = None,
) -> Optional[Subtask]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
        if not row:
            return None
        updates: List[str] = []
        values: List[object] = []
        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if is_done is not None:
            updates.append("is_done = ?")
            values.append(1 if is_done else 0)
        if not updates:
            return _row_to_subtask(row)
        updates.append("updated_at = ?")
        values.append(_now())
        values.append(subtask_id)
        set_clause = ", ".join(updates)
        conn.execute(f"UPDATE subtasks SET {set_clause} WHERE id = ?", tuple(values))
        new_row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
    return _row_to_subtask(new_row)


def delete_subtask(db_path: Path, subtask_id: int) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute("DELETE FROM subtasks WHERE id = ?", (subtask_id,))
    return cursor.rowcount > 0


def subtask_progress(db_path: Path, task_id: int) -> Tuple[int, int]:
    with get_conn(db_path) as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM subtasks WHERE task_id = ?", (task_id,)
        ).fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM subtasks WHERE task_id = ? AND is_done = 1", (task_id,)
        ).fetchone()[0]
    return completed, total


def due_reminders(db_path: Path, now: Optional[datetime] = None) -> Iterable[Task]:
    moment = now or datetime.utcnow()
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE reminder_datetime IS NOT NULL
              AND is_done = 0
              AND reminder_datetime <= ?
            ORDER BY reminder_datetime ASC
            """,
            (moment.isoformat(),),
        ).fetchall()
    return [_row_to_task(row) for row in rows]


def list_task_links(db_path: Path) -> List[Tuple[int, int]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT source_task_id, target_task_id FROM task_links ORDER BY source_task_id, target_task_id"
        ).fetchall()
    return [(row["source_task_id"], row["target_task_id"]) for row in rows]


def create_task_link(db_path: Path, source_task_id: int, target_task_id: int) -> bool:
    if source_task_id == target_task_id:
        return False
    if not get_task(db_path, source_task_id) or not get_task(db_path, target_task_id):
        return False
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO task_links (source_task_id, target_task_id)
            VALUES (?, ?)
            """,
            (source_task_id, target_task_id),
        )
    return cursor.rowcount > 0


def delete_task_link(db_path: Path, source_task_id: int, target_task_id: int) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM task_links WHERE source_task_id = ? AND target_task_id = ?",
            (source_task_id, target_task_id),
        )
    return cursor.rowcount > 0


def get_task_layouts(db_path: Path) -> Dict[int, Tuple[float, float]]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT task_id, x, y FROM task_layout").fetchall()
    return {row["task_id"]: (row["x"], row["y"]) for row in rows}


def set_task_layout(db_path: Path, task_id: int, x: float, y: float) -> bool:
    if not get_task(db_path, task_id):
        return False
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO task_layout (task_id, x, y)
            VALUES (?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET x = excluded.x, y = excluded.y
            """,
            (task_id, x, y),
        )
    return True
