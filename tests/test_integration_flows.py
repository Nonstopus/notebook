import subprocess
import sys
from pathlib import Path

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
