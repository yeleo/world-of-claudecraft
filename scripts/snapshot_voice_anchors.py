#!/usr/bin/env python3
"""
World of Claudecraft 角色声纹母本资产固化工具 (Acoustic Anchor Snapshot Tool)

将当前已验证的各 NPC 纯净基准音频固化至 scripts/voices/anchors/<npcId>.mp3，
并生成 scripts/voices/anchors/anchor_manifest.json 元数据清单。
建立业务台词与角色声纹母本的物理解耦，杜绝上游文案变动导致音色漂移或连带重算。
"""

import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
VOICE_ZH_DIR = ROOT / "public" / "audio" / "voice_zh"
ANCHORS_DIR = ROOT / "scripts" / "voices" / "anchors"
CACHE_FILE = ROOT / "scripts" / "voices" / "zh_voice_cache.json"
MANIFEST_FILE = ANCHORS_DIR / "anchor_manifest.json"

ANCHORS_DIR.mkdir(parents=True, exist_ok=True)
cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}

# 搜集所有 NPC 目录
all_npc_folders = set()
for folder in VOICE_ZH_DIR.iterdir():
    if folder.is_dir() and not folder.name.startswith("."):
        all_npc_folders.add(folder.name)

anchors = {}

# 1. 优先提取各 NPC 的打招呼台词 (greeting__<npcId>) 作为最纯正的声学母本
for key, entry in cache.items():
    if key.startswith("greeting__"):
        actual_npc = key.replace("greeting__", "")
        audio_rel = entry.get("audio_path", "")
        src_file = VOICE_ZH_DIR / audio_rel
        if src_file.exists() and src_file.stat().st_size >= 1024:
            dest_file = ANCHORS_DIR / f"{actual_npc}.mp3"
            shutil.copy2(src_file, dest_file)
            anchors[actual_npc] = {
                "npc_id": actual_npc,
                "file": f"{actual_npc}.mp3",
                "source_key": key,
                "reference_text": entry.get("text", ""),
                "instruct": entry.get("instruct", ""),
                "mode": "anchor_frozen",
                "audio_hash": entry.get("audio_hash", ""),
                "created_at": datetime.now(timezone.utc).isoformat()
            }

# 2. 对于无 greeting 的特殊角色 (如首领与护送 yell 角色)，选用其代表性战斗台词作为母本
missing_npcs = all_npc_folders - set(anchors.keys())
for npc in sorted(missing_npcs):
    npc_entries = [
        (k, v) for k, v in cache.items()
        if v.get("audio_path", "").startswith(f"{npc}/")
    ]
    if npc_entries:
        # 按 key 排序取首条代表台词
        rep_key, rep_entry = sorted(npc_entries, key=lambda x: x[0])[0]
        src_file = VOICE_ZH_DIR / rep_entry.get("audio_path", "")
        if src_file.exists() and src_file.stat().st_size >= 1024:
            dest_file = ANCHORS_DIR / f"{npc}.mp3"
            shutil.copy2(src_file, dest_file)
            anchors[npc] = {
                "npc_id": npc,
                "file": f"{npc}.mp3",
                "source_key": rep_key,
                "reference_text": rep_entry.get("text", ""),
                "instruct": rep_entry.get("instruct", ""),
                "mode": "anchor_frozen",
                "audio_hash": rep_entry.get("audio_hash", ""),
                "created_at": datetime.now(timezone.utc).isoformat()
            }

sorted_anchors = dict(sorted(anchors.items()))
MANIFEST_FILE.write_text(json.dumps(sorted_anchors, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[*] 成功固化 {len(sorted_anchors)} 位 NPC 的永久声纹母本资产至 {ANCHORS_DIR.relative_to(ROOT)}")
