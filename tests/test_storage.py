from datetime import date, datetime, timedelta
from pathlib import Path

from app import storage


def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    storage.init_db(db_path)
    return db_path


def test_create_and_list_tasks(tmp_path):
    db_path = temp_db(tmp_path)
    storage.create_task(db_path, "Первое дело")
    storage.create_task(db_path, "Второе дело")
    tasks = storage.list_tasks(db_path)
    titles = [t.title for t in tasks]
    assert titles == ["Второе дело", "Первое дело"]


def test_subtasks_and_progress(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Основная")
    st1 = storage.create_subtask(db_path, task.id, "Шаг 1")
    st2 = storage.create_subtask(db_path, task.id, "Шаг 2")
    storage.update_subtask(db_path, st1.id, is_done=True)
    completed, total = storage.subtask_progress(db_path, task.id)
    assert completed == 1 and total == 2
    storage.delete_subtask(db_path, st2.id)
    completed, total = storage.subtask_progress(db_path, task.id)
    assert (completed, total) == (1, 1)


def test_reminder_clears_on_completion(tmp_path):
    db_path = temp_db(tmp_path)
    reminder_time = datetime.utcnow() + timedelta(minutes=10)
    task = storage.create_task(db_path, "Напомнить", reminder_datetime=reminder_time)
    storage.update_task(db_path, task.id, is_done=True)
    updated = storage.get_task(db_path, task.id)
    assert updated.reminder_datetime is None


def test_due_reminders(tmp_path):
    db_path = temp_db(tmp_path)
    past = datetime.utcnow() - timedelta(minutes=5)
    future = datetime.utcnow() + timedelta(minutes=5)
    storage.create_task(db_path, "Прошлое", reminder_datetime=past)
    storage.create_task(db_path, "Будущее", reminder_datetime=future)
    due = list(storage.due_reminders(db_path, now=datetime.utcnow()))
    assert len(due) == 1
    assert due[0].title == "Прошлое"


def test_search_by_title_and_note(tmp_path):
    db_path = temp_db(tmp_path)
    storage.create_task(db_path, "Купить молоко")
    storage.create_task(db_path, "Подготовка", note="срочно позвонить клиенту")

    by_title = storage.list_tasks(db_path, search="молоко")
    assert len(by_title) == 1
    assert by_title[0].title == "Купить молоко"

    by_note = storage.list_tasks(db_path, search="клиенту")
    assert len(by_note) == 1
    assert by_note[0].title == "Подготовка"


def test_due_datetime_roundtrip(tmp_path):
    db_path = temp_db(tmp_path)
    due_time = datetime.utcnow() + timedelta(days=1)

    created = storage.create_task(db_path, "Дедлайн", due_datetime=due_time)
    loaded = storage.get_task(db_path, created.id)

    assert loaded is not None
    assert loaded.due_datetime == due_time


def test_update_and_clear_due_datetime(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Обновить дедлайн")
    due_time = datetime.utcnow() + timedelta(hours=2)

    updated = storage.update_task(db_path, task.id, due_datetime=due_time)
    assert updated is not None
    assert updated.due_datetime == due_time

    cleared = storage.update_task(db_path, task.id, due_datetime=None)
    assert cleared is not None
    assert cleared.due_datetime is None


def test_migrate_adds_due_datetime_column(tmp_path):
    db_path = tmp_path / "legacy.db"
    with storage.get_conn(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE tasks (
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

    storage.init_db(db_path)

    with storage.get_conn(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}

    assert "due_datetime" in columns


def test_list_tasks_due_on_date_filter(tmp_path):
    db_path = temp_db(tmp_path)

    storage.create_task(db_path, "Сегодня", due_datetime=datetime(2025, 1, 10, 12, 0, 0))
    storage.create_task(db_path, "Завтра", due_datetime=datetime(2025, 1, 11, 9, 0, 0))
    storage.create_task(db_path, "Без срока")

    tasks = storage.list_tasks(db_path, due_on_date=date(2025, 1, 10))

    assert [task.title for task in tasks] == ["Сегодня"]


def test_list_tasks_overdue_filter(tmp_path):
    db_path = temp_db(tmp_path)
    now = datetime(2025, 1, 10, 12, 0, 0)

    overdue_task = storage.create_task(db_path, "Просрочено", due_datetime=now - timedelta(hours=1))
    storage.create_task(db_path, "В будущем", due_datetime=now + timedelta(hours=1))
    done_overdue = storage.create_task(db_path, "Сделано просроченное", due_datetime=now - timedelta(hours=2))
    storage.update_task(db_path, done_overdue.id, is_done=True)

    tasks = storage.list_tasks(db_path, overdue_only=True, now=now)

    assert [task.title for task in tasks] == [overdue_task.title]


def test_convert_task_to_subtask(tmp_path):
    db_path = temp_db(tmp_path)
    parent = storage.create_task(db_path, "Родитель")
    child = storage.create_task(db_path, "Дочерняя")

    converted = storage.convert_task_to_subtask(db_path, child.id, parent.id)

    assert converted is not None
    subtasks = storage.list_subtasks(db_path, parent.id)
    assert [subtask.title for subtask in subtasks] == ["Дочерняя"]
    assert all(task.id != child.id for task in storage.list_tasks(db_path))


def test_convert_task_to_subtask_requires_different_tasks(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Одна задача")

    try:
        storage.convert_task_to_subtask(db_path, task.id, task.id)
    except ValueError as exc:
        assert "самой себя" in str(exc)
    else:
        raise AssertionError("Expected ValueError for self conversion")


def test_convert_task_to_subtask_with_deleted_parent(tmp_path):
    db_path = temp_db(tmp_path)
    parent = storage.create_task(db_path, "Родитель")
    child = storage.create_task(db_path, "Дочерняя")
    storage.delete_task(db_path, parent.id)

    converted = storage.convert_task_to_subtask(db_path, child.id, parent.id)

    assert converted is None
    assert storage.get_task(db_path, child.id) is not None
