from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from . import storage
from .models import Task

DB_PATH = Path(storage.DB_NAME)


class TaskApp:
    def __init__(self, root: tk.Tk, db_path: Path):
        self.root = root
        self.db_path = db_path
        storage.init_db(db_path)
        self.root.title("Task Tracker Desktop")
        self.root.geometry("760x560")
        self.root.configure(bg="#0f172a")
        self._apply_theme()
        self._build_ui()
        self.refresh_tasks()
        self._schedule_reminder_check()

    def _apply_theme(self) -> None:
        accent = "#2563eb"
        surface = "#1e293b"
        text_muted = "#cbd5e1"
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=surface)
        style.configure("App.TLabel", background=surface, foreground=text_muted, font=("Inter", 10))
        style.configure("App.Heading.TLabel", background=surface, foreground="white", font=("Inter", 12, "bold"))
        style.configure(
            "Primary.TButton",
            background=accent,
            foreground="white",
            padding=(12, 8),
            font=("Inter", 10, "bold"),
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "Primary.TButton",
            background=[("active", "#1d4ed8"), ("disabled", "#475569")],
            foreground=[("disabled", "#94a3b8")],
        )
        style.configure(
            "Secondary.TButton",
            background="#334155",
            foreground=text_muted,
            padding=(10, 6),
            font=("Inter", 10),
            relief="flat",
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#1f2937")],
            foreground=[("active", "white")],
        )
        style.configure(
            "Modern.Treeview",
            background=surface,
            fieldbackground=surface,
            foreground="white",
            bordercolor=surface,
            rowheight=30,
            font=("Inter", 10),
        )
        style.configure("Modern.Treeview.Heading", background=surface, foreground=text_muted, font=("Inter", 10, "bold"))
        style.map("Treeview", background=[("selected", "#1d4ed8")], foreground=[("selected", "white")])
        style.configure(
            "App.TCheckbutton",
            background=surface,
            foreground=text_muted,
            font=("Inter", 10),
            focuscolor=surface,
        )

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        header = ttk.Label(container, text="Задачи", style="App.Heading.TLabel")
        header.pack(anchor=tk.W)

        entry_frame = ttk.Frame(container, style="App.TFrame")
        entry_frame.pack(fill=tk.X, pady=(12, 10))

        self.task_entry = ttk.Entry(entry_frame, font=("Inter", 11))
        self.task_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.task_entry.bind("<Return>", lambda _: self.add_task())

        add_btn = ttk.Button(entry_frame, text="Добавить", command=self.add_task, style="Primary.TButton")
        add_btn.pack(side=tk.LEFT, padx=(8, 0))

        list_frame = ttk.Frame(container, style="App.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("title", "status", "reminder", "progress")
        self.tasks_tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            style="Modern.Treeview",
            selectmode="browse",
        )
        self.tasks_tree.heading("title", text="Задача")
        self.tasks_tree.heading("status", text="Статус")
        self.tasks_tree.heading("reminder", text="Напоминание")
        self.tasks_tree.heading("progress", text="Подзадачи")
        self.tasks_tree.column("title", width=320, anchor=tk.W)
        self.tasks_tree.column("status", width=100, anchor=tk.CENTER)
        self.tasks_tree.column("reminder", width=140, anchor=tk.CENTER)
        self.tasks_tree.column("progress", width=120, anchor=tk.CENTER)
        self.tasks_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        self.tasks_tree.bind("<Double-1>", lambda _: self.open_task())

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tasks_tree.yview)
        self.tasks_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(container, style="App.TFrame")
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Открыть", command=self.open_task, style="Secondary.TButton").pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Готово/Не готово", command=self.toggle_task, style="Secondary.TButton").pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(btn_frame, text="Удалить", command=self.delete_task, style="Secondary.TButton").pack(side=tk.LEFT)

    def refresh_tasks(self) -> None:
        self.tasks_tree.delete(*self.tasks_tree.get_children())
        tasks = storage.list_tasks(self.db_path)
        self._tasks_cache = {task.id: task for task in tasks}
        for task in tasks:
            progress = storage.subtask_progress(self.db_path, task.id)
            reminder_text = task.reminder_datetime.strftime("%d %b %H:%M") if task.reminder_datetime else "—"
            status_text = "Готово" if task.is_done else "В работе"
            self.tasks_tree.insert(
                "",
                tk.END,
                iid=str(task.id),
                values=(task.title, status_text, reminder_text, f"{progress[0]} / {progress[1]}")
            )

    def _selected_task(self) -> Optional[Task]:
        selection = self.tasks_tree.selection()
        if not selection:
            return None
        task_id = int(selection[0])
        return self._tasks_cache.get(task_id)

    def add_task(self) -> None:
        title = self.task_entry.get().strip()
        if not title:
            messagebox.showinfo("Пустой заголовок", "Введите название задачи")
            return
        storage.create_task(self.db_path, title=title)
        self.task_entry.delete(0, tk.END)
        self.refresh_tasks()

    def toggle_task(self) -> None:
        task = self._selected_task()
        if not task:
            messagebox.showinfo("Выберите задачу", "Выберите задачу для обновления")
            return
        updated = storage.update_task(self.db_path, task.id, is_done=not task.is_done)
        if updated:
            self.refresh_tasks()

    def delete_task(self) -> None:
        task = self._selected_task()
        if not task:
            messagebox.showinfo("Выберите задачу", "Выберите задачу для удаления")
            return
        if messagebox.askyesno("Удалить задачу", f"Удалить '{task.title}'?"):
            storage.delete_task(self.db_path, task.id)
            self.refresh_tasks()

    def open_task(self) -> None:
        task = self._selected_task()
        if not task:
            messagebox.showinfo("Выберите задачу", "Выберите задачу для просмотра")
            return
        TaskDetail(self, task)

    def _schedule_reminder_check(self) -> None:
        self.root.after(10_000, self._check_reminders)

    def _check_reminders(self) -> None:
        now = datetime.utcnow()
        reminders = list(storage.due_reminders(self.db_path, now=now))
        for task in reminders:
            messagebox.showinfo("Напоминание", f"Пора заняться: {task.title}")
            storage.update_task(self.db_path, task.id, reminder_datetime=None)
        self._schedule_reminder_check()


class TaskDetail:
    def __init__(self, app: TaskApp, task: Task):
        self.app = app
        self.task = task
        self.window = tk.Toplevel(app.root, bg="#0f172a")
        self.window.title(task.title)
        self._build_ui()
        self.refresh_subtasks()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.window, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        ttk.Label(container, text="Заголовок", style="App.Heading.TLabel").pack(anchor=tk.W)
        self.title_entry = ttk.Entry(container, font=("Inter", 11))
        self.title_entry.insert(0, self.task.title)
        self.title_entry.pack(fill=tk.X, pady=(4, 10))

        self.status_var = tk.BooleanVar(value=self.task.is_done)
        ttk.Checkbutton(
            container,
            text="Задача выполнена",
            variable=self.status_var,
            command=self._on_status_change,
            style="App.TCheckbutton",
        ).pack(anchor=tk.W, pady=(0, 12))

        reminder_frame = ttk.Frame(container, style="App.TFrame")
        reminder_frame.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(reminder_frame, text="Напоминание (YYYY-MM-DD HH:MM)", style="App.TLabel").pack(anchor=tk.W)
        self.reminder_entry = ttk.Entry(reminder_frame, font=("Inter", 11))
        if self.task.reminder_datetime:
            self.reminder_entry.insert(0, self.task.reminder_datetime.strftime("%Y-%m-%d %H:%M"))
        self.reminder_entry.pack(fill=tk.X, pady=4)

        reminder_buttons = ttk.Frame(reminder_frame, style="App.TFrame")
        reminder_buttons.pack(anchor=tk.W)
        ttk.Button(reminder_buttons, text="Сохранить", command=self.save_reminder, style="Primary.TButton").pack(side=tk.LEFT)
        ttk.Button(reminder_buttons, text="Удалить", command=self.clear_reminder, style="Secondary.TButton").pack(
            side=tk.LEFT, padx=8
        )

        ttk.Button(container, text="Сохранить заголовок", command=self.save_title, style="Secondary.TButton").pack(
            anchor=tk.W, pady=(0, 14)
        )

        ttk.Label(container, text="Подзадачи", style="App.Heading.TLabel").pack(anchor=tk.W)
        self.subtask_list = tk.Listbox(container, height=8, bg="#0f172a", fg="white", selectbackground="#1d4ed8")
        self.subtask_list.pack(fill=tk.BOTH, expand=True, pady=(6, 8))

        subtask_controls = ttk.Frame(container, style="App.TFrame")
        subtask_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(subtask_controls, text="Готово/Не готово", command=self.toggle_subtask, style="Secondary.TButton").pack(
            side=tk.LEFT
        )
        ttk.Button(subtask_controls, text="Удалить", command=self.delete_subtask, style="Secondary.TButton").pack(
            side=tk.LEFT, padx=8
        )

        add_frame = ttk.Frame(container, style="App.TFrame")
        add_frame.pack(fill=tk.X)
        self.subtask_entry = ttk.Entry(add_frame, font=("Inter", 11))
        self.subtask_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.subtask_entry.bind("<Return>", lambda _: self.add_subtask())
        ttk.Button(add_frame, text="Добавить подзадачу", command=self.add_subtask, style="Primary.TButton").pack(
            side=tk.LEFT, padx=8
        )

    def refresh_subtasks(self) -> None:
        self.task = storage.get_task(self.app.db_path, self.task.id) or self.task
        self.subtask_list.delete(0, tk.END)
        subtasks = storage.list_subtasks(self.app.db_path, self.task.id)
        self._subtasks_cache = subtasks
        for st in subtasks:
            self.subtask_list.insert(tk.END, f"[{'✓' if st.is_done else ' '}] {st.title}")
        self.app.refresh_tasks()

    def _on_status_change(self) -> None:
        storage.update_task(self.app.db_path, self.task.id, is_done=self.status_var.get())
        self.refresh_subtasks()

    def save_title(self) -> None:
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showinfo("Пустой заголовок", "Введите название задачи")
            return
        storage.update_task(self.app.db_path, self.task.id, title=title)
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
        storage.update_task(self.app.db_path, self.task.id, reminder_datetime=reminder)
        self.refresh_subtasks()

    def clear_reminder(self) -> None:
        storage.update_task(self.app.db_path, self.task.id, reminder_datetime=None)
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
        storage.create_subtask(self.app.db_path, self.task.id, title)
        self.subtask_entry.delete(0, tk.END)
        self.refresh_subtasks()

    def toggle_subtask(self) -> None:
        subtask = self._selected_subtask()
        if not subtask:
            return
        storage.update_subtask(self.app.db_path, subtask.id, is_done=not subtask.is_done)
        self.refresh_subtasks()

    def delete_subtask(self) -> None:
        subtask = self._selected_subtask()
        if not subtask:
            return
        storage.delete_subtask(self.app.db_path, subtask.id)
        self.refresh_subtasks()


def main() -> None:
    root = tk.Tk()
    TaskApp(root, DB_PATH)
    root.mainloop()


if __name__ == "__main__":
    main()
