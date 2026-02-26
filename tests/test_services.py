from datetime import datetime, timedelta
from pathlib import Path

from app.services import tasks


def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_service.db"
    tasks.init_db(db_path)
    return db_path


def test_task_crud_via_service(tmp_path):
    db_path = temp_db(tmp_path)

    created = tasks.create_task(db_path, "Сервисная задача")
    assert created.title == "Сервисная задача"

    updated = tasks.update_task(db_path, created.id, title="Обновлённая")
    assert updated is not None
    assert updated.title == "Обновлённая"

    assert tasks.delete_task(db_path, created.id) is True
    assert tasks.get_task(db_path, created.id) is None


def test_subtasks_and_progress_via_service(tmp_path):
    db_path = temp_db(tmp_path)
    parent = tasks.create_task(db_path, "Родитель")

    st1 = tasks.create_subtask(db_path, parent.id, "Шаг 1")
    st2 = tasks.create_subtask(db_path, parent.id, "Шаг 2")
    assert st1 is not None and st2 is not None

    tasks.update_subtask(db_path, st1.id, is_done=True)
    assert tasks.subtask_progress(db_path, parent.id) == (1, 2)


def test_search_and_due_reminders_via_service(tmp_path):
    db_path = temp_db(tmp_path)
    now = datetime.utcnow()

    tasks.create_task(db_path, "Купить молоко", note="магазин")
    tasks.create_task(db_path, "Позвонить", reminder_datetime=now - timedelta(minutes=1))

    found = tasks.list_tasks(db_path, search="молоко")
    assert [task.title for task in found] == ["Купить молоко"]

    reminders = list(tasks.due_reminders(db_path, now=now))
    assert [task.title for task in reminders] == ["Позвонить"]


def test_links_via_service(tmp_path):
    db_path = temp_db(tmp_path)
    first = tasks.create_task(db_path, "Шаг 1")
    second = tasks.create_task(db_path, "Шаг 2")

    assert tasks.create_task_link(db_path, first.id, second.id) is True
    assert tasks.list_task_links(db_path) == [(first.id, second.id)]
    assert tasks.list_task_links(db_path, task_id=first.id) == [(first.id, second.id)]

    assert tasks.delete_task_link(db_path, first.id, second.id) is True
    assert tasks.list_task_links(db_path) == []
