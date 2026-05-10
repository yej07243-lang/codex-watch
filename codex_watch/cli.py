"""CLI 入口 — argparse 命令行界面."""

import argparse
import sys
import time
from datetime import datetime, timezone, timedelta

from . import __version__
from .checker import check_processes, get_process_details
from .monitor import check_state, MonitorResult, ThreadChange
from .notifier import (
    notify_process_down,
    notify_process_up,
    notify_process_startup,
    notify_thread_change,
    notify_job_start,
    notify_job_done,
)
from .config import config, reload_config, init_config

CST = timezone(timedelta(hours=8))


def _in_quiet_hours() -> bool:
    """检查当前是否在静默时段."""
    qh = config.get("quiet_hours")
    if not qh:
        return False
    now = datetime.now(CST).strftime("%H:%M")
    return qh["start"] <= now <= qh["end"]


def cmd_check(args) -> int:
    """一次性检查 Codex 进程并输出状态."""
    status = check_processes()
    print(status.summary)

    if status.is_running:
        for p in status.processes:
            print(f"  PID {p.pid}: {p.name}")

    # 顺便检查线程状态
    if status.is_running:
        result = check_state()
        if result.success and result.threads:
            print(f"\n📊 活跃线程: {result.thread_count}, 运行中 jobs: {result.active_jobs}")
            for t in result.threads[:5]:
                icon = "🔓" if t.has_full_access else "🔒"
                ts = datetime.fromtimestamp(t.updated_at, CST).strftime("%H:%M") if t.updated_at else "?"
                print(f"  {icon} [{ts}] {t.title[:60]} → {t.tokens:,} tokens")

    return 0


def cmd_watch(args) -> int:
    """守护模式 — 持续监控进程和线程状态."""
    interval = args.interval or config.get("check_interval", 30)
    print(f"🔍 Codex Watch 守护模式启动 (间隔 {interval}s)")
    print(f"   按 Ctrl+C 停止\n")

    last_process_running: bool | None = None
    last_jobs: int = 0

    try:
        while True:
            # 静默时段跳过
            if _in_quiet_hours():
                time.sleep(interval)
                continue

            status = check_processes()

            # --- 进程状态变化检测 ---
            if config.get("alert_on_process_down") and last_process_running is True and not status.is_running:
                ts = datetime.now(CST).strftime("%H:%M:%S")
                print(f"[{ts}] 🚨 Codex 进程停止!")
                details = get_process_details()
                notify_process_down(details)

            elif last_process_running is False and status.is_running:
                ts = datetime.now(CST).strftime("%H:%M:%S")
                print(f"[{ts}] ✅ Codex 进程恢复")
                notify_process_startup(status.processes)

            elif last_process_running is None and status.is_running:
                ts = datetime.now(CST).strftime("%H:%M:%S")
                print(f"[{ts}] ✓ Codex 运行中 ({status.process_count} 进程)")
                notify_process_startup(status.processes)

            last_process_running = status.is_running

            # --- 线程状态变化检测 ---
            if status.is_running and config.get("alert_on_thread_change", True):
                result = check_state()
                if result.success and result.has_changes:
                    print(f"  📊 检测到变化:")
                    for c in result.changes:
                        if c.change_type == ThreadChange.CHANGE_NEW and config.get("alert_on_new_thread"):
                            print(f"    🆕 {c.thread.title}")
                        elif c.change_type == ThreadChange.CHANGE_UPDATE:
                            print(f"    🔄 {c.thread.title}: {c.detail}")
                        elif c.change_type == ThreadChange.CHANGE_STAGE1:
                            print(f"    ✅ {c.thread.title}: 阶段完成")

                    if _should_notify(result):
                        notify_thread_change(result.change_summary)

                # --- Agent Jobs 变化 ---
                if result.active_jobs > last_jobs and config.get("alert_on_job_start"):
                    notify_job_start(result.active_jobs)
                elif result.active_jobs == 0 and last_jobs > 0 and config.get("alert_on_job_done"):
                    notify_job_done()
                last_jobs = result.active_jobs

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n👋 Codex Watch 已停止")
        return 0


def _should_notify(result: MonitorResult) -> bool:
    """判断是否应该发送通知.

    规则: 有新线程或阶段完成时总是通知，纯更新时去重（必须同时有 token 增长）。
    """
    for c in result.changes:
        if c.change_type in (ThreadChange.CHANGE_NEW, ThreadChange.CHANGE_STAGE1):
            return True
        if c.change_type == ThreadChange.CHANGE_UPDATE:
            return True
    return False


def cmd_init(args) -> int:
    """初始化配置文件."""
    init_config()
    print("编辑配置文件以设置飞书 Webhook URL:")
    from .config import CONFIG_FILE
    print(f"  {CONFIG_FILE}")
    print()
    print("或设置环境变量: export FEISHU_WEBHOOK_URL='https://open.feishu.cn/...'")
    return 0


def cmd_status(args) -> int:
    """输出 Codex 当前状态的完整 Markdown 摘要（适合通知）."""
    from .monitor import get_thread_summary

    status = check_processes()
    lines = [f"## Codex 状态 — {datetime.now(CST).strftime('%H:%M:%S')}", ""]

    if status.is_running:
        lines.append(f"🟢 **运行中** ({status.process_count} 进程)")
        for p in status.processes[:10]:
            lines.append(f"- {p.name} (PID {p.pid})")
    else:
        lines.append("🔴 **未运行**")

    lines.append("")
    summary = get_thread_summary()
    if summary:
        lines.append(summary)

    output = "\n".join(lines)
    if args.send:
        from .notifier import _send_feishu
        _send_feishu(output, title="Codex 状态报告")

    print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-watch",
        description="Codex Watch — 自动检测 Codex 进程的守护监控工具",
    )
    parser.add_argument("--version", action="version", version=f"codex-watch {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # check
    p_check = subparsers.add_parser("check", help="一次性检查 Codex 进程状态")
    p_check.set_defaults(func=cmd_check)

    # watch
    p_watch = subparsers.add_parser("watch", help="守护模式：持续监控")
    p_watch.add_argument(
        "-i", "--interval", type=int, default=None,
        help=f"轮询间隔秒数 (默认: {config.get('check_interval', 30)})"
    )
    p_watch.set_defaults(func=cmd_watch)

    # init
    p_init = subparsers.add_parser("init", help="初始化配置文件")
    p_init.set_defaults(func=cmd_init)

    # status
    p_status = subparsers.add_parser("status", help="输出完整状态报告")
    p_status.add_argument("--send", action="store_true", help="同时发送飞书通知")
    p_status.set_defaults(func=cmd_status)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)
