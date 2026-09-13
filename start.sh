#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft - 一键启动脚本 (多分支智能支持)
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

# 1. 检查并可选切换目标分支
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
TARGET_BRANCH="${1:-${BRANCH:-}}"

if [ -n "$TARGET_BRANCH" ] && [ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]; then
    echo "⚠️ 当前处于分支 '$CURRENT_BRANCH'，正在切换至 '$TARGET_BRANCH'..."
    git checkout data/releases.json 2>/dev/null || true
    if git show-ref --verify --quiet "refs/heads/$TARGET_BRANCH"; then
        git checkout "$TARGET_BRANCH"
    else
        echo "💡 本地未找到分支 '$TARGET_BRANCH'，尝试从远程检出..."
        if git fetch origin "$TARGET_BRANCH" 2>/dev/null; then
            git checkout -b "$TARGET_BRANCH" "origin/$TARGET_BRANCH" 2>/dev/null || git checkout "$TARGET_BRANCH"
        else
            echo "❌ 错误: 远程与本地均未找到分支 '$TARGET_BRANCH'！"
            exit 1
        fi
    fi
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "$TARGET_BRANCH")
fi

echo "=================================================="
echo "  🚀 启动 World of Claudecraft"
echo "  🌿 当前分支: ${CURRENT_BRANCH:-未知}"
echo "=================================================="

# 2. 检查并读取 .env 配置文件
if [ ! -f .env ]; then
    if [ -f .env.localtest ]; then
        echo "💡 检测到 .env.localtest，正在复制为 .env..."
        cp .env.localtest .env
    elif [ -f .env.example ]; then
        echo "⚠️ 未检测到 .env，正在从 .env.example 生成默认配置..."
        cp .env.example .env
        echo "✅ 已生成 .env，建议检查其中的密码与配置。"
    else
        echo "❌ 错误: 未找到 .env 配置文件。"
        exit 1
    fi
fi

# 加载 .env 环境变量（忽略注释）
export $(grep -v '^#' .env | xargs -d '\n' 2>/dev/null) || true

# 3. 检查 Docker 环境
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ 错误: 未安装 Docker，请先安装 Docker 和 Docker Compose。"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "❌ 错误: Docker 守护进程未启动，请先启动 Docker 服务。"
    exit 1
fi

# 4. 准备运行时目录与权限，防止 EACCES 权限拒绝
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

# 5. 构建并启动容器
echo "📦 正在启动 Docker 容器服务..."
docker compose up -d --build

# 6. 展示运行状态
echo ""
echo "✨ 服务启动成功！当前分支: ${CURRENT_BRANCH:-未知}"
echo "📊 容器状态："
docker compose ps

SERVER_URL="${PUBLIC_ORIGIN:-http://localhost:8787}"
echo ""
echo "🌐 游戏服务入口: $SERVER_URL"
echo "📜 查看服务实时日志请执行: docker compose logs -f game"
