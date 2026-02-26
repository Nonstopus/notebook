from datetime import date, datetime, timedelta
from pathlib import Path

from app.services import tasks


def temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test_service.db"
    tasks.init_db(db_path)
    return db_path


def test_task_crud_and_get_via_service(tmp_path):
    db_path = temp_db(tmp_path)

    created = tasks.create_task(db_path, "Сервисная задача")
    assert created.title == "Сервисная задача"
    assert tasks.get_task(db_path, created.id) is not None

    updated = tasks.update_task(db_path, created.id, title="Обновлённая", note="Заметка")
    assert updated is not None
    assert updated.title == "Обновлённая"
    assert updated.note == "Заметка"

    assert tasks.delete_task(db_path, created.id) is True
    assert tasks.get_task(db_path, created.id) is None


def test_list_tasks_filters_and_due_reminders_via_service(tmp_path):
    db_path = temp_db(tmp_path)
    now = datetime.utcnow().replace(microsecond=0)

    overdue = tasks.create_task(
        db_path,
        "Купить молоко",
        reminder_datetime=now - timedelta(minutes=1),
        due_datetime=now - timedelta(days=1),
        note="магазин",
    )
    upcoming = tasks.create_task(
        db_path,
        "Позвонить",
        reminder_datetime=now + timedelta(hours=2),
        due_datetime=now + timedelta(days=1),
    )

    assert [task.id for task in tasks.list_tasks(db_path, search="молоко")] == [overdue.id]
    assert sorted(task.id for task in tasks.list_tasks(db_path, has_reminder=True)) == sorted([overdue.id, upcoming.id])

    assert tasks.list_tasks(db_path, overdue_only=True, now=now)

    tasks.update_task(db_path, overdue.id, is_done=True)
    assert [task.id for task in tasks.list_tasks(db_path, is_done=True)] == [overdue.id]
    assert [task.id for task in tasks.list_tasks(db_path, due_on_date=date.today() + timedelta(days=1))] == [upcoming.id]

    assert list(tasks.due_reminders(db_path, now=now)) == []


def test_subtask_methods_and_progress_via_service(tmp_path):
    db_path = temp_db(tmp_path)
    parent = tasks.create_task(db_path, "Родитель")

    st1 = tasks.create_subtask(db_path, parent.id, "Шаг 1")
    st2 = tasks.create_subtask(db_path, parent.id, "Шаг 2")
    assert st1 is not None and st2 is not None

    listed = tasks.list_subtasks(db_path, parent.id)
    assert [item.id for item in listed] == [st1.id, st2.id]
    assert tasks.get_subtask(db_path, st1.id) is not None

    updated = tasks.update_subtask(
        db_path,
        st1.id,
        title="Новый шаг",
        is_done=True,
        note="Заметка",
    )
    assert updated is not None
    assert updated.title == "Новый шаг"
    assert updated.is_done is True
    assert updated.note == "Заметка"

    assert tasks.subtask_progress(db_path, parent.id) == (1, 2)
    assert tasks.delete_subtask(db_path, st2.id) is True
    assert tasks.get_subtask(db_path, st2.id) is None
    assert tasks.subtask_progress(db_path, parent.id) == (1, 1)


def test_convert_task_to_subtask_success(tmp_path):
    db_path = temp_db(tmp_path)

    parent = tasks.create_task(db_path, "Родитель")
    child = tasks.create_task(db_path, "Дочерняя")
    tasks.update_task(db_path, child.id, is_done=True)

    converted = tasks.convert_task_to_subtask(db_path, child.id, parent.id)
    assert converted is not None
    assert converted.task_id == parent.id
    assert converted.is_done is True
    assert tasks.get_task(db_path, child.id) is None


def test_convert_task_to_subtask_errors(tmp_path):
    db_path = temp_db(tmp_path)

    parent = tasks.create_task(db_path, "Родитель")
    child = tasks.create_task(db_path, "Дочерняя")

    try:
        tasks.convert_task_to_subtask(db_path, parent.id, parent.id)
        assert False, "Ожидалось исключение"
    except tasks.ConvertToSubtaskError as exc:
        assert "самой себя" in str(exc)

    try:
        tasks.convert_task_to_subtask(db_path, 999, parent.id)
        assert False, "Ожидалось исключение"
    except tasks.ConvertToSubtaskError as exc:
        assert "не найдена" in str(exc)

    try:
        tasks.convert_task_to_subtask(db_path, child.id, 888)
        assert False, "Ожидалось исключение"
    except tasks.ConvertToSubtaskError as exc:
        assert "Родительская задача" in str(exc)

    tasks.create_subtask(db_path, child.id, "Вложенная")
    try:
        tasks.convert_task_to_subtask(db_path, child.id, parent.id)
        assert False, "Ожидалось исключение"
    except tasks.ConvertToSubtaskError as exc:
        assert "с подзадачами" in str(exc)


def test_convert_task_to_subtask_rejects_linked_child(tmp_path):
    db_path = temp_db(tmp_path)

    parent = tasks.create_task(db_path, "Родитель")
    child = tasks.create_task(db_path, "Дочерняя")
    linked = tasks.create_task(db_path, "Связанная")
    assert tasks.create_task_link(db_path, child.id, linked.id)

    try:
        tasks.convert_task_to_subtask(db_path, child.id, parent.id)
        assert False, "Ожидалось исключение"
    except tasks.ConvertToSubtaskError as exc:
        assert "связях графа" in str(exc)


def test_link_methods_via_service(tmp_path):
    db_path = temp_db(tmp_path)
    first = tasks.create_task(db_path, "Шаг 1")
    second = tasks.create_task(db_path, "Шаг 2")

    assert tasks.create_task_link(db_path, first.id, second.id) is True
    assert tasks.list_task_links(db_path) == [(first.id, second.id)]
    assert tasks.list_task_links(db_path, task_id=first.id) == [(first.id, second.id)]

    assert tasks.delete_task_link(db_path, first.id, second.id) is True
    assert tasks.list_task_links(db_path) == []


def test_layout_methods_via_service(tmp_path):
    db_path = temp_db(tmp_path)
    task = tasks.create_task(db_path, "Вершина")

    assert tasks.get_task_layouts(db_path) == {}
    assert tasks.set_task_layout(db_path, task.id, 10.5, 20.25) is True
    assert tasks.get_task_layouts(db_path)[task.id] == (10.5, 20.25)
