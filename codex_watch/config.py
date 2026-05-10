"""配置管理 — 从环境变量和配置文件加载设置."""

import os
import json
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "codex-watch"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _default_config() -> dict:
    return {
        "feishu_webhook_url": "",
        "check_interval": 30,  # 秒
        "alert_on_process_down": True,
        "alert_on_thread_change": True,
        "alert_on_new_thread": True,
        "alert_on_job_start": True,
        "alert_on_job_done": True,
        "quiet_hours": None,  # {"start": "23:00", "end": "07:00"}
        "log_level": "INFO",
    }


def _load_config() -> dict:
    """从配置文件加载，环境变量覆盖."""
    config = _default_config()

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_conf = json.load(f)
            config.update(file_conf)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠ 配置文件读取失败: {e}", file=sys.stderr)

    # 环境变量覆盖
    env_map = {
        "FEISHU_WEBHOOK_URL": "feishu_webhook_url",
        "CHECK_INTERVAL": ("check_interval", int),
        "ALERT_PROCESS_DOWN": ("alert_on_process_down", lambda v: v.lower() in ("1", "true", "yes")),
        "ALERT_THREAD_CHANGE": ("alert_on_thread_change", lambda v: v.lower() in ("1", "true", "yes")),
        "QUIET_HOURS_START": None,  # handled below
        "QUIET_HOURS_END": None,
    }

    for env_key, map_to in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if isinstance(map_to, tuple):
                key, converter = map_to
                config[key] = converter(val)
            elif map_to:
                config[map_to] = val

    # quiet_hours
    qs = os.environ.get("QUIET_HOURS_START")
    qe = os.environ.get("QUIET_HOURS_END")
    if qs and qe:
        config["quiet_hours"] = {"start": qs, "end": qe}

    # 验证
    if not config.get("feishu_webhook_url"):
        print("⚠ 未配置 FEISHU_WEBHOOK_URL，通知功能不可用", file=sys.stderr)

    return config


# 全局配置实例
config = _load_config()


def reload_config():
    """重新加载配置."""
    global config
    config = _load_config()
    return config


def init_config():
    """初始化配置文件（首次安装时调用）."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(_default_config(), f, indent=2, ensure_ascii=False)
        print(f"✓ 配置已创建: {CONFIG_FILE}")
    else:
        print(f"配置文件已存在: {CONFIG_FILE}")
