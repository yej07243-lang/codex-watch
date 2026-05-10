"""通知模块 — 通过飞书 Webhook 发送通知."""

import json
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional

from .config import config

CST = timezone(timedelta(hours=8))


def _now_str() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _send_feishu(text: str, title: Optional[str] = None) -> bool:
    """通过飞书 Webhook 发送文本消息."""
    webhook_url = config.get("feishu_webhook_url", "")
    if not webhook_url:
        print(f"⚠ 未配置飞书 Webhook URL，跳过通知", file=sys.stderr)
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


def notify_process_down(details: Optional[str] = None) -> bool:
    """通知 Codex 进程已停止."""
    lines = ["🚨 **Codex 进程异常停止**", ""]
    if details:
        lines.append(f"最后检测到的进程:")
        lines.append(f"```")
        lines.append(details)
        lines.append(f"```")
    lines.append(f"⏰ 检测时间: {_now_str()}")
    return _send_feishu("\n".join(lines), title="🚨 Codex 已停止")


def notify_process_up() -> bool:
    """通知 Codex 进程已恢复."""
    text = f"✅ **Codex 进程已恢复运行**\n\n⏰ 恢复时间: {_now_str()}"
    return _send_feishu(text, title="✅ Codex 已恢复")


def notify_process_startup(processes: list) -> bool:
    """通知 Codex 进程已启动."""
    procs_str = "\n".join(f"- {p.name} (PID: {p.pid})" for p in processes[:10])
    text = f"🚀 **Codex 启动检测**\n\n运行进程:\n{procs_str}\n\n⏰ 启动时间: {_now_str()}"
    return _send_feishu(text, title="🚀 Codex 已启动")


def notify_thread_change(change_summary: str) -> bool:
    """通知线程状态变化."""
    text = f"📊 **线程状态变化**\n\n{change_summary}\n\n⏰ 检测时间: {_now_str()}"
    return _send_feishu(text, title="📊 Codex 线程变化")


def notify_job_start(job_count: int) -> bool:
    """通知 agent job 开始."""
    text = f"🔧 **Agent Job 启动**\n\n{job_count} 个 agent_job 进入运行状态\n\n⏰ 检测时间: {_now_str()}"
    return _send_feishu(text, title="🔧 Codex Job 启动")


def notify_job_done() -> bool:
    """通知 agent job 完成."""
    text = f"✅ **Agent Job 完成**\n\n所有 agent_job 已结束\n\n⏰ 检测时间: {_now_str()}"
    return _send_feishu(text, title="✅ Codex Job 完成")
