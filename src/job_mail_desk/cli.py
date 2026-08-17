from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .agent_bridge import apply_task_update, list_tasks, sync_outputs
from .config import (
    APPLICATIONS_DIR,
    DICTIONARIES_DIR,
    DASHBOARD_FILE,
    DIGESTS_DIR,
    TASKS_DIR,
    STATE_NAMESPACE,
    UNRESOLVED_DIR,
    ensure_config,
    load_settings,
)
from .application_registry import ApplicationRegistry, preview_progress_applications
from .identity_dictionaries import (
    DictionaryValidationError,
    load_identity_dictionaries,
)
from .dictionary_compiler import compile_workbook
from .identity_preview import export_identity_preview
from .credentials import configure_interactively
from .digest import generate_digest
from .doctor import run_doctor
from .exporter import export_dashboard, import_checked_states
from .logging_setup import configure_logging
from .markdown_store import MarkdownTaskStore
from .models import ParsedEvent
from .research import pending_requests
from .progress import export_progress
from .parser import PARSER_VERSION
from .scanner import scan_once
from .scheduler import run_forever
from .ui_app import run_ui, show_existing_window
from .task_service import legacy_application_id, task_from_event
from .unresolved_store import UnresolvedStore


LOGGER = logging.getLogger(__name__)


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
    scan.add_argument(
        "--identity-preview",
        action="store_true",
        help="重放邮箱窗口并预览申请归属，不修改任务、状态或 unresolved",
    )
    scan.add_argument(
        "--preview-output",
        type=Path,
        help="将 identity preview 导出为本地脱敏 Markdown",
    )
    subparsers.add_parser("run", help="运行后台调度器")
    digest = subparsers.add_parser("digest", help="生成简报")
    digest.add_argument("period", choices=("morning", "noon", "evening"))
    export = subparsers.add_parser("export", help="导出 Markdown 总览")
    export.add_argument("--obsidian", action="store_true")
    subparsers.add_parser(
        "sync-ledger",
        help="读取岗位投递决策台账并刷新本地卡片，不扫描邮箱",
    )
    subparsers.add_parser("research-queue", help="查看待处理研究请求")
    subparsers.add_parser(
        "application-preview",
        help="只读预览人工台账可生成的申请身份，不写入本地数据",
    )
    application_import = subparsers.add_parser(
        "application-import",
        help="从人工进展台账导入并锁定申请身份",
    )
    application_import.add_argument("--from-progress", action="store_true")
    dictionary_check = subparsers.add_parser(
        "dictionary-check",
        help="校验内置身份词典和本地覆盖，不修改任务或申请数据",
    )
    dictionary_check.add_argument(
        "--user-dir",
        type=Path,
        default=DICTIONARIES_DIR,
        help="本地词典覆盖目录",
    )
    dictionary_compile = subparsers.add_parser(
        "dictionary-compile",
        help="将用户持有的秋招 XLSX 编译成本地覆盖词典",
    )
    dictionary_compile.add_argument("--xlsx", type=Path, required=True)
    dictionary_compile.add_argument("--output", type=Path, required=True)
    dictionary_compile.add_argument(
        "--sheet",
        default="2027秋招信息表",
        help="包含公司及岗位列的工作表名称",
    )
    subparsers.add_parser("unresolved-list", help="列出待人工归属的脱敏邮件")
    unresolved_resolve = subparsers.add_parser(
        "unresolved-resolve",
        help="将待归属邮件绑定到现有申请并生成任务",
    )
    unresolved_resolve.add_argument("source_hash")
    unresolved_resolve.add_argument("--application-key", required=True)
    unresolved_ignore = subparsers.add_parser(
        "unresolved-ignore",
        help="忽略一条待归属邮件",
    )
    unresolved_ignore.add_argument("source_hash")
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
    LOGGER.info(
        "启动版本：app=%s parser=%s state=%s",
        __version__,
        PARSER_VERSION,
        STATE_NAMESPACE,
    )
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
        if args.preview_output and not args.identity_preview:
            raise ValueError("--preview-output 仅能与 --identity-preview 一起使用")
        summary = scan_once(
            settings,
            days=args.days,
            shadow=args.shadow or args.identity_preview,
            identity_preview=args.identity_preview,
        )
        if args.preview_output:
            export_identity_preview(summary, args.preview_output)
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
    if args.command == "sync-ledger":
        if settings.progress_source:
            ApplicationRegistry(APPLICATIONS_DIR).import_progress(
                settings.progress_source
            )
        store = MarkdownTaskStore(TASKS_DIR)
        print(json.dumps(sync_outputs(settings, store), ensure_ascii=False, indent=2))
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
    if args.command == "application-preview":
        records = preview_progress_applications(settings.progress_source)
        print(
            json.dumps(
                [record.to_dict() for record in records],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "application-import":
        if not args.from_progress:
            raise ValueError("当前仅支持 --from-progress。")
        records = ApplicationRegistry(APPLICATIONS_DIR).import_progress(
            settings.progress_source
        )
        print(
            json.dumps(
                [record.to_dict() for record in records],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "dictionary-check":
        try:
            dictionaries = load_identity_dictionaries(args.user_dir)
        except DictionaryValidationError as exc:
            print(
                json.dumps(
                    {"ok": False, "error": str(exc)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "ok": True,
                    "counts": dictionaries.counts(),
                    "sources": dictionaries.sources,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "dictionary-compile":
        report = compile_workbook(
            args.xlsx,
            args.output,
            load_identity_dictionaries(),
            sheet_name=args.sheet,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.command == "unresolved-list":
        records = [
            record.to_dict()
            for record in UnresolvedStore(UNRESOLVED_DIR).all()
            if record.status == "pending"
        ]
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return 0
    if args.command == "unresolved-ignore":
        record = UnresolvedStore(UNRESOLVED_DIR).ignore(args.source_hash)
        print(json.dumps(record.to_dict(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "unresolved-resolve":
        unresolved_store = UnresolvedStore(UNRESOLVED_DIR)
        record = unresolved_store.load(args.source_hash)
        if not record or record.status != "pending":
            raise ValueError("待归属记录不存在或已经处理。")
        registry = ApplicationRegistry(APPLICATIONS_DIR)
        application = registry.load(args.application_key)
        if not application:
            raise ValueError("申请身份不存在，请先在进展台账中确认该申请。")
        legacy_ids = set(application.legacy_application_ids)
        if len(legacy_ids) > 1:
            raise ValueError("申请包含多个旧 ID，必须先人工消除冲突。")
        legacy_id = (
            next(iter(legacy_ids))
            if legacy_ids
            else legacy_application_id(application.application_key)
        )
        if legacy_id not in application.legacy_application_ids:
            application.legacy_application_ids.append(legacy_id)
            registry.save(application)
        event = ParsedEvent(
            company=record.company,
            role=record.role,
            recruiting_project=record.recruiting_project,
            event_type=record.event_type,
            stage=record.stage,
            round=record.round,
            title=record.title,
            start_at=record.start_at,
            end_at=record.end_at,
            deadline_at=record.deadline_at,
            source_message_id=f"unresolved:{record.id}",
            source_received_at=record.received_at,
            source_sender="",
            source_url=None,
            action_summary=record.action_summary,
            requirements=record.requirements,
            matched_keywords=(),
            confidence=record.confidence,
            change_type=record.change_type,  # type: ignore[arg-type]
        )
        task_store = MarkdownTaskStore(TASKS_DIR)
        task = task_from_event(
            event,
            task_store,
            application_key=application.application_key,
            resolved_application_id=legacy_id,
        )
        task_store.save(task)
        unresolved_store.resolve(
            record.id,
            application_key=application.application_key,
            task_id=task.id,
        )
        sync_outputs(settings, task_store)
        print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
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
