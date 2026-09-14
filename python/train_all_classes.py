#!/usr/bin/env python3
"""Multi-Class Neural Policy Batch Trainer for World of Claudecraft.

Trains distinct micro-combat policies across all 9 canonical MMORPG classes,
optimized to support both Solo play (survival, self-sufficiency, DPS)
and Squad/Party cooperative play (Tanking, Healing, Kiting, and Focus DPS).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
CONDA_PREFIX = os.environ.get("CONDA_PREFIX", "/home/yeleo/miniconda3/envs/claudecraft")
PYTHON_BIN = os.path.join(CONDA_PREFIX, "bin", "python")
if not os.path.exists(PYTHON_BIN):
    PYTHON_BIN = sys.executable

ALL_CLASSES = [
    "warrior", "mage", "priest", "hunter", "paladin",
    "rogue", "warlock", "druid", "shaman"
]

CLASS_DESCRIPTIONS = {
    "warrior": {
        "title": "Warrior (战士)",
        "solo": "Melee Sustained Combat, Rage Economy & Execute Burst",
        "party": "Frontline Main Tank, Aggro Holding & Threat Generation",
        "key_shaping": "Moderate damage taken tolerance to hold aggro; high kill reward",
    },
    "mage": {
        "title": "Mage (法师)",
        "solo": "Ranged Spellcasting & Frost Spacing / Kiting",
        "party": "Backline Burst DPS & CC, Maximum Spacing from Melee Danger",
        "key_shaping": "Heavy damage-taken penalty (-0.003) to enforce kiting; high spell burst reward",
    },
    "priest": {
        "title": "Priest (牧师)",
        "solo": "Shadow/Holy DoT Weaving & Shield Attrition",
        "party": "Core Healer & Survival Anchor (Extreme Death Penalty)",
        "key_shaping": "Extreme death penalty (-8.0) and high survival reward shaping",
    },
    "hunter": {
        "title": "Hunter (猎人)",
        "solo": "Deadzone Management & Ranged Physical Stutter-Stepping",
        "party": "Consistent Focused Ranged Physical DPS & Assisting Kills",
        "key_shaping": "Ranged distance maintenance, melee damage aversion (-0.0025)",
    },
    "paladin": {
        "title": "Paladin (圣骑士)",
        "solo": "High Durability, Seal Judgment & Flash of Light Self-Healing",
        "party": "Off-Tank, Sustained Holy Striking & Emergency Support",
        "key_shaping": "Balanced offensive/defensive profile with self-sustain incentives",
    },
    "rogue": {
        "title": "Rogue (潜行者/盗贼)",
        "solo": "High-Mobility Flanking, Energy/Combo Rhythm & Stealth Burst",
        "party": "Melee Assassin DPS, Backstab/Sinister Strike Burst",
        "key_shaping": "Flanking bonus, high DPS burst incentive, energy thrift",
    },
    "warlock": {
        "title": "Warlock (术士)",
        "solo": "Affliction DoT Stacking, Pet Synergy & Health Funneling",
        "party": "Ranged Continuous Shadow Damage & Life Tap Management",
        "key_shaping": "DoT duration reward, controlled health/mana conversion tolerance",
    },
    "druid": {
        "title": "Druid (德鲁伊)",
        "solo": "Shapeshifting Hybrid, Feral Claws, Rejuvenation & Bear Armor",
        "party": "Versatile Off-Healer/Bruiser, HoT Maintenance & Emergency Taunt",
        "key_shaping": "Shapeshift flexibility, hybrid healing & sustained melee reward",
    },
    "shaman": {
        "title": "Shaman (萨满祭司)",
        "solo": "Elemental Shock Burst, Lightning Bolt & Earthbind Kiting",
        "party": "Totem Buff Support, Chain Heal / Lightning Burst DPS",
        "key_shaping": "Shock burst timing, totem proximity reward, hybrid resilience",
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-Class PPO Policy Batch Trainer")
    parser.add_argument(
        "--total-timesteps",
        type=int,
        default=54_000_000,
        help="Global total steps across all targeted classes (default: 54,000,000)",
    )
    parser.add_argument(
        "--classes",
        type=str,
        default=",".join(ALL_CLASSES),
        help="Comma-separated classes to train (default: all 9 classes)",
    )
    parser.add_argument(
        "--steps-per-class",
        type=int,
        default=None,
        help="Optional explicit steps per class. If omitted, total-timesteps / num_classes is used.",
    )
    parser.add_argument("--num-envs", type=int, default=8, help="Number of parallel environments per class")
    parser.add_argument("--save-interval", type=int, default=500_000, help="Checkpoint interval")
    parser.add_argument("--log-file", type=str, default=os.path.join(_HERE, "train_all_classes.log"), help="Path to write log")
    return parser.parse_args()


def main():
    args = parse_args()
    classes = [c.strip().lower() for c in args.classes.split(",") if c.strip()]
    if not classes:
        print("Error: No valid classes specified.")
        sys.exit(1)

    steps_per_class = args.steps_per_class or (args.total_timesteps // len(classes))
    global_total = steps_per_class * len(classes)

    print("==================================================================")
    print(" ⚔️  World of ClaudeCraft - 9-Class Neural Policy Batch Trainer")
    print(f" Target Classes     : {', '.join(classes).upper()} ({len(classes)} classes)")
    print(f" Total Global Steps : {global_total:,}")
    print(f" Steps per Class    : {steps_per_class:,}")
    print(f" Parallel Envs      : {args.num_envs}")
    print(f" Python Binary      : {PYTHON_BIN}")
    print(f" Log File Output    : {args.log_file}")
    print("==================================================================\n")

    start_all_time = time.time()

    for idx, pclass in enumerate(classes, start=1):
        desc = CLASS_DESCRIPTIONS.get(pclass, {})
        print("\n" + "#" * 68)
        print(f" 🚀 [{idx}/{len(classes)}] Training Class: {desc.get('title', pclass.upper())}")
        print(f"    - Solo Doctrine : {desc.get('solo', 'Self-sufficient combat')}")
        print(f"    - Party Doctrine: {desc.get('party', 'Team role synergy')}")
        print(f"    - Shaping Focus : {desc.get('key_shaping', 'Role-specific rewards')}")
        print(f"    - Class Target  : {steps_per_class:,} steps")
        print("#" * 68 + "\n")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        cmd = [
            PYTHON_BIN,
            "-u",
            os.path.join(_HERE, "train_ppo.py"),
            "--player-class", pclass,
            "--total-timesteps", str(steps_per_class),
            "--num-envs", str(args.num_envs),
            "--save-interval", str(args.save_interval),
            "--resume", "auto",
        ]

        # Execute and stream output to both console and log file
        with open(args.log_file, "a", encoding="utf-8") as log_f:
            log_f.write(f"\n\n===== START CLASS [{pclass.upper()}] @ {time.ctime()} =====\n")
            log_f.flush()

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )

            assert proc.stdout is not None
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log_f.write(line)
                log_f.flush()

            proc.wait()
            if proc.returncode != 0:
                print(f"\n❌ Class [{pclass}] training failed with code {proc.returncode}")
                sys.exit(proc.returncode)

        print(f"\n✅ Finished training policy for [{pclass.upper()}]!")

    total_elapsed = time.time() - start_all_time
    print("\n==================================================================")
    print(" 🎉 All Multi-Class Policies Completed Successfully!")
    print(f" Total Elapsed Time : {total_elapsed / 3600:.2f} hours")
    print(f" Total Steps Trained: {global_total:,}")
    print(f" Models Available At: {os.path.join(_HERE, 'models')}")
    print("==================================================================")


if __name__ == "__main__":
    main()
