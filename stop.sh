#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft (中国大陆发布版) - 停止脚本
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 正在平稳停止 World of Claudecraft 服务..."
docker compose down

echo "✅ 服务已停止。"
