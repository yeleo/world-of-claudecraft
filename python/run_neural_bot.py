"""Multi-Agent Neural Bot Client for World of ClaudeCraft.

Features:
- Health check and friendly connection diagnostics for the server URL.
- Support for multiple bots (--count 1~5) operating individually or as a coordinated party.
- Automatic party formation (Leader invites, members accept).
- Cohesive team formation (members follow leader when wandering).
- Coordinated focus-fire combat driven by 3M-step PPO neural policy.
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


def check_server_health(server_url: str) -> bool:
    """Probes the server to ensure it is alive before connecting."""
    clean_url = server_url.rstrip("/")
    try:
        # Check /livez or root
        req = urllib.request.Request(f"{clean_url}/livez", headers={"User-Agent": "WoC-BotProbe"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status in (200, 204, 301, 302)
    except urllib.error.HTTPError as e:
        # If /livez is 404, check root url
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
    # Add Origin and User-Agent to satisfy webLoginEnforced (isWebClientRequest)
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

    def register_and_create_char(self):
        uniq = str(int(time.time()))[-4:] + str(self.bot_idx)
        username = f"bot_{self.name.lower()}_{uniq}"
        reg = make_api_post(f"{self.server_url}/api/register", {
            "username": username,
            "password": "botpassword123",
            "email": f"{username}@claudecraft.local",
        })
        self.token = reg["token"]

        # Server validates character names with /^[A-Za-z\u4e00-\u9fa5][A-Za-z\u4e00-\u9fa5' -]{1,15}$/
        # Digits are disallowed. Use letters only.
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
        facing = s.get("facing", 0.0)
        gcd = s.get("gcd", 0.0)

        obs[0] = hp / mhp
        obs[1] = res / mres
        obs[2] = lv / MAX_LEVEL
        obs[3] = x / WORLD_MAX_X
        obs[4] = (z - WORLD_MIN_Z) / (WORLD_MAX_Z - WORLD_MIN_Z)
        obs[5] = math.cos(facing)
        obs[6] = math.sin(facing)
        obs[7] = 1.0 if s.get("combat") else 0.0
        obs[8] = min(1.0, gcd / 1.5)

        # Team/Leader target synchronization: Focus-fire
        chosen_target = None
        if not self.is_leader and self.leader_ref and self.leader_ref.target_id:
            chosen_target = self.entities.get(self.leader_ref.target_id)

        # If no team target, find nearest enemy
        if not chosen_target:
            nearest_dist = float("inf")
            for ent in self.entities.values():
                if ent.get("type") == "mob" and not ent.get("dead"):
                    ex = ent.get("x", 0.0)
                    ez = ent.get("z", 0.0)
                    d = math.hypot(ex - x, ez - z)
                    if d < nearest_dist:
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
            obs[13] = chosen_target.get("level", 1) / MAX_LEVEL
            obs[14] = 0.0
            obs[15] = 0.0
            obs[16] = 1.0
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
                "movementWire": 2,
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
                                self.entities[ent["id"]] = ent
                        keep = set(msg.get("keep", []))
                        for ent_id in list(self.entities.keys()):
                            if ent_id not in keep and ent_id not in [e["id"] for e in msg.get("ents", [])]:
                                self.entities.pop(ent_id, None)
                    elif t == "events":
                        # Auto-accept party invitation
                        for ev in msg.get("list", []):
                            if ev.get("type") == "party_invite" and not self.is_leader:
                                await ws.send(json.dumps({"t": "cmd", "cmd": "paccept"}))

            async def control_loop():
                while True:
                    await asyncio.sleep(0.05)  # 20 Hz tick
                    if not self.self_state or self.pid < 0:
                        continue

                    # Resurrect if dead
                    if self.self_state.get("dead"):
                        await ws.send(json.dumps({"t": "cmd", "cmd": "release"}))
                        await asyncio.sleep(1.0)
                        continue

                    # Leader: invite team members to party once all PIDs are known
                    if self.is_leader:
                        for other in all_bots:
                            if other != self and other.pid > 0 and other.pid not in self.party_invited_ids:
                                await ws.send(json.dumps({"t": "cmd", "cmd": "pinvite", "id": other.pid}))
                                self.party_invited_ids.add(other.pid)
                                await asyncio.sleep(0.2)

                    # Cohesive Formation: If non-leader and too far from leader, steer toward leader
                    my_x = self.self_state.get("x", 0.0)
                    my_z = self.self_state.get("z", 0.0)
                    if not self.is_leader and self.leader_ref and self.leader_ref.self_state:
                        lx = self.leader_ref.self_state.get("x", my_x)
                        lz = self.leader_ref.self_state.get("z", my_z)
                        dist_to_lead = math.hypot(lx - my_x, lz - my_z)
                        # If far from leader and not in direct combat, walk to leader
                        if dist_to_lead > 8.0 and not self.target_id:
                            angle_to_lead = math.atan2(lx - my_x, lz - my_z)
                            await ws.send(json.dumps({"t": "input", "mi": {"f": 1}, "facing": angle_to_lead}))
                            continue

                    # 3M-Step Neural Policy Action Selection
                    obs = self.build_obs()
                    obs_t = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
                    with torch.no_grad():
                        action, _, _, _ = self.policy.get_action_and_value(obs_t)
                        action_idx = action.item()

                    act_name = ACTIONS[action_idx] if action_idx < len(ACTIONS) else "noop"
                    await self.execute_action(ws, act_name)

            await asyncio.gather(receive_loop(), control_loop())

    async def execute_action(self, ws, act_name: str):
        if act_name == "noop":
            return

        # Movement inputs
        mi = {}
        if act_name == "forward":
            mi["f"] = 1
        elif act_name == "back":
            mi["b"] = 1
        elif act_name == "strafe_left":
            mi["sl"] = 1
        elif act_name == "strafe_right":
            mi["sr"] = 1
        elif act_name == "jump":
            mi["j"] = 1

        if mi:
            await ws.send(json.dumps({"t": "input", "mi": mi}))
            return

        # Facing changes
        facing = self.self_state.get("facing", 0.0)
        if act_name == "turn_left":
            await ws.send(json.dumps({"t": "input", "facing": facing - 0.2}))
            return
        elif act_name == "turn_right":
            await ws.send(json.dumps({"t": "input", "facing": facing + 0.2}))
            return

        # Target selection
        if act_name == "target_nearest":
            if self.target_id is not None:
                await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": self.target_id}))
            return

        # Combat attack
        if act_name == "attack":
            if self.target_id is not None:
                await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": self.target_id}))
                await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
            return

        # Class abilities
        if act_name.startswith("ability_"):
            ability_map = {
                "warrior": "heroic_strike",
                "paladin": "seal_of_righteousness",
                "mage": "fireball",
                "priest": "smite",
                "hunter": "arcane_shot",
            }
            ability = ability_map.get(self.player_class, "heroic_strike")
            await ws.send(json.dumps({"t": "cmd", "cmd": "cast", "ability": ability}))
            return

        # Release/Stop
        if act_name == "stop":
            await ws.send(json.dumps({"t": "input", "mi": {}}))
            return


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

    print("\nAll bots will enter the world and form a party together.")
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
