import subprocess
import sys
from pathlib import Path

import pytest

from app.services import tasks


def run_cli(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "app.cli", "--db", str(db_path), *args]
    return subprocess.run(command, check=True, capture_output=True, text=True)


def test_service_and_cli_end_to_end_flow(tmp_path):
    db_path = tmp_path / "integration.db"
    tasks.init_db(db_path)

    parent = tasks.create_task(db_path, "Подготовить релиз")
    child = tasks.create_task(db_path, "Проверить changelog")
    tasks.create_subtask(db_path, parent.id, "Обновить версию")
    tasks.create_subtask(db_path, parent.id, "Собрать артефакты")

    converted = run_cli(db_path, "convert-to-subtask", str(child.id), str(parent.id))
    assert "преобразована в подзадачу" in converted.stdout

    listed = run_cli(db_path, "list", "--search", "Подготовить")
    assert "Подготовить релиз" in listed.stdout

    progress = tasks.subtask_progress(db_path, parent.id)
    assert progress == (0, 3)

    first_subtask = tasks.list_subtasks(db_path, parent.id)[0]
    tasks.update_subtask(db_path, first_subtask.id, is_done=True)

    assert tasks.subtask_progress(db_path, parent.id) == (1, 3)


def test_cli_done_delete_are_reflected_in_qt_ui(tmp_path):
    pytest.importorskip("PySide6")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - environment guard
        pytest.skip(f"PySide6 runtime unavailable: {exc}")

    from app.main_qt import TaskQtWindow

    db_path = tmp_path / "integration_qt.db"
    tasks.init_db(db_path)

    run_cli(db_path, "add", "Синхронизация")
    app = QApplication.instance() or QApplication([])
    window = TaskQtWindow(db_path)
    window.show()
    app.processEvents()

    assert window.tasks_list.topLevelItemCount() == 1
    window._select_task_in_tree(1)

    run_cli(db_path, "done", "1")
    window.refresh_tasks()
    app.processEvents()
    assert tasks.get_task(db_path, 1).is_done is True

    run_cli(db_path, "delete", "1")
    window.refresh_tasks()
    app.processEvents()
    assert window.tasks_list.topLevelItemCount() == 0

    window.close()
