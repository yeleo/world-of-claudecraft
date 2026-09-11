#!/usr/bin/env bash
# ==============================================================================
# World of Claudecraft - 上游源仓库标准化一键同步工具
# ==============================================================================
# 架构规范:
#   upstream : https://github.com/levy-street/world-of-claudecraft.git (只读源)
#   origin   : https://github.com/yeleo/world-of-claudecraft.git (个人 Fork)
#   main     : 100% 纯净镜像，绝不包含任何额外提交，快进 (Fast-Forward) 对齐
#   release/china : 本地化生产分支，通过 merge main 吸收上游变更
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

# 1. 确保工作区干净
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ 错误: 当前工作区有未提交的改动，请先提交或暂存 (git stash) 后再同步！" >&2
    exit 1
fi

# 2. 检查并配置 upstream 远端
UPSTREAM_URL="https://github.com/levy-street/world-of-claudecraft.git"
if ! git remote get-url upstream 2>/dev/null; then
    echo "📡 正在添加 upstream 远端: $UPSTREAM_URL ..."
    git remote add upstream "$UPSTREAM_URL"
fi

# 3. 拉取上游最新提交
echo "📥 正在拉取 upstream/main 最新代码与发布标签..."
PROXY_FLAGS=()
if [ -n "${HTTP_PROXY:-}" ] || [ -n "${http_proxy:-}" ]; then
    :
elif curl -s --connect-timeout 2 http://127.0.0.1:7890 >/dev/null 2>&1; then
    echo "💡 检测到本地代理 127.0.0.1:7890，启用加速拉取..."
    PROXY_FLAGS=(-c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890)
fi

git "${PROXY_FLAGS[@]}" fetch upstream main

# 4. 快进同步 main 分支 (保证 100% 纯净无人工提交)
CURRENT_BRANCH="$(git branch --show-current)"
echo "🔄 正在快进更新本地 main 分支对齐 upstream/main ..."
git checkout main
git merge --ff-only upstream/main

echo "📤 正在推送最新纯净 main 至 origin/main ..."
git "${PROXY_FLAGS[@]}" push origin main

# 5. 切回本地化分支并合并
echo "🔀 正在切回 $CURRENT_BRANCH 分支并合并最新的 main ..."
git checkout "$CURRENT_BRANCH"

if [ "$CURRENT_BRANCH" != "main" ]; then
    UPSTREAM_VERSION="$(node -p "require('./package.json').version" 2>/dev/null || echo "latest")"
    git merge main -m "chore: sync upstream v${UPSTREAM_VERSION} into ${CURRENT_BRANCH}" || {
        echo "⚠️ 合并出现代码冲突，请按需解决冲突后提交！"
        exit 1
    }
    echo "📤 正在推送合并后的 $CURRENT_BRANCH 至 origin ..."
    git "${PROXY_FLAGS[@]}" push origin "$CURRENT_BRANCH"
fi

echo ""
echo "=================================================================="
echo "  ✨ 上游同步圆满完成！"
echo "  📌 当前 main 版本: $(git rev-parse --short main)"
echo "  📌 当前发布分支: $CURRENT_BRANCH ($(git rev-parse --short HEAD))"
echo "=================================================================="
