"""进程检测 — 检测 Codex 相关进程是否在运行."""

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProcessInfo:
    pid: int
    name: str
    args: str = ""


@dataclass
class CodexProcessStatus:
    """Codex 进程状态快照."""

    is_running: bool = False
    processes: list[ProcessInfo] = field(default_factory=list)
    has_main_app: bool = False  # Codex.app
    has_app_server: bool = False  # codex app-server
    has_codexbar: bool = False  # CodexBar.app
    process_count: int = 0

    @property
    def summary(self) -> str:
        if not self.is_running:
            return "❌ Codex 未运行"
        parts = []
        if self.has_main_app:
            parts.append("Codex.app")
        if self.has_app_server:
            parts.append("app-server")
        if self.has_codexbar:
            parts.append("CodexBar")
        return f"✓ Codex 运行中 ({', '.join(parts)}, 共 {self.process_count} 进程)"


def check_processes() -> CodexProcessStatus:
    """检测 Codex 相关进程."""
    status = CodexProcessStatus()

    try:
        # 使用 pgrep 获取所有 codex 相关进程
        result = subprocess.run(
            ["pgrep", "-l", "-f", "-i", "codex"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0 or not result.stdout.strip():
            return status

        status.is_running = True
        lines = result.stdout.strip().split("\n")
        status.process_count = len(lines)

        for line in lines:
            parts = line.strip().split(" ", 1)
            if len(parts) >= 2:
                pid = int(parts[0])
                name = parts[1]
                proc = ProcessInfo(pid=pid, name=name)

                # 分类
                if "Codex.app/Contents/MacOS/Codex" in name:
                    proc.name = "Codex.app"
                    status.has_main_app = True
                elif "codex app-server" in name or "app-server" in name:
                    proc.name = "app-server"
                    status.has_app_server = True
                elif "CodexBar" in name:
                    proc.name = "CodexBar"
                    status.has_codexbar = True
                elif "codex " in name.lower() or name.endswith("codex"):
                    proc.name = "codex"

                status.processes.append(proc)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"⚠ 进程检测失败: {e}", file=sys.stderr)

    return status


def get_process_details() -> Optional[str]:
    """获取 Codex 进程详细信息（ps aux）."""
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = [
                line for line in result.stdout.split("\n")
                if "codex" in line.lower() and "grep" not in line.lower()
            ]
            if lines:
                # 包含 header + 匹配行
                header = result.stdout.split("\n")[0]
                return header + "\n" + "\n".join(lines[-20:])  # 最多 20 行
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None
