import subprocess
import sys
from pathlib import Path


def run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    db_path = tmp_path / "cli.db"
    command = [sys.executable, "-m", "app.cli", "--db", str(db_path), *args]
    return subprocess.run(command, check=True, capture_output=True, text=True)


def test_cli_add_and_list(tmp_path):
    run_cli(tmp_path, "add", "Купить молоко", "--due-datetime", "2030-01-01 10:00")
    result = run_cli(tmp_path, "list")
    assert "Купить молоко" in result.stdout
    assert "due_datetime=2030-01-01 10:00" in result.stdout


def test_cli_done_and_delete(tmp_path):
    run_cli(tmp_path, "add", "Сделать отчёт")
    done = run_cli(tmp_path, "done", "1")
    assert "Готово" in done.stdout

    deleted = run_cli(tmp_path, "delete", "1")
    assert "Удалено" in deleted.stdout


def test_cli_search(tmp_path):
    run_cli(tmp_path, "add", "Купить молоко")
    run_cli(tmp_path, "add", "Позвонить маме")

    result = run_cli(tmp_path, "list", "--search", "молоко")
    assert "Купить молоко" in result.stdout
    assert "Позвонить маме" not in result.stdout


def test_cli_links(tmp_path):
    run_cli(tmp_path, "add", "Шаг 1")
    run_cli(tmp_path, "add", "Шаг 2")
    added = run_cli(tmp_path, "link", "add", "1", "2")
    assert "Связь добавлена" in added.stdout

    listed = run_cli(tmp_path, "link", "list")
    assert "1 -> 2" in listed.stdout

    deleted = run_cli(tmp_path, "link", "delete", "1", "2")
    assert "Связь удалена" in deleted.stdout


def test_cli_convert_to_subtask_success(tmp_path):
    run_cli(tmp_path, "add", "Родитель")
    run_cli(tmp_path, "add", "Дочерняя")

    converted = run_cli(tmp_path, "convert-to-subtask", "2", "1")
    assert "преобразована в подзадачу" in converted.stdout

    listed = run_cli(tmp_path, "list")
    assert "#2" not in listed.stdout
