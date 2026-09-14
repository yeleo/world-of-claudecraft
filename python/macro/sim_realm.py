"""
Ultra-Fast Headless Game Realm Simulator
Enables sub-second fast-forward simulation of world entities, quests, inventories, and parties.
"""

from __future__ import annotations
import math
from typing import Dict, Any, List, Optional, Callable


class MockWorldRealm:
    """High-speed in-memory simulation of the MMO server environment."""

    def __init__(self):
        self.time_sec = 0.0
        self.entities: Dict[int, Dict[str, Any]] = {}
        self.players: Dict[int, Dict[str, Any]] = {}
        self.next_entity_id = 1000
        self.events: List[Dict[str, Any]] = []

        self._init_static_world()

    def _init_static_world(self):
        """Spawns tutorial NPCs, vendors, and training effigies."""
        # 1. Quest Givers & NPCs
        self.spawn_npc(101, "Overseer Pell", -283.0, -21.0, {"questGiver": True})
        self.spawn_npc(102, "Drillmaster Rook", -345.0, -11.0, {"questGiver": True})
        self.spawn_npc(103, "Quartermaster Dag", -275.0, -15.0, {"vendor": True, "merchant": True})

        # 2. Interactive Objects & Roadside Curiosities
        self.spawn_object(201, "Ferry Bell", -279.0, -10.0, "ps_ferry_bell")
        self.spawn_object(202, "Weathered Memorial Stone", -320.0, -28.0, "scenic_landmark")
        self.spawn_object(203, "Driftwood Supply Crate", -350.0, 18.0, "roadside_crate")
        self.spawn_object(204, "Ancient Anchor Relic", -295.0, -12.0, "ancient_anchor")

        # 3. Training Effigies (Straw Dummies)
        self.spawn_mob(301, "Training Effigy", -336.0, -14.0, hp=120, mhp=120, template="training_effigy")
        self.spawn_mob(302, "Training Effigy", -334.0, -16.0, hp=120, mhp=120, template="training_effigy")

    def spawn_npc(self, eid: int, name: str, x: float, z: float, extra: Dict[str, Any] = None):
        data = {"id": eid, "k": "npc", "nm": name, "x": x, "z": z, "f": 0.0}
        if extra:
            data.update(extra)
        self.entities[eid] = data

    def spawn_object(self, eid: int, name: str, x: float, z: float, object_item_id: str):
        self.entities[eid] = {
            "id": eid, "k": "obj", "nm": name, "x": x, "z": z,
            "objectItemId": object_item_id
        }

    def spawn_mob(self, eid: int, name: str, x: float, z: float, hp: int = 100, mhp: int = 100, template: str = "mob"):
        self.entities[eid] = {
            "id": eid, "k": "mob", "nm": name, "x": x, "z": z, "f": 0.0,
            "hp": hp, "mhp": mhp, "dead": False, "loot": False, "combat": False,
            "template": template
        }

    def register_player(self, pid: int, name: str, pclass: str, x: float = -280.0, z: float = -20.0) -> Dict[str, Any]:
        """Registers a bot into the realm."""
        p_state = {
            "id": pid,
            "pid": pid,
            "k": "player",
            "name": name,
            "nm": name,
            "class": pclass,
            "lv": 1,
            "x": x,
            "y": 0.0,
            "z": z,
            "f": 0.0,
            "hp": 150,
            "mhp": 150,
            "res": 100,
            "mres": 100,
            "rtype": "mana" if pclass in ("mage", "priest", "warlock", "druid", "shaman", "paladin") else ("rage" if pclass == "warrior" else "energy"),
            "dead": False,
            "inCombat": False,
            "party": None,
            "inventory": [None] * 16,
            "equipment": {},
            "qlog": [],
            "qdone": [],
        }
        self.players[pid] = p_state
        self.entities[pid] = p_state
        return p_state

    def step(self, dt: float = 0.05):
        """Advances world time by dt seconds and processes physics/interactions."""
        self.time_sec += dt

        # Respawn dead effigies after 5 seconds
        for ent in self.entities.values():
            if ent.get("k") == "mob" and ent.get("dead"):
                ent["dead_time"] = ent.get("dead_time", 0.0) + dt
                if ent["dead_time"] > 4.0:
                    ent["dead"] = False
                    ent["loot"] = False
                    ent["hp"] = ent["mhp"]
                    ent["dead_time"] = 0.0

        # Server-authoritative Gauntlet Flag Proximity Trigger (mirrors tutorial/gauntlet_run.ts)
        from .intents.quest_intent import GAUNTLET_CHECKPOINTS
        for p in self.players.values():
            for q in p.get("qlog", []):
                if q.get("questId") == "q_ps_the_gauntlet" and q.get("state") != "ready":
                    cur_count = q.get("counts", [0])[0]
                    if cur_count < len(GAUNTLET_CHECKPOINTS):
                        target_flag = GAUNTLET_CHECKPOINTS[cur_count]
                        dist_to_flag = math.hypot(p.get("x", 0.0) - target_flag[0], p.get("z", 0.0) - target_flag[1])
                        if dist_to_flag <= 4.0:
                            q["counts"] = [cur_count + 1]
                            if q["counts"][0] >= len(GAUNTLET_CHECKPOINTS):
                                q["state"] = "ready"

    def process_command(self, pid: int, cmd_payload: Dict[str, Any]):
        """Processes an incoming client WebSocket packet."""
        p = self.players.get(pid)
        if not p:
            return

        t = cmd_payload.get("t")
        if t == "input":
            # Movement update
            mi = cmd_payload.get("mi", {})
            f = cmd_payload.get("facing", p.get("f", 0.0))
            p["f"] = f
            if mi.get("f"):
                speed = 7.0 * 0.05  # 7 m/s * dt
                p["x"] += math.sin(f) * speed
                p["z"] += math.cos(f) * speed

        elif t == "cmd":
            cmd = cmd_payload.get("cmd")
            if cmd == "accept":
                qid = cmd_payload.get("quest")
                if qid and not any(q.get("questId") == qid for q in p["qlog"]):
                    p["qlog"].append({"questId": qid, "state": "active", "counts": [0]})
            elif cmd == "turnin":
                qid = cmd_payload.get("quest")
                p["qlog"] = [q for q in p["qlog"] if q.get("questId") != qid]
                if qid not in p["qdone"]:
                    p["qdone"].append(qid)
                    # Reward class-appropriate upgrade to test gear intent evaluation
                    pclass = p.get("class", "warrior")
                    armor_type = "mail" if pclass in ("warrior", "paladin") else ("leather" if pclass in ("hunter", "rogue", "druid", "shaman") else "cloth")
                    stat_key = "str" if pclass in ("warrior", "paladin") else ("agi" if pclass in ("hunter", "rogue") else "int")
                    p["inventory"][0] = {
                        "name": f"Pell's Honed Chestguard",
                        "kind": "armor",
                        "armorType": armor_type,
                        "slot": "chest",
                        "stats": {stat_key: 5, "sta": 4, "armor": 12},
                        "rarity": "uncommon"
                    }
                    p["inventory"][1] = {
                        "name": "Mother of Pearl",
                        "kind": "ring",
                        "slot": "finger",
                        "stats": {stat_key: 3, "sta": 3},
                        "rarity": "rare"
                    }
            elif cmd == "attack" or cmd == "cast":
                tid = cmd_payload.get("target") or cmd_payload.get("id")
                tgt = self.entities.get(tid)
                if tgt and tgt.get("k") == "mob" and not tgt.get("dead"):
                    dmg = 35
                    tgt["hp"] = max(0, tgt["hp"] - dmg)
                    tgt["combat"] = True
                    p["inCombat"] = True
                    if tgt["hp"] <= 0:
                        tgt["dead"] = True
                        tgt["loot"] = True
                        tgt["combat"] = False
                        p["inCombat"] = False
                        # Advance strike_true quest count if applicable
                        for q in p["qlog"]:
                            if q.get("questId") == "q_ps_strike_true":
                                q["counts"] = [q.get("counts", [0])[0] + 1]
                                if q["counts"][0] >= 1:
                                    q["state"] = "ready"
            elif cmd == "sell_all_junk":
                # Empties junk
                for i in range(len(p["inventory"])):
                    item = p["inventory"][i]
                    if item and item.get("rarity") in ("poor", "junk", "gray"):
                        p["inventory"][i] = None
            elif cmd == "sell":
                slot = cmd_payload.get("slot")
                if slot is not None and 0 <= slot < len(p["inventory"]):
                    p["inventory"][slot] = None
            elif cmd == "equip":
                slot = cmd_payload.get("slot")
                to_slot = cmd_payload.get("toSlot")
                if 0 <= slot < len(p["inventory"]) and p["inventory"][slot]:
                    item = p["inventory"][slot]
                    p["inventory"][slot] = None
                    p["equipment"][to_slot] = item
            elif cmd == "pleave":
                p["party"] = None

    def get_snapshot_for_player(self, pid: int) -> Dict[str, Any]:
        """Generates the authoritative World Snapshot for the bot."""
        p = self.players.get(pid, {})
        return {
            "self": dict(p),
            "entities": {eid: dict(e) for eid, e in self.entities.items() if eid != pid},
            "time": self.time_sec,
        }
