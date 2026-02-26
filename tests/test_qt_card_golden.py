import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

try:
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QImage, QPainter, QStandardItem, QStandardItemModel
    from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
except ImportError as exc:  # pragma: no cover - environment guard
    pytest.skip(f"PySide6 runtime unavailable: {exc}", allow_module_level=True)

from app.main_qt import (
    ROLE_DEADLINE,
    ROLE_DEADLINE_COLOR,
    ROLE_DONE,
    ROLE_META,
    ROLE_PRIORITY,
    ROLE_PROGRESS,
    ROLE_SUBTASKS,
    TaskCardDelegate,
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "task_card"
CURRENT_DIR = Path(__file__).parent / "artifacts" / "task_card"
UPDATE_GOLDENS = os.getenv("UPDATE_QT_GOLDENS", "0") == "1"


@pytest.fixture(scope="module")
def app_instance():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _render_task_card(case_name: str, width: int, *, deadline: str, subtasks: int, priority: str) -> Path:
    model = QStandardItemModel(1, 1)
    item = QStandardItem("Задача для визуального теста")
    item.setData("Тестовый проект", ROLE_META)
    item.setData(45, ROLE_PROGRESS)
    item.setData(deadline, ROLE_DEADLINE)
    item.setData(subtasks, ROLE_SUBTASKS)
    item.setData(False, ROLE_DONE)
    item.setData(priority, ROLE_PRIORITY)
    item.setData("#1F2933", ROLE_DEADLINE_COLOR)
    model.setItem(0, 0, item)

    index = model.index(0, 0)
    delegate = TaskCardDelegate()

    image = QImage(width, 110, QImage.Format.Format_ARGB32)
    image.fill(0xFFFFFFFF)

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, width, 110)

    painter = QPainter(image)
    delegate.paint(painter, option, index)
    painter.end()

    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    actual_path = CURRENT_DIR / f"{case_name}.png"
    image.save(str(actual_path))
    return actual_path


def _assert_matches_golden(case_name: str, actual_path: Path) -> None:
    golden_path = GOLDEN_DIR / f"{case_name}.png"
    if UPDATE_GOLDENS or not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_bytes(actual_path.read_bytes())
        pytest.skip(f"Golden updated for {case_name}")

    assert actual_path.read_bytes() == golden_path.read_bytes(), (
        f"Visual mismatch for {case_name}. "
        f"Inspect artifact: {actual_path} against baseline: {golden_path}"
    )


@pytest.mark.parametrize(
    ("case_name", "width", "deadline", "subtasks", "priority"),
    [
        ("short_values", 520, "сегодня", 1, "Низкий"),
        ("medium_values", 420, "через 3 дня", 12, "Средний"),
        (
            "long_values",
            360,
            "очень длинный срок выполнения до конца следующего месяца",
            128,
            "Критический приоритет с дополнительным описанием",
        ),
    ],
)
def test_task_card_meta_fields_golden(case_name, width, deadline, subtasks, priority, app_instance):
    del app_instance
    actual_path = _render_task_card(
        case_name,
        width,
        deadline=deadline,
        subtasks=subtasks,
        priority=priority,
    )

    _assert_matches_golden(case_name, actual_path)


def test_task_card_bug_case_narrow_width_golden(app_instance):
    del app_instance
    actual_path = _render_task_card(
        "bug_subtasks_zero_low_priority_narrow",
        280,
        deadline="до 15:00",
        subtasks=0,
        priority="Низкий",
    )

    _assert_matches_golden("bug_subtasks_zero_low_priority_narrow", actual_path)
