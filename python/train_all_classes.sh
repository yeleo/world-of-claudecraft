#!/usr/bin/env bash
# ==============================================================================
# World of ClaudeCraft - Multi-Class Neural Policy Batch Trainer
# Trains high-performance PPO policies individually per MMORPG class (30M total).
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/home/yeleo/miniconda3/envs/claudecraft/bin/python}"
TOTAL_STEPS="${TOTAL_STEPS:-30000000}"
ENVS_COUNT="${ENVS_COUNT:-8}"

export PATH="/home/yeleo/miniconda3/envs/claudecraft/bin:${PATH}"

$PYTHON_BIN "${SCRIPT_DIR}/train_all_classes.py" \
    --total-timesteps "${TOTAL_STEPS}" \
    --num-envs "${ENVS_COUNT}" \
    --save-interval 500000 \
    "$@"
