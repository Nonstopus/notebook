from __future__ import annotations

import argparse
from pathlib import Path

from . import storage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Консольный таск-трекер")
    parser.add_argument("--db", type=Path, default=Path(storage.DB_NAME), help="Путь до SQLite базы")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Добавить задачу")
    add_parser.add_argument("title", help="Название задачи")

    list_parser = subparsers.add_parser("list", help="Показать все задачи")
    list_parser.add_argument("--search", help="Строка для поиска по заголовку и заметке")

    done_parser = subparsers.add_parser("done", help="Пометить задачу как выполненную")
    done_parser.add_argument("task_id", type=int, help="ID задачи")

    delete_parser = subparsers.add_parser("delete", help="Удалить задачу")
    delete_parser.add_argument("task_id", type=int, help="ID задачи")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    storage.init_db(args.db)

    if args.command == "add":
        task = storage.create_task(args.db, title=args.title)
        print(f"Добавлено: #{task.id} {task.title}")
        return

    if args.command == "list":
        tasks = storage.list_tasks(args.db, search=args.search)
        if not tasks:
            print("Ничего не найдено" if args.search else "Список задач пуст")
            return

        for task in tasks:
            mark = "x" if task.is_done else " "
            print(f"[{mark}] #{task.id} {task.title}")
        return

    if args.command == "done":
        task = storage.update_task(args.db, args.task_id, is_done=True)
        if not task:
            print(f"Задача #{args.task_id} не найдена")
            return
        print(f"Готово: #{task.id} {task.title}")
        return

    if args.command == "delete":
        deleted = storage.delete_task(args.db, args.task_id)
        if not deleted:
            print(f"Задача #{args.task_id} не найдена")
            return
        print(f"Удалено: #{args.task_id}")


if __name__ == "__main__":
    main()
