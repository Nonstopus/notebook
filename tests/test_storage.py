from datetime import datetime, timedelta
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



def test_create_and_list_task_links(tmp_path):
    db_path = temp_db(tmp_path)
    t1 = storage.create_task(db_path, "A")
    t2 = storage.create_task(db_path, "B")

    link = storage.create_task_link(db_path, t1.id, t2.id)

    links = storage.list_task_links(db_path)
    assert len(links) == 1
    assert links[0].id == link.id
    assert links[0].from_task_id == t1.id
    assert links[0].to_task_id == t2.id
    assert links[0].link_type == "sequence"



def test_task_link_constraints_and_delete(tmp_path):
    import sqlite3

    db_path = temp_db(tmp_path)
    t1 = storage.create_task(db_path, "A")
    t2 = storage.create_task(db_path, "B")

    storage.create_task_link(db_path, t1.id, t2.id, link_type="dependency")

    try:
        storage.create_task_link(db_path, t1.id, t2.id)
        assert False, "Expected duplicate link to fail"
    except sqlite3.IntegrityError:
        pass

    try:
        storage.create_task_link(db_path, t1.id, t1.id)
        assert False, "Expected self link to fail"
    except sqlite3.IntegrityError:
        pass

    assert storage.delete_task_link(db_path, from_task_id=t1.id, to_task_id=t2.id)
    assert storage.list_task_links(db_path) == []



def test_task_link_deleted_with_task(tmp_path):
    db_path = temp_db(tmp_path)
    t1 = storage.create_task(db_path, "A")
    t2 = storage.create_task(db_path, "B")
    link = storage.create_task_link(db_path, t1.id, t2.id)

    assert storage.delete_task_link(db_path, link.id)

    link2 = storage.create_task_link(db_path, t1.id, t2.id)
    storage.delete_task(db_path, t1.id)

    assert not storage.delete_task_link(db_path, link2.id)
