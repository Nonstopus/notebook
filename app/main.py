from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
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

    def refresh_tasks(self) -> None:
        self.tasks_listbox.delete(0, tk.END)
        tasks = storage.list_tasks(self.db_path)
        for task in tasks:
            progress = storage.subtask_progress(self.db_path, task.id)
            reminder_flag = " ⏰" if task.reminder_datetime else ""
            label = f"[{'✓' if task.is_done else ' '}] {task.title}{reminder_flag} ({progress[0]}/{progress[1]})"
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
