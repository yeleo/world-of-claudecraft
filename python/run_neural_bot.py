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

from macro.intents.gear_intent import evaluate_inventory_upgrades, decide_loot_roll, HumanGearInspectionFSM
from macro.intents.economy_intent import should_visit_vendor, find_nearby_vendor, HumanVendorInteractionFSM
from macro.intents.party_intent import PartyLifecycleManager
from macro.intents.quest_intent import QuestNavigator
from macro.intents.curiosity_intent import CuriosityIntentManager

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
    ("paladin", "Tank-Off"),
    ("rogue", "DPS-Melee"),
    ("warlock", "DPS-Caster"),
    ("druid", "Healer-Hybrid"),
    ("shaman", "DPS-Hybrid"),
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
        "rogue": [
        "潜行闷棍", "暗影伏击", "匕首淬毒", "影舞狂欢", "偷心盗贼", "夜之影", "背刺暴击", "疾跑如风", "开锁大师", "致命毒药"
    ],
    "warlock": [
        "吸取灵魂", "痛苦无常", "糖门大师", "末日降临", "恶魔契约", "恐惧嚎叫", "灵魂石绑定", "暗影箭雨", "地狱火降世", "腐蚀缠身"
    ],
    "druid": [
        "变熊拍晕", "猫德撕咬", "自然之力", "回春满天飞", "月火洗礼", "丛林守护者", "野性咆哮", "咕咕起舞", "生命绽放", "化身巨熊"
    ],
    "shaman": [
        "插满图腾", "闪电风暴", "风怒连击", "嗜血开起", "治疗波涌动", "先祖之魂", "地缚图腾", "大地震击", "激流奔涌", "元素之怒"
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
        "rogue": [
        "潜行闷棍", "暗影伏击", "匕首淬毒", "影舞狂欢", "偷心盗贼", "夜之影", "背刺暴击", "疾跑如风", "开锁大师", "致命毒药"
    ],
    "warlock": [
        "吸取灵魂", "痛苦无常", "糖门大师", "末日降临", "恶魔契约", "恐惧嚎叫", "灵魂石绑定", "暗影箭雨", "地狱火降世", "腐蚀缠身"
    ],
    "druid": [
        "变熊拍晕", "猫德撕咬", "自然之力", "回春满天飞", "月火洗礼", "丛林守护者", "野性咆哮", "咕咕起舞", "生命绽放", "化身巨熊"
    ],
    "shaman": [
        "插满图腾", "闪电风暴", "风怒连击", "嗜血开起", "治疗波涌动", "先祖之魂", "地缚图腾", "大地震击", "激流奔涌", "元素之怒"
    ],
    "paladin": ["誓言", "守护", "领主", "黎明", "圣堂", "圣裁", "光耀", "神辉", "正义", "坚毅", "圣印", "光痕"],
}
NAME_SUFFIXES = ["君", "客", "者", "儿", "子", "侠", "尊", "羽", "仙", "生", "痕", "影", "灵", "落", "绝", "心", "歌", "尘", "风"]

def generate_chinese_mmo_name(player_class: str, bot_idx: int) -> str:
    p = random.choice(NAME_PREFIXES)
    b = random.choice(NAME_BASES.get(player_class, NAME_BASES["warrior"]))
    s = random.choice(NAME_SUFFIXES)
    return f"{p}{b}{s}"



# ------------------------------------------------------------------------------
# Class-Specific Neural Policy Management Pool
# ------------------------------------------------------------------------------
class ClassPolicyPool:
    """Dynamic multi-model registry for class-specialized neural policies."""

    def __init__(self, models_dir: str, default_model_path: str = ""):
        self.models_dir = os.path.abspath(models_dir)
        self.default_model_path = os.path.abspath(default_model_path) if default_model_path else ""
        self.policies: dict[str, ActorCritic] = {}
        self.default_policy: ActorCritic | None = None
        self._init_default_policy()

    def _init_default_policy(self):
        pass

    def get_policy(self, player_class: str) -> ActorCritic:
        if player_class in self.policies:
            return self.policies[player_class]

        class_model_path = os.path.join(self.models_dir, f"policy_{player_class}.pth")
        if os.path.exists(class_model_path):
            try:
                ckpt = torch.load(class_model_path, map_location="cpu", weights_only=False)
                obs_dim = ckpt.get("obs_dim", 607)
                act_dim = ckpt.get("act_dim", 61)
                model = ActorCritic(obs_dim, act_dim)
                model.load_state_dict(ckpt["model_state_dict"])
                model.eval()
                self.policies[player_class] = model
                print(f"[+] [ModelPool] Bound dedicated [{player_class.upper()}] neural policy (Obs: {obs_dim}, Act: {act_dim})")
                return model
            except Exception as e:
                print(f"[!] Error loading dedicated model for {player_class}: {e}")

        # If dedicated weights are still training, instantiate dedicated architecture for this class
        print(f"[*] [ModelPool] Initializing dedicated real-time policy architecture for [{player_class.upper()}]")
        model = ActorCritic(607, 61)
        model.eval()
        self.policies[player_class] = model
        return model

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
        self.travel_heading = 0.0
        self.last_casual_jump_time = time.time() + random.uniform(3.0, 10.0)
        self.prev_x = 0.0
        self.prev_z = 0.0
        self.stuck_ticks = 0
        self.is_trying_to_move = False

        # Macro quest goal tracking
        self.macro_goal_action = "patrol"
        self.macro_goal_param = ""
        self.regroup_wait_start = 0.0

        # Human-like Interaction Timers & Delays
        self.last_rest_time = 0.0
        self.last_loot_time = 0.0
        self.last_quest_action_time = 0.0
        self.last_heal_time = 0.0
        self.last_cast_time = 0.0
        self.last_chat_time = 0.0
        self.last_emote_time = 0.0
        self.npc_reading_until = 0.0
        self.cast_freeze_until = 0.0

        # Known other player pids (for human greeting)
        self.last_greet_time = 0.0

        # Connection & Resilient State
        self.running = True
        self.last_sent_target_id: int | None = None
        self.last_attack_cmd_time = 0.0

        # Autonomous Macro Intent Managers & Human-Paced FSMs
        self.party_mgr = PartyLifecycleManager(self.pid, self.player_class, is_solo_personality=(self.player_class == "rogue"))
        self.vendor_fsm = HumanVendorInteractionFSM(self.pid)
        self.gear_fsm = HumanGearInspectionFSM(self.pid, self.player_class)
        self.curiosity_mgr = CuriosityIntentManager(self.pid, self.player_class)
        self.last_gear_eval_time = 0.0
        self.last_vendor_action_time = -999.0
        self.all_bots_ref: list[SingleBotInstance] = []
        self.last_inference_time = 0.0
        self.cached_action_idx = 0

    def get_squad_min_crate_count(self) -> int:
        """Returns the minimum number of crates collected among active squad members for q_ps_the_wreck_line."""
        squad = self.all_bots_ref
        if not squad or len(squad) <= 1:
            qlog = {q["questId"]: q for q in self.self_state.get("qlog", []) if isinstance(q, dict) and "questId" in q}
            q_entry = qlog.get("q_ps_the_wreck_line")
            counts = q_entry.get("counts", [0]) if q_entry else [0]
            return counts[0] if counts else 0
        min_crates = 6
        for b in squad:
            if b.pid < 0:
                continue
            if "q_ps_the_wreck_line" in set(b.self_state.get("qdone", [])):
                continue
            b_qlog = {q["questId"]: q for q in b.self_state.get("qlog", []) if isinstance(q, dict) and "questId" in q}
            q_entry = b_qlog.get("q_ps_the_wreck_line")
            if not q_entry:
                return 0
            counts = q_entry.get("counts", [0])
            cnt = counts[0] if counts else 0
            if cnt < min_crates:
                min_crates = cnt
        return min_crates

    def is_squad_ready_for_turnin(self, quest_id: str) -> tuple[bool, list[str]]:
        """Checks whether all active squad members have completed the quest and are ready to turn in."""
        squad = self.all_bots_ref
        if not squad or len(squad) <= 1:
            return True, []
        lagging = []
        for b in squad:
            if b == self or b.pid < 0:
                continue
            if quest_id in set(b.self_state.get("qdone", [])):
                continue
            b_qlog = {q["questId"]: q for q in b.self_state.get("qlog", []) if isinstance(q, dict) and "questId" in q}
            q_entry = b_qlog.get(quest_id)
            if not q_entry:
                name = b.char_name or f"Bot#{b.bot_idx+1}"
                lagging.append(f"{name}[not accepted]")
                continue
            if quest_id == "q_ps_set_sail":
                b_x = b.self_state.get("x", 0)
                b_z = b.self_state.get("z", 0)
                if math.hypot(b_x - (-284.0), b_z - (-9.0)) > 15.0:
                    name = b.char_name or f"Bot#{b.bot_idx+1}"
                    lagging.append(f"{name}[traveling]")
                continue
            if quest_id == "q_ps_mother_of_pearl":
                counts = q_entry.get("counts", [0, 0])
                if counts[0] < 1 or (len(counts) > 1 and counts[1] < 1):
                    name = b.char_name or f"Bot#{b.bot_idx+1}"
                    lagging.append(f"{name}{counts}")
                continue
            if q_entry.get("state") != "ready":
                name = b.char_name or f"Bot#{b.bot_idx+1}"
                counts = q_entry.get("counts", []) if q_entry else []
                lagging.append(f"{name}{counts}")
        return len(lagging) == 0, lagging

    def find_entity_id(self, keywords: list[str], must_be_alive: bool = True) -> int | None:
        """Robust multi-attribute entity finder across lite and full records."""
        for eid, e in self.entities.items():
            if must_be_alive and e.get("dead"):
                continue
            tid = str(e.get("tid", e.get("template", ""))).lower()
            nm = str(e.get("nm", e.get("name", ""))).lower()
            obj_id = str(e.get("objectItemId", "")).lower()
            is_dummy = bool(e.get("dummy"))
            for kw in keywords:
                lkw = kw.lower()
                if lkw in tid or lkw in nm or lkw in obj_id or (lkw == "effigy" and is_dummy):
                    return eid
        return None

    def is_squad_ready_for_accept(self, quest_id: str) -> tuple[bool, list[str]]:
        """Checks whether all active squad members have accepted the quest."""
        squad = self.all_bots_ref
        if not squad or len(squad) <= 1:
            return True, []
        lagging = []
        for b in squad:
            if b == self or b.pid < 0:
                continue
            if quest_id in set(b.self_state.get("qdone", [])):
                continue
            b_qlog = {q["questId"]: q for q in b.self_state.get("qlog", []) if isinstance(q, dict) and "questId" in q}
            if quest_id not in b_qlog:
                name = b.char_name or f"Bot#{b.bot_idx+1}"
                lagging.append(name)
        return len(lagging) == 0, lagging

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

    def is_passive_dummy(self, ent: dict) -> bool:
        if ent.get("dummy"):
            return True
        template = str(ent.get("templateId", ent.get("template", ent.get("tid", "")))).lower()
        name = str(ent.get("nm", ent.get("name", ""))).lower()
        return "effigy" in template or "effigy" in name or "training_effigy" in template or "dummy" in template

    def get_valid_combat_target(self) -> dict | None:
        s = self.self_state
        my_x = s.get("x", 0.0)
        my_z = s.get("z", 0.0)
        in_combat = bool(s.get("inCombat"))

        # If current target is still alive and valid, keep it
        if self.target_id and self.target_id in self.entities:
            curr = self.entities[self.target_id]
            if not curr.get("dead") and not curr.get("loot"):
                if not in_combat and self.is_passive_dummy(curr):
                    act = self.macro_goal_action or (self.leader_ref.macro_goal_action if self.leader_ref else "")
                    prm = self.macro_goal_param or (self.leader_ref.macro_goal_param if self.leader_ref else "")
                    if act in ("hunt", "ability_drill") or "effigy" in prm.lower():
                        return curr
                else:
                    return curr

        # Out of combat: followers assist leader, OR self-initiate if on active hunt/ability_drill
        if not in_combat and not self.is_leader:
            if self.leader_ref and self.leader_ref.target_id:
                lt = self.entities.get(self.leader_ref.target_id)
                if lt and not lt.get("dead") and not lt.get("loot"):
                    return lt
            if self.macro_goal_action not in ("hunt", "ability_drill"):
                return None

        # Determine target name/type to hunt
        hunt_goal = ""
        act = self.macro_goal_action or (self.leader_ref.macro_goal_action if self.leader_ref else "")
        prm = self.macro_goal_param or (self.leader_ref.macro_goal_param if self.leader_ref else "")
        if act == "ability_drill" or "effigy" in prm.lower():
            hunt_goal = "effigy"
        elif act == "hunt":
            hunt_goal = prm.lower().replace("_", " ")

        nearest_dist = float("inf")
        best_ent = None
        max_dist = 45.0 if in_combat else (25.0 if hunt_goal else 4.5)

        for ent in self.entities.values():
            if ent.get("dead") or ent.get("loot"):
                continue
            is_dummy = self.is_passive_dummy(ent)
            if ent.get("k") != "mob" and not is_dummy:
                continue
            if is_dummy and ("effigy" not in hunt_goal and not in_combat):
                continue

            ex = ent.get("x", 0.0)
            ez = ent.get("z", 0.0)
            d = math.hypot(ex - my_x, ez - my_z)

            if d <= max_dist:
                if not in_combat and not hunt_goal:
                    if not ent.get("combat"):
                        continue

                if hunt_goal:
                    nm = str(ent.get("template") or ent.get("tid") or ent.get("nm") or "").lower().replace("_", " ")
                    if hunt_goal not in nm and not any(w in nm for w in hunt_goal.split() if len(w) > 3):
                        continue

                if d < nearest_dist:
                    nearest_dist = d
                    best_ent = ent

        return best_ent

    def predict_neural_action(self, obs: np.ndarray) -> int:
        """Perform sub-millisecond forward inference with the class-specific neural policy."""
        try:
            with torch.no_grad():
                t_obs = torch.from_numpy(obs).unsqueeze(0)
                action, _, _, _ = self.policy.get_action_and_value(t_obs)
                return int(action.item())
        except Exception as e:
            return 0  # noop fallback

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
            chosen_target = self.get_valid_combat_target()

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
        self.all_bots_ref = all_bots
        if not self.token or not self.char_id:
            self.register_and_create_char()

        reconnect_delay = 1.0
        while self.running:
            try:
                print(f"  [+] Player #{self.bot_idx + 1} '{self.char_name}' ({self.player_class}/{self.role}) connecting...")
                async with websockets.connect(
                    self.ws_url,
                    origin=self.origin_url,
                    ping_interval=15,
                    ping_timeout=20,
                    close_timeout=5,
                ) as ws:
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
                    reconnect_delay = 1.0

                    async def receive_loop():
                        async for raw in ws:
                            msg = json.loads(raw)
                            t = msg.get("t")
                            if t == "hello":
                                self.pid = msg.get("pid", -1)
                                print(f"  >>> Player #{self.bot_idx + 1} '{self.char_name}' joined the realm! (PID: {self.pid})")
                            elif t == "error":
                                err_text = msg.get("error", msg.get("message", ""))
                                print(f"  [Bot #{self.bot_idx + 1} '{self.char_name}'] Server notice: {err_text}")
                            elif t == "snap":
                                if "self" in msg:
                                    s = msg["self"]
                                    # Sparse flags: server omits false values
                                    s["dead"] = bool(s.get("dead", False))
                                    s["ghost"] = bool(s.get("gh", False))
                                    s["gh"] = s["ghost"]
                                    self.self_state.update(s)
                                if "ents" in msg:
                                    for ent in msg["ents"]:
                                        if "gh" in ent:
                                            ent["ghost"] = bool(ent["gh"])
                                        eid = ent.get("id")
                                        if eid is not None:
                                            if eid in self.entities:
                                                # Clear sparse boolean flags when omitted by server
                                                cur_hp = ent.get("hp", self.entities[eid].get("hp", 0))
                                                if "dead" not in ent and cur_hp > 0:
                                                    self.entities[eid]["dead"] = 0
                                                if "loot" not in ent:
                                                    self.entities[eid]["loot"] = 0
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
                                    if ev_type == "error":
                                        print(f"  [Server Error] Bot #{self.bot_idx + 1} '{self.char_name}': {ev.get('text')}")
                                    elif ev_type == "log":
                                        l_text = ev.get("text", "")
                                        print(f"  [Server Log] Bot #{self.bot_idx + 1} '{self.char_name}': {l_text}")
                                        if "The Keeper set you on your feet" in l_text:
                                            self.self_state["dead"] = False
                                            self.self_state["ghost"] = False
                                            self.self_state["gh"] = False
                                    elif ev_type == "respawn":
                                        self.self_state["dead"] = False
                                        self.self_state["ghost"] = False
                                        self.self_state["gh"] = False
                                    elif ev_type in ("partyInvite", "party_invite"):
                                        inviter_pid = ev.get("fromPid")
                                        squad_pids = {b.pid for b in self.all_bots_ref if b.pid > 0}
                                        if inviter_pid in squad_pids:
                                            print(f"  [Party] Bot #{self.bot_idx + 1} '{self.char_name}' accepting party invite from #{inviter_pid}!")
                                            if self.self_state.get("party"):
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "pleave"}))
                                                await asyncio.sleep(0.1)
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "paccept"}))
                                    elif ev_type in ("lootRoll", "loot_roll"):
                                        roll_id = ev.get("rollId") or ev.get("id")
                                        item_data = ev.get("item", {})
                                        roll_cmd = self.party_mgr.process_loot_roll_event(roll_id, item_data)
                                        await ws.send(json.dumps(roll_cmd))

                    async def control_loop():
                        wp_idx = 0
                        last_log_time = 0.0
                        bot_pids = {b.pid for b in all_bots}

                        while True:
                            await asyncio.sleep(0.05)  # 20 Hz tick
                            if not self.self_state or self.pid < 0:
                                continue

                            now = time.time()

                            # Auto-handle spirit release & resurrection for Death Lesson or fallen heroes
                            is_dead = bool(self.self_state.get("dead"))
                            is_ghost = bool(self.self_state.get("ghost") or self.self_state.get("gh"))
                            if is_dead and not is_ghost:
                                if now - getattr(self, "last_release_cmd_time", 0.0) > 1.5:
                                    self.last_release_cmd_time = now
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "release"}))
                                    print(f"  [Spirit] Bot #{self.bot_idx + 1} '{self.char_name}' released spirit from corpse.")
                                continue

                            if is_ghost:
                                if now - getattr(self, "last_rez_cmd_time", 0.0) > 1.5:
                                    self.last_rez_cmd_time = now
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "resurrect_healer"}))
                                    print(f"  [Spirit] Bot #{self.bot_idx + 1} '{self.char_name}' resurrected at Spirit Healer.")
                                    self.self_state["ghost"] = False
                                    self.self_state["gh"] = False
                                    self.self_state["dead"] = False
                                continue

                            # Resurrect if dead or ghost
                            if self.self_state.get("dead"):
                                await asyncio.sleep(random.uniform(0.8, 1.5))
                                await ws.send(json.dumps({"t": "cmd", "cmd": "release"}))
                                continue
                            if self.self_state.get("ghost"):
                                await asyncio.sleep(random.uniform(1.0, 2.0))
                                await ws.send(json.dumps({"t": "cmd", "cmd": "resurrect_healer"}))
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

                            # Persistent Party Maintenance: Any current leader maintains full squad
                            if self.is_leader and len(all_bots) > 1:
                                cur_party_members = set()
                                if is_grouped and isinstance(party_data, dict):
                                    for m in party_data.get("members", []):
                                        if isinstance(m, dict):
                                            mpid = m.get("pid") or m.get("id")
                                            if mpid:
                                                cur_party_members.add(mpid)
                                        elif isinstance(m, int):
                                            cur_party_members.add(m)
                                for other in all_bots:
                                    if other != self and other.pid > 0 and other.pid not in cur_party_members:
                                        last_inv = getattr(self, f"last_inv_{other.bot_idx}", 0.0)
                                        if now - last_inv > 5.0:
                                            setattr(self, f"last_inv_{other.bot_idx}", now)
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "pinvite", "id": other.pid}))

                                # If Bot 1 (Tank/Lead) is in party but not leader, promote Bot 1 back to lead
                                if self.bot_idx != 0 and all_bots and all_bots[0].pid in cur_party_members:
                                    if now - getattr(self, "last_promote_time", 0.0) > 10.0:
                                        self.last_promote_time = now
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "ppromote", "id": all_bots[0].pid}))

                            my_x = self.self_state.get("x", 0.0)
                            my_z = self.self_state.get("z", 0.0)
                            my_hp = self.self_state.get("hp", 100)
                            my_mhp = max(1, self.self_state.get("mhp", 100))
                            my_hp_pct = my_hp / my_mhp
                            my_res = self.self_state.get("res", 100)
                            my_mres = max(1, self.self_state.get("mres", 100))
                            my_mana_pct = my_res / my_mres

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
                            # 1.5. Authentic Multi-Stage Human Interaction FSMs
                            # ---------------------------------------------------------
                            in_combat = bool(self.self_state.get("inCombat"))
                            inv = self.self_state.get("inventory", [])
                            equip = self.self_state.get("equipment", {})

                            # A. Deliberate Multi-Step Merchant Session (Approach -> Open -> Browse -> Click-by-Click)
                            if self.vendor_fsm.is_busy():
                                v_cmds, note = self.vendor_fsm.step_transaction(now, inv)
                                for c in v_cmds:
                                    await ws.send(json.dumps(c))
                                continue

                            if not in_combat and now - self.last_vendor_action_time > 20.0:
                                nearby_v = find_nearby_vendor(self.entities, my_x, my_z, max_dist=12.0)
                                if nearby_v and should_visit_vendor(inv, in_combat=False, opportunist=True):
                                    dist_v = math.hypot(nearby_v["x"] - my_x, nearby_v["z"] - my_z)
                                    if dist_v <= 3.5:
                                        self.vendor_fsm.start_transaction(nearby_v["id"], inv, now)
                                        self.last_vendor_action_time = now
                                        continue
                                    else:
                                        angle_v = math.atan2(nearby_v["x"] - my_x, nearby_v["z"] - my_z)
                                        self.is_trying_to_move = True
                                        await ws.send(json.dumps(make_move_input(angle_v)))
                                        continue

                            # B. Human Gear Inspection & Tooltip Comparison
                            if self.gear_fsm.is_busy():
                                g_cmds, note = self.gear_fsm.step(now)
                                for c in g_cmds:
                                    await ws.send(json.dumps(c))
                                continue

                            if not in_combat and now - self.last_gear_eval_time > 3.0:
                                upgrade = evaluate_inventory_upgrades(inv, equip, self.player_class)
                                if upgrade:
                                    self.gear_fsm.consider_upgrade(upgrade, now, in_combat)
                                self.last_gear_eval_time = now

                            # C. Curiosity & Scenic Wandering Intent
                            if not in_combat:
                                c_goal = self.curiosity_mgr.evaluate_curiosity(now, my_x, my_z, self.entities, in_combat)
                                if c_goal:
                                    cx, cz, c_act, c_param = c_goal
                                    dist_c = math.hypot(cx - my_x, cz - my_z)
                                    angle_c = math.atan2(cx - my_x, cz - my_z)
                                    if c_act == "sightseeing":
                                        look_angle = (now * 0.4 + self.pid) % 6.28
                                        self.is_trying_to_move = False
                                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": look_angle}))
                                        continue
                                    elif c_act == "investigate":
                                        if dist_c > 2.2:
                                            self.is_trying_to_move = True
                                            await ws.send(json.dumps(make_move_input(angle_c)))
                                            continue

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

                            # Determine current leader goal action to know if in town/camp
                            l_qdone = set(self.self_state.get("qdone", []))
                            l_qlog_list = self.self_state.get("qlog", [])
                            l_qlog = {q["questId"]: q for q in l_qlog_list if isinstance(q, dict) and "questId" in q}
                            _, _, l_action, _ = QuestNavigator.resolve_macro_objective(
                                my_x, my_z, l_qdone, l_qlog,
                                waypoint_index=getattr(self, "current_wp_index", 0),
                                player_class=self.player_class,
                                is_ghost=self.self_state.get("ghost", False)
                            )
                            is_town_action = l_action in ("accept", "turnin", "signpost", "buy_pouch", "death_lesson", "ferry")

                            if self.mode == "squad" and self.is_leader and is_grouped:
                                raw_members = party_data.get("members", [])
                                members = [m.get("member", m) for m in raw_members if isinstance(m, dict)]
                                living_members = [m for m in members if not m.get("dead") and not m.get("ghost") and not m.get("gh")]

                                # Filter tracking members: ignore members ahead on mainland or with more quests done
                                my_qdone_count = len(l_qdone)
                                tracking_members = []
                                for m in living_members:
                                    if m.get("pid") == self.pid:
                                        continue
                                    if my_x < -200.0 and m.get("x", 0.0) > -200.0:
                                        continue
                                    if len(m.get("qdone", [])) > my_qdone_count:
                                        continue
                                    tracking_members.append(m)

                                min_hp_pct = min((m.get("hp", 100) / max(1, m.get("mhp", 100))) for m in living_members) if living_members else 1.0
                                mana_members = [m for m in living_members if m.get("rtype") == "mana"]
                                min_mana_pct = min((m.get("res", 100) / max(1, m.get("mres", 100))) for m in mana_members) if mana_members else 1.0

                                member_dists = [(m, math.hypot(m.get("x", my_x) - my_x, m.get("z", my_z) - my_z)) for m in tracking_members]
                                max_dist = max([d for _, d in member_dists], default=0.0)
                                party_in_combat = any(m.get("inCombat") for m in members) or bool(self.self_state.get("inCombat"))

                                # Rest & Recovery assessment - NEVER in town/camp or during death lesson
                                if self.team_state == "RESTING":
                                    rest_dur = now - getattr(self, "rest_start_time", 0.0)
                                    if is_town_action or (min_hp_pct >= 0.85 and min_mana_pct >= 0.70) or rest_dur > 8.0:
                                        self.team_state = "READY"
                                        print(f"  [Squad] Team vitals recovered (HP: {min_hp_pct*100:.0f}%, MP: {min_mana_pct*100:.0f}%). Advancing!")
                                        if now - self.last_chat_time > 4.0:
                                            resume_msg = random.choice(CHAT_RESUME_LINES)
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p {resume_msg}"}))
                                            self.last_chat_time = now
                                    else:
                                        team_needs_rest = True
                                else:
                                    if not is_town_action and not party_in_combat and (min_hp_pct < 0.50 or min_mana_pct < 0.30):
                                        if l_action in ("hunt", "crab_boss"):
                                            self.team_state = "RESTING"
                                            self.rest_start_time = now
                                            team_needs_rest = True
                                            print(f"  [Squad] Leader halted squad for Rest & Recovery (Min HP: {min_hp_pct*100:.0f}%, Min MP: {min_mana_pct*100:.0f}%)")
                                            if now - self.last_chat_time > 5.0:
                                                rest_msg = random.choice(CHAT_REST_LINES)
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p {rest_msg}"}))
                                                self.last_chat_time = now

                                # Cohesion & Lagging Tethering assessment - NEVER halt leader in town/camp!
                                if not team_needs_rest and not party_in_combat and not is_town_action:
                                    last_regroup_finish = getattr(self, "last_regroup_finish_time", 0.0)
                                    can_regroup = (now - last_regroup_finish > 12.0)

                                    if self.team_state == "REGROUPING":
                                        if my_x > -200.0:
                                            still_on_island = any(m.get("x", 0) < -200.0 for m, _ in member_dists)
                                            if still_on_island:
                                                team_needs_regroup = True
                                            elif max_dist <= 7.5 or (self.regroup_wait_start > 0 and now - self.regroup_wait_start > 15.0):
                                                self.team_state = "READY"
                                                self.regroup_wait_start = 0.0
                                                self.last_regroup_finish_time = now
                                                print(f"  [Squad] Team regrouped ({max_dist:.1f}m)! Resuming advance.")
                                            else:
                                                team_needs_regroup = True
                                        else:
                                            if max_dist <= 7.5 or (self.regroup_wait_start > 0 and now - self.regroup_wait_start > 6.0):
                                                self.team_state = "READY"
                                                self.regroup_wait_start = 0.0
                                                self.last_regroup_finish_time = now
                                                print(f"  [Squad] Team regrouped ({max_dist:.1f}m)! Resuming advance.")
                                            else:
                                                team_needs_regroup = True
                                    else:
                                        if can_regroup and (max_dist > 14.0 or (my_x > -200.0 and any(m.get("x", 0) < -200.0 for m, _ in member_dists))):
                                            self.team_state = "REGROUPING"
                                            self.regroup_wait_start = now
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

                            # Focus Fire Assist for DPS & Healer
                            if (self.role in ("DPS-Caster", "DPS-Ranged", "Healer") or not self.is_leader) and self.leader_ref:
                                lead_tgt = self.leader_ref.target_id
                                if lead_tgt and lead_tgt in self.entities and not self.entities[lead_tgt].get("dead"):
                                    self.target_id = lead_tgt

                            # ---------------------------------------------------------
                            # 5. Combat & Target Engagement
                            # ---------------------------------------------------------
                            # 5. Combat & Target Engagement
                            # ---------------------------------------------------------
                            obs = self.build_obs()
                            target_ent = self.entities.get(self.target_id) if self.target_id else None

                            # Check if active quest or objective is already fulfilled or ready for turn-in
                            qdone_s = set(self.self_state.get("qdone", []))
                            qlog_d = {q["questId"]: q for q in self.self_state.get("qlog", []) if isinstance(q, dict) and "questId" in q}

                            is_dummy = target_ent and (target_ent.get("dummy") or "effigy" in str(target_ent.get("nm", "")).lower() or "effigy" in str(target_ent.get("template", "")).lower())
                            if is_dummy:
                                lead_has_effigy = bool(self.leader_ref and self.leader_ref.target_id and self.leader_ref.target_id == self.target_id)
                                if self.macro_goal_action not in ("hunt", "ability_drill") and not lead_has_effigy:
                                    if self.target_id is not None:
                                        self.target_id = None
                                        target_ent = None
                                        self.is_trying_to_move = False
                                        if self.last_sent_target_id is not None:
                                            self.last_sent_target_id = None
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": None}))

                            # General drop target if out of combat and squad is ready to turn in
                            ready_quests = [qid for qid, q in qlog_d.items() if q.get("state") == "ready"]
                            in_combat = bool(self.self_state.get("inCombat"))
                            if target_ent and not in_combat and ready_quests:
                                squad_ready_to_turnin = True
                                if len(self.all_bots_ref) > 1:
                                    squad_ready_to_turnin = all(self.is_squad_ready_for_turnin(rq)[0] for rq in ready_quests)
                                if squad_ready_to_turnin and self.macro_goal_action not in ("hunt", "ability_drill", "crate"):
                                    if not (self.leader_ref and self.leader_ref.target_id == self.target_id):
                                        self.target_id = None
                                        target_ent = None
                                        self.is_trying_to_move = False
                                        if self.last_sent_target_id is not None:
                                            self.last_sent_target_id = None
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": None}))


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

                                is_ranged = self.player_class in ("mage", "priest")
                                desired_dist = 11.5 if is_ranged else 2.2
                                # If actively casting a spell, hold still so movement doesn't interrupt cast
                                if (now < self.cast_freeze_until) or (self.self_state.get("castRemaining", 0) > 0) or self.self_state.get("castingAbility"):
                                    self.is_trying_to_move = False
                                    smoothed_face = self.smooth_turn_facing(angle_to_tgt, 0.05)
                                    await ws.send(json.dumps({"t": "input", "mi": {}, "facing": smoothed_face}))
                                    await asyncio.sleep(0.08)
                                    continue


                                # Melee tactical flanking (walk slightly to mob's flank/rear)
                                move_angle = angle_to_tgt
                                if not is_ranged and self.role != "Tank" and dist_to_tgt < 3.5:
                                    flank_side = 0.4 if (self.bot_idx % 2 == 0) else -0.4
                                    move_angle = angle_to_tgt + flank_side

                                # --- Human Reaction Latency Neural Micro-Combat Inference (~6.5 Hz) ---
                                if now - self.last_inference_time > 0.15:
                                    self.cached_action_idx = self.predict_neural_action(obs)
                                    self.last_inference_time = now
                                action_idx = self.cached_action_idx

                                # Neural action mapping (0: noop, 1: fwd, 2: back, 3: left, 4: right, 5: strafe_l, 6: strafe_r, 7: jump, 8: target, 9: attack, 10+: abilities)
                                # Tactical range arbitration:
                                # Ranged classes back off if mob is dangerously close (<5m)
                                if is_ranged and dist_to_tgt < 4.5:
                                    retreat_angle = angle_to_tgt + math.pi
                                    self.is_trying_to_move = True
                                    await ws.send(json.dumps(make_move_input(retreat_angle)))
                                elif dist_to_tgt > desired_dist:
                                    self.is_trying_to_move = True
                                    await ws.send(json.dumps(make_move_input(move_angle)))
                                else:
                                    self.is_trying_to_move = False
                                    # Strafe slightly if model recommends strafe, otherwise face target
                                    if action_idx in (5, 6):
                                        strafe_dir = 1.2 if action_idx == 5 else -1.2
                                        await ws.send(json.dumps(make_move_input(angle_to_tgt + strafe_dir)))
                                    else:
                                        smoothed_face = self.smooth_turn_facing(angle_to_tgt, 0.05)
                                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": smoothed_face}))

                                if self.target_id != self.last_sent_target_id:
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": self.target_id}))
                                    self.last_sent_target_id = self.target_id
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                    self.last_attack_cmd_time = now

                                elif now - self.last_attack_cmd_time > 3.5:
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                    self.last_attack_cmd_time = now

                                # Class ability execution guided by neural policy and class kit
                                ability_map = {
                                    "warrior": "heroic_strike",
                                    "paladin": "hammer_of_grace",
                                    "mage": "fireball",
                                    "priest": "smite",
                                    "hunter": "raptor_strike",
                                    "rogue": "sinister_strike",
                                    "warlock": "shadow_bolt",
                                    "druid": "wrath",
                                    "shaman": "lightning_bolt",
                                }
                                # Map starter level-1 class attack abilities
                                chosen_ability = ability_map.get(self.player_class, "heroic_strike")
                                if self.player_class == "mage" and dist_to_tgt > 8.0 and random.random() < 0.4:
                                    chosen_ability = "frostbolt"  # tactical slow
                                elif self.player_class == "priest" and my_hp_pct < 0.5:
                                    chosen_ability = "lesser_heal"
                                elif self.player_class == "paladin" and dist_to_tgt > 4.0:
                                    chosen_ability = "judgement"

                                if now - self.last_cast_time > random.uniform(1.5, 1.8):
                                    cast_dur = 2.1 if chosen_ability in ("smite", "shadow_bolt") else (1.6 if chosen_ability in ("fireball", "frostbolt") else 0.0)
                                    if cast_dur > 0:
                                        self.cast_freeze_until = now + cast_dur
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "cast", "ability": chosen_ability}))
                                    self.last_cast_time = now
                            elif target_ent and (target_ent.get("dead") or target_ent.get("loot")):
                                # Target died - release lock and let team transition smoothly
                                self.target_id = None
                                self.is_trying_to_move = False

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

                                # Sea Crossing Check:
                                # If leader has already crossed to mainland (lx > -200) but follower is still on island (my_x < -200):
                                if lx > -200.0 and my_x < -200.0:
                                    ferry_x, ferry_z = -279.0, -10.0
                                    dist_to_ferry = math.hypot(ferry_x - my_x, ferry_z - my_z)
                                    angle_to_ferry = math.atan2(ferry_x - my_x, ferry_z - my_z)

                                    if dist_to_ferry <= 5.5 and now - self.last_quest_action_time > 1.5:
                                        bell_id = None
                                        for eid, e in self.entities.items():
                                            if e.get("objectItemId") == "ps_ferry_bell" or "ferry" in str(e.get("name", "")).lower():
                                                bell_id = eid
                                                break
                                        if bell_id is not None:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": bell_id}))
                                        else:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                        self.last_quest_action_time = now

                                    if dist_to_ferry > 2.0:
                                        self.is_trying_to_move = True
                                        await ws.send(json.dumps(make_move_input(angle_to_ferry)))
                                    else:
                                        self.is_trying_to_move = False
                                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.smooth_turn_facing(angle_to_ferry, 0.05)}))
                                    continue

                                # Formation breathing drift
                                base_x, base_z = FORMATION_OFFSETS[self.bot_idx % len(FORMATION_OFFSETS)]
                                drift_x = math.sin(now * 0.7 + self.bot_idx) * 0.35
                                drift_z = math.cos(now * 0.6 + self.bot_idx) * 0.35
                                off_x = base_x + drift_x
                                off_z = base_z + drift_z

                                # Use travel heading so orientation doesn't invert when leader pauses/looks back
                                heading = getattr(self.leader_ref, "travel_heading", lf)
                                slot_x = lx + (off_x * math.cos(heading) + off_z * math.sin(heading))
                                slot_z = lz + (-off_x * math.sin(heading) + off_z * math.cos(heading))

                                dist_to_slot = math.hypot(slot_x - my_x, slot_z - my_z)
                                angle_to_slot = math.atan2(slot_x - my_x, slot_z - my_z)

                                # Follower synchronous quest acceptance & turn-in (staggered human-like)
                                qdone_f = set(self.self_state.get("qdone", []))
                                qlog_list_f = self.self_state.get("qlog", [])
                                qlog_f = {q["questId"]: q for q in qlog_list_f if isinstance(q, dict) and "questId" in q}

                                fgx, fgz, faction, fparam = QuestNavigator.resolve_macro_objective(
                                    my_x, my_z, qdone_f, qlog_f,
                                    waypoint_index=0,
                                    player_class=self.player_class,
                                    is_ghost=self.self_state.get("ghost", False)
                                )

                                self.macro_goal_action = faction
                                self.macro_goal_param = fparam

                                # Follower independent waypoint sprint (Guarantees hitting gauntlet flags!)
                                if faction == "waypoint":
                                    dist_to_wp = math.hypot(fgx - my_x, fgz - my_z)
                                    angle_to_wp = math.atan2(fgx - my_x, fgz - my_z)
                                    if dist_to_wp > 1.2:
                                        self.is_trying_to_move = True
                                        self.travel_heading = angle_to_wp
                                        await ws.send(json.dumps(make_move_input(angle_to_wp)))
                                        continue

                                dist_to_fgoal = math.hypot(fgx - my_x, fgz - my_z)
                                dist_leader_to_fgoal = math.hypot(fgx - lx, fgz - lz)
                                # Follower ONLY steps directly to quest objective if squad is already nearby (within 6.5m)
                                if faction in ("accept", "turnin", "signpost", "buy_pouch", "death_lesson") and (dist_to_fgoal <= 6.5 or dist_leader_to_fgoal <= 6.5) and dist_to_fgoal > 2.2:
                                    angle_to_fgoal = math.atan2(fgx - my_x, fgz - my_z)
                                    self.is_trying_to_move = True
                                    self.travel_heading = angle_to_fgoal
                                    await ws.send(json.dumps(make_move_input(angle_to_fgoal)))
                                    continue

                                # Follower move to crate if squad is at this crate and follower needs to open it
                                if faction == "crate":
                                    from macro.intents.quest_intent import WRECK_LINE_CRATES
                                    q_entry_cr = qlog_f.get("q_ps_the_wreck_line", {})
                                    cr_counts = q_entry_cr.get("counts", [0])
                                    my_cr_cnt = cr_counts[0] if cr_counts else 0
                                    min_cr = self.get_squad_min_crate_count() if self.leader_ref else my_cr_cnt
                                    if my_cr_cnt <= min_cr and min_cr < len(WRECK_LINE_CRATES):
                                        cx, cz = WRECK_LINE_CRATES[min_cr]
                                        d_to_crate = math.hypot(cx - my_x, cz - my_z)
                                        if d_to_crate > 2.0:
                                            a_crate = math.atan2(cx - my_x, cz - my_z)
                                            self.is_trying_to_move = True
                                            self.travel_heading = a_crate
                                            await ws.send(json.dumps(make_move_input(a_crate)))
                                            continue

                                if dist_to_fgoal <= 8.5 and now - self.last_quest_action_time > 1.5:
                                    if faction == "accept":
                                        await asyncio.sleep(random.uniform(0.3, 0.8))
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "accept", "quest": fparam}))
                                        self.last_quest_action_time = now
                                    elif faction == "turnin":
                                        await asyncio.sleep(random.uniform(0.3, 0.8))
                                        if fparam == "q_ps_set_sail":
                                            odo_id = self.find_entity_id(["odo", "ferryman_odo", "ferryman"])
                                            if odo_id is None:
                                                for eid, e in self.entities.items():
                                                    if math.hypot(e.get("x", 0) - (-284.0), e.get("z", 0) - (-9.0)) < 6.0 and (e.get("k") == "npc" or "npc" in str(e)):
                                                        odo_id = eid
                                                        break
                                            if odo_id is not None:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": int(odo_id)}))
                                            else:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                            await asyncio.sleep(0.3)
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "turnin", "quest": fparam}))
                                        self.last_quest_action_time = now
                                    elif faction == "ability_drill":
                                        self.last_quest_action_time = now
                                        effigy_id = self.find_entity_id(["effigy", "training_effigy"])
                                        if effigy_id is not None:
                                            self.target_id = effigy_id
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": effigy_id}))
                                            cast_dur = 1.8 if fparam in ("fireball", "smite", "shadow_bolt") else 0.0
                                            if cast_dur > 0:
                                                self.cast_freeze_until = now + cast_dur
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "cast", "ability": fparam}))
                                            if cast_dur == 0.0:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                    elif faction == "crab_boss":
                                        crab_id = self.find_entity_id(["mister_crabs", "crabs", "crab"])
                                        if crab_id is not None:
                                            crab_ent = self.entities.get(crab_id, {})
                                            if not crab_ent.get("dead") and not crab_ent.get("loot"):
                                                if self.target_id != crab_id:
                                                    self.target_id = crab_id
                                                    self.last_sent_target_id = crab_id
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": int(crab_id)}))
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                                    self.last_attack_cmd_time = now
                                            elif crab_ent.get("loot"):
                                                cx = crab_ent.get("x", my_x)
                                                cz = crab_ent.get("z", my_z)
                                                if math.hypot(cx - my_x, cz - my_z) <= 4.5 and now - self.last_loot_time > 1.2:
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "loot", "id": int(crab_id)}))
                                                    self.last_loot_time = now
                                    elif faction == "crate":
                                        from macro.intents.quest_intent import WRECK_LINE_CRATES
                                        q_entry_cr = qlog_f.get("q_ps_the_wreck_line", {})
                                        cr_counts = q_entry_cr.get("counts", [0])
                                        my_cr_cnt = cr_counts[0] if cr_counts else 0
                                        min_cr = self.get_squad_min_crate_count() if self.leader_ref else my_cr_cnt

                                        # Only interact if this follower hasn't opened this crate yet
                                        if my_cr_cnt <= min_cr and now - self.last_quest_action_time > 2.0:
                                            crate_id = None
                                            nearest_d = 4.5
                                            for eid, e in self.entities.items():
                                                if e.get("objectItemId") == "ps_castaway_crate" or "crate" in str(e.get("name", "")).lower():
                                                    d = math.hypot(e.get("x", 0) - my_x, e.get("z", 0) - my_z)
                                                    if d < nearest_d:
                                                        nearest_d = d
                                                        crate_id = eid
                                            if crate_id is not None:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": crate_id}))
                                            else:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                            self.last_quest_action_time = now
                                    elif faction == "buy_pouch":
                                        finch_id = self.find_entity_id(["quartermaster_finch", "finch", "quartermaster"])
                                        if finch_id is None:
                                            for eid, e in self.entities.items():
                                                if math.hypot(e.get("x", 0) - (-312.0), e.get("z", 0) - 57.2) < 6.0 and (e.get("k") == "npc" or "npc" in str(e)):
                                                    finch_id = eid
                                                    break
                                        if finch_id is not None:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "buy", "npc": int(finch_id), "item": "linen_pouch"}))
                                            await asyncio.sleep(0.5)
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "equip_bag", "item": "linen_pouch", "socket": 0}))
                                        self.last_quest_action_time = now
                                    elif faction == "signpost":
                                        board_id = self.find_entity_id(["noticeboard", "signpost", "proving_shore_noticeboard"])
                                        if board_id is None:
                                            for eid, e in self.entities.items():
                                                if eid == 2000000002 or math.hypot(e.get("x", 0) - (-312.0), e.get("z", 0) - 41.0) < 6.0:
                                                    board_id = eid
                                                    break
                                        if board_id is not None:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": int(board_id)}))
                                        else:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": 2000000002}))
                                        self.last_quest_action_time = now
                                    elif faction == "death_lesson":
                                        if not self.self_state.get("dead") and not self.self_state.get("ghost"):
                                            if now - self.last_quest_action_time > 2.0:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "use", "item": "ps_passing_stone"}))
                                                self.last_quest_action_time = now
                                    elif faction == "ferry" and (lx > -200.0):
                                        bell_id = self.find_entity_id(["ferry_bell", "bell", "ps_ferry_bell"])
                                        if bell_id is None:
                                            for eid, e in self.entities.items():
                                                if math.hypot(e.get("x", 0) - (-279.0), e.get("z", 0) - (-10.0)) < 6.0:
                                                    bell_id = eid
                                                    break
                                        if bell_id is not None:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": int(bell_id)}))
                                        else:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                        self.last_quest_action_time = now

                                is_casting = (now < self.cast_freeze_until) or (self.self_state.get("castRemaining", 0) > 0) or bool(self.self_state.get("castingAbility"))
                                if is_casting:
                                    self.is_trying_to_move = False
                                    await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.self_state.get("f", 0.0)}))
                                    continue

                                if dist_to_slot > 1.8:
                                    self.is_trying_to_move = True
                                    await ws.send(json.dumps(make_move_input(angle_to_slot)))
                                else:
                                    self.is_trying_to_move = False
                                    smoothed_lf = self.smooth_turn_facing(heading, 0.05)
                                    await ws.send(json.dumps({"t": "input", "mi": {}, "facing": smoothed_lf}))

                            # D. Autonomous Quest & World Navigation (Leader / Solo)
                            elif not target_ent and self.is_leader:
                                qdone = set(self.self_state.get("qdone", []))
                                qlog_list = self.self_state.get("qlog", [])
                                qlog = {q["questId"]: q for q in qlog_list if isinstance(q, dict) and "questId" in q}

                                goal_x, goal_z, goal_action, goal_param = QuestNavigator.resolve_macro_objective(
                                    my_x, my_z, qdone, qlog,
                                    waypoint_index=wp_idx,
                                    player_class=self.player_class,
                                    is_ghost=self.self_state.get("ghost", False)
                                )

                                self.macro_goal_action = goal_action
                                self.macro_goal_param = goal_param

                                # Squad Accept Barrier: Don't march away until squad has accepted current quest
                                active_quests = [q["questId"] for q in qlog_list if isinstance(q, dict) and q.get("state") == "active"]
                                if active_quests and len(self.all_bots_ref) > 1:
                                    latest_quest = active_quests[-1]
                                    squad_accepted, not_accepted = self.is_squad_ready_for_accept(latest_quest)
                                    if not squad_accepted and goal_action != "accept":
                                        if now - self.last_chat_time > 8.0:
                                            names_str = "、".join(not_accepted[:2])
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p 来NPC这里接任务，等下{names_str}"}))
                                            self.last_chat_time = now
                                        self.is_trying_to_move = False
                                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.self_state.get("f", 0.0)}))
                                        continue

                                # Squad Crate Progression Barrier: Keep squad together on each crate!
                                if goal_action == "crate" and len(self.all_bots_ref) > 1:
                                    from macro.intents.quest_intent import WRECK_LINE_CRATES
                                    min_c = self.get_squad_min_crate_count()
                                    if min_c < len(WRECK_LINE_CRATES):
                                        cx, cz = WRECK_LINE_CRATES[min_c]
                                        goal_x, goal_z = cx, cz
                                        goal_action = "crate"
                                        goal_param = f"Crate #{min_c + 1}"
                                        self.macro_goal_action = goal_action
                                        self.macro_goal_param = goal_param

                                # Squad Turn-in Barrier & Strategic Hunt Fallback:
                                if goal_action == "turnin" and len(self.all_bots_ref) > 1:
                                    squad_ready, lagging = self.is_squad_ready_for_turnin(goal_param)
                                    if not squad_ready:
                                        from macro.intents.quest_intent import PROVING_SHORE_QUESTS
                                        qinfo = PROVING_SHORE_QUESTS.get(goal_param, {})
                                        if "hunt_pos" in qinfo:
                                            hx, hz = qinfo["hunt_pos"]
                                            goal_x, goal_z = hx, hz
                                            goal_action = "hunt"
                                            goal_param = qinfo.get("target", "training_effigy")
                                            self.macro_goal_action = goal_action
                                            self.macro_goal_param = goal_param
                                            if now - self.last_chat_time > 10.0:
                                                names_str = "、".join(lagging[:2])
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p 走，回去帮{names_str}补齐任务目标"}))
                                                self.last_chat_time = now
                                        else:
                                            dist_to_turnin = math.hypot(goal_x - my_x, goal_z - my_z)
                                            if dist_to_turnin <= 5.0:
                                                if now - self.last_chat_time > 8.0:
                                                    names_str = "、".join(lagging[:2])
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p 稍等下，等{names_str}赶上任务进度"}))
                                                    self.last_chat_time = now
                                                self.is_trying_to_move = False
                                                await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.self_state.get("f", 0.0)}))
                                                continue

                                # Proactive hunt target scanning: acquire target at range
                                if goal_action in ("hunt", "ability_drill"):
                                    hunt_term = goal_param.lower().replace("_", " ")
                                    chosen_id = None
                                    nearest_d = float("inf")
                                    chosen_ent = None
                                    for eid, ent in self.entities.items():
                                        if ent.get("dead") or ent.get("loot"):
                                            continue
                                        nm = str(ent.get("template") or ent.get("tid") or ent.get("nm") or ent.get("name") or "").lower().replace("_", " ")
                                        is_effigy = (goal_param == "training_effigy" or "effigy" in goal_param) and (ent.get("dummy") or "effigy" in nm)
                                        if is_effigy or hunt_term in nm or any(w in nm for w in hunt_term.split() if len(w) > 3):
                                            d = math.hypot(ent.get("x", 0) - my_x, ent.get("z", 0) - my_z)
                                            if d < nearest_d:
                                                nearest_d = d
                                                chosen_id = eid
                                                chosen_ent = ent
                                    if chosen_id is not None and nearest_d <= 25.0:
                                        if self.target_id != chosen_id:
                                            self.target_id = chosen_id
                                            self.last_sent_target_id = chosen_id
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": chosen_id}))
                                            if now - self.last_attack_cmd_time > 3.0:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                                self.last_attack_cmd_time = now
                                            print(f"  [Quest] Leader acquired hunt target '{goal_param}' (#{chosen_id}) at {nearest_d:.1f}m!")
                                        if chosen_ent is not None:
                                            goal_x = chosen_ent.get("x", goal_x)
                                            goal_z = chosen_ent.get("z", goal_z)

                                dist_to_goal = math.hypot(goal_x - my_x, goal_z - my_z)
                                angle_to_goal = math.atan2(goal_x - my_x, goal_z - my_z)

                                # Check if reached goal for quest action
                                if dist_to_goal <= 4.0 and now - self.last_quest_action_time > 2.0:
                                    # Human-like reading hesitation before clicking accept/turnin
                                    if now < self.npc_reading_until:
                                        self.is_trying_to_move = False
                                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.smooth_turn_facing(angle_to_goal, 0.05)}))
                                        continue

                                    if self.npc_reading_until == 0.0 and goal_action in ("accept", "turnin", "ferry"):
                                        self.npc_reading_until = now + random.uniform(0.8, 1.6)
                                        continue

                                    self.npc_reading_until = 0.0

                                    if goal_action == "accept":
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "accept", "quest": goal_param}))
                                        print(f"  [Quest] Leader accepted '{goal_param}' from NPC!")
                                        self.last_quest_action_time = now
                                        # Generous reading pause so squad followers accept synchronously
                                        self.npc_reading_until = now + random.uniform(3.0, 5.0)
                                        if random.random() < 0.5:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "emote", "emote": "salute"}))

                                    elif goal_action == "turnin":
                                        # Squad Turn-in Barrier: Ensure all members ready before leader turns in
                                        squad_ready, lagging = self.is_squad_ready_for_turnin(goal_param)
                                        if not squad_ready:
                                            # If lagging members need mob kills, lead squad back to hunt location!
                                            from macro.intents.quest_intent import PROVING_SHORE_QUESTS
                                            qinfo = PROVING_SHORE_QUESTS.get(goal_param, {})
                                            if "hunt_pos" in qinfo:
                                                hx, hz = qinfo["hunt_pos"]
                                                # Temporarily redirect leader back to hunt zone
                                                self.macro_goal_action = "hunt"
                                                self.macro_goal_param = qinfo.get("target", "training_effigy")
                                                angle_to_hunt = math.atan2(hx - my_x, hz - my_z)
                                                self.is_trying_to_move = True
                                                self.travel_heading = angle_to_hunt
                                                await ws.send(json.dumps(make_move_input(angle_to_hunt)))
                                                if now - self.last_chat_time > 10.0:
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": "/p 走，回去帮队友把怪补齐"}))
                                                    self.last_chat_time = now
                                                continue

                                            if now - self.last_chat_time > 8.0:
                                                names_str = "、".join(lagging[:2])
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p 稍等下，等{names_str}赶上任务进度"}))
                                                self.last_chat_time = now
                                            self.is_trying_to_move = False
                                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.smooth_turn_facing(angle_to_goal, 0.05)}))
                                            continue

                                        if goal_param == "q_ps_set_sail":
                                            odo_id = self.find_entity_id(["odo", "ferryman_odo", "ferryman"])
                                            if odo_id is None:
                                                for eid, e in self.entities.items():
                                                    if math.hypot(e.get("x", 0) - (-284.0), e.get("z", 0) - (-9.0)) < 6.0 and (e.get("k") == "npc" or "npc" in str(e)):
                                                        odo_id = eid
                                                        break
                                            if odo_id is not None:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": int(odo_id)}))
                                            else:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                            await asyncio.sleep(0.3)
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "turnin", "quest": goal_param}))
                                        print(f"  [Quest] Leader turned in & completed '{goal_param}'!")
                                        self.last_quest_action_time = now
                                        self.npc_reading_until = now + random.uniform(2.5, 4.0)
                                        vic_msg = random.choice(CHAT_VICTORY_LINES)
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": f"/p {vic_msg}"}))
                                        await ws.send(json.dumps({"t": "cmd", "cmd": "emote", "emote": "cheer"}))

                                    elif goal_action == "hunt":
                                        # Active hunt target acquisition
                                        hunt_term = goal_param.lower().replace("_", " ")
                                        chosen_id = None
                                        nearest_d = float("inf")
                                        for eid, ent in self.entities.items():
                                            if ent.get("dead") or ent.get("loot"):
                                                continue
                                            nm = str(ent.get("template") or ent.get("tid") or ent.get("nm") or ent.get("name") or "").lower().replace("_", " ")
                                            is_effigy = (goal_param == "training_effigy") and (ent.get("dummy") or "effigy" in nm)
                                            if is_effigy or hunt_term in nm or any(w in nm for w in hunt_term.split() if len(w) > 3):
                                                d = math.hypot(ent.get("x", 0) - my_x, ent.get("z", 0) - my_z)
                                                if d < nearest_d:
                                                    nearest_d = d
                                                    chosen_id = eid

                                        if chosen_id is not None and nearest_d <= 25.0:
                                            if self.target_id != chosen_id:
                                                self.target_id = chosen_id
                                                self.last_sent_target_id = chosen_id
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": chosen_id}))
                                                if now - self.last_attack_cmd_time > 3.0:
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                                    self.last_attack_cmd_time = now
                                                self.last_quest_action_time = now
                                                print(f"  [Quest] Leader locked & engaged hunt target '{goal_param}' (#{chosen_id}) at {nearest_d:.1f}m!")

                                    elif goal_action == "ability_drill":
                                        self.last_quest_action_time = now
                                        effigy_id = self.find_entity_id(["effigy", "training_effigy"])
                                        if effigy_id is not None:
                                            self.target_id = effigy_id
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": effigy_id}))
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "cast", "ability": goal_param}))
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                            print(f"  [Quest] Landing ability drill '{goal_param}' on effigy #{effigy_id}!")

                                    elif goal_action == "crab_boss":
                                        crab_id = self.find_entity_id(["mister_crabs", "crabs", "crab"])
                                        if crab_id is not None:
                                            crab_ent = self.entities.get(crab_id, {})
                                            if not crab_ent.get("dead") and not crab_ent.get("loot"):
                                                if self.target_id != crab_id:
                                                    self.target_id = crab_id
                                                    self.last_sent_target_id = crab_id
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": int(crab_id)}))
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                                                    self.last_attack_cmd_time = now
                                                    print(f"  [Quest] Leader locked & engaged boss Mister Crabs (#{crab_id})!")
                                            elif crab_ent.get("loot"):
                                                cx = crab_ent.get("x", my_x)
                                                cz = crab_ent.get("z", my_z)
                                                if math.hypot(cx - my_x, cz - my_z) <= 4.5 and now - self.last_loot_time > 1.2:
                                                    await ws.send(json.dumps({"t": "cmd", "cmd": "loot", "id": int(crab_id)}))
                                                    self.last_loot_time = now
                                                    print(f"  [Quest] Looted Lustrous Pearl from Mister Crabs!")
                                        else:
                                            # If near tide pool summon spot (-398.0, -17.0), use lure
                                            if math.hypot(my_x - (-398.0), my_z - (-17.0)) < 12.0 and now - self.last_quest_action_time > 4.0:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "use", "item": "ps_briny_lure"}))
                                                print(f"  [Quest] Used Briny Lure at tide pool to summon Mister Crabs!")
                                                self.last_quest_action_time = now

                                    elif goal_action == "crate":
                                        from macro.intents.quest_intent import WRECK_LINE_CRATES
                                        q_entry_cr = qlog.get("q_ps_the_wreck_line", {})
                                        cr_counts = q_entry_cr.get("counts", [0])
                                        my_cr_cnt = cr_counts[0] if cr_counts else 0
                                        min_cr = self.get_squad_min_crate_count() if len(self.all_bots_ref) > 1 else my_cr_cnt

                                        # Only interact if leader hasn't opened this crate yet
                                        if my_cr_cnt <= min_cr and now - self.last_quest_action_time > 2.0:
                                            crate_id = None
                                            nearest_d = 4.5
                                            for eid, e in self.entities.items():
                                                if e.get("objectItemId") == "ps_castaway_crate" or "crate" in str(e.get("name", "")).lower():
                                                    d = math.hypot(e.get("x", 0) - my_x, e.get("z", 0) - my_z)
                                                    if d < nearest_d:
                                                        nearest_d = d
                                                        crate_id = eid
                                            if crate_id is not None:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": crate_id}))
                                            else:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                            print(f"  [Quest] Opened Castaway Crate ({goal_param})!")
                                            self.last_quest_action_time = now

                                    elif goal_action == "buy_pouch":
                                        finch_id = self.find_entity_id(["quartermaster_finch", "finch", "quartermaster"])
                                        if finch_id is None:
                                            for eid, e in self.entities.items():
                                                if math.hypot(e.get("x", 0) - (-312.0), e.get("z", 0) - 57.2) < 6.0 and (e.get("k") == "npc" or "npc" in str(e)):
                                                    finch_id = eid
                                                    break
                                        if finch_id is not None:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "buy", "npc": int(finch_id), "item": "linen_pouch"}))
                                            await asyncio.sleep(0.5)
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "equip_bag", "item": "linen_pouch", "socket": 0}))
                                            print(f"  [Quest] Bought & equipped Linen Pouch from Finch (#{finch_id})!")
                                        self.last_quest_action_time = now

                                    elif goal_action == "signpost":
                                        board_id = self.find_entity_id(["noticeboard", "signpost", "proving_shore_noticeboard"])
                                        if board_id is None:
                                            for eid, e in self.entities.items():
                                                if eid == 2000000002 or math.hypot(e.get("x", 0) - (-312.0), e.get("z", 0) - 41.0) < 6.0:
                                                    board_id = eid
                                                    break
                                        if board_id is not None:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": int(board_id)}))
                                        else:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": 2000000002}))
                                        print(f"  [Quest] Inspected guild signpost (#{board_id})!")
                                        self.last_quest_action_time = now

                                    elif goal_action == "death_lesson":
                                        if not self.self_state.get("dead") and not self.self_state.get("ghost"):
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "use", "item": "ps_passing_stone"}))
                                            print(f"  [Quest] Used Passing Stone for the death lesson!")
                                            self.last_quest_action_time = now

                                    elif goal_action == "ferry":
                                        squad_at_pier = True
                                        if len(self.all_bots_ref) > 1:
                                            for b in self.all_bots_ref:
                                                if b == self or b.pid < 0:
                                                    continue
                                                if "q_ps_set_sail" not in set(b.self_state.get("qdone", [])):
                                                    squad_at_pier = False
                                                    break
                                                b_x = b.self_state.get("x", 0)
                                                b_z = b.self_state.get("z", 0)
                                                if math.hypot(b_x - (-279.0), b_z - (-10.0)) > 12.0:
                                                    squad_at_pier = False
                                                    break
                                        if not squad_at_pier:
                                            if now - self.last_chat_time > 8.0:
                                                await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": "/p 码头集合，准备敲钟起航！"}))
                                                self.last_chat_time = now
                                            self.is_trying_to_move = False
                                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.smooth_turn_facing(angle_to_goal, 0.05)}))
                                            continue

                                        await ws.send(json.dumps({"t": "cmd", "cmd": "chat", "text": "/p 全员到齐！敲响渡船铜钟，前往东溪谷大陆！"}))
                                        bell_id = self.find_entity_id(["ferry_bell", "bell", "ps_ferry_bell"])
                                        if bell_id is None:
                                            for eid, e in self.entities.items():
                                                if math.hypot(e.get("x", 0) - (-279.0), e.get("z", 0) - (-10.0)) < 6.0:
                                                    bell_id = eid
                                                    break
                                        if bell_id is not None:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact", "id": int(bell_id)}))
                                        else:
                                            await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))
                                        print(f"  [Ferry] Ringing Ferry Bell to sail across to Eastbrook mainland!")
                                        self.last_quest_action_time = now

                                    elif goal_action in ("waypoint", "explore"):
                                        wp_idx = (wp_idx + 1) % max(1, len(EASTBROOK_WAYPOINTS))
                                        self.last_quest_action_time = now

                                stop_dist = 1.2 if goal_action == "waypoint" else (2.5 if goal_action in ("hunt", "ability_drill") else 2.2)
                                if dist_to_goal > stop_dist:
                                    self.is_trying_to_move = True
                                    self.travel_heading = angle_to_goal
                                    await ws.send(json.dumps(make_move_input(angle_to_goal)))
                                else:
                                    if goal_action == "hunt" and not self.target_id:
                                        self.is_trying_to_move = False
                                        # Slowly scan / pan camera looking for spawns
                                        scan_angle = (now * 0.4) % (2 * math.pi)
                                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": self.smooth_turn_facing(scan_angle, 0.05)}))
                                    else:
                                        self.is_trying_to_move = False
                                        smoothed_goal = self.smooth_turn_facing(angle_to_goal, 0.05)
                                        await ws.send(json.dumps({"t": "input", "mi": {}, "facing": smoothed_goal}))

                                if now - last_log_time > 5.0:
                                    print(f"  [Explore] Leader '{self.char_name}' pos=({my_x:.1f}, {my_z:.1f}) -> Objective: {goal_action} ({goal_param}) at ({goal_x:.1f}, {goal_z:.1f}), dist={dist_to_goal:.1f}")
                                    last_log_time = now

                    async def safe_control_loop():
                        while True:
                            try:
                                await control_loop()
                                break
                            except asyncio.CancelledError:
                                break
                            except Exception as err:
                                if isinstance(err, (websockets.exceptions.ConnectionClosed, ConnectionResetError, BrokenPipeError, OSError)):
                                    raise
                                print(f"  [Bot #{self.bot_idx + 1} '{self.char_name}'] Auto-recovered from transient control loop error: {err}")
                                await asyncio.sleep(0.5)

                    recv_task = asyncio.create_task(receive_loop())
                    ctrl_task = asyncio.create_task(safe_control_loop())
                    try:
                        done, pending = await asyncio.wait(
                            [recv_task, ctrl_task],
                            return_when=asyncio.FIRST_EXCEPTION
                        )
                        for t in pending:
                            t.cancel()
                            try:
                                await t
                            except (asyncio.CancelledError, Exception):
                                pass
                        for t in done:
                            exc = t.exception()
                            if exc:
                                raise exc
                    finally:
                        for t in (recv_task, ctrl_task):
                            if not t.done():
                                t.cancel()
            except (websockets.exceptions.ConnectionClosed, ConnectionResetError, BrokenPipeError, OSError) as e:
                if not self.running:
                    break
                print(f"  [Bot #{self.bot_idx + 1} '{self.char_name}'] Network reset/disconnected ({type(e).__name__}). Reconnecting in {reconnect_delay:.1f}s...")
                self.pid = -1
                self.last_sent_target_id = None
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(8.0, reconnect_delay * 1.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if not self.running:
                    break
                print(f"  [Bot #{self.bot_idx + 1} '{self.char_name}'] Unexpected error: {e}. Reconnecting in {reconnect_delay:.1f}s...")
                self.pid = -1
                self.last_sent_target_id = None
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(8.0, reconnect_delay * 1.5)


async def main_async(args):
    # 1. Health check
    print(f"[*] Checking server availability at {args.server}...")
    if not check_server_health(args.server):
        print(f"[!] Warning: Server at {args.server} did not respond to health check.")
        print(f"    Please make sure the World of ClaudeCraft server is running and reachable.")
        print(f"    (e.g., run 'npm run dev' on port 8787)\n")
    else:
        print(f"[OK] Game server is online and responding!\n")

    # 2. Initialize Multi-Class Neural Policy Pool
    models_dir = args.models_dir or os.path.dirname(args.model)
    print(f"[*] Initializing Class-Specific Neural Policy Pool from: {models_dir}")
    policy_pool = ClassPolicyPool(models_dir=models_dir, default_model_path=args.model)

    # 3. Create Bot Instances with Class-Specific Neural Policies
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
        # Bind dedicated class policy
        class_policy = policy_pool.get_policy(pclass)

        bot = SingleBotInstance(
            bot_idx=idx,
            server_url=args.server,
            name=args.name,
            player_class=pclass,
            role=role,
            policy=class_policy,
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

    # 4. Run all bots concurrently with individual supervisor
    async def run_supervised(bot_inst):
        while True:
            try:
                await bot_inst.run(bots)
                break
            except asyncio.CancelledError:
                break
            except Exception as exc:
                print(f"  [Supervisor] Player #{bot_inst.bot_idx + 1} '{bot_inst.char_name}' error: {exc}. Restarting in 2s...")
                await asyncio.sleep(2.0)

    await asyncio.gather(
        *(run_supervised(bot) for bot in bots),
        squad_watchdog_task(bots),
        return_exceptions=True,
    )



async def squad_watchdog_task(bots: list[SingleBotInstance]):
    """Headless macro deadlock watchdog: detects softlocks and triggers automated recovery."""
    print("  [*] Headless Macro Deadlock Watchdog activated (cadence: 2.5s).")
    last_states = {}
    last_progress_time = {}

    while True:
        await asyncio.sleep(2.5)
        now = time.time()
        for b in bots:
            if b.pid < 0 or not b.self_state:
                continue

            qdone_len = len(b.self_state.get("qdone", []))
            qlog_summary = tuple(
                (q.get("questId", ""), q.get("state", ""), tuple(q.get("counts", [])))
                for q in b.self_state.get("qlog", [])
                if isinstance(q, dict)
            )
            fp = (b.macro_goal_action, b.macro_goal_param, qdone_len, qlog_summary)

            if b.pid not in last_states or last_states[b.pid] != fp:
                last_states[b.pid] = fp
                last_progress_time[b.pid] = now
            else:
                elapsed = now - last_progress_time[b.pid]
                in_combat = bool(b.self_state.get("inCombat"))
                is_resting = (b.team_state == "RESTING")

                if elapsed > 16.0 and not in_combat and not is_resting:
                    my_x = b.self_state.get("x", 0.0)
                    my_z = b.self_state.get("z", 0.0)
                    print(
                        f"\n  [WATCHDOG SOFTLOCK ALERT] Bot #{b.bot_idx + 1} '{b.char_name}' "
                        f"stagnant in [{b.macro_goal_action}: {b.macro_goal_param}] for {elapsed:.1f}s at ({my_x:.1f}, {my_z:.1f})!"
                    )
                    print(f"    - Quest Log: {b.self_state.get('qlog', [])}")
                    print(f"    - Quests Done: {list(b.self_state.get('qdone', []))}")
                    print(f"    - Team State: {b.team_state}, Target ID: {b.target_id}")

                    # Active recovery
                    b.npc_reading_until = 0.0
                    b.last_quest_action_time = 0.0
                    b.team_state = "READY"
                    b.regroup_wait_start = 0.0
                    b.stuck_ticks = 4

                    # If follower completely missed first quest, attempt an accept command directly if near Tam
                    if b.macro_goal_action == "accept" and b.macro_goal_param == "q_ps_the_gauntlet":
                        tam_dist = ((my_x - (-283.0))**2 + (my_z - (-21.0))**2)**0.5
                        if tam_dist <= 15.0:
                            if b.ws and b.ws.open:
                                asyncio.create_task(b.ws.send(json.dumps({"t": "cmd", "cmd": "accept", "quest": "q_ps_the_gauntlet"})))

                    if b.target_id and b.target_id in b.entities:
                        tgt = b.entities[b.target_id]
                        if tgt.get("dead") or tgt.get("loot"):
                            b.target_id = None

                    last_progress_time[b.pid] = now - 6.0


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
        help="Number of bots to spawn (default: 5).\nBots automatically cover the 9 MMORPG classes.",
    )
    parser.add_argument(
        "-m", "--model",
        type=str,
        default=os.path.join(_HERE, "models", "woc_policy_3m.pth"),
        help="Path to baseline or default .pth model file.\nDefault: python/models/woc_policy_3m.pth",
    )
    parser.add_argument(
        "--models-dir",
        type=str,
        default=os.path.join(_HERE, "models"),
        help="Directory containing class-specific neural policies (e.g. policy_mage.pth).\nDefault: python/models",
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
        choices=["auto", "warrior", "paladin", "priest", "mage", "hunter", "rogue", "warlock", "druid", "shaman"],
        help="Class for bots. 'auto' assigns all 9 classes in rotation.\nChoices: auto, warrior, paladin, priest, mage, hunter, rogue, warlock, druid, shaman.",
    )

    args = parser.parse_args()
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n[!] Disconnecting all bots and shutting down gracefully.")


if __name__ == "__main__":
    main()
