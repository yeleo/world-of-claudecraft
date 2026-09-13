#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft - 一键平滑更新脚本 (多分支智能支持)
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

# 1. 确定目标分支
# 优先级: 命令行参数 $1 > 环境变量 $BRANCH > 当前所在分支 > 默认 release/china
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
TARGET_BRANCH="${1:-${BRANCH:-}}"

if [ -z "$TARGET_BRANCH" ]; then
    if [ -n "$CURRENT_BRANCH" ] && [ "$CURRENT_BRANCH" != "HEAD" ]; then
        TARGET_BRANCH="$CURRENT_BRANCH"
    else
        TARGET_BRANCH="release/china"
    fi
fi

echo "=================================================="
echo "  🔄 检查并更新 World of Claudecraft"
echo "  🌿 目标分支: $TARGET_BRANCH"
echo "=================================================="

# 2. 检查并切换至目标分支
if [ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]; then
    echo "⚠️ 当前处于分支 '$CURRENT_BRANCH'，正在切换至 '$TARGET_BRANCH'..."
    # 保护可能阻碍切换的本地元数据文件
    git checkout data/releases.json 2>/dev/null || true
    if git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
        git checkout "$TARGET_BRANCH"
    else
        echo "💡 本地未找到分支 '$TARGET_BRANCH'，正在尝试从远程检出..."
        if git fetch origin "$TARGET_BRANCH" 2>/dev/null; then
            git checkout -b "$TARGET_BRANCH" "origin/$TARGET_BRANCH" 2>/dev/null || git checkout "$TARGET_BRANCH"
        else
            echo "❌ 错误: 远程与本地均未找到分支 '$TARGET_BRANCH'！"
            exit 1
        fi
    fi
fi

# 3. 保护临时运行时文件变动
git checkout data/releases.json 2>/dev/null || true

# 4. 智能拉取远端代码并对齐（如果远端存在该分支）
echo "📥 正在检查并同步远端分支 '$TARGET_BRANCH' 最新代码..."
if git ls-remote --exit-code --heads origin "$TARGET_BRANCH" >/dev/null 2>&1; then
    if [ -f .git/shallow ]; then
        echo "💡 检测到生产环境浅克隆仓库 (Shallow Clone)，执行深度为 1 的快速拉取..."
        git fetch --depth=1 origin "$TARGET_BRANCH"
    else
        git fetch origin "$TARGET_BRANCH"
    fi
    echo "🔄 正在将本地分支严格对齐至 origin/$TARGET_BRANCH..."
    git reset --hard "origin/$TARGET_BRANCH"
else
    echo "ℹ️ 远端未找到 origin/$TARGET_BRANCH（当前为本地开发/测试分支），保留本地提交直接构建！"
fi

# 5. 准备运行时目录与权限
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

# 6. 平滑构建并重启容器
echo "🔨 正在重建并重启应用容器..."
docker compose up -d --build

# 7. 清理构建产生的悬空无用镜像，防止磁盘膨胀
echo "🧹 正在清理旧版本悬空镜像..."
docker image prune -f

# 8. 显示最终状态
echo ""
echo "✨ 更新完成！当前分支: $TARGET_BRANCH"
echo "📊 容器运行状态："
docker compose ps
echo ""
echo "📜 查看实时日志请执行: docker compose logs -f game"
