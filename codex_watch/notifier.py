"""通知模块 — 支持飞书 Webhook 和 Hermes 文件桥接两种模式."""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from .config import config

CST = timezone(timedelta(hours=8))

# Hermes 模式告警文件路径
HERMES_ALERT_FILE = Path("/tmp/codex-watch-alerts.jsonl")

# 通知模式: "webhook" | "hermes" | "none"
NOTIFY_MODE = os.environ.get("NOTIFY_MODE", config.get("notify_mode", "webhook"))


def _now_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _append_usage(text: str, usage: Optional[str]) -> str:
    """在通知文本末尾追加用量信息."""
    if usage:
        return text + "\n\n" + usage
    return text


def _send_feishu(text: str, title: Optional[str] = None) -> bool:
    """通过飞书 Webhook 发送消息 (NOTIFY_MODE=webhook)."""
    webhook_url = config.get("feishu_webhook_url", "")
    if not webhook_url:
        print(f"⚠ 未配置飞书 Webhook URL", file=sys.stderr)
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"content": title or "Codex Watch", "tag": "plain_text"},
                "template": "blue",
            },
            "elements": [
                {"tag": "markdown", "content": text},
                {
                    "tag": "note",
                    "elements": [
                        {"tag": "plain_text", "content": f"Codex Watch · {_now_str()}"}
                    ],
                },
            ],
        },
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            if body.get("code") == 0:
                return True
            else:
                print(f"⚠ 飞书通知失败: {body}", file=sys.stderr)
                return False
    except Exception as e:
        print(f"⚠ 飞书通知异常: {e}", file=sys.stderr)
        return False


def _write_hermes_alert(alert_type: str, title: str, text: str) -> bool:
    """写入告警到 JSONL 文件，由 Hermes cron job 消费 (NOTIFY_MODE=hermes)."""
    try:
        entry = {
            "ts": datetime.now(CST).isoformat(),
            "type": alert_type,
            "title": title,
            "text": text,
        }
        with open(HERMES_ALERT_FILE, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"⚠ 写入告警文件失败: {e}", file=sys.stderr)
        return False


def _send(title: str, text: str, alert_type: str) -> bool:
    """根据 NOTIFY_MODE 选择通知方式."""
    if NOTIFY_MODE == "hermes":
        return _write_hermes_alert(alert_type, title, text)
    elif NOTIFY_MODE == "webhook":
        return _send_feishu(text, title)
    else:
        return False


# ─── 具体通知函数 ─────────────────────────────────────────


def notify_process_down(details: Optional[str] = None, usage: Optional[str] = None) -> bool:
    lines = ["🚨 **Codex 进程异常停止**", ""]
    if details:
        lines.append("最后检测到的进程:")
        lines.append("```")
        lines.append(details)
        lines.append("```")
    lines.append(f"⏰ 检测时间: {_now_str()}")
    return _send("🚨 Codex 已停止", _append_usage("\n".join(lines), usage), "process_down")


def notify_process_up(usage: Optional[str] = None) -> bool:
    text = f"✅ **Codex 进程已恢复运行**\n\n⏰ 恢复时间: {_now_str()}"
    return _send("✅ Codex 已恢复", _append_usage(text, usage), "process_up")


def notify_process_startup(processes: list, usage: Optional[str] = None) -> bool:
    procs_str = "\n".join(f"- {p.name} (PID: {p.pid})" for p in processes[:10])
    text = f"🚀 **Codex 启动检测**\n\n运行进程:\n{procs_str}\n\n⏰ 启动时间: {_now_str()}"
    return _send("🚀 Codex 已启动", _append_usage(text, usage), "process_startup")


def notify_thread_change(change_summary: str, usage: Optional[str] = None) -> bool:
    text = f"📊 **线程状态变化**\n\n{change_summary}\n\n⏰ 检测时间: {_now_str()}"
    return _send("📊 Codex 线程变化", _append_usage(text, usage), "thread_change")


def notify_job_start(job_count: int, usage: Optional[str] = None) -> bool:
    text = f"🔧 **Agent Job 启动**\n\n{job_count} 个 agent_job 进入运行状态\n\n⏰ 检测时间: {_now_str()}"
    return _send("🔧 Codex Job 启动", _append_usage(text, usage), "job_start")


def notify_job_done(usage: Optional[str] = None) -> bool:
    text = f"✅ **Agent Job 完成**\n\n所有 agent_job 已结束\n\n⏰ 检测时间: {_now_str()}"
    return _send("✅ Codex Job 完成", _append_usage(text, usage), "job_done")
