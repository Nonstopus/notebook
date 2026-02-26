from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, Optional, Set, Tuple

from .models import Task
from .services import tasks as task_service

from .storage import DB_NAME

DB_PATH = Path(DB_NAME)


class TaskApp:
    def __init__(self, root: tk.Tk, db_path: Path):
        self.root = root
        self.db_path = db_path
        task_service.init_db(db_path)
        self.root.title("Task Tracker Desktop")
        self.root.geometry("640x480")
        self._build_ui()
        self.refresh_tasks()
        self._schedule_reminder_check()

    def _build_ui(self) -> None:
        entry_frame = tk.Frame(self.root)
        entry_frame.pack(fill=tk.X, padx=10, pady=5)

        self.task_entry = tk.Entry(entry_frame)
        self.task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.task_entry.bind("<Return>", lambda _: self.add_task())

        add_btn = tk.Button(entry_frame, text="Добавить", command=self.add_task)
        add_btn.pack(side=tk.LEFT, padx=(5, 0))

        self.tasks_listbox = tk.Listbox(self.root)
        self.tasks_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(btn_frame, text="Открыть", command=self.open_task).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="Готово/Не готово", command=self.toggle_task).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Удалить", command=self.delete_task).pack(side=tk.LEFT)
        tk.Button(btn_frame, text="План", command=self.open_plan).pack(side=tk.RIGHT)

    def refresh_tasks(self) -> None:
        self.tasks_listbox.delete(0, tk.END)
        tasks = task_service.list_tasks(self.db_path)
        for task in tasks:
            progress = task_service.subtask_progress(self.db_path, task.id)
            reminder_flag = " ⏰" if task.reminder_datetime else ""
            prefix = "📁 " if progress[1] > 0 else ""
            label = (
                f"[{'✓' if task.is_done else ' '}] {prefix}{task.title}{reminder_flag} "
                f"({progress[0]}/{progress[1]}, subtasks: {progress[1]})"
            )
            self.tasks_listbox.insert(tk.END, label)
        self._tasks_cache = tasks

    def _selected_task(self) -> Optional[Task]:
        selection = self.tasks_listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        return self._tasks_cache[index]

    def add_task(self) -> None:
        title = self.task_entry.get().strip()
        if not title:
            messagebox.showinfo("Пустой заголовок", "Введите название задачи")
            return
        task_service.create_task(self.db_path, title=title)
        self.task_entry.delete(0, tk.END)
        self.refresh_tasks()

    def toggle_task(self) -> None:
        task = self._selected_task()
        if not task:
            messagebox.showinfo("Выберите задачу", "Выберите задачу для обновления")
            return
        updated = task_service.update_task(self.db_path, task.id, is_done=not task.is_done)
        if updated:
            self.refresh_tasks()

    def delete_task(self) -> None:
        task = self._selected_task()
        if not task:
            messagebox.showinfo("Выберите задачу", "Выберите задачу для удаления")
            return
        if messagebox.askyesno("Удалить задачу", f"Удалить '{task.title}'?"):
            task_service.delete_task(self.db_path, task.id)
            self.refresh_tasks()

    def open_task(self) -> None:
        task = self._selected_task()
        if not task:
            messagebox.showinfo("Выберите задачу", "Выберите задачу для просмотра")
            return
        TaskDetail(self, task)

    def open_plan(self) -> None:
        PlanWindow(self)

    def _schedule_reminder_check(self) -> None:
        self.root.after(10_000, self._check_reminders)

    def _check_reminders(self) -> None:
        now = datetime.utcnow()
        reminders = list(task_service.due_reminders(self.db_path, now=now))
        for task in reminders:
            messagebox.showinfo("Напоминание", f"Пора заняться: {task.title}")
            task_service.update_task(self.db_path, task.id, reminder_datetime=None)
        self._schedule_reminder_check()


class TaskDetail:
    def __init__(self, app: TaskApp, task: Task):
        self.app = app
        self.task = task
        self.window = tk.Toplevel(app.root)
        self.window.title(task.title)
        self._build_ui()
        self.refresh_subtasks()

    def _build_ui(self) -> None:
        tk.Label(self.window, text="Заголовок:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.title_entry = tk.Entry(self.window)
        self.title_entry.insert(0, self.task.title)
        self.title_entry.pack(fill=tk.X, padx=10)

        self.status_var = tk.BooleanVar(value=self.task.is_done)
        tk.Checkbutton(self.window, text="Задача выполнена", variable=self.status_var, command=self._on_status_change).pack(
            anchor=tk.W, padx=10, pady=5
        )

        reminder_frame = tk.Frame(self.window)
        reminder_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(reminder_frame, text="Напоминание (YYYY-MM-DD HH:MM):").pack(anchor=tk.W)
        self.reminder_entry = tk.Entry(reminder_frame)
        if self.task.reminder_datetime:
            self.reminder_entry.insert(0, self.task.reminder_datetime.strftime("%Y-%m-%d %H:%M"))
        self.reminder_entry.pack(fill=tk.X)
        tk.Button(reminder_frame, text="Сохранить напоминание", command=self.save_reminder).pack(side=tk.LEFT, pady=5)
        tk.Button(reminder_frame, text="Удалить", command=self.clear_reminder).pack(side=tk.LEFT, padx=5, pady=5)

        tk.Button(self.window, text="Сохранить заголовок", command=self.save_title).pack(anchor=tk.W, padx=10, pady=5)

        tk.Label(self.window, text="Подзадачи:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        self.subtask_list = tk.Listbox(self.window)
        self.subtask_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        subtask_controls = tk.Frame(self.window)
        subtask_controls.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(subtask_controls, text="Готово/Не готово", command=self.toggle_subtask).pack(side=tk.LEFT)
        tk.Button(subtask_controls, text="Удалить", command=self.delete_subtask).pack(side=tk.LEFT, padx=5)

        add_frame = tk.Frame(self.window)
        add_frame.pack(fill=tk.X, padx=10, pady=5)
        self.subtask_entry = tk.Entry(add_frame)
        self.subtask_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.subtask_entry.bind("<Return>", lambda _: self.add_subtask())
        tk.Button(add_frame, text="Добавить подзадачу", command=self.add_subtask).pack(side=tk.LEFT, padx=5)

        convert_frame = tk.LabelFrame(self.window, text="Сделать эту задачу подзадачей")
        convert_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        self.parent_task_var = tk.StringVar()
        self.parent_task_combobox = ttk.Combobox(convert_frame, textvariable=self.parent_task_var, state="readonly")
        self.parent_task_combobox.pack(fill=tk.X, padx=8, pady=(8, 6))
        tk.Button(convert_frame, text="Преобразовать в подзадачу", command=self.convert_to_subtask).pack(
            anchor=tk.E, padx=8, pady=(0, 8)
        )
        self._refresh_parent_options()

    def _refresh_parent_options(self) -> None:
        tasks = task_service.list_tasks(self.app.db_path)
        options = []
        self._parent_options: Dict[str, int] = {}
        for task in tasks:
            if task.id == self.task.id:
                continue
            option = f"#{task.id} {task.title}"
            options.append(option)
            self._parent_options[option] = task.id
        self.parent_task_combobox["values"] = options
        self.parent_task_var.set("")

    def refresh_subtasks(self) -> None:
        self.task = task_service.get_task(self.app.db_path, self.task.id) or self.task
        self.subtask_list.delete(0, tk.END)
        subtasks = task_service.list_subtasks(self.app.db_path, self.task.id)
        self._subtasks_cache = subtasks
        for st in subtasks:
            self.subtask_list.insert(tk.END, f"[{'✓' if st.is_done else ' '}] {st.title}")
        self._refresh_parent_options()
        self.app.refresh_tasks()

    def _on_status_change(self) -> None:
        task_service.update_task(self.app.db_path, self.task.id, is_done=self.status_var.get())
        self.refresh_subtasks()

    def save_title(self) -> None:
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showinfo("Пустой заголовок", "Введите название задачи")
            return
        task_service.update_task(self.app.db_path, self.task.id, title=title)
        self.window.title(title)
        self.refresh_subtasks()

    def save_reminder(self) -> None:
        text = self.reminder_entry.get().strip()
        if not text:
            messagebox.showinfo("Неверная дата", "Введите дату в формате YYYY-MM-DD HH:MM")
            return
        try:
            reminder = datetime.strptime(text, "%Y-%m-%d %H:%M")
        except ValueError:
            messagebox.showinfo("Неверный формат", "Используйте YYYY-MM-DD HH:MM")
            return
        task_service.update_task(self.app.db_path, self.task.id, reminder_datetime=reminder)
        self.refresh_subtasks()

    def clear_reminder(self) -> None:
        task_service.update_task(self.app.db_path, self.task.id, reminder_datetime=None)
        self.reminder_entry.delete(0, tk.END)
        self.refresh_subtasks()

    def _selected_subtask(self):
        selection = self.subtask_list.curselection()
        if not selection:
            return None
        return self._subtasks_cache[selection[0]]

    def add_subtask(self) -> None:
        title = self.subtask_entry.get().strip()
        if not title:
            return
        task_service.create_subtask(self.app.db_path, self.task.id, title)
        self.subtask_entry.delete(0, tk.END)
        self.refresh_subtasks()

    def toggle_subtask(self) -> None:
        subtask = self._selected_subtask()
        if not subtask:
            return
        task_service.update_subtask(self.app.db_path, subtask.id, is_done=not subtask.is_done)
        self.refresh_subtasks()

    def delete_subtask(self) -> None:
        subtask = self._selected_subtask()
        if not subtask:
            return
        task_service.delete_subtask(self.app.db_path, subtask.id)
        self.refresh_subtasks()

    def convert_to_subtask(self) -> None:
        selected_target = self.parent_task_var.get().strip()
        if not selected_target:
            messagebox.showinfo("Выберите цель", "Выберите задачу, в которую нужно перенести текущую задачу")
            return

        parent_task_id = self._parent_options.get(selected_target)
        if parent_task_id is None:
            messagebox.showinfo("Неверный выбор", "Выбранная задача недоступна. Обновите список и попробуйте снова")
            self._refresh_parent_options()
            return

        if parent_task_id == self.task.id:
            messagebox.showinfo("Неверный выбор", "Нельзя сделать задачу подзадачей самой себя")
            return

        converted = task_service.convert_task_to_subtask(self.app.db_path, self.task.id, parent_task_id)
        if not converted:
            messagebox.showinfo("Не удалось преобразовать", "Целевая задача не найдена или уже удалена")
            self._refresh_parent_options()
            return

        self.window.destroy()
        self.app.refresh_tasks()


class PlanWindow:
    NODE_WIDTH = 180
    NODE_HEIGHT = 70

    def __init__(self, app: TaskApp):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title("План")
        self._drag_task_id: Optional[int] = None
        self._drag_offset: Tuple[float, float] = (0.0, 0.0)
        self._highlighted_nodes: Set[int] = set()
        self._highlighted_links: Set[Tuple[int, int]] = set()
        self._build_ui()
        self.refresh_canvas()

    def _build_ui(self) -> None:
        controls = tk.Frame(self.window)
        controls.pack(fill=tk.X, padx=10, pady=8)

        tk.Label(controls, text="Источник:").pack(side=tk.LEFT)
        self.source_var = tk.StringVar()
        self.source_menu = tk.OptionMenu(controls, self.source_var, "")
        self.source_menu.pack(side=tk.LEFT, padx=(5, 10))

        tk.Label(controls, text="Цель:").pack(side=tk.LEFT)
        self.target_var = tk.StringVar()
        self.target_menu = tk.OptionMenu(controls, self.target_var, "")
        self.target_menu.pack(side=tk.LEFT, padx=(5, 10))

        tk.Button(controls, text="Связать", command=self.create_link).pack(side=tk.LEFT)

        tk.Label(controls, text="Связь:").pack(side=tk.LEFT, padx=(15, 0))
        self.link_var = tk.StringVar()
        self.link_menu = tk.OptionMenu(controls, self.link_var, "")
        self.link_menu.pack(side=tk.LEFT, padx=5)
        tk.Button(controls, text="Удалить связь", command=self.delete_link).pack(side=tk.LEFT)

        self.canvas = tk.Canvas(self.window, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish_drag)

    def refresh_canvas(self) -> None:
        self.tasks = task_service.list_tasks(self.app.db_path)
        self.links = task_service.list_task_links(self.app.db_path)
        layout = task_service.get_task_layouts(self.app.db_path)

        self.canvas.delete("all")
        self._nodes: Dict[int, Tuple[float, float]] = {}
        cols = 4
        x_step = self.NODE_WIDTH + 40
        y_step = self.NODE_HEIGHT + 35

        for index, task in enumerate(self.tasks):
            default_x = 60 + (index % cols) * x_step
            default_y = 60 + (index // cols) * y_step
            x, y = layout.get(task.id, (default_x, default_y))
            self._nodes[task.id] = (x, y)

        for source_id, target_id in self.links:
            if source_id not in self._nodes or target_id not in self._nodes:
                continue
            sx, sy = self._nodes[source_id]
            tx, ty = self._nodes[target_id]
            is_highlight = (source_id, target_id) in self._highlighted_links
            self.canvas.create_line(
                sx + self.NODE_WIDTH / 2,
                sy + self.NODE_HEIGHT / 2,
                tx + self.NODE_WIDTH / 2,
                ty + self.NODE_HEIGHT / 2,
                arrow=tk.LAST,
                width=3 if is_highlight else 1,
                fill="#0f766e" if is_highlight else "#6b7280",
            )

        for task in self.tasks:
            x, y = self._nodes[task.id]
            self._draw_task_node(task, x, y)

        self._refresh_controls()

    def _draw_task_node(self, task: Task, x: float, y: float) -> None:
        is_highlight = task.id in self._highlighted_nodes
        rect = self.canvas.create_rectangle(
            x,
            y,
            x + self.NODE_WIDTH,
            y + self.NODE_HEIGHT,
            fill="#d1fae5" if is_highlight else "#f3f4f6",
            outline="#0f766e" if is_highlight else "#9ca3af",
            width=2 if is_highlight else 1,
            tags=(f"task:{task.id}", "task-node"),
        )
        due_text = task.reminder_datetime.strftime("%Y-%m-%d %H:%M") if task.reminder_datetime else "—"
        txt = self.canvas.create_text(
            x + self.NODE_WIDTH / 2,
            y + self.NODE_HEIGHT / 2,
            text=f"{task.title}\nИсполнение: {due_text}",
            justify=tk.CENTER,
            tags=(f"task:{task.id}", "task-node"),
        )
        self.canvas.tag_raise(txt, rect)

    def _refresh_controls(self) -> None:
        self._task_label_to_id = {f"#{task.id} {task.title}": task.id for task in self.tasks}
        labels = list(self._task_label_to_id.keys()) or [""]
        self._rebuild_option_menu(self.source_menu, self.source_var, labels)
        self._rebuild_option_menu(self.target_menu, self.target_var, labels)

        link_labels = [f"{s} -> {t}" for s, t in self.links] or [""]
        self._rebuild_option_menu(self.link_menu, self.link_var, link_labels)

    def _rebuild_option_menu(self, menu: tk.OptionMenu, var: tk.StringVar, options: list[str]) -> None:
        internal = menu["menu"]
        internal.delete(0, "end")
        for opt in options:
            internal.add_command(label=opt, command=tk._setit(var, opt))
        var.set(options[0])

    def create_link(self) -> None:
        source = self._task_label_to_id.get(self.source_var.get())
        target = self._task_label_to_id.get(self.target_var.get())
        if source is None or target is None:
            return
        if not task_service.create_task_link(self.app.db_path, source, target):
            messagebox.showinfo("Нельзя связать", "Проверьте выбранные задачи (они не должны совпадать)")
        self._clear_highlight()
        self.refresh_canvas()

    def delete_link(self) -> None:
        raw = self.link_var.get()
        if "->" not in raw:
            return
        source_id, target_id = [int(part.strip()) for part in raw.split("->", maxsplit=1)]
        task_service.delete_task_link(self.app.db_path, source_id, target_id)
        self._clear_highlight()
        self.refresh_canvas()

    def _start_drag(self, event: tk.Event) -> None:
        task_id = self._task_id_at(event.x, event.y)
        if task_id is None:
            self._clear_highlight()
            self.refresh_canvas()
            return
        self._drag_task_id = task_id
        x, y = self._nodes[task_id]
        self._drag_offset = (event.x - x, event.y - y)
        self._set_highlight_chain(task_id)
        self.refresh_canvas()

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_task_id is None:
            return
        x = max(20, event.x - self._drag_offset[0])
        y = max(20, event.y - self._drag_offset[1])
        task_service.set_task_layout(self.app.db_path, self._drag_task_id, x, y)
        self.refresh_canvas()

    def _finish_drag(self, _event: tk.Event) -> None:
        self._drag_task_id = None

    def _task_id_at(self, x: float, y: float) -> Optional[int]:
        item = self.canvas.find_closest(x, y)
        if not item:
            return None
        for tag in self.canvas.gettags(item[0]):
            if tag.startswith("task:"):
                return int(tag.split(":", maxsplit=1)[1])
        return None

    def _set_highlight_chain(self, task_id: int) -> None:
        forward: Dict[int, Set[int]] = {}
        backward: Dict[int, Set[int]] = {}
        for source, target in self.links:
            forward.setdefault(source, set()).add(target)
            backward.setdefault(target, set()).add(source)

        visited_nodes: Set[int] = set()
        visited_links: Set[Tuple[int, int]] = set()

        stack = [task_id]
        while stack:
            node = stack.pop()
            if node in visited_nodes:
                continue
            visited_nodes.add(node)
            for nxt in forward.get(node, set()):
                visited_links.add((node, nxt))
                stack.append(nxt)
            for prev in backward.get(node, set()):
                visited_links.add((prev, node))
                stack.append(prev)

        self._highlighted_nodes = visited_nodes
        self._highlighted_links = visited_links

    def _clear_highlight(self) -> None:
        self._highlighted_nodes.clear()
        self._highlighted_links.clear()


def main() -> None:
    root = tk.Tk()
    TaskApp(root, DB_PATH)
    root.mainloop()


if __name__ == "__main__":
    main()
