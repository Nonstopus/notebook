import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app.main_qt import TaskQtWindow


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
