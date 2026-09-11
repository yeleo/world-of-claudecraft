#!/usr/bin/env bash
# ==============================================================================
# World of ClaudeCraft - 神经网络智能体小队一键启动脚本 (start_bots.sh)
# ==============================================================================
set -e

# 获取脚本所在根目录
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_EXEC="/home/yeleo/miniconda3/envs/claudecraft/bin/python"

# 默认参数
SERVER_URL="http://localhost:8787"
BOT_COUNT=5
MODEL_PATH="$ROOT_DIR/python/models/woc_policy_3m.pth"
BOT_NAME="ClaudeBot"
CLASS_NAME="auto"

# 帮助函数
show_help() {
  cat << EOF

🎮 World of ClaudeCraft - 神经网络 Bot 组团上线工具

用法 (Usage):
  ./start_bots.sh [选项]

参数说明 (Options):
  -s, --server <URL>      游戏服务器 HTTP 地址 (默认: http://localhost:8787)
                          可选值: 任何合法的游戏服 URL，例如:
                            - 本地测试: http://localhost:8787
                            - 局域网机: http://192.168.1.100:8787
                            - 远程公网: https://game.example.com

  -c, --count <数量>      同时上线的 Bot 数量 (默认: 5，范围: 1 ~ 5)
                          可选值:
                            - 1 : 单独一个 Bot 自由探索
                            - 2~5 : 自动组成一支冒险队伍 (由队长带队跟随、集火并组团战斗)

  -m, --model <路径>      使用的强化学习模型权重文件 (默认: 300万步最终模型)
                          可选值:
                            - python/models/woc_policy_3m.pth (默认 300w 步最终模型)
                            - python/models/woc_ppo_step_501760.pth (50w 步早期模型)
                            - python/models/woc_ppo_step_1003520.pth (100w 步进阶模型)
                            - python/models/woc_ppo_step_2007040.pth (200w 步精通模型)

  -n, --name <前缀>       Bot 角色的游戏内命名前缀 (默认: ClaudeBot)
                          说明: 若 count > 1，会自动生成 ClaudeBot1, ClaudeBot2 等

  --class <职业>          Bot 职业选择 (默认: auto)
                          可选值:
                            - auto : (推荐) 自动配置经典战法牧黄金铁三角小队:
                                     Bot 1: 战士 (坦克/队长)
                                     Bot 2: 牧师 (治疗)
                                     Bot 3: 法师 (远程法系输出)
                                     Bot 4: 猎人 (远程物理输出)
                                     Bot 5: 圣骑士 (近战辅助)
                            - warrior : 全部强制指定为战士
                            - paladin : 全部强制指定为圣骑士
                            - priest  : 全部强制指定为牧师
                            - mage    : 全部强制指定为法师
                            - hunter  : 全部强制指定为猎人

  -h, --help              显示本帮助信息并退出

运行示例 (Examples):
  1. 默认一键启动 5 人黄金阵容小队:
     ./start_bots.sh

  2. 启动 3 个 Bot，连接局域网服务器:
     ./start_bots.sh --server http://192.168.1.50:8787 --count 3

  3. 启动单个法师 Bot 进行单挑测试:
     ./start_bots.sh --count 1 --class mage --name FireMage

EOF
}

# 解析命令行参数
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
      echo "[错误] 未知参数: $1"
      show_help
      exit 1
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
echo " 正在准备启动神经网络 Bot 小队..."
echo " - 服务器地址 : $SERVER_URL"
echo " - Bot 数量   : $BOT_COUNT"
echo " - 职业配置   : $CLASS_NAME"
echo " - 模型权重   : $MODEL_PATH"
echo "=================================================="

exec "$PYTHON_EXEC" "$ROOT_DIR/python/run_neural_bot.py" \
  --server "$SERVER_URL" \
  --count "$BOT_COUNT" \
  --model "$MODEL_PATH" \
  --name "$BOT_NAME" \
  --class-name "$CLASS_NAME"
