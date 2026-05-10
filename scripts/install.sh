#!/bin/bash
# 安装 Codex Watch 为 macOS launchd 服务
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_FILE="$REPO_DIR/com.codex.watch.plist"
LAUNCHD_PLIST="$HOME/Library/LaunchAgents/com.codex.watch.plist"

echo "=== Codex Watch 安装脚本 ==="
echo ""

# 1. 获取 Python 路径
PYTHON=$(which python3 2>/dev/null || echo "/usr/local/bin/python3")
echo "→ Python: $PYTHON"

# 2. 检查飞书 Webhook
if [ -z "$FEISHU_WEBHOOK_URL" ]; then
    echo "⚠ 未设置 FEISHU_WEBHOOK_URL 环境变量"
    echo "  请在 plist 或环境中设置，否则通知不可用"
fi

# 3. 初始化配置
echo "→ 初始化配置..."
cd "$REPO_DIR"
$PYTHON -m codex_watch init

# 4. 生成 plist（替换 Python 路径）
echo "→ 生成 launchd plist..."
mkdir -p "$HOME/Library/LaunchAgents"

sed "s|/usr/local/bin/python3|$PYTHON|g" "$PLIST_FILE" > "$LAUNCHD_PLIST"

# 注入 FEISHU_WEBHOOK_URL
if [ -n "$FEISHU_WEBHOOK_URL" ]; then
    /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:FEISHU_WEBHOOK_URL $FEISHU_WEBHOOK_URL" "$LAUNCHD_PLIST" 2>/dev/null || true
fi

# 5. 加载服务
echo "→ 加载 launchd 服务..."
launchctl unload "$LAUNCHD_PLIST" 2>/dev/null || true
launchctl load "$LAUNCHD_PLIST"

echo ""
echo "✓ 安装完成!"
echo "  服务名: com.codex.watch"
echo "  日志:   /tmp/codex-watch.log"
echo "  错误:   /tmp/codex-watch.err"
echo ""
echo "管理命令:"
echo "  启动:   launchctl start com.codex.watch"
echo "  停止:   launchctl stop com.codex.watch"
echo "  卸载:   launchctl unload ~/Library/LaunchAgents/com.codex.watch.plist"
