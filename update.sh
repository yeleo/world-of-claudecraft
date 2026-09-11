#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft (中国大陆合规发布版) - 一键平滑更新脚本
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
echo "  🔄 检查并更新 World of Claudecraft (Release/China) "
echo "=================================================="

# 1. 确保在 release/china 分支
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ "$CURRENT_BRANCH" != "release/china" ]; then
    echo "⚠️ 当前分支为 '$CURRENT_BRANCH'，正在切换至 release/china 分支..."
    git checkout release/china
fi

# 2. 拉取最新远端代码（智能适配浅克隆与完整克隆）
echo "📥 正在拉取远端 release/china 最新代码..."
if [ -f .git/shallow ]; then
    echo "💡 检测到生产环境浅克隆仓库 (Shallow Clone)，执行深度为 1 的快速拉取..."
    git pull --depth=1 origin release/china
else
    git pull origin release/china
fi

# 3. 准备运行时目录与权限
MEDIA_DIR="${EASTBROOK_MEDIA_DIR:-./media-cache}"
SFX_DIR="${EASTBROOK_SFX_DIR:-./sfx-runtime}"
SPOOL_DIR="${PARSE_SPOOL_HOST_DIR:-./parse-spool}"
CENSOR_DIR="${CENSOR_DIR:-./data/censor}"

mkdir -p "$MEDIA_DIR" "$SFX_DIR" "$SPOOL_DIR" "$CENSOR_DIR" data
chmod -R 777 "$MEDIA_DIR" "$SPOOL_DIR" 2>/dev/null || true

# 确保敏感词典与本地更新文件存在
touch "$CENSOR_DIR/censor_soft.txt" "$CENSOR_DIR/censor_hard.txt"
if [ ! -f data/releases.json ]; then
    echo "[]" > data/releases.json
fi

# 4. 平滑构建并重启容器
echo "🔨 正在重建并重启应用容器..."
docker compose up -d --build

# 5. 清理构建产生的悬空无用镜像，防止磁盘膨胀
echo "🧹 正在清理旧版本悬空镜像..."
docker image prune -f

# 6. 显示最终状态
echo ""
echo "✨ 更新完成！当前服务运行状态："
docker compose ps
echo ""
echo "📜 查看实时日志请执行: docker compose logs -f game"
