#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft (中国大陆发布版) - 一键平滑更新脚本
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  🔄 检查并更新 World of Claudecraft (Release/China) "
echo "=================================================="

# 1. 确保在 release/china 分支
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$CURRENT_BRANCH" != "release/china" ]; then
    echo "⚠️ 当前分支为 $CURRENT_BRANCH，正在切换至 release/china 分支..."
    git checkout release/china
fi

# 2. 拉取最新远端代码
echo "📥 正在拉取远端 release/china 最新提交..."
git pull origin release/china

# 3. 平滑构建并重启容器
echo "🔨 正在重建并重启应用容器..."
docker compose up -d --build

# 4. 显示最终状态
echo ""
echo "✨ 更新完成！当前服务运行状态："
docker compose ps
echo "📜 查看实时日志请执行: docker compose logs -f game"
