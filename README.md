# Codex Watch

自动检测 [OpenAI Codex](https://github.com/openai/codex) 桌面端进程的守护监控工具。

- 检测 Codex 进程存活状态（Codex.app、app-server、CodexBar）
- 监控线程状态变化（新线程、更新、阶段完成）
- 检测 agent_jobs 启停
- 通过飞书 Webhook 发送实时通知
- 支持 launchd 后台守护运行

## 安装

```bash
git clone https://github.com/yej07243-lang/codex-watch.git
cd codex-watch
pip install -e .
```

或者直接运行（无需安装）：

```bash
python3 -m codex_watch check
```

## 配置

### 飞书 Webhook（必需）

获取飞书机器人 Webhook URL，然后任选一种方式配置：

```bash
# 方式一：环境变量
export FEISHU_WEBHOOK_URL='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'

# 方式二：配置文件
python3 -m codex_watch init
# 编辑 ~/.config/codex-watch/config.json
```

### 可选配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `CHECK_INTERVAL` | 30 | 轮询间隔（秒） |
| `ALERT_PROCESS_DOWN` | true | 进程停止时通知 |
| `ALERT_THREAD_CHANGE` | true | 线程变化时通知 |
| `QUIET_HOURS_START` | - | 静默时段开始 (如 `23:00`) |
| `QUIET_HOURS_END` | - | 静默时段结束 (如 `07:00`) |

## 使用

### 一次性检查

```bash
python3 -m codex_watch check
```

输出示例：

```
✓ Codex 运行中 (Codex.app, app-server, CodexBar, 共 8 进程)
  PID 82134: Codex.app
  PID 82201: app-server
  PID 82189: CodexBar

📊 活跃线程: 3, 运行中 jobs: 0
  🔓 [14:23] 重构 auth 模块 → 1,234,567 tokens
  🔒 [13:50] 修复 bug #42 → 567,890 tokens
```

### 守护模式

```bash
python3 -m codex_watch watch --interval 30
```

持续监控，检测到变化时自动发飞书通知。

### 状态报告

```bash
# 终端输出
python3 -m codex_watch status

# 同时发送飞书通知
python3 -m codex_watch status --send
```

## 安装为 macOS 后台服务

```bash
bash scripts/install.sh
```

管理命令：

```bash
launchctl start com.codex.watch    # 启动
launchctl stop com.codex.watch     # 停止
launchctl unload ~/Library/LaunchAgents/com.codex.watch.plist  # 卸载
```

日志位置：

- `/tmp/codex-watch.log` — 标准输出
- `/tmp/codex-watch.err` — 错误输出

## 通知示例

飞书卡片通知示例：

> 🚨 Codex 已停止
> 最后检测到的进程: [进程列表]
> ⏰ 检测时间: 2026-05-11 15:30:00

> 📊 线程状态变化
> 🆕 新线程: 实现用户登录功能
> 🔄 重构 auth 模块: +45s, tokens: 1,250,000

## 项目结构

```
codex-watch/
├── codex_watch/
│   ├── __init__.py
│   ├── __main__.py      # python -m 入口
│   ├── cli.py           # 命令行解析 + 守护循环
│   ├── checker.py       # 进程检测
│   ├── monitor.py       # 线程状态监控
│   ├── notifier.py      # 飞书通知
│   └── config.py        # 配置管理
├── scripts/
│   └── install.sh       # launchd 安装脚本
├── com.codex.watch.plist
├── pyproject.toml
└── README.md
```

## License

MIT
