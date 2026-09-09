#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft (中国大陆发布版) - 启动脚本
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  🚀 启动 World of Claudecraft (Release/China)    "
echo "=================================================="

# 1. 检查 .env 配置文件
if [ ! -f .env ]; then
    echo "⚠️ 未检测到 .env 文件，正在从 .env.example 复制默认配置..."
    cp .env.example .env
    echo "✅ 已生成 .env，建议先根据实际情况检查并修改配置。"
fi

# 2. 检查 Docker 环境
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ 错误: 未安装 Docker，请先安装 Docker 和 Docker Compose。"
    exit 1
fi

# 3. 构建并启动容器
echo "📦 正在启动 Docker 容器网络..."
docker compose up -d --build

# 4. 展示运行状态
echo ""
echo "✨ 容器已启动成功！当前服务状态："
docker compose ps

echo ""
echo "🌐 默认服务访问端口: http://localhost:8787"
echo "📜 查看实时日志请执行: docker compose logs -f game"
