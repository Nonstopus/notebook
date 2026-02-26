import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

try:
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError as exc:  # pragma: no cover - environment guard
    pytest.skip(f"PySide6 runtime unavailable: {exc}", allow_module_level=True)

from app.main_qt import (
    ROLE_BADGES,
    ROLE_PROGRESS,
    ROLE_SUBTASKS,
    SELECTED_TEXT_CONTRAST,
    GraphEdgeItem,
    TaskCardDelegate,
    TaskGraphDialog,
    TaskQtWindow,
)
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


def test_qt_task_card_flow_edit_toggle_delete(app_instance, tmp_path, monkeypatch):
    db_path = Path(tmp_path / "qt.db")
    created = tasks.create_task(db_path, "Черновик")

    window = TaskQtWindow(db_path)
    window.show()
    app_instance.processEvents()

    window._select_task_in_tree(created.id)
    app_instance.processEvents()

    window.title_input.setText("Финальный заголовок")
    window.save_card_btn.click()
    app_instance.processEvents()

    renamed = tasks.get_task(db_path, created.id)
    assert renamed is not None
    assert renamed.title == "Финальный заголовок"

    window.complete_btn.click()
    app_instance.processEvents()
    toggled_done = tasks.get_task(db_path, created.id)
    assert toggled_done is not None
    assert toggled_done.is_done is True

    window.complete_btn.click()
    app_instance.processEvents()
    toggled_back = tasks.get_task(db_path, created.id)
    assert toggled_back is not None
    assert toggled_back.is_done is False

    monkeypatch.setattr("app.main_qt.QMessageBox.question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    window.delete_btn.click()
    app_instance.processEvents()

    assert tasks.get_task(db_path, created.id) is None
    assert window.tasks_list.topLevelItemCount() == 0

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
    assert window.tasks_list.topLevelItem(0).data(0, ROLE_PROGRESS) == 0
    assert window.tasks_list.topLevelItem(0).data(0, ROLE_SUBTASKS) == 1

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

    badges = window.tasks_list.topLevelItem(0).data(0, ROLE_BADGES)
    assert any(badge[0] == "🧩" for badge in badges)

    window.close()


def test_qt_main_entrypoint_smoke(monkeypatch, app_instance, tmp_path):
    from app import main_qt

    monkeypatch.setattr(main_qt, "DB_PATH", Path(tmp_path / "entrypoint.db"))
    monkeypatch.setattr(main_qt, "QApplication", lambda argv: app_instance)
    monkeypatch.setattr("app.ui_qt.main_window.MainWindow.show", lambda self: None)
    monkeypatch.setattr(app_instance, "exec", lambda: 0)

    tasks.create_task(main_qt.DB_PATH, "Из entrypoint")

    result = main_qt.main()

    assert result == 0


def test_qt_selected_row_text_contrast_smoke(app_instance, tmp_path):
    db_path = Path(tmp_path / "qt.db")
    tasks.create_task(db_path, "Контраст")

    window = TaskQtWindow(db_path)
    window.show()
    app_instance.processEvents()

    assert window.tasks_list.styleSheet()
    assert SELECTED_TEXT_CONTRAST >= 4.5

    window.tasks_list.setCurrentItem(window.tasks_list.topLevelItem(0))
    app_instance.processEvents()
    assert window.tasks_list.currentItem() is not None

    window.close()


@pytest.mark.parametrize(
    ("width", "expect_wrapped"),
    [
        (280, True),
        (320, True),
        (480, False),
    ],
)
def test_task_meta_layout_breakpoints(width, expect_wrapped):
    delegate = TaskCardDelegate()
    rects = delegate._meta_section_rects(QRectF(0, 0, width, 30))

    assert len(rects) == 3
    if expect_wrapped:
        assert rects[0].top() == rects[1].top()
        assert rects[2].top() > rects[0].top()
        assert rects[2].width() == pytest.approx(width)
    else:
        assert rects[0].top() == rects[1].top() == rects[2].top()


def test_main_window_restores_active_tab(app_instance, tmp_path):
    from PySide6.QtCore import QSettings

    from app.ui_qt.main_window import MainWindow

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))

    db_path = Path(tmp_path / "qt.db")
    tasks.create_task(db_path, "Tab test")

    first = MainWindow(db_path)
    first.tabs.setCurrentIndex(1)
    first.close()

    second = MainWindow(db_path)
    assert second.tabs.currentIndex() == 1
    second.close()


def test_graph_dialog_renders_only_task_dependencies(app_instance, tmp_path):
    db_path = Path(tmp_path / "qt_graph.db")
    first = tasks.create_task(db_path, "Первая")
    second = tasks.create_task(db_path, "Вторая")
    tasks.create_subtask(db_path, first.id, "Подзадача")
    tasks.create_task_link(db_path, first.id, second.id)

    dialog = TaskGraphDialog(db_path)
    dialog.refresh_graph(force=True)

    edges = [item for item in dialog.scene.items() if isinstance(item, GraphEdgeItem)]
    assert len(dialog._node_items) == 2
    assert edges
    assert all(edge.relation_type == "dependency" for edge in edges)

    dialog.close()


def test_graph_dialog_cycle_warning_and_toggle(app_instance, tmp_path):
    db_path = Path(tmp_path / "qt_graph_cycle.db")
    first = tasks.create_task(db_path, "A")
    second = tasks.create_task(db_path, "B")
    tasks.create_task_link(db_path, first.id, second.id)
    tasks.create_task_link(db_path, second.id, first.id, prevent_cycles=False)

    dialog = TaskGraphDialog(db_path)
    dialog.refresh_graph(force=True)

    assert "Найдены циклы" in dialog.warning_label.text()
    edges = [item for item in dialog.scene.items() if isinstance(item, GraphEdgeItem)]
    assert any(edge.relation_type == "cyclic_dependency" for edge in edges)

    dialog.cycle_mode.setChecked(False)
    dialog.refresh_graph(force=True)
    edges = [item for item in dialog.scene.items() if isinstance(item, GraphEdgeItem)]
    assert all(edge.relation_type != "cyclic_dependency" for edge in edges)

    dialog.close()




def test_graph_dialog_layout_is_stable(app_instance, tmp_path):
    db_path = Path(tmp_path / "qt_graph_layout.db")
    a = tasks.create_task(db_path, "A")
    b = tasks.create_task(db_path, "B")
    c = tasks.create_task(db_path, "C")
    tasks.create_task_link(db_path, a.id, b.id)
    tasks.create_task_link(db_path, b.id, c.id)

    dialog = TaskGraphDialog(db_path)
    dialog.refresh_graph(force=True)
    first_positions = {
        node_id: (item.scenePos().x(), item.scenePos().y())
        for node_id, item in dialog._node_items.items()
    }

    dialog.refresh_graph(force=True)
    second_positions = {
        node_id: (item.scenePos().x(), item.scenePos().y())
        for node_id, item in dialog._node_items.items()
    }

    assert first_positions == second_positions
    dialog.close()


def test_graph_dialog_uses_rectangular_nodes(app_instance, tmp_path):
    db_path = Path(tmp_path / "qt_graph_nodes.db")
    task = tasks.create_task(db_path, "Карточка")
    tasks.create_subtask(db_path, task.id, "sub")

    dialog = TaskGraphDialog(db_path)
    dialog.refresh_graph(force=True)

    assert len(dialog._node_items) == 1
    node = next(iter(dialog._node_items.values()))
    assert node.rect().width() > node.rect().height()

    dialog.close()
def test_note_toolbar_scoped_to_note_editor(app_instance, tmp_path):
    db_path = Path(tmp_path / "qt.db")
    created = tasks.create_task(db_path, "Фокус")

    window = TaskQtWindow(db_path)
    window.show()
    app_instance.processEvents()
    window._select_task_in_tree(created.id)
    app_instance.processEvents()

    assert not window.note_toolbar.isEnabled()

    window.note_input.setFocus()
    app_instance.processEvents()
    assert window.note_toolbar.isEnabled()

    window.note_input.setPlainText("тест")
    window.note_input.selectAll()
    bold_action = next(action for action in window.note_toolbar.actions() if action.text() == "Ж")
    bold_action.trigger()
    app_instance.processEvents()

    assert "font-weight" in window.note_input.toHtml().lower()
    assert window.title_input.text() == "Фокус"

    window.title_input.setFocus()
    app_instance.processEvents()
    assert not window.note_toolbar.isEnabled()

    window.note_input.setReadOnly(True)
    window.note_input.setFocus()
    app_instance.processEvents()
    window._update_note_toolbar_state()
    assert not window.note_toolbar.isEnabled()

    window.close()
