import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - environment guard
    pytest.skip(f"PySide6 runtime unavailable: {exc}", allow_module_level=True)

from app.main_qt import TaskQtWindow
from app.services import tasks


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_main_qt_import_has_no_tkinter_dependency(monkeypatch):
    import importlib
    import sys

    sys.modules.pop("app.main_qt", None)
    sys.modules.pop("tkinter", None)

    def _blocked_import(name, *args, **kwargs):
        if name == "tkinter" or name.startswith("tkinter."):
            raise AssertionError("Tkinter import is forbidden for Qt entrypoint")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", _blocked_import)

    module = importlib.import_module("app.main_qt")

    assert module is not None
    assert "tkinter" not in sys.modules


def test_qt_window_starts(app_instance, tmp_path):
    tasks.create_task(Path(tmp_path / "qt.db"), "Первая задача")
    window = TaskQtWindow(Path(tmp_path / "qt.db"))
    window.show()
    app_instance.processEvents()

    assert window.windowTitle() == "Task Tracker Desktop (Qt)"
    assert window.tasks_list is not None
    assert window.tasks_list.topLevelItemCount() == 1
    assert window.isVisible()

    window.close()


def test_convert_task_to_subtask_refreshes_list(app_instance, tmp_path, monkeypatch):
    db_path = Path(tmp_path / "qt.db")
    window = TaskQtWindow(db_path)

    parent = tasks.create_task(db_path, "Родитель")
    child = tasks.create_task(db_path, "Дочерняя")
    window.refresh_tasks()

    child_row = next(index for index, task in enumerate(window._tasks_cache) if task.id == child.id)
    window.tasks_list.setCurrentItem(window.tasks_list.topLevelItem(child_row))

    monkeypatch.setattr(
        "app.main_qt.QInputDialog.getItem",
        lambda *args, **kwargs: (f"#{parent.id} {parent.title}", True),
    )

    window.convert_task_to_subtask()

    titles = [task.title for task in window._tasks_cache]
    assert titles == ["Родитель"]
    assert window.tasks_list.topLevelItem(0).text(1) == "0/1 (0%) · подзадач: 1"

    window.close()


def test_qt_filters_by_status_and_subtasks(app_instance, tmp_path):
    db_path = Path(tmp_path / "qt.db")
    window = TaskQtWindow(db_path)

    with_subtasks = tasks.create_task(db_path, "С подзадачами")
    done_task = tasks.create_task(db_path, "Завершённая")
    tasks.create_subtask(db_path, with_subtasks.id, "Подшаг")
    tasks.update_task(db_path, done_task.id, is_done=True)

    window.status_filter.setCurrentText("Выполненные")
    window.subtasks_filter.setCurrentText("Без подзадач")
    window.refresh_tasks()

    visible_titles = [task.title for task in window._tasks_cache]
    assert visible_titles == ["Завершённая"]

    window.subtasks_filter.setCurrentText("Есть подзадачи")
    window.status_filter.setCurrentText("Все")
    window.sort_mode.setCurrentText("Подзадачи (по убыванию)")
    window.refresh_tasks()

    visible_titles = [task.title for task in window._tasks_cache]
    assert visible_titles == ["С подзадачами"]

    row_title = window.tasks_list.topLevelItem(0).text(0)
    assert "🧩" in row_title

    window.close()


def test_qt_main_entrypoint_smoke(monkeypatch, app_instance, tmp_path):
    from app import main_qt

    monkeypatch.setattr(main_qt, "DB_PATH", Path(tmp_path / "entrypoint.db"))
    monkeypatch.setattr(main_qt, "QApplication", lambda argv: app_instance)
    monkeypatch.setattr(TaskQtWindow, "show", lambda self: None)
    monkeypatch.setattr(app_instance, "exec", lambda: 0)

    tasks.create_task(main_qt.DB_PATH, "Из entrypoint")

    result = main_qt.main()

    assert result == 0
