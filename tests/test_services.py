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


def test_board_service_multi_board_statuses_and_moves(tmp_path):
    db_path = temp_db(tmp_path)

    board_one = tasks.create_board(db_path, "Team A", ["Todo", "Doing", "Done"])
    board_two = tasks.create_board(db_path, "Team B", ["Queue", "Review"])

    assert [column.name for column in tasks.list_board_columns(db_path, board_one.id)] == ["Todo", "Doing", "Done"]
    assert [column.name for column in tasks.list_board_columns(db_path, board_two.id)] == ["Queue", "Review"]

    task_a = tasks.create_task(db_path, "Task A")
    task_b = tasks.create_task(db_path, "Task B")

    todo, doing, _ = tasks.list_board_columns(db_path, board_one.id)
    queue, review = tasks.list_board_columns(db_path, board_two.id)

    tasks.move_board_item(db_path, board_one.id, task_a.id, todo.id, 0)
    tasks.move_board_item(db_path, board_one.id, task_b.id, todo.id, 1)
    tasks.move_board_item(db_path, board_one.id, task_b.id, doing.id, 0)

    first_board_items = tasks.list_board_items(db_path, board_one.id)
    assert [item.task_id for item in first_board_items if item.column_id == todo.id] == [task_a.id]
    assert [item.task_id for item in first_board_items if item.column_id == doing.id] == [task_b.id]

    tasks.move_board_item(db_path, board_two.id, task_a.id, queue.id, 0)
    tasks.move_board_item(db_path, board_two.id, task_a.id, review.id, 0)
    second_board_items = tasks.list_board_items(db_path, board_two.id)
    assert [item.task_id for item in second_board_items if item.column_id == review.id] == [task_a.id]


def test_board_service_move_by_board_item_id(tmp_path):
    db_path = temp_db(tmp_path)
    board = tasks.create_board(db_path, "Team A", ["Todo", "Doing"])
    todo, doing = tasks.list_board_columns(db_path, board.id)

    task_a = tasks.create_task(db_path, "Task A")
    task_b = tasks.create_task(db_path, "Task B")
    item_a = tasks.move_board_item(db_path, board.id, task_a.id, todo.id, 0)
    tasks.move_board_item(db_path, board.id, task_b.id, todo.id, 1)

    moved = tasks.move_board_item_by_id(db_path, item_a.id, doing.id, 0)
    assert moved.column_id == doing.id

    board_items = tasks.list_board_items(db_path, board.id)
    assert [item.task_id for item in board_items if item.column_id == doing.id] == [task_a.id]



def test_board_service_column_validation_and_reorder(tmp_path):
    db_path = temp_db(tmp_path)
    board = tasks.create_board(db_path, "Ops", ["Incoming", "Working"])
    columns = tasks.list_board_columns(db_path, board.id)

    created = tasks.create_board_column(db_path, board.id, "Done")
    assert created.position == 2

    renamed = tasks.rename_board_column(db_path, created.id, "Closed")
    assert renamed is not None
    assert renamed.name == "Closed"

    try:
        tasks.rename_board_column(db_path, created.id, "Incoming")
    except tasks.BoardValidationError as exc:
        assert "уникальными" in str(exc)
    else:
        raise AssertionError("Expected BoardValidationError for duplicate rename")

    reordered = tasks.reorder_board_columns(db_path, board.id, [created.id, columns[0].id, columns[1].id])
    assert [column.id for column in reordered] == [created.id, columns[0].id, columns[1].id]


def test_board_service_delete_column_moves_cards_to_target(tmp_path):
    db_path = temp_db(tmp_path)
    board = tasks.create_board(db_path, "Ops", ["Incoming", "Working", "Done"])
    incoming, working, done = tasks.list_board_columns(db_path, board.id)

    updated = tasks.update_board_column(db_path, working.id, name="In Progress")
    assert updated is not None
    assert updated.name == "In Progress"

    task_a = tasks.create_task(db_path, "A")
    task_b = tasks.create_task(db_path, "B")
    tasks.move_board_item(db_path, board.id, task_a.id, incoming.id, 0)
    tasks.move_board_item(db_path, board.id, task_b.id, incoming.id, 1)

    assert tasks.delete_board_column(db_path, incoming.id, done.id) is True

    columns = tasks.list_board_columns(db_path, board.id)
    assert [column.name for column in columns] == ["In Progress", "Done"]
    done_items = [item.task_id for item in tasks.list_board_items(db_path, board.id) if item.column_id == done.id]
    assert done_items == [task_a.id, task_b.id]
