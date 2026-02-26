from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from .models import Board, BoardColumn, BoardItem, Subtask, Task

DB_NAME = "data.db"
_UNSET = object()


class ConvertToSubtaskError(ValueError):
    """Domain validation error for converting a task to subtask."""


class BoardValidationError(ValueError):
    """Domain validation error for board operations."""


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
                due_datetime TEXT,
                note TEXT
            );
            """
        )
        task_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        if "due_datetime" not in task_columns:
            conn.execute("ALTER TABLE tasks ADD COLUMN due_datetime TEXT")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL,
                is_done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reminder_datetime TEXT,
                due_datetime TEXT,
                note TEXT,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            """
        )
        subtask_columns = {row["name"] for row in conn.execute("PRAGMA table_info(subtasks)").fetchall()}
        if "reminder_datetime" not in subtask_columns:
            conn.execute("ALTER TABLE subtasks ADD COLUMN reminder_datetime TEXT")
        if "due_datetime" not in subtask_columns:
            conn.execute("ALTER TABLE subtasks ADD COLUMN due_datetime TEXT")
        if "note" not in subtask_columns:
            conn.execute("ALTER TABLE subtasks ADD COLUMN note TEXT")
        if "position" not in subtask_columns:
            conn.execute("ALTER TABLE subtasks ADD COLUMN position INTEGER NOT NULL DEFAULT 0")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_links (
                from_task_id INTEGER NOT NULL,
                to_task_id INTEGER NOT NULL,
                type TEXT NOT NULL DEFAULT 'depends_on',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (from_task_id, to_task_id),
                FOREIGN KEY(from_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(to_task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                CHECK (from_task_id != to_task_id)
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subtask_links (
                from_subtask_id INTEGER NOT NULL,
                to_subtask_id INTEGER NOT NULL,
                link_type TEXT NOT NULL DEFAULT 'depends_on',
                created_at TEXT NOT NULL,
                PRIMARY KEY (from_subtask_id, to_subtask_id, link_type),
                FOREIGN KEY(from_subtask_id) REFERENCES subtasks(id) ON DELETE CASCADE,
                FOREIGN KEY(to_subtask_id) REFERENCES subtasks(id) ON DELETE CASCADE,
                CHECK (from_subtask_id != to_subtask_id)
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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS board_columns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                position INTEGER NOT NULL,
                wip_limit INTEGER,
                FOREIGN KEY(board_id) REFERENCES boards(id) ON DELETE CASCADE,
                UNIQUE(board_id, name),
                UNIQUE(board_id, position),
                CHECK(position >= 0),
                CHECK(wip_limit IS NULL OR wip_limit > 0)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS board_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                column_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY(board_id) REFERENCES boards(id) ON DELETE CASCADE,
                FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY(column_id) REFERENCES board_columns(id) ON DELETE CASCADE,
                UNIQUE(board_id, task_id),
                UNIQUE(column_id, position),
                CHECK(position >= 0)
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
        due_datetime=datetime.fromisoformat(row["due_datetime"]) if row["due_datetime"] else None,
        note=row["note"],
    )


def _row_to_subtask(row: sqlite3.Row) -> Subtask:
    return Subtask(
        id=row["id"],
        task_id=row["task_id"],
        position=row["position"],
        title=row["title"],
        is_done=bool(row["is_done"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        reminder_datetime=datetime.fromisoformat(row["reminder_datetime"]) if row["reminder_datetime"] else None,
        due_datetime=datetime.fromisoformat(row["due_datetime"]) if row["due_datetime"] else None,
        note=row["note"],
    )


def _now() -> str:
    return datetime.utcnow().isoformat()


def _row_to_board(row: sqlite3.Row) -> Board:
    return Board(
        id=row["id"],
        name=row["name"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _row_to_board_column(row: sqlite3.Row) -> BoardColumn:
    return BoardColumn(
        id=row["id"],
        board_id=row["board_id"],
        name=row["name"],
        position=row["position"],
        wip_limit=row["wip_limit"],
    )


def _row_to_board_item(row: sqlite3.Row) -> BoardItem:
    return BoardItem(
        id=row["id"],
        board_id=row["board_id"],
        task_id=row["task_id"],
        column_id=row["column_id"],
        position=row["position"],
    )


def _validate_non_empty(name: str, field_name: str) -> str:
    value = name.strip()
    if not value:
        raise BoardValidationError(f"{field_name} не может быть пустым")
    return value


def create_task(
    db_path: Path,
    title: str,
    reminder_datetime: Optional[datetime] = None,
    due_datetime: Optional[datetime] = None,
    note: Optional[str] = None,
) -> Task:
    created_at = _now()
    reminder_value = reminder_datetime.isoformat() if reminder_datetime else None
    due_value = due_datetime.isoformat() if due_datetime else None
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (title, is_done, created_at, updated_at, reminder_datetime, due_datetime, note)
            VALUES (?, 0, ?, ?, ?, ?, ?)
            """,
            (title, created_at, created_at, reminder_value, due_value, note),
        )
        task_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _row_to_task(row)


def list_tasks(
    db_path: Path,
    search: Optional[str] = None,
    has_reminder: Optional[bool] = None,
    is_done: Optional[bool] = None,
    due_on_date: Optional[date] = None,
    overdue_only: bool = False,
    now: Optional[datetime] = None,
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
    if due_on_date is not None:
        clauses.append("due_datetime >= ? AND due_datetime < ?")
        start_of_day = datetime.combine(due_on_date, datetime.min.time())
        start_of_next_day = start_of_day + timedelta(days=1)
        values.extend([start_of_day.isoformat(), start_of_next_day.isoformat()])
    if overdue_only:
        current_moment = (now or datetime.utcnow()).isoformat()
        clauses.append("due_datetime IS NOT NULL")
        clauses.append("is_done = 0")
        clauses.append("due_datetime <= ?")
        values.append(current_moment)
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
    due_datetime: Optional[Optional[datetime]] | object = _UNSET,
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
    if due_datetime is not _UNSET:
        updates.append("due_datetime = ?")
        values.append(due_datetime.isoformat() if due_datetime else None)
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


def convert_task_to_subtask(db_path: Path, child_task_id: int, parent_task_id: int) -> Optional[Subtask]:
    if child_task_id == parent_task_id:
        raise ConvertToSubtaskError("Нельзя сделать задачу подзадачей самой себя")

    with get_conn(db_path) as conn:
        child_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (child_task_id,)).fetchone()
        parent_exists = conn.execute("SELECT id FROM tasks WHERE id = ?", (parent_task_id,)).fetchone()
        if not child_row:
            raise ConvertToSubtaskError(f"Задача #{child_task_id} не найдена")
        if not parent_exists:
            raise ConvertToSubtaskError(f"Родительская задача #{parent_task_id} не найдена")

        child_subtasks_count = conn.execute(
            "SELECT COUNT(*) FROM subtasks WHERE task_id = ?", (child_task_id,)
        ).fetchone()[0]
        if child_subtasks_count > 0:
            raise ConvertToSubtaskError(
                "Нельзя конвертировать задачу с подзадачами: сначала перенесите или удалите её подзадачи"
            )

        linked_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM task_links
            WHERE from_task_id = ? OR to_task_id = ?
            """,
            (child_task_id, child_task_id),
        ).fetchone()[0]
        if linked_count > 0:
            raise ConvertToSubtaskError(
                "Нельзя конвертировать задачу, участвующую в связях графа: сначала удалите связи"
            )

        now = _now()
        next_position = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM subtasks WHERE task_id = ?",
            (parent_task_id,),
        ).fetchone()[0]
        cursor = conn.execute(
            """
            INSERT INTO subtasks (
                task_id, position, title, is_done, created_at, updated_at, reminder_datetime, due_datetime, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parent_task_id,
                next_position,
                child_row["title"],
                child_row["is_done"],
                now,
                now,
                child_row["reminder_datetime"],
                child_row["due_datetime"],
                child_row["note"],
            ),
        )
        subtask_row = conn.execute(
            "SELECT * FROM subtasks WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()

        deleted_cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (child_task_id,))
        if deleted_cursor.rowcount == 0:
            return None

    return _row_to_subtask(subtask_row)


def create_subtask(db_path: Path, task_id: int, title: str) -> Optional[Subtask]:
    if not get_task(db_path, task_id):
        return None
    created_at = _now()
    with get_conn(db_path) as conn:
        next_position = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM subtasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()[0]
        cursor = conn.execute(
            """
            INSERT INTO subtasks (
                task_id, position, title, is_done, created_at, updated_at, reminder_datetime, due_datetime, note
            )
            VALUES (?, ?, ?, 0, ?, ?, NULL, NULL, NULL)
            """,
            (task_id, next_position, title, created_at, created_at),
        )
        subtask_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
    return _row_to_subtask(row)


def list_subtasks(db_path: Path, task_id: int) -> List[Subtask]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY position ASC, created_at ASC", (task_id,)
        ).fetchall()
    return [_row_to_subtask(row) for row in rows]


def reorder_subtask(db_path: Path, subtask_id: int, new_position: int) -> List[Subtask]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT task_id FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
        if not row:
            return []

        task_id = row["task_id"]
        rows = conn.execute(
            "SELECT id FROM subtasks WHERE task_id = ? ORDER BY position ASC, created_at ASC",
            (task_id,),
        ).fetchall()
        ordered_ids = [item["id"] for item in rows]
        if subtask_id not in ordered_ids:
            return []

        old_index = ordered_ids.index(subtask_id)
        target_index = min(max(0, new_position), len(ordered_ids) - 1)
        if old_index != target_index:
            moved_id = ordered_ids.pop(old_index)
            ordered_ids.insert(target_index, moved_id)

        now = _now()
        conn.executemany(
            "UPDATE subtasks SET position = ?, updated_at = ? WHERE id = ?",
            [(index, now, item_id) for index, item_id in enumerate(ordered_ids)],
        )
        reordered_rows = conn.execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY position ASC, created_at ASC",
            (task_id,),
        ).fetchall()
    return [_row_to_subtask(item) for item in reordered_rows]


def bulk_reorder_subtasks(db_path: Path, task_id: int, ordered_subtask_ids: List[int]) -> List[Subtask]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM subtasks WHERE task_id = ? ORDER BY position ASC, created_at ASC",
            (task_id,),
        ).fetchall()
        current_ids = [row["id"] for row in rows]
        if not current_ids:
            return []

        seen = set()
        valid_order: List[int] = []
        current_set = set(current_ids)
        for subtask_id in ordered_subtask_ids:
            if subtask_id in current_set and subtask_id not in seen:
                valid_order.append(subtask_id)
                seen.add(subtask_id)

        for subtask_id in current_ids:
            if subtask_id not in seen:
                valid_order.append(subtask_id)

        now = _now()
        conn.executemany(
            "UPDATE subtasks SET position = ?, updated_at = ? WHERE id = ?",
            [(index, now, subtask_id) for index, subtask_id in enumerate(valid_order)],
        )
        reordered_rows = conn.execute(
            "SELECT * FROM subtasks WHERE task_id = ? ORDER BY position ASC, created_at ASC",
            (task_id,),
        ).fetchall()
    return [_row_to_subtask(row) for row in reordered_rows]


def get_subtask(db_path: Path, subtask_id: int) -> Optional[Subtask]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM subtasks WHERE id = ?", (subtask_id,)).fetchone()
    return _row_to_subtask(row) if row else None


def update_subtask(
    db_path: Path,
    subtask_id: int,
    *,
    title: Optional[str] = None,
    is_done: Optional[bool] = None,
    reminder_datetime: Optional[Optional[datetime]] = None,
    due_datetime: Optional[Optional[datetime]] | object = _UNSET,
    note: Optional[Optional[str]] = None,
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
        if reminder_datetime is not None:
            updates.append("reminder_datetime = ?")
            values.append(reminder_datetime.isoformat() if reminder_datetime else None)
        if due_datetime is not _UNSET:
            updates.append("due_datetime = ?")
            values.append(due_datetime.isoformat() if due_datetime else None)
        if note is not None:
            updates.append("note = ?")
            values.append(note)
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


def _would_create_cycle(db_path: Path, source_task_id: int, target_task_id: int) -> bool:
    graph: Dict[int, List[int]] = {}
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT from_task_id, to_task_id FROM task_links").fetchall()
    for row in rows:
        graph.setdefault(row["from_task_id"], []).append(row["to_task_id"])

    stack = [target_task_id]
    visited = set()
    while stack:
        node = stack.pop()
        if node == source_task_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph.get(node, []))
    return False


def _would_create_subtask_cycle(db_path: Path, source_subtask_id: int, target_subtask_id: int) -> bool:
    graph: Dict[int, List[int]] = {}
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT from_subtask_id, to_subtask_id FROM subtask_links WHERE link_type = 'depends_on'"
        ).fetchall()
    for row in rows:
        graph.setdefault(row["from_subtask_id"], []).append(row["to_subtask_id"])

    stack = [target_subtask_id]
    visited = set()
    while stack:
        node = stack.pop()
        if node == source_subtask_id:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph.get(node, []))
    return False


def list_task_links(db_path: Path) -> List[Tuple[int, int]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT from_task_id, to_task_id FROM task_links ORDER BY from_task_id, to_task_id"
        ).fetchall()
    return [(row["from_task_id"], row["to_task_id"]) for row in rows]


def list_task_links_with_type(db_path: Path) -> List[Tuple[int, int, str]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT from_task_id, to_task_id, type FROM task_links ORDER BY from_task_id, to_task_id"
        ).fetchall()
    return [(row["from_task_id"], row["to_task_id"], row["type"]) for row in rows]


def create_task_link(
    db_path: Path,
    source_task_id: int,
    target_task_id: int,
    *,
    prevent_cycles: bool = True,
) -> bool:
    if source_task_id == target_task_id:
        return False
    if not get_task(db_path, source_task_id) or not get_task(db_path, target_task_id):
        return False
    if prevent_cycles and _would_create_cycle(db_path, source_task_id, target_task_id):
        return False

    now = _now()
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO task_links (from_task_id, to_task_id, type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (source_task_id, target_task_id, "depends_on", now, now),
        )
    return cursor.rowcount > 0


def delete_task_link(db_path: Path, source_task_id: int, target_task_id: int) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM task_links WHERE from_task_id = ? AND to_task_id = ?",
            (source_task_id, target_task_id),
        )
    return cursor.rowcount > 0


def list_subtask_links(db_path: Path) -> List[Tuple[int, int, str]]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT from_subtask_id, to_subtask_id, link_type
            FROM subtask_links
            ORDER BY from_subtask_id, to_subtask_id, link_type
            """
        ).fetchall()
    return [(row["from_subtask_id"], row["to_subtask_id"], row["link_type"]) for row in rows]


def create_subtask_link(
    db_path: Path,
    source_subtask_id: int,
    target_subtask_id: int,
    *,
    link_type: str = "depends_on",
    prevent_cycles: bool = True,
) -> bool:
    if source_subtask_id == target_subtask_id:
        return False
    if not get_subtask(db_path, source_subtask_id) or not get_subtask(db_path, target_subtask_id):
        return False
    if link_type == "depends_on" and prevent_cycles:
        if _would_create_subtask_cycle(db_path, source_subtask_id, target_subtask_id):
            return False

    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO subtask_links (from_subtask_id, to_subtask_id, link_type, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (source_subtask_id, target_subtask_id, link_type, _now()),
        )
    return cursor.rowcount > 0


def delete_subtask_link(
    db_path: Path,
    source_subtask_id: int,
    target_subtask_id: int,
    *,
    link_type: Optional[str] = None,
) -> bool:
    with get_conn(db_path) as conn:
        if link_type is None:
            cursor = conn.execute(
                "DELETE FROM subtask_links WHERE from_subtask_id = ? AND to_subtask_id = ?",
                (source_subtask_id, target_subtask_id),
            )
        else:
            cursor = conn.execute(
                """
                DELETE FROM subtask_links
                WHERE from_subtask_id = ? AND to_subtask_id = ? AND link_type = ?
                """,
                (source_subtask_id, target_subtask_id, link_type),
            )
    return cursor.rowcount > 0


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


def create_board(db_path: Path, name: str, column_names: Optional[List[str]] = None) -> Board:
    board_name = _validate_non_empty(name, "Название доски")
    prepared_columns = column_names or ["To Do"]
    normalized_columns = [_validate_non_empty(col, "Название колонки") for col in prepared_columns]
    if len(set(normalized_columns)) != len(normalized_columns):
        raise BoardValidationError("Названия колонок в рамках доски должны быть уникальными")
    if not normalized_columns:
        raise BoardValidationError("У доски должна быть хотя бы одна колонка")

    timestamp = _now()
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO boards (name, created_at, updated_at) VALUES (?, ?, ?)",
            (board_name, timestamp, timestamp),
        )
        board_id = cursor.lastrowid
        for position, column_name in enumerate(normalized_columns):
            conn.execute(
                """
                INSERT INTO board_columns (board_id, name, position, wip_limit)
                VALUES (?, ?, ?, NULL)
                """,
                (board_id, column_name, position),
            )
        row = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    return _row_to_board(row)


def list_boards(db_path: Path) -> List[Board]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT * FROM boards ORDER BY created_at ASC").fetchall()
    return [_row_to_board(row) for row in rows]


def get_board(db_path: Path, board_id: int) -> Optional[Board]:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    return _row_to_board(row) if row else None


def update_board(db_path: Path, board_id: int, name: str) -> Optional[Board]:
    board_name = _validate_non_empty(name, "Название доски")
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            "UPDATE boards SET name = ?, updated_at = ? WHERE id = ?",
            (board_name, _now(), board_id),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM boards WHERE id = ?", (board_id,)).fetchone()
    return _row_to_board(row)


def delete_board(db_path: Path, board_id: int) -> bool:
    with get_conn(db_path) as conn:
        cursor = conn.execute("DELETE FROM boards WHERE id = ?", (board_id,))
    return cursor.rowcount > 0


def list_board_columns(db_path: Path, board_id: int) -> List[BoardColumn]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM board_columns WHERE board_id = ? ORDER BY position ASC",
            (board_id,),
        ).fetchall()
    return [_row_to_board_column(row) for row in rows]


def create_board_column(
    db_path: Path,
    board_id: int,
    name: str,
    *,
    wip_limit: Optional[int] = None,
) -> BoardColumn:
    column_name = _validate_non_empty(name, "Название колонки")
    if get_board(db_path, board_id) is None:
        raise BoardValidationError(f"Доска #{board_id} не найдена")
    if wip_limit is not None and wip_limit <= 0:
        raise BoardValidationError("WIP лимит должен быть положительным")

    with get_conn(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM board_columns WHERE board_id = ? AND name = ?",
            (board_id, column_name),
        ).fetchone()
        if exists:
            raise BoardValidationError("Названия колонок в рамках доски должны быть уникальными")
        max_position = conn.execute(
            "SELECT COALESCE(MAX(position), -1) AS max_pos FROM board_columns WHERE board_id = ?",
            (board_id,),
        ).fetchone()["max_pos"]
        cursor = conn.execute(
            """
            INSERT INTO board_columns (board_id, name, position, wip_limit)
            VALUES (?, ?, ?, ?)
            """,
            (board_id, column_name, max_position + 1, wip_limit),
        )
        row = conn.execute("SELECT * FROM board_columns WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_board_column(row)


def rename_board_column(db_path: Path, column_id: int, new_name: str) -> Optional[BoardColumn]:
    column_name = _validate_non_empty(new_name, "Название колонки")
    with get_conn(db_path) as conn:
        column = conn.execute("SELECT * FROM board_columns WHERE id = ?", (column_id,)).fetchone()
        if not column:
            return None
        duplicate = conn.execute(
            "SELECT 1 FROM board_columns WHERE board_id = ? AND name = ? AND id != ?",
            (column["board_id"], column_name, column_id),
        ).fetchone()
        if duplicate:
            raise BoardValidationError("Названия колонок в рамках доски должны быть уникальными")
        conn.execute(
            "UPDATE board_columns SET name = ? WHERE id = ?",
            (column_name, column_id),
        )
        row = conn.execute("SELECT * FROM board_columns WHERE id = ?", (column_id,)).fetchone()
    return _row_to_board_column(row)


def reorder_board_columns(db_path: Path, board_id: int, ordered_column_ids: List[int]) -> List[BoardColumn]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id FROM board_columns WHERE board_id = ? ORDER BY position ASC",
            (board_id,),
        ).fetchall()
        existing_ids = [row["id"] for row in rows]
        if not existing_ids:
            raise BoardValidationError("У доски должна быть хотя бы одна колонка")
        if set(existing_ids) != set(ordered_column_ids) or len(existing_ids) != len(ordered_column_ids):
            raise BoardValidationError("Некорректный список колонок для переупорядочивания")
        for offset, column_id in enumerate(ordered_column_ids):
            conn.execute("UPDATE board_columns SET position = ? WHERE id = ?", (1000 + offset, column_id))
        for position, column_id in enumerate(ordered_column_ids):
            conn.execute("UPDATE board_columns SET position = ? WHERE id = ?", (position, column_id))

    return list_board_columns(db_path, board_id)


def _repack_column_positions(conn: sqlite3.Connection, column_id: int) -> None:
    rows = conn.execute(
        "SELECT id FROM board_items WHERE column_id = ? ORDER BY position ASC, id ASC",
        (column_id,),
    ).fetchall()
    for position, row in enumerate(rows):
        conn.execute("UPDATE board_items SET position = ? WHERE id = ?", (position, row["id"]))


def list_board_items(db_path: Path, board_id: int) -> List[BoardItem]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM board_items WHERE board_id = ? ORDER BY column_id ASC, position ASC",
            (board_id,),
        ).fetchall()
    return [_row_to_board_item(row) for row in rows]


def move_board_item(
    db_path: Path,
    board_id: int,
    task_id: int,
    column_id: int,
    position: int,
) -> BoardItem:
    if position < 0:
        raise BoardValidationError("Позиция должна быть неотрицательной")

    with get_conn(db_path) as conn:
        board = conn.execute("SELECT id FROM boards WHERE id = ?", (board_id,)).fetchone()
        if not board:
            raise BoardValidationError(f"Доска #{board_id} не найдена")

        task = conn.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task:
            raise BoardValidationError(f"Задача #{task_id} не найдена")

        target_column = conn.execute(
            "SELECT id, board_id FROM board_columns WHERE id = ?",
            (column_id,),
        ).fetchone()
        if not target_column or target_column["board_id"] != board_id:
            raise BoardValidationError("Колонка не принадлежит указанной доске")

        item = conn.execute(
            "SELECT * FROM board_items WHERE board_id = ? AND task_id = ?",
            (board_id, task_id),
        ).fetchone()

        if item:
            old_column_id = item["column_id"]
            item_id = item["id"]
            conn.execute("DELETE FROM board_items WHERE id = ?", (item_id,))
            _repack_column_positions(conn, old_column_id)
        else:
            item_id = None

        target_count = conn.execute(
            "SELECT COUNT(*) AS count FROM board_items WHERE column_id = ?",
            (column_id,),
        ).fetchone()["count"]
        normalized_position = min(position, target_count)

        conn.execute(
            "UPDATE board_items SET position = position + 1 WHERE column_id = ? AND position >= ?",
            (column_id, normalized_position),
        )

        if item_id is None:
            cursor = conn.execute(
                """
                INSERT INTO board_items (board_id, task_id, column_id, position)
                VALUES (?, ?, ?, ?)
                """,
                (board_id, task_id, column_id, normalized_position),
            )
            item_id = cursor.lastrowid
        else:
            conn.execute(
                """
                INSERT INTO board_items (id, board_id, task_id, column_id, position)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item_id, board_id, task_id, column_id, normalized_position),
            )

        row = conn.execute("SELECT * FROM board_items WHERE id = ?", (item_id,)).fetchone()

    return _row_to_board_item(row)


def ensure_board_item(db_path: Path, board_id: int, task_id: int) -> Optional[BoardItem]:
    with get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT * FROM board_items WHERE board_id = ? AND task_id = ?",
            (board_id, task_id),
        ).fetchone()
        if existing:
            return _row_to_board_item(existing)

        first_column = conn.execute(
            "SELECT id FROM board_columns WHERE board_id = ? ORDER BY position ASC LIMIT 1",
            (board_id,),
        ).fetchone()
        if not first_column:
            return None

    return move_board_item(db_path, board_id, task_id, first_column["id"], position=10**9)
