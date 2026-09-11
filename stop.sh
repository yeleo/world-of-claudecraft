#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft (中国大陆合规发布版) - 停止脚本
# ==============================================================================
set -e

# 防呆检查: 避免用户误用 source 或 . 执行导致 set -e 意外退出父 Shell
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    echo "❌ 错误: 请勿使用 'source' 或 '.' 执行此脚本，这可能会在命令出错时意外退出您的终端窗口！"
    echo "👉 正确执行方式: ./$(basename "${BASH_SOURCE[0]}") 或 bash ./$(basename "${BASH_SOURCE[0]}")"
    return 1 2>/dev/null || exit 1
fi


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  🛑 正在停止 World of Claudecraft 服务...         "
echo "=================================================="

docker compose down

echo ""
echo "✅ 服务已安全平稳停止。"
echo "💾 说明: 数据库（PostgreSQL/MariaDB）数据与上传媒体文件已完整保留在数据卷中。"
echo "🚀 重新启动请直接运行: ./start.sh"
