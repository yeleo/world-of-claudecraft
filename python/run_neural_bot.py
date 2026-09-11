"""Bridge client to run a trained PyTorch RL agent in the live World of ClaudeCraft server.

Connects to the game server via REST + WebSocket as a real player entity,
extracts observations from live game state snapshots, and sends neural-policy
actions back to the authoritative server at 20 Hz.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
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
from wow_env import ACTIONS

MAX_LEVEL = 10
WORLD_MAX_X = 140.0
WORLD_MAX_Z = 140.0
WORLD_MIN_Z = 0.0


def make_api_post(url: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


class LiveBotClient:
    def __init__(self, server_url: str, bot_name: str, player_class: str, model_path: str):
        self.server_url = server_url.rstrip("/")
        self.ws_url = self.server_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        self.bot_name = bot_name
        self.player_class = player_class
        self.model_path = model_path
        self.token = ""
        self.char_id = 0
        self.pid = -1

        # State tracking
        self.self_state: dict = {}
        self.entities: dict[int, dict] = {}
        self.target_id: int | None = None

        # Load Model
        print(f"Loading policy from: {model_path}...")
        checkpoint = torch.load(model_path, map_location="cpu")
        obs_dim = checkpoint.get("obs_dim", 607)
        act_dim = checkpoint.get("act_dim", 61)
        self.policy = ActorCritic(obs_dim, act_dim)
        self.policy.load_state_dict(checkpoint["model_state_dict"])
        self.policy.eval()
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        print("Neural policy loaded successfully!")

    def register_and_login(self):
        uniq = str(int(time.time()))[-5:]
        username = f"bot_{self.bot_name.lower()}_{uniq}"
        print(f"Registering bot account '{username}' on {self.server_url}...")
        reg = make_api_post(f"{self.server_url}/api/register", {
            "username": username,
            "password": "botpassword123",
            "email": f"{username}@claudecraft.local",
        })
        self.token = reg["token"]

        print(f"Creating character '{self.bot_name}' ({self.player_class})...")
        char = make_api_post(f"{self.server_url}/api/characters", {
            "name": f"{self.bot_name}{uniq}",
            "class": self.player_class,
        }, token=self.token)
        self.char_id = char["id"]
        print(f"Character ready! CharID: {self.char_id}")

    def build_obs(self) -> np.ndarray:
        """Constructs an observation vector from the current snapshot."""
        s = self.self_state
        obs = np.zeros(self.obs_dim, dtype=np.float32)
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
        dead = 1.0 if s.get("dead") else 0.0

        # Self (16)
        obs[0] = hp / mhp
        obs[1] = res / mres
        obs[2] = lv / MAX_LEVEL
        obs[4] = np.clip(x / WORLD_MAX_X, -1.0, 1.0)
        obs[5] = np.clip((z - (WORLD_MIN_Z + WORLD_MAX_Z) / 2) / ((WORLD_MAX_Z - WORLD_MIN_Z) / 2), -1.0, 1.0)
        obs[6] = math.sin(facing)
        obs[7] = math.cos(facing)
        obs[8] = gcd / 1.5
        obs[10] = dead

        # Target (5)
        mobs = [e for e in self.entities.values() if e.get("k") == "mob" and not e.get("dead")]
        if mobs:
            # Sort by distance
            mobs.sort(key=lambda m: math.hypot(m.get("x", 0.0) - x, m.get("z", 0.0) - z))
            nearest = mobs[0]
            ndist = math.hypot(nearest.get("x", 0.0) - x, nearest.get("z", 0.0) - z)
            obs[16] = 1.0
            obs[17] = nearest.get("hp", 0) / max(1, nearest.get("mhp", 1))
            obs[18] = min(1.0, ndist / 50.0)
            self.target_id = nearest.get("id")
        else:
            self.target_id = None

        return obs

    async def run(self):
        self.register_and_login()
        print(f"Connecting to live WebSocket: {self.ws_url}...")

        async with websockets.connect(self.ws_url) as ws:
            # Send worldAuthMessage
            auth_msg = {
                "t": "auth",
                "token": self.token,
                "charId": self.char_id,
            }
            await ws.send(json.dumps(auth_msg))

            # Receiver loop
            async def receive_loop():
                async for raw in ws:
                    msg = json.loads(raw)
                    t = msg.get("t")
                    if t == "hello":
                        self.pid = msg.get("pid", -1)
                        print(f"\n>>> BOT IS LIVE IN GAME WORLD! (PID: {self.pid}) <<<")
                        print("Other players can now see and interact with this bot at http://localhost:8787!\n")
                    elif t == "snap":
                        if "self" in msg:
                            self.self_state.update(msg["self"])
                        if "ents" in msg:
                            for ent in msg["ents"]:
                                self.entities[ent["id"]] = ent
                        # Remove absent entities
                        keep = set(msg.get("keep", []))
                        for ent_id in list(self.entities.keys()):
                            if ent_id not in keep and ent_id not in [e["id"] for e in msg.get("ents", [])]:
                                self.entities.pop(ent_id, None)

            async def control_loop():
                while True:
                    await asyncio.sleep(0.05)  # 20 Hz tick
                    if not self.self_state or self.pid < 0:
                        continue

                    # If dead, release spirit
                    if self.self_state.get("dead"):
                        await ws.send(json.dumps({"t": "cmd", "cmd": "release"}))
                        await asyncio.sleep(1.0)
                        continue

                    obs = self.build_obs()
                    obs_t = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
                    with torch.no_grad():
                        action, _, _, _ = self.policy.get_action_and_value(obs_t)
                        action_idx = action.item()

                    action_name = ACTIONS[action_idx] if action_idx < len(ACTIONS) else "noop"

                    # Map discrete action to wire format
                    if action_name == "forward":
                        await ws.send(json.dumps({"t": "input", "mi": {"f": 1}}))
                    elif action_name == "back":
                        await ws.send(json.dumps({"t": "input", "mi": {"b": 1}}))
                    elif action_name == "turn_left":
                        await ws.send(json.dumps({"t": "input", "mi": {"tl": 1}}))
                    elif action_name == "turn_right":
                        await ws.send(json.dumps({"t": "input", "mi": {"tr": 1}}))
                    elif action_name == "strafe_left":
                        await ws.send(json.dumps({"t": "input", "mi": {"sl": 1}}))
                    elif action_name == "strafe_right":
                        await ws.send(json.dumps({"t": "input", "mi": {"sr": 1}}))
                    elif action_name == "jump":
                        await ws.send(json.dumps({"t": "input", "mi": {"j": 1}}))
                    elif action_name == "target_nearest":
                        if self.target_id:
                            await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": self.target_id}))
                    elif action_name == "attack":
                        if self.target_id:
                            await ws.send(json.dumps({"t": "cmd", "cmd": "target", "id": self.target_id}))
                            await ws.send(json.dumps({"t": "cmd", "cmd": "attack"}))
                    elif action_name.startswith("ability_"):
                        # Cast class primary ability
                        ability_map = {
                            "warrior": "heroic_strike",
                            "paladin": "seal_of_righteousness",
                            "mage": "fireball",
                            "priest": "smite",
                            "hunter": "arcane_shot",
                        }
                        ability = ability_map.get(self.player_class, "heroic_strike")
                        await ws.send(json.dumps({"t": "cmd", "cmd": "cast", "ability": ability}))
                    elif action_name == "eat_drink":
                        await ws.send(json.dumps({"t": "cmd", "cmd": "use", "item": "spring_water"}))
                    elif action_name == "interact":
                        await ws.send(json.dumps({"t": "cmd", "cmd": "interact"}))

            await asyncio.gather(receive_loop(), control_loop())


def main():
    parser = argparse.ArgumentParser(description="Live Neural Bot for World of ClaudeCraft")
    parser.add_argument("--model", type=str, default=os.path.join(_HERE, "models", "woc_policy_3m.pth"), help="Trained .pth model")
    parser.add_argument("--server", type=str, default="http://localhost:8787", help="Game server URL")
    parser.add_argument("--name", type=str, default="ClaudeBot", help="In-game character name")
    parser.add_argument("--class-name", type=str, default="warrior", help="Player class")
    args = parser.parse_args()

    client = LiveBotClient(args.server, args.name, args.class_name, args.model)
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\nBot disconnected.")


if __name__ == "__main__":
    main()
