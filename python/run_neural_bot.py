"""Multi-Agent Neural Bot Client for World of ClaudeCraft.

Features:
- Health check and friendly connection diagnostics for the server URL.
- Zero-CLI Dynamic Mode Switching:
  * Solo Mode: single bot autonomous micro-combat, survival, and questing.
  * Squad Mode: multi-agent coordination, party vitals, post-combat rest/eat/drink,
    lagging tethering wait, threat peel, smart healing, and assist focus-fire.
- Autonomous Quest & Progression Engine:
  * Dynamic parsing of server quest state (qlog, qdone, NPCs, Camps).
  * Auto-accepts and completes Proving Shore introductory questline.
  * Boards the ferry at Old Pier to sail to Eastbrook mainland.
  * Explores and levels up on Eastbrook Vale with camp grinding and auto-looting.
- Obstacle Vaulting: Automatic jump over fence rails and anti-stuck navigation.
- Extensible Policy Interface: Loads 3M-step PPO policy for micro-combat actions.
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

ACTIONS = [
    "noop", "forward", "back", "turn_left", "turn_right", "strafe_left", "strafe_right", "jump",
    "target_nearest", "attack",
    "ability_1", "ability_2", "ability_3", "ability_4", "ability_5", "ability_6", "ability_7",
    "ability_8", "ability_9", "ability_10", "ability_11", "ability_12", "ability_13", "ability_14",
    "ability_15", "ability_16", "ability_17", "ability_18", "ability_19", "ability_20", "ability_21",
    "ability_22", "ability_23", "ability_24", "ability_25", "ability_26", "ability_27", "ability_28",
    "ability_29", "ability_30", "ability_31", "ability_32", "ability_33", "ability_34", "ability_35",
    "ability_36", "ability_37", "ability_38", "ability_39", "ability_40", "ability_41", "ability_42",
    "ability_43", "ability_44", "ability_45", "ability_46", "ability_47", "ability_48",
    "interact", "stop", "eat_drink",
]

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

        # Timers
        self.last_rest_time = 0.0
        self.last_loot_time = 0.0
        self.last_quest_action_time = 0.0
        self.last_heal_time = 0.0
        self.last_cast_time = 0.0

        # Obstacle vaulting and anti-stuck tracking
        self.prev_x = 0.0
        self.prev_z = 0.0
        self.stuck_ticks = 0
        self.is_trying_to_move = False

    def register_and_create_char(self):
        uniq = str(int(time.time()))[-4:] + str(self.bot_idx)
        username = f"bot_{self.name.lower()}_{uniq}"
        reg = make_api_post(f"{self.server_url}/api/register", {
            "username": username,
            "password": "botpassword123",
            "email": f"{username}@claudecraft.local",
        })
        self.token = reg["token"]

        clean_prefix = re.sub(r"[^A-Za-z]", "", self.name)[:8] or "Bot"
        role_tag = chr(65 + (self.bot_idx % 26))
        alpha_suffix = "".join(random.choices(string.ascii_lowercase, k=4))
        self.char_name = f"{clean_prefix}{role_tag}{alpha_suffix}"[:16]

        char = make_api_post(f"{self.server_url}/api/characters", {
            "name": self.char_name,
            "class": self.player_class,
        }, token=self.token)
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

        # Target selection: if none chosen, find nearest living mob
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

    async def run(self, all_bots: list[SingleBotInstance]):
        self.register_and_create_char()
        print(f"  [+] Bot #{self.bot_idx + 1} '{self.char_name}' ({self.player_class}/{self.role}) connecting...")

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
                        print(f"  >>> Bot #{self.bot_idx + 1} '{self.char_name}' LIVE in world! (PID: {self.pid})")
                    elif t == "error":
                        print(f"  [!] Bot #{self.bot_idx + 1} '{self.char_name}' server error: {msg.get('error')}")
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
                                await ws.send(json.dumps({"t": "cmd", "cmd": "paccept"}))

            async def control_loop():
                wp_idx = 0
                last_log_time = 0.0

                while True:
                    await asyncio.sleep(0.05)  # 20 Hz tick
                    if not self.self_state or self.pid < 0:
                        continue

                    now = time.time()

                    # Resurrect if dead
                    if self.self_state.get("dead"):
                        await ws.send(json.dumps({"t": "cmd", "cmd": "release"}))
                        await asyncio.sleep(1.0)
                        continue

                    # ---------------------------------------------------------
                    # 1. Dynamic Mode & Party Detection (Zero-CLI Auto-Switching)
                    # ---------------------------------------------------------
                    party_data = self.self_state.get("party")
                    is_grouped = isinstance(party_data, dict) and len(party_data.get("members", [])) >= 2
                    prev_mode = self.mode
                    self.mode = "squad" if is_grouped else "solo"

                    if prev_mode != self.mode and self.bot_idx == 0:
                        print(f"  [*] Mode auto-switched to: [{self.mode.upper()}] (Party members: {len(party_data.get('members', [])) if is_grouped else 1})")

                    if is_grouped:
                        # Server-authoritative party leadership
                        self.is_leader = (party_data.get("leader") == self.pid)
                    else:
                        # Solo mode: bot is its own leader
                        self.is_leader = (self.bot_idx == 0)

                    # Leader invites remaining bots if party is not yet full
                    if self.is_leader and len(all_bots) > 1:
                        for other in all_bots:
                            if other != self and other.pid > 0 and other.pid not in self.party_invited_ids:
                                await ws.send(json.dumps({"t": "cmd", "cmd": "pinvite", "id": other.pid}))
                                self.party_invited_ids.add(other.pid)
                                await asyncio.sleep(0.08)

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

                    def make_move_input(facing: float):
                        mi = {"f": 1}
                        if need_jump:
                            mi["j"] = 1
                        if need_strafe_left:
                            mi["sl"] = 1
                        elif need_strafe_right:
                            mi["sr"] = 1
                        return {"t": "input", "mi": mi, "facing": facing}

                    # ---------------------------------------------------------
                    # 2. Team Vitals & Readiness Arbiter (Leader Mind)
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
                                print(f"  [Squad] Team fully recovered (HP: {min_hp_pct*100:.0f}%, MP: {min_mana_pct*100:.0f}%). Resuming march!")
                            else:
                                team_needs_rest = True
                        else:
                            if not party_in_combat and (min_hp_pct < 0.65 or min_mana_pct < 0.40):
                                self.team_state = "RESTING"
                                team_needs_rest = True
                                print(f"  [Squad] Leader halted squad for Rest & Recovery (Min HP: {min_hp_pct*100:.0f}%, Min MP: {min_mana_pct*100:.0f}%)")

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
                                    print(f"  [Squad] Member '{lagging_member.get('name')}' is lagging behind ({max_dist:.1f}m). Leader holding up!")

                        if team_needs_regroup and member_dists:
                            lagging_member, _ = max(member_dists, key=lambda x: x[1])
                            lx = lagging_member.get("x", my_x)
                            lz = lagging_member.get("z", my_z)
                            lagging_target_facing = math.atan2(lx - my_x, lz - my_z)

                    # Propagate rest state to leader_ref for followers
                    effective_resting = (self.team_state == "RESTING" or (self.leader_ref and self.leader_ref.team_state == "RESTING"))

                    # Handle Eating/Drinking during Rest
                    if effective_resting:
                        my_hp_pct = self.self_state.get("hp", 100) / max(1, self.self_state.get("mhp", 100))
                        my_mana_pct = self.self_state.get("res", 100) / max(1, self.self_state.get("mres", 100))
                        if my_hp_pct < 0.85 or (self.self_state.get("rtype") == "mana" and my_mana_pct < 0.70):
                            if now - self.last_rest_time > 3.0:
                                await ws.send(json.dumps({"t": "cmd", "cmd": "eat_drink"}))
                                self.last_rest_time = now

                        # Halt movement while resting
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
                    # 3. Smart Healing & Threat Peel (Role Coordination)
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
                                # A backline ally is attacked, find mob near them
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
                    # 4. Target Selection & micro-combat
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

                        if now - last_log_time > 4.0:
                            tgt_name = target_ent.get("nm", "enemy")
                            print(f"  [Combat] Bot #{self.bot_idx + 1} '{self.char_name}' fighting {tgt_name} (Dist: {dist_to_tgt:.1f}m)")
                            last_log_time = now

                        is_ranged = self.player_class in ("mage", "hunter", "priest")
                        desired_dist = 11.5 if is_ranged else 2.2

                        if dist_to_tgt > desired_dist:
                            await ws.send(json.dumps(make_move_input(angle_to_tgt)))
                        else:
                            self.is_trying_to_move = False
                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": angle_to_tgt}))

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
                        if now - self.last_cast_time > 1.2:
                            await ws.send(json.dumps({"t": "cmd", "cmd": "cast", "ability": ability, "target": self.target_id}))
                            self.last_cast_time = now

                    # B. Out of Combat Auto-Looting
                    elif not self.self_state.get("inCombat") and now - self.last_loot_time > 1.0:
                        for ent_id, ent in self.entities.items():
                            if ent.get("k") == "mob" and ent.get("loot"):
                                if math.hypot(ent.get("x", 0) - my_x, ent.get("z", 0) - my_z) <= 5.0:
                                    await ws.send(json.dumps({"t": "cmd", "cmd": "loot", "id": ent_id}))
                                    self.last_loot_time = now
                                    break

                    # C. Squad Follower Mode (maintain formation with Leader)
                    if not target_ent and not self.is_leader and self.leader_ref and self.leader_ref.self_state:
                        lx = self.leader_ref.self_state.get("x", my_x)
                        lz = self.leader_ref.self_state.get("z", my_z)
                        lf = self.leader_ref.self_state.get("f", self.leader_ref.self_state.get("facing", 0.0))

                        off_x, off_z = FORMATION_OFFSETS[self.bot_idx % len(FORMATION_OFFSETS)]
                        slot_x = lx + (off_x * math.cos(lf) + off_z * math.sin(lf))
                        slot_z = lz + (-off_x * math.sin(lf) + off_z * math.cos(lf))

                        dist_to_slot = math.hypot(slot_x - my_x, slot_z - my_z)
                        angle_to_slot = math.atan2(slot_x - my_x, slot_z - my_z)

                        if dist_to_slot > 1.8:
                            self.is_trying_to_move = True
                            await ws.send(json.dumps(make_move_input(angle_to_slot)))
                        else:
                            self.is_trying_to_move = False
                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": lf}))

                    # D. Autonomous Quest & World Navigation (Leader / Solo)
                    elif not target_ent and self.is_leader:
                        # Dynamic quest & target objective resolver
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
                        if dist_to_goal <= 3.8 and now - self.last_quest_action_time > 2.0:
                            if goal_action == "accept":
                                await ws.send(json.dumps({"t": "cmd", "cmd": "accept", "quest": goal_param}))
                                print(f"  [Quest] Leader accepted '{goal_param}' from NPC!")
                                self.last_quest_action_time = now
                            elif goal_action == "turnin":
                                await ws.send(json.dumps({"t": "cmd", "cmd": "turnin", "quest": goal_param}))
                                print(f"  [Quest] Leader turned in & completed '{goal_param}'!")
                                self.last_quest_action_time = now
                            elif goal_action == "ferry":
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
                            await ws.send(json.dumps({"t": "input", "mi": {}, "facing": angle_to_goal}))

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

    print(f"[*] Launching {args.count} bots into the world:")
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
        lead_tag = " (Leader)" if is_lead else ""
        print(f"  - {args.name} {role_tag}{lead_tag}")

    print("\nAll bots will enter the world and dynamically coordinate together.")
    print(f"Real players can join or watch at {args.server}!\n")

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
