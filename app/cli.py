from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from .models import ALLOWED_PRIORITIES
from .storage import DB_NAME
from .services import tasks as task_service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Консольный таск-трекер")
    parser.add_argument("--db", type=Path, default=Path(DB_NAME), help="Путь до SQLite базы")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Добавить задачу")
    add_parser.add_argument("title", help="Название задачи")
    add_parser.add_argument(
        "--due-datetime",
        help="Дедлайн в формате YYYY-MM-DD HH:MM",
    )
    add_parser.add_argument("--priority", choices=ALLOWED_PRIORITIES, default="medium", help="Приоритет")

    update_parser = subparsers.add_parser("update", help="Обновить задачу")
    update_parser.add_argument("task_id", type=int, help="ID задачи")
    update_parser.add_argument("--title", help="Новое название задачи")
    update_parser.add_argument("--priority", choices=ALLOWED_PRIORITIES, help="Приоритет")

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

    task_service.init_db(args.db)

    if args.command == "add":
        due_datetime = None
        if args.due_datetime:
            try:
                due_datetime = datetime.strptime(args.due_datetime, "%Y-%m-%d %H:%M")
            except ValueError:
                print("Неверный формат --due-datetime. Используйте YYYY-MM-DD HH:MM")
                return
        task = task_service.create_task(
            args.db,
            title=args.title,
            reminder_datetime=due_datetime,
            priority=args.priority,
        )
        print(f"Добавлено: #{task.id} {task.title}")
        return


    if args.command == "update":
        if args.title is None and args.priority is None:
            print("Укажите хотя бы один параметр: --title или --priority")
            return
        task = task_service.update_task(args.db, args.task_id, title=args.title, priority=args.priority)
        if not task:
            print(f"Задача #{args.task_id} не найдена")
            return
        print(f"Обновлено: #{task.id} {task.title}")
        return

    if args.command == "list":
        tasks = task_service.list_tasks(args.db, search=args.search)
        if not tasks:
            print("Ничего не найдено" if args.search else "Список задач пуст")
            return

        for task in tasks:
            mark = "x" if task.is_done else " "
            due_label = task.reminder_datetime.strftime("%Y-%m-%d %H:%M") if task.reminder_datetime else "-"
            print(f"[{mark}] #{task.id} {task.title} due_datetime={due_label}")
        return

    if args.command == "done":
        task = task_service.update_task(args.db, args.task_id, is_done=True)
        if not task:
            print(f"Задача #{args.task_id} не найдена")
            return
        print(f"Готово: #{task.id} {task.title}")
        return

    if args.command == "delete":
        deleted = task_service.delete_task(args.db, args.task_id)
        if not deleted:
            print(f"Задача #{args.task_id} не найдена")
            return
        print(f"Удалено: #{args.task_id}")
        return

    if args.command == "convert-to-subtask":
        try:
            subtask = task_service.convert_task_to_subtask(args.db, args.task_id, args.parent_task_id)
        except task_service.ConvertToSubtaskError as exc:
            print(str(exc))
            return
        if not subtask:
            print("Не удалось преобразовать задачу")
            return
        print(
            f"Задача #{args.task_id} преобразована в подзадачу #{subtask.id} для задачи #{args.parent_task_id}"
        )
        return

    if args.command == "link":
        if args.link_command == "add":
            created = task_service.create_task_link(args.db, args.from_id, args.to_id)
            if not created:
                print("Не удалось добавить связь")
                return
            print(f"Связь добавлена: {args.from_id} -> {args.to_id}")
            return

        if args.link_command == "list":
            links = task_service.list_task_links(args.db, task_id=args.task_id)
            if not links:
                print("Связи не найдены")
                return
            for source_task_id, target_task_id in links:
                print(f"{source_task_id} -> {target_task_id}")
            return

        if args.link_command == "delete":
            if args.from_id is None or args.to_id is None:
                print("Укажите пару from_id to_id")
                return
            deleted = task_service.delete_task_link(args.db, args.from_id, args.to_id)
            if not deleted:
                print("Связь не найдена")
                return
            print("Связь удалена")


if __name__ == "__main__":
    main()
