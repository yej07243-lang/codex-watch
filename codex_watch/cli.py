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
from .usage import get_today_summary
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
                print(f"  {icon} [{ts}] {t.title[:60]} -> {t.tokens:,} tokens")

    # 今日用量
    from .usage import get_today_summary
    print(f"\n{get_today_summary()}")

    return 0


def cmd_watch(args) -> int:
    """守护模式 — 持续监控进程和线程状态."""
    # 设置通知模式
    if args.notify:
        import os
        os.environ["NOTIFY_MODE"] = args.notify

    interval = args.interval or config.get("check_interval", 30)
    print(f"🔍 Codex Watch 守护模式启动 (间隔 {interval}s, 通知: {args.notify or 'webhook'})")
    print(f"   按 Ctrl+C 停止\n")

    last_process_running: bool | None = None
    last_jobs: int = 0

    # 进程停止确认机制 — 只有持续停止 N 次才通知
    down_streak: int = 0
    down_notified: bool = False
    down_details: str | None = None
    confirm_count: int = config.get("process_down_confirm_count", 3)

    # 线程变化去重 — 冷却时间 + token 增量过滤
    thread_cooldown: int = config.get("thread_change_cooldown", 300)
    thread_min_delta: int = config.get("thread_change_min_token_delta", 50)
    last_thread_notify: float = 0
    last_thread_tokens: dict[str, int] = {}  # thread_id -> 上次通知时的 tokens

    try:
        while True:
            # 静默时段跳过
            if _in_quiet_hours():
                time.sleep(interval)
                continue

            status = check_processes()
            usage_text = get_today_summary() if status.is_running else None

            # --- 进程状态变化检测（带确认窗口） ---
            if status.is_running:
                # 进程在运行
                if last_process_running is False:
                    if down_notified:
                        # 之前通知过彻底停止，现在是真正的恢复
                        ts = datetime.now(CST).strftime("%H:%M:%S")
                        print(f"[{ts}] ✅ Codex 进程恢复")
                        notify_process_startup(status.processes, usage_text)
                    else:
                        # 在确认窗口内恢复（临时停止），不通知飞书
                        ts = datetime.now(CST).strftime("%H:%M:%S")
                        print(f"[{ts}] ✓ Codex 进程恢复（临时停止，未通知）")
                elif last_process_running is None:
                    ts = datetime.now(CST).strftime("%H:%M:%S")
                    print(f"[{ts}] ✓ Codex 运行中 ({status.process_count} 进程)")
                    notify_process_startup(status.processes, usage_text)

                # 重置停止状态
                down_streak = 0
                down_notified = False
                down_details = None
                last_process_running = True

            else:
                # 进程停止 — 开始/继续确认计数
                if config.get("alert_on_process_down"):
                    if last_process_running is True:
                        # 刚停止，捕获详情
                        down_streak = 1
                        down_details = get_process_details()
                        ts = datetime.now(CST).strftime("%H:%M:%S")
                        print(f"[{ts}] ⚠ Codex 进程消失 (确认 {down_streak}/{confirm_count})")
                    elif last_process_running is False:
                        down_streak += 1
                        if not down_notified:
                            ts = datetime.now(CST).strftime("%H:%M:%S")
                            print(f"[{ts}] ⚠ 仍无进程 (确认 {down_streak}/{confirm_count})")

                    # 达到确认阈值 → 通知
                    if down_streak >= confirm_count and not down_notified:
                        ts = datetime.now(CST).strftime("%H:%M:%S")
                        print(f"[{ts}] 🚨 Codex 彻底停止（已确认 {confirm_count} 次）!")
                        _usage = get_today_summary()
                        notify_process_down(down_details, _usage)
                        down_notified = True

                last_process_running = False

            # --- 线程状态变化检测（带冷却和 token 过滤） ---
            if status.is_running and config.get("alert_on_thread_change", True):
                result = check_state()
                if result.success and result.has_changes:
                    # 打印终端日志（始终输出）
                    print(f"  📊 检测到变化:")
                    for c in result.changes:
                        if c.change_type == ThreadChange.CHANGE_NEW and config.get("alert_on_new_thread"):
                            print(f"    🆕 {c.thread.title}")
                        elif c.change_type == ThreadChange.CHANGE_UPDATE:
                            print(f"    🔄 {c.thread.title}: {c.detail}")
                        elif c.change_type == ThreadChange.CHANGE_STAGE1:
                            print(f"    ✅ {c.thread.title}: 阶段完成")

                    # 通知去重：冷却时间 + token 增量过滤
                    now = time.time()
                    should_notify = _should_notify_thread_changes(
                        result, last_thread_notify, thread_cooldown,
                        last_thread_tokens, thread_min_delta
                    )
                    if should_notify:
                        last_thread_notify = now
                        notify_thread_change(result.change_summary, usage_text)

                # --- Agent Jobs 变化 ---
                if result.active_jobs > last_jobs and config.get("alert_on_job_start"):
                    notify_job_start(result.active_jobs, usage_text)
                elif result.active_jobs == 0 and last_jobs > 0 and config.get("alert_on_job_done"):
                    notify_job_done(usage_text)
                last_jobs = result.active_jobs

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n👋 Codex Watch 已停止")
        return 0


def _should_notify_thread_changes(
    result: MonitorResult,
    last_notify: float,
    cooldown: int,
    last_tokens: dict[str, int],
    min_token_delta: int,
) -> bool:
    """判断是否应该发送线程变化通知，带冷却和 token 增量过滤.

    规则:
    1. 新线程 / 阶段完成 → 总是通知（不受冷却限制，但受冷却去重）
    2. 纯更新 → 必须过冷却时间 + token 增长 ≥ min_token_delta
    3. 冷却时间内的任何变化都抑制
    """
    now = time.time()
    if now - last_notify < cooldown:
        return False

    has_important = False
    has_update = False

    for c in result.changes:
        if c.change_type in (ThreadChange.CHANGE_NEW, ThreadChange.CHANGE_STAGE1):
            has_important = True
        elif c.change_type == ThreadChange.CHANGE_UPDATE:
            has_update = True
            # 检查 token 增量
            tid = c.thread.id
            prev_tokens = last_tokens.get(tid, 0)
            token_delta = c.thread.tokens - prev_tokens
            if token_delta >= min_token_delta:
                has_important = True

    if has_important:
        # 更新 token 记录
        for c in result.changes:
            last_tokens[c.thread.id] = c.thread.tokens
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

    # 今日用量
    from .usage import get_today_summary
    lines.append("")
    lines.append(get_today_summary())

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
    p_watch.add_argument(
        "--notify", choices=["webhook", "hermes", "none"], default=None,
        help="通知模式: webhook (飞书 Webhook), hermes (写 JSONL 文件由 Hermes 消费), none (不通知)"
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
