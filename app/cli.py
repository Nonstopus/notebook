from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from . import storage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Консольный таск-трекер")
    parser.add_argument("--db", type=Path, default=Path(storage.DB_NAME), help="Путь до SQLite базы")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Добавить задачу")
    add_parser.add_argument("title", help="Название задачи")
    add_parser.add_argument(
        "--due-datetime",
        help="Дедлайн в формате YYYY-MM-DD HH:MM",
    )

    list_parser = subparsers.add_parser("list", help="Показать все задачи")
    list_parser.add_argument("--search", help="Строка для поиска по заголовку и заметке")

    done_parser = subparsers.add_parser("done", help="Пометить задачу как выполненную")
    done_parser.add_argument("task_id", type=int, help="ID задачи")

    delete_parser = subparsers.add_parser("delete", help="Удалить задачу")
    delete_parser.add_argument("task_id", type=int, help="ID задачи")

    convert_parser = subparsers.add_parser(
        "convert-to-subtask",
        help="Сделать задачу подзадачей другой задачи",
    )
    convert_parser.add_argument("task_id", type=int, help="ID преобразуемой задачи")
    convert_parser.add_argument("parent_task_id", type=int, help="ID родительской задачи")

    link_parser = subparsers.add_parser("link", help="Управление связями между задачами")
    link_subparsers = link_parser.add_subparsers(dest="link_command", required=True)

    link_add_parser = link_subparsers.add_parser("add", help="Добавить связь from -> to")
    link_add_parser.add_argument("from_id", type=int, help="ID исходной задачи")
    link_add_parser.add_argument("to_id", type=int, help="ID целевой задачи")

    link_list_parser = link_subparsers.add_parser("list", help="Показать связи")
    link_list_parser.add_argument("--task-id", type=int, help="Показывать связи конкретной задачи")

    link_delete_parser = link_subparsers.add_parser("delete", help="Удалить связь")
    link_delete_parser.add_argument("from_id", type=int, nargs="?", help="ID исходной задачи")
    link_delete_parser.add_argument("to_id", type=int, nargs="?", help="ID целевой задачи")
    link_delete_parser.add_argument("--link-id", type=int, help="ID связи для удаления")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    storage.init_db(args.db)

    if args.command == "add":
        due_datetime = None
        if args.due_datetime:
            try:
                due_datetime = datetime.strptime(args.due_datetime, "%Y-%m-%d %H:%M")
            except ValueError:
                print("Неверный формат --due-datetime. Используйте YYYY-MM-DD HH:MM")
                return
        task = storage.create_task(args.db, title=args.title, reminder_datetime=due_datetime)
        print(f"Добавлено: #{task.id} {task.title}")
        return

    if args.command == "list":
        tasks = storage.list_tasks(args.db, search=args.search)
        if not tasks:
            print("Ничего не найдено" if args.search else "Список задач пуст")
            return

        for task in tasks:
            mark = "x" if task.is_done else " "
            due_label = task.reminder_datetime.strftime("%Y-%m-%d %H:%M") if task.reminder_datetime else "-"
            print(f"[{mark}] #{task.id} {task.title} due_datetime={due_label}")
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
        return

    if args.command == "convert-to-subtask":
        try:
            subtask = storage.convert_task_to_subtask(args.db, args.task_id, args.parent_task_id)
        except ValueError:
            print("Нельзя сделать задачу подзадачей самой себя")
            return
        if not subtask:
            print("Задача не найдена")
            return
        print(
            f"Задача #{args.task_id} преобразована в подзадачу #{subtask.id} для задачи #{args.parent_task_id}"
        )
        return

    if args.command == "link":
        if args.link_command == "add":
            try:
                link = storage.create_task_link(args.db, args.from_id, args.to_id)
            except ValueError as exc:
                print(str(exc))
                return
            print(f"Связь добавлена: #{link.id} {link.from_task_id} -> {link.to_task_id}")
            return

        if args.link_command == "list":
            links = storage.list_task_links(args.db, task_id=args.task_id)
            if not links:
                print("Связи не найдены")
                return
            for link in links:
                print(f"#{link.id}: {link.from_task_id} -> {link.to_task_id}")
            return

        if args.link_command == "delete":
            if args.link_id is None and (args.from_id is None or args.to_id is None):
                print("Укажите --link-id или пару from_id to_id")
                return
            try:
                deleted = storage.delete_task_link(
                    args.db,
                    from_task_id=args.from_id,
                    to_task_id=args.to_id,
                    link_id=args.link_id,
                )
            except ValueError as exc:
                print(str(exc))
                return
            if not deleted:
                print("Связь не найдена")
                return
            print("Связь удалена")


if __name__ == "__main__":
    main()
