from __future__ import annotations

import argparse
import json
import sys

from .agent_bridge import apply_task_update, list_tasks
from .config import (
    DASHBOARD_FILE,
    DIGESTS_DIR,
    TASKS_DIR,
    ensure_config,
    load_settings,
)
from .credentials import configure_interactively
from .digest import generate_digest
from .doctor import run_doctor
from .exporter import export_dashboard, import_checked_states
from .logging_setup import configure_logging
from .markdown_store import MarkdownTaskStore
from .research import pending_requests
from .progress import export_progress
from .scanner import scan_once
from .scheduler import run_forever
from .ui_app import run_ui, show_existing_window


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobmaildesk")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("configure", help="配置 IMAP 凭据和本地配置")
    doctor = subparsers.add_parser("doctor", help="检查本地环境")
    doctor.add_argument("--offline", action="store_true")
    scan = subparsers.add_parser("scan", help="扫描邮件")
    scan.add_argument("--once", action="store_true")
    scan.add_argument("--days", type=int)
    scan.add_argument("--shadow", action="store_true")
    subparsers.add_parser("run", help="运行后台调度器")
    digest = subparsers.add_parser("digest", help="生成简报")
    digest.add_argument("period", choices=("morning", "noon", "evening"))
    export = subparsers.add_parser("export", help="导出 Markdown 总览")
    export.add_argument("--obsidian", action="store_true")
    subparsers.add_parser("research-queue", help="查看待处理研究请求")
    task_list = subparsers.add_parser(
        "task-list",
        help="为本地 Agent 列出可更新任务及稳定 ID",
    )
    task_list.add_argument("--company", default="")
    task_list.add_argument("--role", default="")
    task_list.add_argument("--stage", default="")
    task_list.add_argument("--include-irrelevant", action="store_true")
    task_update = subparsers.add_parser(
        "task-update",
        help="按稳定 ID 更新任务并同步 Markdown、进展和 Obsidian",
    )
    task_update.add_argument("task_id")
    task_update.add_argument(
        "--status",
        choices=(
            "needs_review",
            "confirmed",
            "planned",
            "done",
            "cancelled",
            "irrelevant",
        ),
    )
    task_update.add_argument("--start-at")
    task_update.add_argument("--end-at")
    task_update.add_argument("--deadline-at")
    task_update.add_argument("--company")
    task_update.add_argument("--role")
    task_update.add_argument("--stage")
    task_update.add_argument("--round")
    task_update.add_argument("--action-summary")
    task_update.add_argument("--manual-notes")
    subparsers.add_parser("ui", help="启动桌面组件")
    subparsers.add_parser("show", help="显示现有桌面组件；未运行时启动")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    if argv is None and getattr(sys, "frozen", False) and len(sys.argv) == 1:
        argv = ["ui"]
    args = _parser().parse_args(argv)
    ensure_config()
    settings = load_settings()
    if args.command == "configure":
        configure_interactively()
        print("配置完成。请运行 jobmaildesk doctor 验证。")
        return 0
    if args.command == "doctor":
        checks = run_doctor(settings, online=not args.offline)
        for check in checks:
            print(f"{'OK' if check.ok else 'FAIL'}  {check.name}: {check.detail}")
        return 0 if all(check.ok for check in checks) else 1
    if args.command == "scan":
        summary = scan_once(settings, days=args.days, shadow=args.shadow)
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        run_forever(settings)
        return 0
    if args.command == "digest":
        path = generate_digest(
            args.period,
            MarkdownTaskStore(TASKS_DIR),
            DIGESTS_DIR,
        )
        print(path)
        return 0
    if args.command == "export":
        store = MarkdownTaskStore(TASKS_DIR)
        target = settings.obsidian_output if args.obsidian else DASHBOARD_FILE
        if args.obsidian:
            import_checked_states(target, store)
        export_dashboard(store.all(), target, settings)
        if settings.progress_enabled:
            export_progress(
                store.all(),
                settings.progress_output,
                source_path=settings.progress_source,
            )
        print(target)
        return 0
    if args.command == "research-queue":
        print(
            json.dumps(
                pending_requests(settings.research_queue),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "task-list":
        print(
            json.dumps(
                list_tasks(
                    company=args.company,
                    role=args.role,
                    stage=args.stage,
                    include_irrelevant=args.include_irrelevant,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "task-update":
        changes = {
            key: value
            for key, value in {
                "status": args.status,
                "start_at": args.start_at,
                "end_at": args.end_at,
                "deadline_at": args.deadline_at,
                "company": args.company,
                "role": args.role,
                "stage": args.stage,
                "round": args.round,
                "action_summary": args.action_summary,
                "manual_notes": args.manual_notes,
            }.items()
            if value is not None
        }
        if not changes:
            raise ValueError("至少提供一个更新字段。")
        print(
            json.dumps(
                apply_task_update(settings, args.task_id, changes),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "ui":
        run_ui(settings)
        return 0
    if args.command == "show":
        if not show_existing_window():
            run_ui(settings)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
