#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft (中国大陆合规发布版) - 启动脚本
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  🚀 启动 World of Claudecraft (Release/China)    "
echo "=================================================="

# 1. 检查并读取 .env 配置文件
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
export $(grep -v '^#' .env | xargs -d '
' 2>/dev/null) || true

# 2. 检查 Docker 环境
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ 错误: 未安装 Docker，请先安装 Docker 和 Docker Compose。"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "❌ 错误: Docker 守护进程未启动，请先启动 Docker 服务。"
    exit 1
fi

# 3. 准备运行时目录与权限，防止 EACCES 权限拒绝
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

# 4. 构建并启动容器
echo "📦 正在启动 Docker 容器服务..."
docker compose up -d --build

# 5. 展示运行状态
echo ""
echo "✨ 服务启动成功！当前容器状态："
docker compose ps

SERVER_URL="${PUBLIC_ORIGIN:-http://localhost:8787}"
echo ""
echo "🌐 游戏服务入口: $SERVER_URL"
echo "📜 查看服务实时日志请执行: docker compose logs -f game"
