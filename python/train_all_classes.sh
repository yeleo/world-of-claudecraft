#!/usr/bin/env bash
# ==============================================================================
# World of ClaudeCraft - Multi-Class Neural Policy Batch Trainer
# Trains high-performance PPO policies individually per MMORPG class.
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
STEPS_PER_CLASS="${STEPS_PER_CLASS:-1000000}"
ENVS_COUNT="${ENVS_COUNT:-8}"

CLASSES=("warrior" "mage" "priest" "hunter" "paladin")

echo "=================================================="
echo " ⚔️  World of ClaudeCraft - Multi-Class PPO Batch"
echo " Target Classes : ${CLASSES[*]}"
echo " Steps/Class    : ${STEPS_PER_CLASS}"
echo " Parallel Envs  : ${ENVS_COUNT}"
echo " Python Binary  : ${PYTHON_BIN}"
echo "=================================================="

for pclass in "${CLASSES[@]}"; do
    echo ""
    echo "--------------------------------------------------"
    echo " 🚀 Training Neural Micro-Policy for Class: [${pclass^^}]"
    echo "--------------------------------------------------"
    
    $PYTHON_BIN "${SCRIPT_DIR}/train_ppo.py" \
        --player-class "${pclass}" \
        --total-timesteps "${STEPS_PER_CLASS}" \
        --num-envs "${ENVS_COUNT}" \
        --save-interval 250000
        
    echo " [OK] Class [${pclass^^}] policy training completed!"
done

echo ""
echo "=================================================="
echo " 🎉 All 5 MMORPG Class Policies Successfully Trained!"
echo " Models available at: ${SCRIPT_DIR}/models/"
echo "=================================================="
