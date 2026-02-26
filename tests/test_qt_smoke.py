import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.main_qt import TaskQtWindow
from app.services import tasks


@pytest.fixture
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_qt_window_starts(app_instance, tmp_path):
    window = TaskQtWindow(Path(tmp_path / "qt.db"))
    window.show()
    app_instance.processEvents()

    assert window.windowTitle() == "Task Tracker Desktop (Qt)"
    assert window.tasks_list is not None
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
    assert window.tasks_list.topLevelItem(0).text(1) == "0/1"

    window.close()
