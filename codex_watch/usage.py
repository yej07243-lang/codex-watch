"""用量查询 — 解析 Codex session JSONL 文件，计算每日 token 消耗."""

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

CST = timezone(timedelta(hours=8))
SESSION_BASE = Path.home() / ".codex" / "sessions"

# GPT-5 定价 (per 1M tokens)
PRICING = {"input": 1.25, "output": 10.0}


@dataclass
class SessionUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost(self) -> float:
        return (self.input_tokens / 1e6 * PRICING["input"]) + (
            self.output_tokens / 1e6 * PRICING["output"]
        )

    @property
    def summary(self) -> str:
        cost = self.estimated_cost
        total = self.total_tokens
        if total >= 1_000_000:
            return f"{total/1_000_000:.1f}M tokens · ~${cost:.2f}"
        elif total >= 1_000:
            return f"{total/1_000:.0f}K tokens · ~${cost:.2f}"
        else:
            return f"{total} tokens · ~${cost:.2f}"


@dataclass
class DailyUsage:
    date: str
    sessions: int = 0
    usage: SessionUsage = field(default_factory=SessionUsage)

    @property
    def summary(self) -> str:
        return f"{self.sessions} 会话 · {self.usage.summary}"


def _parse_session_tokens(filepath: str) -> Optional[SessionUsage]:
    """解析单个 session 文件，返回累计 token 用量.

    取最后一条包含 total_token_usage 的 event_msg。
    """
    last_total = None
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "event_msg":
                    continue
                info = obj.get("payload", {}).get("info")
                if not info or not isinstance(info, dict):
                    continue
                ttu = info.get("total_token_usage")
                if ttu and isinstance(ttu, dict) and "input_tokens" in ttu:
                    last_total = ttu
    except Exception:
        return None

    if last_total is None:
        return None

    return SessionUsage(
        input_tokens=last_total.get("input_tokens", 0),
        output_tokens=last_total.get("output_tokens", 0),
        cached_input_tokens=last_total.get("cached_input_tokens", 0),
    )


def get_today_usage() -> DailyUsage:
    """获取今日 Codex token 用量."""
    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    year = now.strftime("%Y")
    month = now.strftime("%m")
    day_dir = SESSION_BASE / year / month / now.strftime("%d")

    result = DailyUsage(date=today)
    if not day_dir.exists():
        return result

    # 扫描今日的 session 文件
    today_pattern = f"rollout-{today}T*.jsonl"
    files = list(day_dir.rglob(today_pattern))

    for fp in sorted(files):
        usage = _parse_session_tokens(str(fp))
        if usage:
            result.usage.input_tokens += usage.input_tokens
            result.usage.output_tokens += usage.output_tokens
            result.usage.cached_input_tokens += usage.cached_input_tokens
            result.sessions += 1

    return result


def get_today_summary() -> str:
    """获取今日用量摘要文本."""
    usage = get_today_usage()
    if usage.sessions == 0:
        return "📈 今日用量: 无数据"
    return f"📈 今日用量: {usage.summary}"


def get_thread_usage_summary(thread_tokens: int, prev_tokens: int = 0) -> str:
    """生成线程用量摘要."""
    parts = []
    if thread_tokens >= 1_000_000:
        parts.append(f"累计 {thread_tokens/1_000_000:.1f}M tokens")
    elif thread_tokens >= 1_000:
        parts.append(f"累计 {thread_tokens/1_000:.0f}K tokens")
    else:
        parts.append(f"累计 {thread_tokens} tokens")

    if prev_tokens > 0 and thread_tokens > prev_tokens:
        delta = thread_tokens - prev_tokens
        if delta >= 1_000_000:
            parts.append(f"+{delta/1_000_000:.1f}M")
        elif delta >= 1_000:
            parts.append(f"+{delta/1_000:.0f}K")
        else:
            parts.append(f"+{delta}")

    return " · ".join(parts)
