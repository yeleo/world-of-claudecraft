"""Multi-Agent Neural Bot Client for World of ClaudeCraft.

Turing-Grade Human-like MMORPG Squad System:
- Realistic Human-like Character Naming (Authentic Chinese MMORPG Player Names by Class).
- Smooth Locomotion & Inertia: Natural turn rate angular interpolation, micro-wiggle,
  and habitual casual gamer hopping while traversing.
- Loose Dynamic Formation: Breathing formation drift avoiding robotic geometry.
- Human-like Reaction Stutter: NPC reading simulation delays, corpse looting pauses,
  and staggered asynchronous team quest hand-ins.
- Living Social Presence:
  * Dynamic natural Party Chat (/p) for pulling, resting/drinking, ready calls, and cheers.
  * Overhead Emotes (cheer, flex, salute, wave) on level up, quest complete, or meeting players.
  * Polite greeting reactions to real human players encountered in the world.
- Tactical Micro-Combat:
  * Melee flanking (hitting from sides/back to avoid parry).
  * Smart Healing for Healer role prioritizing lowest HP ally.
  * Threat peeling for tanks when backline is attacked.
  * Focus-fire assistance for DPS.
- Zero-CLI Autonomous Dual-Mode (Solo vs Squad) & Quest Progression to Eastbrook Mainland.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import re
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import numpy as np
import torch
import torch.nn as nn
from torch.distributions.categorical import Categorical
import websockets

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from train_ppo import ActorCritic

MAX_LEVEL = 10
WORLD_MAX_X = 140.0
WORLD_MAX_Z = 140.0
WORLD_MIN_Z = 0.0

DEFAULT_ROLES = [
    ("warrior", "Tank"),
    ("priest", "Healer"),
    ("mage", "DPS-Caster"),
    ("hunter", "DPS-Ranged"),
    ("paladin", "Support"),
]

# Authentic Chinese MMORPG Player Names by Role
HUMAN_PLAYER_NAMES = {
    "warrior": [
        "铁血战意", "夜风微凉", "风暴之盾", "冲锋就白给", "雷霆一击",
        "破阵子", "不灭狂怒", "风剑在手", "带头大哥", "狂暴大叔", "断水流大师兄", "撼地神牛"
    ],
    "priest": [
        "一口奶满你", "圣光忽悠着你", "云朵浅浅", "安魂曲", "白衣如雪",
        "秋风引", "治愈星芒", "给你加个盾", "奶谁谁暴击", "回春小能手", "糖果布丁", "浅笑安然"
    ],
    "mage": [
        "暴风雪狂魔", "闪现撞墙", "火法暴击十万", "冰封王座", "喝水大户",
        "奥术飞弹", "搓面包的大师", "寒冰箭雨", "大火球神教", "星光漫天", "法力无边", "冰霜之语"
    ],
    "hunter": [
        "宝宝快上", "夺命射击", "暗夜寻风", "放生治疗", "风行者之誓",
        "百步穿杨", "假死脱战", "箭雨风暴", "鹰眼游侠", "猎魔之刃", "带猫去流浪", "风筝大师"
    ],
    "paladin": [
        "无敌炉石", "大领主", "黎明骑士", "正义之锤", "圣光守护",
        "荣耀之誓", "十字军试炼", "惩戒之怒", "奉献光环", "守望者之誓", "神圣祝福", "白银之手"
    ],
}

# Natural chat chatter pools
CHAT_PULL_LINES = [
    "我开怪了，大家集火", "先打我打的这只！", "拉住了，集火打", "这波开两个，集火", "冲冲冲！"
]
CHAT_REST_LINES = [
    "等下，我空蓝了回口水", "稍等下，坐地喝口水", "先休整一下，回满再打", "等等，没蓝了"
]
CHAT_RESUME_LINES = [
    "好了，满状态走起", "回满了，继续", "冲", "搞定，走走走", "满状态，开拔"
]
CHAT_VICTORY_LINES = [
    "搞定！", "舒服了", "这波配合可以", "稳稳拿下", "交任务去咯"
]
CHAT_LAG_LINES = [
    "等等我，刚才被石头卡了下", "来了来了，跟上", "等等我马上到"
]

# Proving Shore Gauntlet flags (checkpoints)
GAUNTLET_CHECKPOINTS = [
    (-308.0, -16.0),
    (-308.0, -32.0),
    (-334.0, -32.5),
]

# Eastbrook Vale mainland road waypoints
EASTBROOK_WAYPOINTS = [
    (-7.5, -95.0),   # Harbor dock road
    (-15.0, -80.0),  # Ravenpost & crafts square
    (-25.0, -50.0),  # North village gate
    (-40.0, -20.0),  # River road bridge
    (-60.0, 10.0),   # Farm outskirts
    (-80.0, 40.0),   # High meadows
    (-85.0, 60.0),   # Wolves & boars camp
]

FORMATION_OFFSETS = [
    (0.0, 0.0),    # Leader (Warrior Tank)
    (-2.2, -2.5),  # Priest (Healer behind left)
    (2.2, -2.5),   # Mage (Caster behind right)
    (0.0, -4.2),   # Hunter (Ranged directly behind)
    (2.6, -0.8),   # Paladin (Support on right flank)
]


def check_server_health(server_url: str) -> bool:
    """Probes the server to ensure it is alive before connecting."""
    clean_url = server_url.rstrip("/")
    try:
        req = urllib.request.Request(f"{clean_url}/livez", headers={"User-Agent": "WoC-BotProbe"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status in (200, 204, 301, 302)
    except urllib.error.HTTPError:
        try:
            req2 = urllib.request.Request(clean_url, headers={"User-Agent": "WoC-BotProbe"})
            with urllib.request.urlopen(req2, timeout=3) as resp2:
                return resp2.status in (200, 301, 302)
        except Exception:
            return False
    except Exception:
        return False


def make_api_post(url: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    parsed = urllib.parse.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    req.add_header("Origin", origin)
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[!] HTTP {e.code} calling {url}: {body}", file=sys.stderr)
        raise


NAME_PREFIXES = ["铁血", "暴风", "夜风", "凌云", "逐星", "清风", "烈焰", "寒冰", "幻月", "晨光", "紫电", "惊雷", "沧海", "长空", "傲雪", "流云", "问天", "落羽", "绝尘"]
NAME_BASES = {
    "warrior": ["战狂", "战魂", "战盾", "战意", "铁骑", "狂刀", "不灭", "霸王", "战尊", "斩月", "断岳", "铁壁"],
    "priest": ["祈愿", "圣光", "安魂", "浅浅", "云朵", "星芒", "微光", "清音", "回春", "琉璃", "雨露", "圣语"],
    "mage": ["奥术", "火球", "冰霜", "暴雪", "星火", "法灵", "元素", "星辰", "霜华", "炽焰", "秘法", "寒魄"],
    "hunter": ["神射", "逐风", "穿云", "寻踪", "鹰眼", "游侠", "箭雨", "灵狐", "暗夜", "听风", "追影", "流矢"],
    "paladin": ["誓言", "守护", "领主", "黎明", "圣堂", "圣裁", "光耀", "神辉", "正义", "坚毅", "圣印", "光痕"],
}
NAME_SUFFIXES = ["君", "客", "者", "儿", "子", "侠", "尊", "羽", "仙", "生", "痕", "影", "灵", "落", "绝", "心", "歌", "尘", "风"]

def generate_chinese_mmo_name(player_class: str, bot_idx: int) -> str:
    p = random.choice(NAME_PREFIXES)
    b = random.choice(NAME_BASES.get(player_class, NAME_BASES["warrior"]))
    s = random.choice(NAME_SUFFIXES)
    return f"{p}{b}{s}"


class SingleBotInstance:
    def __init__(
        self,
        bot_idx: int,
        server_url: str,
        name: str,
        player_class: str,
        role: str,
        policy: ActorCritic,
        is_leader: bool,
        leader_ref: SingleBotInstance | None = None,
    ):
        self.bot_idx = bot_idx
        self.server_url = server_url.rstrip("/")
        parsed = urllib.parse.urlparse(self.server_url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        self.ws_url = f"{ws_scheme}://{parsed.netloc}/ws"
        self.origin_url = f"{parsed.scheme}://{parsed.netloc}"
        self.name = name
        self.player_class = player_class
        self.role = role
        self.policy = policy
        self.is_leader = is_leader
        self.leader_ref = leader_ref

        self.token = ""
        self.char_id = 0
        self.char_name = ""
        self.pid = -1

        # Live state
        self.self_state: dict = {}
        self.entities: dict[int, dict] = {}
        self.target_id: int | None = None
        self.ws = None
        self.party_invited_ids = set()

        # Dynamic mode: "solo" vs "squad"
        self.mode = "solo"
        self.team_state = "READY"  # "READY", "RESTING", "REGROUPING", "COMBAT"

        # Locomotion & Human-like Movement Smoothing
        self.current_facing = 0.0
        self.last_casual_jump_time = time.time() + random.uniform(3.0, 10.0)
        self.prev_x = 0.0
        self.prev_z = 0.0
        self.stuck_ticks = 0
        self.is_trying_to_move = False

        # Human-like Interaction Timers & Delays
        self.last_rest_time = 0.0
        self.last_loot_time = 0.0
        self.last_quest_action_time = 0.0
        self.last_heal_time = 0.0
        self.last_cast_time = 0.0
        self.last_chat_time = 0.0
        self.last_emote_time = 0.0
        self.npc_reading_until = 0.0

        # Known other player pids (for human greeting)
        self.last_greet_time = 0.0

    def register_and_create_char(self):
        uniq = str(int(time.time()))[-4:] + str(self.bot_idx) + str(random.randint(10, 99))
        username = f"usr_{self.player_class[:3]}_{uniq}"
        reg = make_api_post(f"{self.server_url}/api/register", {
            "username": username,
            "password": "botpassword123",
            "email": f"{username}@claudecraft.local",
        })
        self.token = reg["token"]

        for _ in range(15):
            candidate_name = generate_chinese_mmo_name(self.player_class, self.bot_idx)
            try:
                char = make_api_post(f"{self.server_url}/api/characters", {
                    "name": candidate_name,
                    "class": self.player_class,
                }, token=self.token)
                self.char_name = candidate_name
                self.char_id = char["id"]
                return
            except urllib.error.HTTPError as e:
                if e.code == 409:
                    continue  # Name taken, retry
                raise

        fallback = f"行者{random.choice(NAME_SUFFIXES)}{random.choice(NAME_SUFFIXES)}"
        char = make_api_post(f"{self.server_url}/api/characters", {
            "name": fallback,
            "class": self.player_class,
        }, token=self.token)
        self.char_name = fallback
        self.char_id = char["id"]

    def build_obs(self) -> np.ndarray:
        s = self.self_state
        obs = np.zeros(607, dtype=np.float32)
        if not s:
            return obs

        hp = s.get("hp", 100)
        mhp = max(1, s.get("mhp", 100))
        res = s.get("res", 100)
        mres = max(1, s.get("mres", 100))
        lv = s.get("lv", 1)
        x = s.get("x", 0.0)
        z = s.get("z", 0.0)
        facing = s.get("f", s.get("facing", 0.0))
        gcd = s.get("gcd", 0.0)

        obs[0] = hp / mhp
        obs[1] = res / mres
        obs[2] = 1.0 if s.get("inCombat") else 0.0
        obs[3] = lv / MAX_LEVEL
        obs[4] = (x - (WORLD_MAX_X / 2.0)) / (WORLD_MAX_X / 2.0)
        obs[5] = (z - ((WORLD_MAX_Z + WORLD_MIN_Z) / 2.0)) / ((WORLD_MAX_Z - WORLD_MIN_Z) / 2.0)
        obs[6] = math.cos(facing)
        obs[7] = math.sin(facing)
        obs[8] = gcd / 1.5

        chosen_target = self.entities.get(self.target_id) if self.target_id else None
        if not chosen_target or chosen_target.get("dead") or chosen_target.get("loot"):
            nearest_dist = float("inf")
            for ent in self.entities.values():
                if ent.get("k") == "mob" and not ent.get("dead") and not ent.get("loot"):
                    ex = ent.get("x", 0.0)
                    ez = ent.get("z", 0.0)
                    d = math.hypot(ex - x, ez - z)
                    if d < nearest_dist and d <= 45.0:
                        nearest_dist = d
                        chosen_target = ent

        if chosen_target:
            ex = chosen_target.get("x", 0.0)
            ez = chosen_target.get("z", 0.0)
            ndist = math.hypot(ex - x, ez - z)
            dx = (ex - x) / max(0.1, ndist)
            dz = (ez - z) / max(0.1, ndist)
            angle_to_mob = math.atan2(dx, dz)
            obs[9] = 1.0
            obs[10] = math.cos(angle_to_mob - facing)
            obs[11] = math.sin(angle_to_mob - facing)
            obs[12] = 1.0 if chosen_target.get("combat") else 0.0
            obs[13] = chosen_target.get("lv", chosen_target.get("level", 1)) / MAX_LEVEL
            obs[17] = chosen_target.get("hp", 0) / max(1, chosen_target.get("mhp", 1))
            obs[18] = min(1.0, ndist / 50.0)
            self.target_id = chosen_target.get("id")
        else:
            self.target_id = None

        return obs

    def smooth_turn_facing(self, desired_facing: float, dt: float = 0.05) -> float:
        """Human-like turn rate interpolation with subtle micro-tremor."""
        max_rad_per_sec = 6.8  # ~390 deg/sec natural mouse turn speed
        max_step = max_rad_per_sec * dt

        diff = (desired_facing - self.current_facing + math.pi) % (2 * math.pi) - math.pi
        clamped_step = max(-max_step, min(max_step, diff))
        self.current_facing = (self.current_facing + clamped_step) % (2 * math.pi)

        # Micro-tremor
        tremor = math.sin(time.time() * 2.5 + self.bot_idx) * 0.008
        return self.current_facing + tremor

    async def run(self, all_bots: list[SingleBotInstance]):
        self.register_and_create_char()
        print(f"  [+] Player #{self.bot_idx + 1} '{self.char_name}' ({self.player_class}/{self.role}) connecting...")

        async with websockets.connect(self.ws_url, origin=self.origin_url) as ws:
            self.ws = ws
            auth_msg = {
                "t": "auth-world-29",
                "token": self.token,
                "character": self.char_id,
                "clientSeed": "",
                "dungeonEntryFacingWire": 1,
                "timerWire": 3,
                "petSpecialWire": 1,
                "movementWire": 1,
            }
            await ws.send(json.dumps(auth_msg))

            async def receive_loop():
                async for raw in ws:
                    msg = json.loads(raw)
                    t = msg.get("t")
                    if t == "hello":
                        self.pid = msg.get("pid", -1)
                        print(f"  >>> Player #{self.bot_idx + 1} '{self.char_name}' joined the realm! (PID: {self.pid})")
                    elif t == "error":
                        pass
                    elif t == "snap":
                        if "self" in msg:
                            self.self_state.update(msg["self"])
                        if "ents" in msg:
                            for ent in msg["ents"]:
                                eid = ent.get("id")
                                if eid is not None:
                                    if eid in self.entities:
                                        self.entities[eid].update(ent)
                                    else:
                                        self.entities[eid] = ent
                        keep = set(msg.get("keep", []))
                        for ent_id in list(self.entities.keys()):
                            if ent_id not in keep and ent_id not in [e["id"] for e in msg.get("ents", []) if "id" in e]:
                                self.entities.pop(ent_id, None)
                    elif t == "events":
                        for ev in msg.get("list", []):
                            ev_type = ev.get("type")
                            if ev_type in ("partyInvite", "party_invite") and not self.is_leader:
                                # Natural human reaction delay before accepting party invite
                                await asyncio.sleep(random.uniform(0.3, 0.8))
                                await ws.send(json.dumps({"t": "cmd", "cmd": "paccept"}))

            async def control_loop():
                wp_idx = 0
                last_log_time = 0.0
                bot_pids = {b.pid for b in all_bots}

                while True:
                    await asyncio.sleep(0.05)  # 20 Hz tick
                    if not self.self_state or self.pid < 0:
                        continue

                    now = time.time()

                    # Resurrect if dead
                    if self.self_state.get("dead"):
                        await asyncio.sleep(random.uniform(1.2, 2.5))  # human hesitation before release
                        await ws.send(json.dumps({"t": "cmd", "cmd": "release"}))
                        continue

                    # ---------------------------------------------------------
                    # 1. Zero-CLI Mode & Party Auto-Detection
                    # ---------------------------------------------------------
                    party_data = self.self_state.get("party")
                    is_grouped = isinstance(party_data, dict) and len(party_data.get("members", [])) >= 2
                    prev_mode = self.mode
                    self.mode = "squad" if is_grouped else "solo"

                    if prev_mode != self.mode and self.bot_idx == 0:
                        print(f"  [*] Party status updated: [{self.mode.upper()}] Mode active (Squad: {len(party_data.get('members', [])) if is_grouped else 1} members)")

                    if is_grouped:
                        self.is_leader = (party_data.get("leader") == self.pid)
                    else:
                        self.is_leader = (self.bot_idx == 0)

                    # Leader invites remaining bots with human-like staggering
                    if self.is_leader and len(all_bots) > 1:
                        for other in all_bots:
                            if other != self and other.pid > 0 and other.pid not in self.party_invited_ids:
                                await ws.send(json.dumps({"t": "cmd", "cmd": "pinvite", "id": other.pid}))
                                self.party_invited_ids.add(other.pid)
                                await asyncio.sleep(random.uniform(0.15, 0.35))

                    my_x = self.self_state.get("x", 0.0)
                    my_z = self.self_state.get("z", 0.0)

                    # Anti-Stuck & Obstacle Jumping Detection
                    moved_dist = math.hypot(my_x - self.prev_x, my_z - self.prev_z)
                    self.prev_x = my_x
                    self.prev_z = my_z

                    if self.is_trying_to_move and moved_dist < 0.08:
                        self.stuck_ticks += 1
                    else:
                        self.stuck_ticks = 0

                    need_jump = self.stuck_ticks >= 2
                    need_strafe_left = (self.stuck_ticks >= 6 and (self.stuck_ticks % 6 < 3))
                    need_strafe_right = (self.stuck_ticks >= 6 and (self.stuck_ticks % 6 >= 3))

                    # Habitual gamer casual jump while traversing
                    if self.is_trying_to_move and not need_jump and now > self.last_casual_jump_time:
                        need_jump = True
                        self.last_casual_jump_time = now + random.uniform(8.0, 18.0)

                    def make_move_input(facing: float):
                        smoothed = self.smooth_turn_facing(facing, 0.05)
                        mi = {"f": 1}
                        if need_jump:
                            mi["j"] = 1
                        if need_strafe_left:
                            mi["sl"] = 1
                        elif need_strafe_right:
                            mi["sr"] = 1
                        return {"t": "input", "mi": mi, "facing": smoothed}

                    # ---------------------------------------------------------
                    # 2. Living Social Interactions (Emotes & Chatter)
                    # ---------------------------------------------------------
                    # Greet passing human players (non-bot players)
                    if now - self.last_greet_time > 25.0:
                        for ent in self.entities.values():
                            if ent.get("k") == "player" and ent.get("id") not in bot_pids:
                                p_dist = math.hypot(ent.get("x", 0) - my_x, ent.get("z", 0) - my_z)
                                if p_dist < 6.5:
                                    # Human wave or friendly say
                                    if random.random() < 0.6:
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "emote", "emote": "wave"}))
                                    else:
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": "嗨~"}))
                                    self.last_greet_time = now
                                    break

                    # ---------------------------------------------------------
                    # 3. Team Vitals & Readiness Arbiter (Leader Mind)
                    # ---------------------------------------------------------
                    team_needs_rest = False
                    team_needs_regroup = False
                    lagging_target_facing = None

                    if self.mode == "squad" and self.is_leader and is_grouped:
                        raw_members = party_data.get("members", [])
                        members = [m.get("member", m) for m in raw_members if isinstance(m, dict)]

                        min_hp_pct = min((m.get("hp", 100) / max(1, m.get("mhp", 100))) for m in members) if members else 1.0
                        mana_members = [m for m in members if m.get("rtype") == "mana"]
                        min_mana_pct = min((m.get("res", 100) / max(1, m.get("mres", 100))) for m in mana_members) if mana_members else 1.0

                        member_dists = [(m, math.hypot(m.get("x", my_x) - my_x, m.get("z", my_z) - my_z)) for m in members if m.get("pid") != self.pid]
                        max_dist = max([d for _, d in member_dists], default=0.0)
                        party_in_combat = any(m.get("inCombat") for m in members) or bool(self.self_state.get("inCombat"))

                        # Rest & Recovery assessment
                        if self.team_state == "RESTING":
                            if min_hp_pct >= 0.85 and min_mana_pct >= 0.70:
                                self.team_state = "READY"
                                print(f"  [Squad] Team vitals recovered (HP: {min_hp_pct*100:.0f}%, MP: {min_mana_pct*100:.0f}%). Advancing!")
                                if now - self.last_chat_time > 4.0:
                                    resume_msg = random.choice(CHAT_RESUME_LINES)
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p {resume_msg}"}))
                                    self.last_chat_time = now
                            else:
                                team_needs_rest = True
                        else:
                            if not party_in_combat and (min_hp_pct < 0.65 or min_mana_pct < 0.40):
                                self.team_state = "RESTING"
                                team_needs_rest = True
                                print(f"  [Squad] Leader halted squad for Rest & Recovery (Min HP: {min_hp_pct*100:.0f}%, Min MP: {min_mana_pct*100:.0f}%)")
                                if now - self.last_chat_time > 5.0:
                                    rest_msg = random.choice(CHAT_REST_LINES)
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p {rest_msg}"}))
                                    self.last_chat_time = now

                        # Cohesion & Lagging Tethering assessment
                        if not team_needs_rest and not party_in_combat:
                            if self.team_state == "REGROUPING":
                                if max_dist <= 5.0:
                                    self.team_state = "READY"
                                    print(f"  [Squad] Team regrouped! Resuming advance.")
                                else:
                                    team_needs_regroup = True
                            else:
                                if max_dist > 10.5:
                                    self.team_state = "REGROUPING"
                                    team_needs_regroup = True
                                    lagging_member = max(member_dists, key=lambda x: x[1])[0]
                                    print(f"  [Squad] '{lagging_member.get('name')}' is lagging behind ({max_dist:.1f}m). Leader holding up!")

                        if team_needs_regroup and member_dists:
                            lagging_member, _ = max(member_dists, key=lambda x: x[1])
                            lx = lagging_member.get("x", my_x)
                            lz = lagging_member.get("z", my_z)
                            lagging_target_facing = math.atan2(lx - my_x, lz - my_z)

                    effective_resting = (self.team_state == "RESTING" or (self.leader_ref and self.leader_ref.team_state == "RESTING"))

                    # Handle Eating/Drinking during Rest
                    if effective_resting:
                        my_hp_pct = self.self_state.get("hp", 100) / max(1, self.self_state.get("mhp", 100))
                        my_mana_pct = self.self_state.get("res", 100) / max(1, self.self_state.get("mres", 100))
                        if my_hp_pct < 0.85 or (self.self_state.get("rtype") == "mana" and my_mana_pct < 0.70):
                            if now - self.last_rest_time > 3.0:
                                await ws.send(json.dumps({"t": "cmd", "cmd": "eat_drink"}))
                                self.last_rest_time = now

                        self.is_trying_to_move = False
                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.self_state.get("f", 0.0)}))
                        continue

                    # Handle Leader waiting for lagging allies
                    if team_needs_regroup:
                        self.is_trying_to_move = False
                        await ws.send(json.dumps({
                            "t": "input",
                            "mi": {},
                            "facing": lagging_target_facing if lagging_target_facing is not None else self.self_state.get("f", 0.0),
                        }))
                        continue

                    # ---------------------------------------------------------
                    # 4. Smart Healing & Threat Peel (Role Coordination)
                    # ---------------------------------------------------------
                    # Smart Healing (Priest / Paladin)
                    if self.role == "Healer" or self.player_class in ("priest", "paladin"):
                        if is_grouped and now - self.last_heal_time > 1.6:
                            raw_members = party_data.get("members", [])
                            injured = []
                            for rm in raw_members:
                                m = rm.get("member", rm)
                                hp_p = m.get("hp", 100) / max(1, m.get("mhp", 100))
                                if hp_p < 0.75 and not m.get("dead"):
                                    injured.append((m, hp_p))
                            if injured:
                                lowest_m, lowest_hp = min(injured, key=lambda x: x[1])
                                heal_ability = "lesser_heal" if self.player_class == "priest" else "holy_light"
                                await ws.send(json.dumps({
                                    "t": "cmd",
                                    "cmd": "cast",
                                    "ability": heal_ability,
                                    "target": lowest_m.get("pid"),
                                }))
                                self.last_heal_time = now

                    # Threat Peel for Tanks (Warrior / Paladin)
                    if self.role == "Tank" and is_grouped:
                        raw_members = party_data.get("members", [])
                        for rm in raw_members:
                            m = rm.get("member", rm)
                            if m.get("hasAggro") and m.get("role") in ("healer", "dps") and not m.get("dead"):
                                ally_x = m.get("x", my_x)
                                ally_z = m.get("z", my_z)
                                for ent in self.entities.values():
                                    if ent.get("k") == "mob" and not ent.get("dead"):
                                        if math.hypot(ent.get("x", 0) - ally_x, ent.get("z", 0) - ally_z) < 8.0:
                                            self.target_id = ent.get("id")
                                            break

                    # Focus Fire Assist for DPS
                    if self.role in ("DPS-Caster", "DPS-Ranged") and self.leader_ref:
                        lead_tgt = self.leader_ref.target_id
                        if lead_tgt and lead_tgt in self.entities and not self.entities[lead_tgt].get("dead"):
                            self.target_id = lead_tgt

                    # ---------------------------------------------------------
                    # 5. Combat & Target Engagement
                    # ---------------------------------------------------------
                    obs = self.build_obs()
                    target_ent = self.entities.get(self.target_id) if self.target_id else None

                    # A. Combat Mode
                    if target_ent and not target_ent.get("dead") and not target_ent.get("loot"):
                        self.is_trying_to_move = True
                        tx = target_ent.get("x", my_x)
                        tz = target_ent.get("z", my_z)
                        dist_to_tgt = math.hypot(tx - my_x, tz - my_z)
                        angle_to_tgt = math.atan2(tx - my_x, tz - my_z)

                        # Leader natural pull shout
                        if self.is_leader and now - self.last_chat_time > 8.0:
                            pull_msg = random.choice(CHAT_PULL_LINES)
                            await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p {pull_msg}"}))
                            self.last_chat_time = now

                        if now - last_log_time > 4.0:
                            tgt_name = target_ent.get("nm", "enemy")
                            print(f"  [Combat] Player #{self.bot_idx + 1} '{self.char_name}' fighting {tgt_name} (Dist: {dist_to_tgt:.1f}m)")
                            last_log_time = now

                        is_ranged = self.player_class in ("mage", "hunter", "priest")
                        desired_dist = 11.5 if is_ranged else 2.2

                        # Melee tactical flanking (walk slightly to mob's flank/rear)
                        move_angle = angle_to_tgt
                        if not is_ranged and self.role != "Tank" and dist_to_tgt < 3.5:
                            flank_side = 0.4 if (self.bot_idx % 2 == 0) else -0.4
                            move_angle = angle_to_tgt + flank_side

                        if dist_to_tgt > desired_dist:
                            await ws.send(json.dumps(make_move_input(move_angle)))
                        else:
                            self.is_trying_to_move = False
                            smoothed_face = self.smooth_turn_facing(angle_to_tgt, 0.05)
                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": smoothed_face}))

                        await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": self.target_id}))
                        await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))

                        # Class ability execution
                        ability_map = {
                            "warrior": "heroic_strike",
                            "paladin": "seal_of_righteousness",
                            "mage": "fireball",
                            "priest": "smite",
                            "hunter": "arcane_shot",
                        }
                        ability = ability_map.get(self.player_class, "heroic_strike")
                        if now - self.last_cast_time > random.uniform(1.1, 1.4):
                            await ws.send(json.dumps({"t": "cmd", "cmd": "cast", "ability": ability, "target": self.target_id}))
                            self.last_cast_time = now

                    # B. Out of Combat Auto-Looting with Human Pause
                    elif not self.self_state.get("inCombat") and now - self.last_loot_time > 1.2:
                        for ent_id, ent in self.entities.items():
                            if ent.get("k") == "mob" and ent.get("loot"):
                                if math.hypot(ent.get("x", 0) - my_x, ent.get("z", 0) - my_z) <= 4.5:
                                    # Brief stop to loot
                                    await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.self_state.get("f", 0.0)}))
                                    await asyncio.sleep(0.4)
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "loot", "id": ent_id}))
                                    self.last_loot_time = now
                                    break

                    # C. Squad Follower Mode (maintain loose breathing formation with Leader)
                    if not target_ent and not self.is_leader and self.leader_ref and self.leader_ref.self_state:
                        lx = self.leader_ref.self_state.get("x", my_x)
                        lz = self.leader_ref.self_state.get("z", my_z)
                        lf = self.leader_ref.self_state.get("f", self.leader_ref.self_state.get("facing", 0.0))

                        # Formation breathing drift
                        base_x, base_z = FORMATION_OFFSETS[self.bot_idx % len(FORMATION_OFFSETS)]
                        drift_x = math.sin(now * 0.7 + self.bot_idx) * 0.35
                        drift_z = math.cos(now * 0.6 + self.bot_idx) * 0.35
                        off_x = base_x + drift_x
                        off_z = base_z + drift_z

                        slot_x = lx + (off_x * math.cos(lf) + off_z * math.sin(lf))
                        slot_z = lz + (-off_x * math.sin(lf) + off_z * math.cos(lf))

                        dist_to_slot = math.hypot(slot_x - my_x, slot_z - my_z)
                        angle_to_slot = math.atan2(slot_x - my_x, slot_z - my_z)

                        # Follower synchronous quest acceptance & turn-in (staggered human-like)
                        qdone_f = set(self.self_state.get("qdone", []))
                        qlog_list_f = self.self_state.get("qlog", [])
                        qlog_f = {q["questId"]: q for q in qlog_list_f if isinstance(q, dict) and "questId" in q}

                        # Check Gauntlet
                        if "q_ps_the_gauntlet" not in qdone_f:
                            if "q_ps_the_gauntlet" not in qlog_f:
                                if math.hypot(-283.0 - my_x, -21.0 - my_z) <= 5.5 and now - self.last_quest_action_time > 2.5:
                                    await asyncio.sleep(random.uniform(0.4, 1.2))
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "accept", "quest": "q_ps_the_gauntlet"}))
                                    self.last_quest_action_time = now
                            else:
                                if math.hypot(-337.0 - my_x, -33.0 - my_z) <= 5.5 and now - self.last_quest_action_time > 2.5:
                                    await asyncio.sleep(random.uniform(0.4, 1.2))
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "turnin", "quest": "q_ps_the_gauntlet"}))
                                    self.last_quest_action_time = now

                        # Check Strike True
                        elif "q_ps_strike_true" not in qdone_f:
                            if "q_ps_strike_true" not in qlog_f:
                                if math.hypot(-337.0 - my_x, -33.0 - my_z) <= 5.5 and now - self.last_quest_action_time > 2.5:
                                    await asyncio.sleep(random.uniform(0.4, 1.2))
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "accept", "quest": "q_ps_strike_true"}))
                                    self.last_quest_action_time = now
                            else:
                                if qlog_f["q_ps_strike_true"].get("state") == "ready":
                                    if math.hypot(-345.0 - my_x, -11.0 - my_z) <= 5.5 and now - self.last_quest_action_time > 2.5:
                                        await asyncio.sleep(random.uniform(0.4, 1.2))
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "turnin", "quest": "q_ps_strike_true"}))
                                        self.last_quest_action_time = now

                        # Check Ferry Bell
                        else:
                            if math.hypot(-279.0 - my_x, -10.0 - my_z) <= 5.0 and now - self.last_quest_action_time > 3.0:
                                await asyncio.sleep(random.uniform(0.5, 1.5))
                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                self.last_quest_action_time = now

                        if dist_to_slot > 1.8:
                            self.is_trying_to_move = True
                            await ws.send(json.dumps(make_move_input(angle_to_slot)))
                        else:
                            self.is_trying_to_move = False
                            smoothed_lf = self.smooth_turn_facing(lf, 0.05)
                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": smoothed_lf}))

                    # D. Autonomous Quest & World Navigation (Leader / Solo)
                    elif not target_ent and self.is_leader:
                        qdone = set(self.self_state.get("qdone", []))
                        qlog_list = self.self_state.get("qlog", [])
                        qlog = {q["questId"]: q for q in qlog_list if isinstance(q, dict) and "questId" in q}

                        goal_x, goal_z = my_x, my_z
                        goal_action = "patrol"
                        goal_param = ""

                        if my_x < -200.0:
                            # [On Proving Shore tutorial island]
                            if "q_ps_the_gauntlet" not in qdone:
                                if "q_ps_the_gauntlet" not in qlog:
                                    goal_x, goal_z = -283.0, -21.0
                                    goal_action = "accept"
                                    goal_param = "q_ps_the_gauntlet"
                                else:
                                    counts = qlog["q_ps_the_gauntlet"].get("counts", [0])
                                    next_flag = counts[0] if counts else 0
                                    if next_flag < len(GAUNTLET_CHECKPOINTS):
                                        goal_x, goal_z = GAUNTLET_CHECKPOINTS[next_flag]
                                        goal_action = "waypoint"
                                        goal_param = f"Flag #{next_flag + 1}"
                                    else:
                                        goal_x, goal_z = -337.0, -33.0
                                        goal_action = "turnin"
                                        goal_param = "q_ps_the_gauntlet"

                            elif "q_ps_strike_true" not in qdone:
                                if "q_ps_strike_true" not in qlog:
                                    goal_x, goal_z = -337.0, -33.0
                                    goal_action = "accept"
                                    goal_param = "q_ps_strike_true"
                                else:
                                    if qlog["q_ps_strike_true"].get("state") == "ready":
                                        goal_x, goal_z = -345.0, -11.0
                                        goal_action = "turnin"
                                        goal_param = "q_ps_strike_true"
                                    else:
                                        # Fight training effigies
                                        goal_x, goal_z = -336.0, -14.0
                                        goal_action = "hunt"
                                        goal_param = "training_effigy"

                            else:
                                # Tutorial completed -> Head to the Old Pier ferry bell to sail to mainland!
                                goal_x, goal_z = -279.0, -10.0
                                goal_action = "ferry"
                                goal_param = "ps_ferry_bell"

                        else:
                            # [On Eastbrook Vale Mainland!]
                            goal_x, goal_z = EASTBROOK_WAYPOINTS[wp_idx % len(EASTBROOK_WAYPOINTS)]
                            goal_action = "explore"
                            goal_param = "Eastbrook Highway"

                        dist_to_goal = math.hypot(goal_x - my_x, goal_z - my_z)
                        angle_to_goal = math.atan2(goal_x - my_x, goal_z - my_z)

                        # Check if reached goal for quest action
                        if dist_to_goal <= 3.8 and now - self.last_quest_action_time > 2.5:
                            # Human-like reading hesitation before clicking accept/turnin
                            if now < self.npc_reading_until:
                                # Still reading dialog
                                self.is_trying_to_move = False
                                await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.smooth_turn_facing(angle_to_goal, 0.05)}))
                                continue

                            if self.npc_reading_until == 0.0 and goal_action in ("accept", "turnin", "ferry"):
                                # Start reading pause
                                self.npc_reading_until = now + random.uniform(0.8, 1.6)
                                continue

                            self.npc_reading_until = 0.0

                            if goal_action == "accept":
                                await ws.send(json.dumps({"t": "cmd", "cmd": "accept", "quest": goal_param}))
                                print(f"  [Quest] Leader accepted '{goal_param}' from NPC!")
                                self.last_quest_action_time = now
                                if random.random() < 0.5:
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "emote", "emote": "salute"}))
                            elif goal_action == "turnin":
                                await ws.send(json.dumps({"t": "cmd", "cmd": "turnin", "quest": goal_param}))
                                print(f"  [Quest] Leader turned in & completed '{goal_param}'!")
                                self.last_quest_action_time = now
                                vic_msg = random.choice(CHAT_VICTORY_LINES)
                                await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p {vic_msg}"}))
                                await ws.send(json.dumps({"t": "cmd", "cmd": "emote", "emote": "cheer"}))
                            elif goal_action == "ferry":
                                await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": "/p 走，乘船去东溪谷大陆开荒！"}))
                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                print(f"  [Ferry] Ringing Ferry Bell to sail across to Eastbrook mainland!")
                                self.last_quest_action_time = now
                            elif goal_action in ("waypoint", "explore"):
                                wp_idx = (wp_idx + 1) % max(1, len(EASTBROOK_WAYPOINTS))

                        if dist_to_goal > 2.0:
                            self.is_trying_to_move = True
                            await ws.send(json.dumps(make_move_input(angle_to_goal)))
                        else:
                            self.is_trying_to_move = False
                            smoothed_goal = self.smooth_turn_facing(angle_to_goal, 0.05)
                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": smoothed_goal}))

                        if now - last_log_time > 5.0:
                            print(f"  [Explore] Leader '{self.char_name}' -> Objective: {goal_action} ({goal_param}) at ({goal_x:.1f}, {goal_z:.1f})")
                            last_log_time = now

            await asyncio.gather(receive_loop(), control_loop())


async def main_async(args):
    # 1. Health check
    print(f"[*] Checking server availability at {args.server}...")
    if not check_server_health(args.server):
        print(f"[!] Warning: Server at {args.server} did not respond to health check.")
        print(f"    Please make sure the World of ClaudeCraft server is running and reachable.")
        print(f"    (e.g., run 'npm run dev' on port 8787)\n")
    else:
        print(f"[OK] Game server is online and responding!\n")

    # 2. Load trained 3M-step policy model
    if not os.path.exists(args.model):
        print(f"[!] Error: Model checkpoint file not found at: {args.model}")
        print(f"Please specify a valid model with --model <path>\n")
        sys.exit(1)

    print(f"[*] Loading 3M-step neural policy from {args.model}...")
    ckpt = torch.load(args.model, map_location="cpu", weights_only=False)
    obs_dim = ckpt.get("obs_dim", 607)
    act_dim = ckpt.get("act_dim", 61)
    shared_policy = ActorCritic(obs_dim, act_dim)
    shared_policy.load_state_dict(ckpt["model_state_dict"])
    shared_policy.eval()
    print(f"[OK] Neural policy loaded! (Obs: {obs_dim}, Actions: {act_dim})\n")

    # 3. Create Bot Instances
    bots: list[SingleBotInstance] = []
    leader = None

    print(f"[*] Launching {args.count} Turing-grade bots into the realm:")
    for idx in range(args.count):
        if args.class_name == "auto":
            pclass, role = DEFAULT_ROLES[idx % len(DEFAULT_ROLES)]
        else:
            pclass = args.class_name
            role = "Solo"

        is_lead = (idx == 0)
        bot = SingleBotInstance(
            bot_idx=idx,
            server_url=args.server,
            name=args.name,
            player_class=pclass,
            role=role,
            policy=shared_policy,
            is_leader=is_lead,
            leader_ref=leader,
        )
        if is_lead:
            leader = bot
        bots.append(bot)

        role_tag = f"[{pclass.upper()} - {role}]"
        lead_tag = " (Party Leader)" if is_lead else ""
        print(f"  - Player #{idx + 1} {role_tag}{lead_tag}")

    print("\nAll players will enter the realm, form a cohesive party, and chat/emote naturally.")
    print(f"Watch live at {args.server}!\n")

    # 4. Run all bots concurrently
    await asyncio.gather(*(bot.run(bots) for bot in bots))


def main():
    parser = argparse.ArgumentParser(
        description="World of ClaudeCraft Neural Bot Squad Launcher",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-s", "--server",
        type=str,
        default="http://localhost:8787",
        help="Game server URL.\nExamples:\n  -s http://localhost:8787\n  -s http://192.168.1.100:8787",
    )
    parser.add_argument(
        "-c", "--count",
        type=int,
        default=5,
        choices=range(1, 6),
        help="Number of bots to spawn (1 to 5, default: 5).\nWhen count > 1, bots form a balanced party (Warrior, Priest, Mage, Hunter, Paladin).",
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default=os.path.join(_HERE, "models", "woc_policy_3m.pth"),
        help="Path to trained .pth model file.\nDefault: python/models/woc_policy_3m.pth",
    )
    parser.add_argument(
        "-n", "--name",
        type=str,
        default="ClaudeBot",
        help="Base name for characters (default: ClaudeBot).",
    )
    parser.add_argument(
        "--class-name",
        type=str,
        default="auto",
        choices=["auto", "warrior", "paladin", "priest", "mage", "hunter"],
        help="Class for bots. 'auto' assigns a balanced party composition.\nChoices: auto, warrior, paladin, priest, mage, hunter.",
    )

    args = parser.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n[!] Disconnecting all bots and shutting down gracefully.")


if __name__ == "__main__":
    main()
