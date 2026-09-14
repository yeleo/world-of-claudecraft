#!/usr/bin/env bash
# ==============================================================================
# World of ClaudeCraft - 神经网络智能体小队一键极简启动脚本 (start_bots.sh)
# ==============================================================================
set -e

# 获取脚本所在根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="/home/yeleo/miniconda3/envs/claudecraft/bin/python"

# 默认参数
SERVER_URL="http://localhost:8787"
BOT_COUNT=9
MODEL_PATH="$ROOT_DIR/python/models/policy_warrior.pth"
BOT_NAME="ClaudeBot"
CLASS_NAME="auto"

# 帮助函数
show_help() {
  cat << EOF

🎮 World of ClaudeCraft - 神经网络 Bot 组团上线工具

极简用法 (Quick Start):
  ./start_bots.sh <Bot数量>
  例如:
    ./start_bots.sh 9               # 启动 9 个 Bot (自动覆盖全部 9 职业)
    ./start_bots.sh 10              # 启动 10 个自主仿生 Bot 模拟真实玩家生活

高级用法 (Options):
  ./start_bots.sh [选项] [数量]

参数说明:
  -s, --server <URL>      游戏服务器 HTTP 地址 (默认: http://localhost:8787)
  -c, --count <数量>      Bot 数量 (默认: 9)
  -n, --name <前缀>       命名前缀 (默认: ClaudeBot)
  --class <职业>          强制指定职业 (默认: auto, 覆盖 9 大职业)
                          支持: auto, warrior, paladin, priest, mage, hunter, rogue, warlock, druid, shaman
  -h, --help              显示帮助信息

EOF
}

# 优先支持首个位置参数为数字（例如: ./start_bots.sh 10）
if [[ $# -gt 0 && "$1" =~ ^[0-9]+$ ]]; then
  BOT_COUNT="$1"
  shift
fi

# 解析其余命令行参数
while [[ $# -gt 0 ]]; do
  case $1 in
    -s|--server)
      SERVER_URL="$2"
      shift 2
      ;;
    -c|--count)
      BOT_COUNT="$2"
      shift 2
      ;;
    -m|--model)
      MODEL_PATH="$2"
      shift 2
      ;;
    -n|--name)
      BOT_NAME="$2"
      shift 2
      ;;
    --class)
      CLASS_NAME="$2"
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        BOT_COUNT="$1"
        shift
      else
        echo "[错误] 未知参数: $1"
        show_help
        exit 1
      fi
      ;;
  esac
done

# 确保 Python 运行环境存在
if [ ! -f "$PYTHON_EXEC" ]; then
  echo "[错误] 未找到 claudecraft Conda 环境的 Python: $PYTHON_EXEC"
  exit 1
fi

# 确保 Node 在 PATH 中
export PATH="/home/yeleo/miniconda3/envs/claudecraft/bin:$PATH"

# 启动运行
echo "=================================================="
echo " 正在准备启动神经网络 9 职业 Bot 小队..."
echo " - 服务器地址 : $SERVER_URL"
echo " - Bot 数量   : $BOT_COUNT"
echo " - 职业分配   : $CLASS_NAME (全 9 职业真实生态覆盖)"
echo " - 宏观行为   : 自动做任务/Roll点分配/装备打分换装/遇商卖垃圾/阶段离队"
echo "=================================================="

exec "$PYTHON_EXEC" -u "$ROOT_DIR/python/run_neural_bot.py" \
  --server "$SERVER_URL" \
  --count "$BOT_COUNT" \
  --name "$BOT_NAME" \
  --class-name "$CLASS_NAME"
