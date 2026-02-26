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






def test_task_priority_create_and_update(tmp_path):
    db_path = temp_db(tmp_path)

    created = storage.create_task(db_path, "Приоритетная", priority="high")
    assert created.priority == "high"

    updated = storage.update_task(db_path, created.id, priority="critical")
    assert updated is not None
    assert updated.priority == "critical"


def test_subtask_priority_create_and_update(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Родитель")

    created = storage.create_subtask(db_path, task.id, "Подзадача", priority="low")
    assert created is not None
    assert created.priority == "low"

    updated = storage.update_subtask(db_path, created.id, priority="medium")
    assert updated is not None
    assert updated.priority == "medium"


def test_priority_validation_rejects_invalid_values(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Обычная")

    try:
        storage.create_task(db_path, "Плохой приоритет", priority="urgent")
    except storage.PriorityValidationError:
        pass
    else:
        raise AssertionError("Expected PriorityValidationError for invalid task priority")

    try:
        storage.update_task(db_path, task.id, priority="urgent")
    except storage.PriorityValidationError:
        pass
    else:
        raise AssertionError("Expected PriorityValidationError for invalid task priority update")

    subtask = storage.create_subtask(db_path, task.id, "Подзадача")
    assert subtask is not None
    try:
        storage.update_subtask(db_path, subtask.id, priority="urgent")
    except storage.PriorityValidationError:
        pass
    else:
        raise AssertionError("Expected PriorityValidationError for invalid subtask priority update")


def test_reorder_subtask_moves_item_with_clamped_position(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Основная")
    first = storage.create_subtask(db_path, task.id, "Шаг 1")
    second = storage.create_subtask(db_path, task.id, "Шаг 2")
    third = storage.create_subtask(db_path, task.id, "Шаг 3")

    reordered = storage.reorder_subtask(db_path, second.id, -10)
    assert [subtask.id for subtask in reordered] == [second.id, first.id, third.id]

    reordered = storage.reorder_subtask(db_path, second.id, 99)
    assert [subtask.id for subtask in reordered] == [first.id, third.id, second.id]


def test_bulk_reorder_subtasks_ignores_invalid_ids_and_normalizes_positions(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Основная")
    first = storage.create_subtask(db_path, task.id, "Шаг 1")
    second = storage.create_subtask(db_path, task.id, "Шаг 2")
    third = storage.create_subtask(db_path, task.id, "Шаг 3")

    reordered = storage.bulk_reorder_subtasks(
        db_path,
        task.id,
        [third.id, 999999, third.id, first.id],
    )
    assert [subtask.id for subtask in reordered] == [third.id, first.id, second.id]
    assert [subtask.position for subtask in reordered] == [0, 1, 2]

    listed = storage.list_subtasks(db_path, task.id)
    assert [subtask.id for subtask in listed] == [third.id, first.id, second.id]


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
    assert "priority" in columns


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
    storage.create_task(db_path, "Без дедлайна", reminder_datetime=now - timedelta(days=1))
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


def test_convert_task_to_subtask_keeps_done_status(tmp_path):
    db_path = temp_db(tmp_path)
    parent = storage.create_task(db_path, "Родитель")
    child = storage.create_task(db_path, "Дочерняя")
    storage.update_task(db_path, child.id, is_done=True)

    converted = storage.convert_task_to_subtask(db_path, child.id, parent.id)

    assert converted is not None
    subtasks = storage.list_subtasks(db_path, parent.id)
    assert len(subtasks) == 1
    assert subtasks[0].is_done is True


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

    try:
        storage.convert_task_to_subtask(db_path, child.id, parent.id)
    except storage.ConvertToSubtaskError as exc:
        assert f"Родительская задача #{parent.id} не найдена" in str(exc)
    else:
        raise AssertionError("Expected ConvertToSubtaskError for missing parent")

    assert storage.get_task(db_path, child.id) is not None


def test_convert_task_to_subtask_rejects_child_with_subtasks(tmp_path):
    db_path = temp_db(tmp_path)
    parent = storage.create_task(db_path, "Родитель")
    child = storage.create_task(db_path, "Дочерняя")
    storage.create_subtask(db_path, child.id, "Внутренняя подзадача")

    try:
        storage.convert_task_to_subtask(db_path, child.id, parent.id)
    except ValueError as exc:
        assert "задачу с подзадачами" in str(exc)
    else:
        raise AssertionError("Expected ValueError for child with subtasks")

    assert storage.get_task(db_path, child.id) is not None
    assert storage.list_subtasks(db_path, parent.id) == []


def test_convert_task_to_subtask_rejects_child_with_links(tmp_path):
    db_path = temp_db(tmp_path)
    parent = storage.create_task(db_path, "Родитель")
    child = storage.create_task(db_path, "Дочерняя")
    extra = storage.create_task(db_path, "Связанная")
    assert storage.create_task_link(db_path, child.id, extra.id) is True

    try:
        storage.convert_task_to_subtask(db_path, child.id, parent.id)
    except ValueError as exc:
        assert "связях графа" in str(exc)
    else:
        raise AssertionError("Expected ValueError for child with graph links")

    assert storage.get_task(db_path, child.id) is not None
    assert storage.list_subtasks(db_path, parent.id) == []


def test_task_links_prevent_self_and_cycles(tmp_path):
    db_path = temp_db(tmp_path)
    first = storage.create_task(db_path, "A")
    second = storage.create_task(db_path, "B")
    third = storage.create_task(db_path, "C")

    assert storage.create_task_link(db_path, first.id, first.id) is False
    assert storage.create_task_link(db_path, first.id, second.id) is True
    assert storage.create_task_link(db_path, second.id, third.id) is True
    assert storage.create_task_link(db_path, third.id, first.id) is False

    assert storage.list_task_links(db_path) == [
        (first.id, second.id),
        (second.id, third.id),
    ]


def test_task_layout_roundtrip(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Node")

    assert storage.set_task_layout(db_path, task.id, 125.5, 77.25) is True
    assert storage.get_task_layouts(db_path)[task.id] == (125.5, 77.25)

    assert storage.set_task_layout(db_path, task.id, 300.0, 140.0) is True
    assert storage.get_task_layouts(db_path)[task.id] == (300.0, 140.0)


def test_delete_task_link_returns_false_for_missing_link(tmp_path):
    db_path = temp_db(tmp_path)
    first = storage.create_task(db_path, "A")
    second = storage.create_task(db_path, "B")

    assert storage.delete_task_link(db_path, first.id, second.id) is False


def test_task_links_schema_and_metadata(tmp_path):
    db_path = temp_db(tmp_path)
    first = storage.create_task(db_path, "A")
    second = storage.create_task(db_path, "B")

    assert storage.create_task_link(db_path, first.id, second.id) is True

    with storage.get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT from_task_id, to_task_id, type, created_at, updated_at FROM task_dependencies"
        ).fetchone()

    assert row["from_task_id"] == first.id
    assert row["to_task_id"] == second.id
    assert row["type"] == "depends_on"
    assert row["created_at"]
    assert row["updated_at"]


def test_subtask_links_create_chain_and_prevent_cycles(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Цепочка")
    first = storage.create_subtask(db_path, task.id, "A")
    second = storage.create_subtask(db_path, task.id, "B")
    third = storage.create_subtask(db_path, task.id, "C")

    assert storage.create_subtask_link(db_path, first.id, second.id) is True
    assert storage.create_subtask_link(db_path, second.id, third.id) is True
    assert storage.create_subtask_link(db_path, third.id, first.id) is False
    assert storage.create_subtask_link(db_path, first.id, first.id) is False

    assert storage.list_subtask_links(db_path) == [
        (first.id, second.id, "depends_on"),
        (second.id, third.id, "depends_on"),
    ]


def test_subtask_links_cascade_deleted_node(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Каскад")
    first = storage.create_subtask(db_path, task.id, "A")
    second = storage.create_subtask(db_path, task.id, "B")
    third = storage.create_subtask(db_path, task.id, "C")

    assert storage.create_subtask_link(db_path, first.id, second.id) is True
    assert storage.create_subtask_link(db_path, second.id, third.id) is True

    assert storage.delete_subtask(db_path, second.id) is True
    assert storage.list_subtask_links(db_path) == []


def test_subtask_links_cascade_on_task_delete(tmp_path):
    db_path = temp_db(tmp_path)
    parent = storage.create_task(db_path, "Родитель")
    first = storage.create_subtask(db_path, parent.id, "A")
    second = storage.create_subtask(db_path, parent.id, "B")
    assert storage.create_subtask_link(db_path, first.id, second.id) is True

    assert storage.delete_task(db_path, parent.id) is True
    assert storage.list_subtask_links(db_path) == []


def test_board_crud_and_columns_validation(tmp_path):
    db_path = temp_db(tmp_path)

    board = storage.create_board(db_path, "Разработка", ["Backlog", "Doing", "Done"])
    assert board.name == "Разработка"

    loaded = storage.get_board(db_path, board.id)
    assert loaded is not None

    renamed = storage.update_board(db_path, board.id, "Новая разработка")
    assert renamed is not None
    assert renamed.name == "Новая разработка"

    columns = storage.list_board_columns(db_path, board.id)
    assert [col.name for col in columns] == ["Backlog", "Doing", "Done"]

    try:
        storage.create_board_column(db_path, board.id, "Doing")
    except storage.BoardValidationError as exc:
        assert "уникальными" in str(exc)
    else:
        raise AssertionError("Expected BoardValidationError for duplicate column name")

    assert storage.delete_board(db_path, board.id) is True
    assert storage.get_board(db_path, board.id) is None


def test_board_column_reorder_and_move_items(tmp_path):
    db_path = temp_db(tmp_path)
    board = storage.create_board(db_path, "Flow", ["Todo", "Doing", "Done"])
    columns = storage.list_board_columns(db_path, board.id)
    todo, doing, done = columns

    task_a = storage.create_task(db_path, "A")
    task_b = storage.create_task(db_path, "B")
    task_c = storage.create_task(db_path, "C")

    storage.move_board_item(db_path, board.id, task_a.id, todo.id, 0)
    storage.move_board_item(db_path, board.id, task_b.id, todo.id, 1)
    storage.move_board_item(db_path, board.id, task_c.id, todo.id, 1)

    items = storage.list_board_items(db_path, board.id)
    in_todo = [item.task_id for item in items if item.column_id == todo.id]
    assert in_todo == [task_a.id, task_c.id, task_b.id]

    storage.move_board_item(db_path, board.id, task_c.id, doing.id, 0)
    items = storage.list_board_items(db_path, board.id)
    todo_ids = [item.task_id for item in items if item.column_id == todo.id]
    doing_ids = [item.task_id for item in items if item.column_id == doing.id]
    assert todo_ids == [task_a.id, task_b.id]
    assert doing_ids == [task_c.id]

    reordered = storage.reorder_board_columns(db_path, board.id, [done.id, todo.id, doing.id])
    assert [col.id for col in reordered] == [done.id, todo.id, doing.id]


def test_move_board_item_by_id_reorders_inside_same_column(tmp_path):
    db_path = temp_db(tmp_path)
    board = storage.create_board(db_path, "Flow", ["Todo", "Doing"])
    todo = storage.list_board_columns(db_path, board.id)[0]

    task_a = storage.create_task(db_path, "A")
    task_b = storage.create_task(db_path, "B")
    task_c = storage.create_task(db_path, "C")

    item_a = storage.move_board_item(db_path, board.id, task_a.id, todo.id, 0)
    item_b = storage.move_board_item(db_path, board.id, task_b.id, todo.id, 1)
    item_c = storage.move_board_item(db_path, board.id, task_c.id, todo.id, 2)

    moved = storage.move_board_item_by_id(db_path, item_c.id, todo.id, 1)
    assert moved.id == item_c.id

    items = storage.list_board_items(db_path, board.id)
    ordered = [item.task_id for item in items if item.column_id == todo.id]
    assert ordered == [task_a.id, task_c.id, task_b.id]
    positions = [item.position for item in items if item.column_id == todo.id]
    assert positions == [0, 1, 2]


def test_move_board_item_by_id_between_columns_and_fix_neighbors(tmp_path):
    db_path = temp_db(tmp_path)
    board = storage.create_board(db_path, "Flow", ["Todo", "Doing", "Done"])
    todo, doing, _ = storage.list_board_columns(db_path, board.id)

    task_a = storage.create_task(db_path, "A")
    task_b = storage.create_task(db_path, "B")
    task_c = storage.create_task(db_path, "C")
    task_d = storage.create_task(db_path, "D")

    item_a = storage.move_board_item(db_path, board.id, task_a.id, todo.id, 0)
    item_b = storage.move_board_item(db_path, board.id, task_b.id, todo.id, 1)
    storage.move_board_item(db_path, board.id, task_c.id, doing.id, 0)
    storage.move_board_item(db_path, board.id, task_d.id, doing.id, 1)

    moved = storage.move_board_item_by_id(db_path, item_b.id, doing.id, 1)
    assert moved.column_id == doing.id
    assert moved.position == 1

    items = storage.list_board_items(db_path, board.id)
    todo_items = [item for item in items if item.column_id == todo.id]
    doing_items = [item for item in items if item.column_id == doing.id]

    assert [item.task_id for item in todo_items] == [task_a.id]
    assert [item.position for item in todo_items] == [0]
    assert [item.task_id for item in doing_items] == [task_c.id, task_b.id, task_d.id]
    assert [item.position for item in doing_items] == [0, 1, 2]


def test_board_validation_position_and_board_isolation(tmp_path):
    db_path = temp_db(tmp_path)
    board_a = storage.create_board(db_path, "A", ["Todo", "Done"])
    board_b = storage.create_board(db_path, "B", ["Queue"])

    task = storage.create_task(db_path, "Shared")
    a_todo = storage.list_board_columns(db_path, board_a.id)[0]
    b_queue = storage.list_board_columns(db_path, board_b.id)[0]

    try:
        storage.move_board_item(db_path, board_a.id, task.id, b_queue.id, 0)
    except storage.BoardValidationError as exc:
        assert "не принадлежит" in str(exc)
    else:
        raise AssertionError("Expected BoardValidationError for foreign column")

    try:
        storage.move_board_item(db_path, board_a.id, task.id, a_todo.id, -1)
    except storage.BoardValidationError as exc:
        assert "неотрицательной" in str(exc)
    else:
        raise AssertionError("Expected BoardValidationError for negative position")

    storage.move_board_item(db_path, board_a.id, task.id, a_todo.id, 99)
    item = storage.list_board_items(db_path, board_a.id)[0]
    assert item.position == 0


def test_update_and_delete_board_column_with_transfer(tmp_path):
    db_path = temp_db(tmp_path)
    board = storage.create_board(db_path, "Flow", ["Todo", "Doing", "Done"])
    todo, doing, done = storage.list_board_columns(db_path, board.id)

    updated = storage.update_board_column(db_path, doing.id, name="In Progress", wip_limit=2)
    assert updated is not None
    assert updated.name == "In Progress"
    assert updated.wip_limit == 2

    task_a = storage.create_task(db_path, "A")
    task_b = storage.create_task(db_path, "B")
    storage.move_board_item(db_path, board.id, task_a.id, todo.id, 0)
    storage.move_board_item(db_path, board.id, task_b.id, todo.id, 1)

    assert storage.delete_board_column(db_path, todo.id, done.id) is True

    columns_after = storage.list_board_columns(db_path, board.id)
    assert [col.name for col in columns_after] == ["In Progress", "Done"]
    assert [col.position for col in columns_after] == [0, 1]

    items_after = storage.list_board_items(db_path, board.id)
    transferred = [item.task_id for item in items_after if item.column_id == done.id]
    assert transferred == [task_a.id, task_b.id]


def test_board_items_are_filtered_by_board_id(tmp_path):
    db_path = temp_db(tmp_path)
    board_a = storage.create_board(db_path, "A", ["Todo"])
    board_b = storage.create_board(db_path, "B", ["Todo"])
    a_col = storage.list_board_columns(db_path, board_a.id)[0]
    b_col = storage.list_board_columns(db_path, board_b.id)[0]

    task_one = storage.create_task(db_path, "Task 1")
    task_two = storage.create_task(db_path, "Task 2")
    storage.move_board_item(db_path, board_a.id, task_one.id, a_col.id, 0)
    storage.move_board_item(db_path, board_b.id, task_two.id, b_col.id, 0)

    assert [item.task_id for item in storage.list_board_items(db_path, board_a.id)] == [task_one.id]
    assert [item.task_id for item in storage.list_board_items(db_path, board_b.id)] == [task_two.id]


def test_subtask_due_datetime_can_be_before_or_equal_parent_due(tmp_path):
    db_path = temp_db(tmp_path)
    parent_due = datetime(2026, 1, 10, 18, 0, 0)
    parent = storage.create_task(db_path, "Родитель", due_datetime=parent_due)

    earlier = storage.create_subtask(db_path, parent.id, "Раньше", due_datetime=datetime(2026, 1, 10, 17, 0, 0))
    equal = storage.create_subtask(db_path, parent.id, "Равно", due_datetime=parent_due)

    assert earlier is not None
    assert equal is not None
    assert earlier.due_datetime < parent_due
    assert equal.due_datetime == parent_due


def test_subtask_due_datetime_cannot_be_later_than_parent_due(tmp_path):
    db_path = temp_db(tmp_path)
    parent_due = datetime(2026, 1, 10, 18, 0, 0)
    parent = storage.create_task(db_path, "Родитель", due_datetime=parent_due)

    try:
        storage.create_subtask(db_path, parent.id, "Позже", due_datetime=datetime(2026, 1, 10, 19, 0, 0))
    except storage.DeadlineValidationError as exc:
        assert "не может быть позже" in str(exc)
    else:
        raise AssertionError("Expected DeadlineValidationError for subtask due datetime")


def test_update_parent_due_datetime_rejects_conflicting_subtasks(tmp_path):
    db_path = temp_db(tmp_path)
    parent = storage.create_task(db_path, "Родитель", due_datetime=datetime(2026, 1, 10, 18, 0, 0))
    storage.create_subtask(db_path, parent.id, "Подзадача", due_datetime=datetime(2026, 1, 10, 17, 30, 0))

    try:
        storage.update_task(db_path, parent.id, due_datetime=datetime(2026, 1, 10, 17, 0, 0))
    except storage.DeadlineValidationError as exc:
        assert "Нельзя установить дедлайн задачи раньше" in str(exc)
    else:
        raise AssertionError("Expected DeadlineValidationError for parent due datetime update")


def test_move_subtask_success(tmp_path):
    db_path = temp_db(tmp_path)
    source = storage.create_task(db_path, "Source")
    target = storage.create_task(db_path, "Target")

    first = storage.create_subtask(db_path, source.id, "Первый")
    moved = storage.create_subtask(db_path, source.id, "Перенос")
    assert moved is not None
    existing_target = storage.create_subtask(db_path, target.id, "Уже в target")
    assert existing_target is not None

    updated = storage.move_subtask(db_path, moved.id, target.id)

    assert updated is not None
    assert updated.task_id == target.id
    assert [item.id for item in storage.list_subtasks(db_path, source.id)] == [first.id]
    target_subtasks = storage.list_subtasks(db_path, target.id)
    assert [item.id for item in target_subtasks] == [existing_target.id, updated.id]
    assert [item.position for item in target_subtasks] == [0, 1]


def test_move_subtask_rejects_deadline_violation(tmp_path):
    db_path = temp_db(tmp_path)
    source = storage.create_task(db_path, "Source")
    target = storage.create_task(db_path, "Target", due_datetime=datetime(2026, 1, 10, 10, 0, 0))
    moved = storage.create_subtask(db_path, source.id, "Перенос", due_datetime=datetime(2026, 1, 10, 12, 0, 0))
    assert moved is not None

    try:
        storage.move_subtask(db_path, moved.id, target.id)
    except storage.DeadlineValidationError as exc:
        assert "не может быть позже" in str(exc)
    else:
        raise AssertionError("Expected DeadlineValidationError for move_subtask")


def test_move_subtask_rejects_missing_target_task(tmp_path):
    db_path = temp_db(tmp_path)
    source = storage.create_task(db_path, "Source")
    moved = storage.create_subtask(db_path, source.id, "Перенос")
    assert moved is not None

    try:
        storage.move_subtask(db_path, moved.id, 99999)
    except ValueError as exc:
        assert "не найдена" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown target task")


def test_note_html_sanitization(tmp_path):
    db_path = temp_db(tmp_path)
    raw = "<h2>Заголовок</h2><script>alert(1)</script><p><strong>Текст</strong></p>"

    task = storage.create_task(db_path, "Заметка", note=raw)

    assert task.note is not None
    assert "<script>" not in task.note
    assert "<h2>" in task.note


def test_note_roundtrip_strips_qt_css_and_keeps_user_formatting(tmp_path):
    db_path = temp_db(tmp_path)
    raw = (
        "<!DOCTYPE HTML><html><head><meta charset='utf-8'/>"
        "<style type='text/css'>p, li { white-space: pre-wrap; }</style></head>"
        "<body><h2>Список</h2><ul><li>Первый</li><li><strong>Второй</strong></li></ul>"
        "<blockquote>Цитата</blockquote></body></html>"
    )

    created = storage.create_task(db_path, "Заметка", note=raw)
    reloaded = storage.get_task(db_path, created.id)

    assert reloaded is not None
    assert reloaded.note is not None
    assert "white-space" not in reloaded.note
    assert "<style" not in reloaded.note
    assert "<ul>" in reloaded.note
    assert "<blockquote>" in reloaded.note


def test_repair_sanitized_notes_updates_corrupted_notes(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Task", note="<p>ok</p>")
    subtask = storage.create_subtask(db_path, task.id, "Subtask")
    assert subtask is not None

    broken = "<style>p, li { white-space: pre-wrap; }</style><p>Текст</p>"
    with storage.get_conn(db_path) as conn:
        conn.execute("UPDATE tasks SET note = ? WHERE id = ?", (broken, task.id))
        conn.execute("UPDATE subtasks SET note = ? WHERE id = ?", (broken, subtask.id))

    repaired = storage.repair_sanitized_notes(db_path)
    repaired_task = storage.get_task(db_path, task.id)
    repaired_subtask = storage.get_subtask(db_path, subtask.id)

    assert repaired == {"tasks": 1, "subtasks": 1}
    assert repaired_task is not None and repaired_task.note == "<p>Текст</p>"
    assert repaired_subtask is not None and repaired_subtask.note == "<p>Текст</p>"


def test_attachment_crud_for_task_and_subtask(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Task")
    subtask = storage.create_subtask(db_path, task.id, "Subtask")
    assert subtask is not None

    source_file = tmp_path / "sample.txt"
    source_file.write_text("hello attachment", encoding="utf-8")

    task_attachment = storage.create_attachment(
        db_path,
        entity_type="task",
        entity_id=task.id,
        source_path=source_file,
        original_name="task-sample.txt",
        mime="text/plain",
    )
    subtask_attachment = storage.create_attachment(
        db_path,
        entity_type="subtask",
        entity_id=subtask.id,
        source_path=source_file,
        original_name="subtask-sample.txt",
        mime="text/plain",
    )

    task_items = storage.list_attachments(db_path, entity_type="task", entity_id=task.id)
    subtask_items = storage.list_attachments(db_path, entity_type="subtask", entity_id=subtask.id)

    assert [item.id for item in task_items] == [task_attachment.id]
    assert [item.id for item in subtask_items] == [subtask_attachment.id]

    assert storage.delete_attachment(db_path, task_attachment.id) is True
    assert storage.get_attachment(db_path, task_attachment.id) is None


def test_attachment_errors_for_missing_and_big_file(tmp_path):
    db_path = temp_db(tmp_path)
    task = storage.create_task(db_path, "Task")

    missing_file = tmp_path / "missing.bin"
    try:
        storage.create_attachment(
            db_path,
            entity_type="task",
            entity_id=task.id,
            source_path=missing_file,
        )
    except storage.AttachmentStorageError:
        pass
    else:
        raise AssertionError("Expected AttachmentStorageError for missing file")

    big_file = tmp_path / "big.bin"
    big_file.write_bytes(b"x" * (storage.MAX_ATTACHMENT_SIZE + 1))
    try:
        storage.create_attachment(
            db_path,
            entity_type="task",
            entity_id=task.id,
            source_path=big_file,
        )
    except storage.AttachmentValidationError:
        pass
    else:
        raise AssertionError("Expected AttachmentValidationError for too large file")
