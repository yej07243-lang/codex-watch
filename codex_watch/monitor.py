"""线程监控 — 对比 state_5.sqlite 快照，检测线程变化."""

import json
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

CST = timezone(timedelta(hours=8))
STATE_DB = Path.home() / ".codex" / "state_5.sqlite"
SNAPSHOT_FILE = Path("/tmp/codex_watch_snapshot.json")


@dataclass
class ThreadInfo:
    id: str
    title: str
    tokens: int
    updated_at: int
    has_full_access: bool
    stage1_ts: int = 0


@dataclass
class ThreadChange:
    """线程变化事件."""

    CHANGE_UPDATE = "update"
    CHANGE_NEW = "new"
    CHANGE_STAGE1 = "stage1_done"

    change_type: str
    thread: ThreadInfo
    detail: str = ""


@dataclass
class MonitorResult:
    """监控结果."""

    success: bool = True
    error: str = ""
    thread_count: int = 0
    active_jobs: int = 0
    changes: list[ThreadChange] = field(default_factory=list)
    threads: list[ThreadInfo] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0

    @property
    def change_summary(self) -> str:
        if not self.changes:
            return ""
        lines = []
        for c in self.changes:
            if c.change_type == ThreadChange.CHANGE_NEW:
                lines.append(f"🆕 新线程: {c.thread.title}")
            elif c.change_type == ThreadChange.CHANGE_UPDATE:
                lines.append(f"🔄 {c.thread.title} — {c.detail}")
            elif c.change_type == ThreadChange.CHANGE_STAGE1:
                lines.append(f"✅ {c.thread.title} — 阶段完成")
        return "\n".join(lines)


def _read_threads() -> list[ThreadInfo]:
    """从 state_5.sqlite 读取活跃线程."""
    if not STATE_DB.exists():
        return []

    conn = sqlite3.connect(str(STATE_DB))
    rows = conn.execute("""
        SELECT id, substr(title,1,80), tokens_used, updated_at, sandbox_policy
        FROM threads WHERE archived=0
        ORDER BY updated_at DESC LIMIT 10
    """).fetchall()

    threads = []
    for r in rows:
        t = ThreadInfo(
            id=r[0],
            title=r[1] or "(无标题)",
            tokens=r[2] or 0,
            updated_at=r[3] or 0,
            has_full_access="danger-full-access" in (r[4] or ""),
        )
        # 检查 stage1_outputs
        s = conn.execute(
            "SELECT generated_at FROM stage1_outputs WHERE thread_id=? ORDER BY generated_at DESC LIMIT 1",
            (r[0],)
        ).fetchone()
        if s:
            t.stage1_ts = s[0]
        threads.append(t)

    conn.close()
    return threads


def _count_active_jobs() -> int:
    """计算正在运行的 agent_jobs."""
    if not STATE_DB.exists():
        return 0
    conn = sqlite3.connect(str(STATE_DB))
    count = conn.execute(
        "SELECT COUNT(*) FROM agent_jobs WHERE status='running' OR status='pending'"
    ).fetchone()[0]
    conn.close()
    return count


def check_state() -> MonitorResult:
    """检测线程状态变化（与上次快照对比）."""
    result = MonitorResult()

    if not STATE_DB.exists():
        result.success = False
        result.error = "Codex state_5.sqlite 不存在（Codex 可能未安装或未运行过）"
        return result

    try:
        current_threads = _read_threads()
        result.thread_count = len(current_threads)
        result.threads = current_threads
        result.active_jobs = _count_active_jobs()

        # 加载上次快照
        prev: dict = {}
        if SNAPSHOT_FILE.exists():
            try:
                with open(SNAPSHOT_FILE) as f:
                    prev = json.load(f)
            except json.JSONDecodeError:
                pass

        # 保存当前快照
        snapshot = {
            "time": int(datetime.now(CST).timestamp()),
            "threads": [
                {
                    "id": t.id,
                    "title": t.title,
                    "tokens": t.tokens,
                    "updated": t.updated_at,
                    "stage1_ts": t.stage1_ts,
                    "full_access": t.has_full_access,
                }
                for t in current_threads
            ],
            "active_jobs": result.active_jobs,
        }
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump(snapshot, f, ensure_ascii=False)

        if not prev:
            # 首次运行，所有线程算新线程
            for t in current_threads:
                result.changes.append(ThreadChange(
                    change_type=ThreadChange.CHANGE_NEW,
                    thread=t,
                    detail=f"首次检测到线程"
                ))
        else:
            prev_threads = {p["id"]: p for p in prev.get("threads", [])}
            for t in current_threads:
                pt = prev_threads.get(t.id)
                if pt:
                    # 已有线程，检查更新
                    if t.updated_at > pt["updated"]:
                        delta = t.updated_at - pt["updated"]
                        result.changes.append(ThreadChange(
                            change_type=ThreadChange.CHANGE_UPDATE,
                            thread=t,
                            detail=f"+{delta}s, tokens: {t.tokens:,}"
                        ))
                    if t.stage1_ts > pt.get("stage1_ts", 0):
                        result.changes.append(ThreadChange(
                            change_type=ThreadChange.CHANGE_STAGE1,
                            thread=t,
                            detail="新阶段完成"
                        ))
                else:
                    # 新线程
                    result.changes.append(ThreadChange(
                        change_type=ThreadChange.CHANGE_NEW,
                        thread=t,
                    ))

    except Exception as e:
        result.success = False
        result.error = str(e)

    return result


def get_thread_summary() -> Optional[str]:
    """获取当前线程摘要（用于通知）."""
    if not STATE_DB.exists():
        return None

    try:
        threads = _read_threads()
        jobs = _count_active_jobs()

        lines = [f"📊 Codex 线程状态 ({len(threads)} 活跃线程, {jobs} 运行中任务)"]
        for t in threads[:5]:
            icon = "🔓" if t.has_full_access else "🔒"
            ts = datetime.fromtimestamp(t.updated_at, CST).strftime("%H:%M") if t.updated_at else "?"
            lines.append(f"  {icon} [{ts}] {t.title[:50]} → {t.tokens:,} tokens")

        return "\n".join(lines)
    except Exception as e:
        return f"⚠ 线程检测失败: {e}"
