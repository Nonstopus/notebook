import subprocess
import sys
from pathlib import Path


def run_cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    db_path = tmp_path / "cli.db"
    command = [sys.executable, "-m", "app.cli", "--db", str(db_path), *args]
    return subprocess.run(command, check=True, capture_output=True, text=True)


def test_cli_add_and_list(tmp_path):
    run_cli(tmp_path, "add", "Купить молоко")
    result = run_cli(tmp_path, "list")
    assert "Купить молоко" in result.stdout


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
