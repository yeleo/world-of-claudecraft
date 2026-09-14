"""
Macro Bot Closed-Loop Simulation Supervisor & Verification Pipeline
Drives end-to-end multi-bot simulations, samples telemetries, and generates gap reports.
"""

from __future__ import annotations
import json
import math
import os
import sys
import time

# Ensure import paths
_HERE = os.path.dirname(os.path.abspath(__file__))
_PYTHON_ROOT = os.path.dirname(_HERE)
if _PYTHON_ROOT not in sys.path:
    sys.path.insert(0, _PYTHON_ROOT)

from macro.sim_realm import MockWorldRealm
from macro.gap_miner import RealmGapMiner
from macro.intents.gear_intent import evaluate_inventory_upgrades, decide_loot_roll
from macro.intents.economy_intent import count_free_inventory_slots, should_visit_vendor, find_nearby_vendor, get_vendor_disposal_actions
from macro.intents.party_intent import PartyLifecycleManager
from macro.intents.quest_intent import QuestNavigator


ALL_9_CLASSES = ["warrior", "paladin", "hunter", "rogue", "priest", "shaman", "mage", "warlock", "druid"]


class SimulatedBotAgent:
    """Agent instance executing the modular macro decision tree in simulation."""

    def __init__(self, pid: int, name: str, pclass: str, is_leader: bool = False):
        self.pid = pid
        self.name = name
        self.pclass = pclass
        self.is_leader = is_leader
        self.party_mgr = PartyLifecycleManager(pid, pclass, is_solo_personality=(pclass == "rogue"))
        self.target_id = None
        self.macro_goal_action = ""
        self.macro_goal_param = ""
        self.macro_goal_x = -283.0
        self.macro_goal_z = -21.0
        self.last_vendor_action_time = -999.0

    def decide_tick_actions(self, realm: MockWorldRealm, sim_time: float) -> list:
        """Executes the macro decision tree for one simulation tick."""
        actions = []
        p_snap = realm.players.get(self.pid)
        if not p_snap or p_snap.get("dead"):
            return actions

        my_x = p_snap.get("x", 0.0)
        my_z = p_snap.get("z", 0.0)
        inventory = p_snap.get("inventory", [])
        equipment = p_snap.get("equipment", {})
        qdone = set(p_snap.get("qdone", []))
        qlog_list = p_snap.get("qlog", [])
        qlog = {q["questId"]: q for q in qlog_list if isinstance(q, dict) and "questId" in q}

        # 1. Gear Evaluation & Auto-Equipping Branch
        upgrade = evaluate_inventory_upgrades(inventory, equipment, self.pclass)
        if upgrade:
            inv_slot, to_slot = upgrade
            actions.append({"t": "cmd", "cmd": "equip", "slot": inv_slot, "toSlot": to_slot})

        # 2. Bag Management & Merchant Disposal Branch
        nearby_vendor = find_nearby_vendor(realm.entities, my_x, my_z, max_dist=12.0)
        if should_visit_vendor(inventory, in_combat=bool(p_snap.get("inCombat")), opportunist=(nearby_vendor is not None)):
            if nearby_vendor and sim_time - self.last_vendor_action_time > 2.0:
                disposal_cmds = get_vendor_disposal_actions(inventory, nearby_vendor["id"])
                actions.extend(disposal_cmds)
                self.last_vendor_action_time = sim_time

        # 3. Combat & Engagement Branch
        if not self.target_id or self.target_id not in realm.entities or realm.entities[self.target_id].get("dead"):
            # Find closest alive training dummy or enemy
            closest_mob = None
            min_d = float("inf")
            for eid, ent in realm.entities.items():
                if ent.get("k") == "mob" and not ent.get("dead"):
                    d = math.hypot(ent.get("x", 0) - my_x, ent.get("z", 0) - my_z)
                    if d < 15.0 and d < min_d:
                        min_d = d
                        closest_mob = eid
            self.target_id = closest_mob

        if self.target_id:
            tgt = realm.entities.get(self.target_id)
            if tgt and not tgt.get("dead"):
                dist = math.hypot(tgt.get("x", 0) - my_x, tgt.get("z", 0) - my_z)
                angle = math.atan2(tgt.get("x", 0) - my_x, tgt.get("z", 0) - my_z)
                if dist > 2.5:
                    actions.append({"t": "input", "mi": {"f": 1}, "facing": angle})
                else:
                    actions.append({"t": "cmd", "cmd": "attack", "target": self.target_id})
                    actions.append({"t": "cmd", "cmd": "cast", "ability": "strike", "target": self.target_id})
                return actions

        # 4. Quest Navigation & Progression Branch
        gx, gz, g_action, g_param = QuestNavigator.resolve_macro_objective(my_x, my_z, qdone, qlog)
        self.macro_goal_x, self.macro_goal_z = gx, gz
        self.macro_goal_action, self.macro_goal_param = g_action, g_param

        dist_to_goal = math.hypot(gx - my_x, gz - my_z)
        angle_to_goal = math.atan2(gx - my_x, gz - my_z)

        if dist_to_goal > 2.5:
            actions.append({"t": "input", "mi": {"f": 1}, "facing": angle_to_goal})
        else:
            if g_action == "accept":
                actions.append({"t": "cmd", "cmd": "accept", "quest": g_param})
            elif g_action == "turnin":
                actions.append({"t": "cmd", "cmd": "turnin", "quest": g_param})
            elif g_action == "waypoint":
                actions.append({"t": "input", "mi": {"f": 1}, "facing": angle_to_goal})
            elif g_action == "hunt":
                # Vigilant scanning while awaiting mob respawn (lifelike human behavior)
                look_angle = (sim_time * 2.0 + self.pid) % 6.28
                actions.append({"t": "input", "mi": {}, "facing": look_angle})

        # 5. Party Lifecycle Departure Check (Tutorial first phase completion milestone)
        if p_snap.get("party"):
            should_leave, _ = self.party_mgr.evaluate_departure_decision(
                p_snap.get("party"), qdone, milestone_quest="q_ps_the_gauntlet"
            )
            if should_leave:
                actions.append({"t": "cmd", "cmd": "pleave"})

        return actions


def run_headless_simulation(num_bots: int = 9, ticks: int = 250) -> dict:
    """Runs a fast-forward simulation with bots covering all specified classes."""
    print("==================================================================")
    print(" 🚀 World of ClaudeCraft - Headless Macro Supervisor Pipeline")
    print(f" Simulated Bots   : {num_bots} (Covering MMORPG classes)")
    print(f" Fast-Forward Ticks: {ticks} (Simulating ~{ticks*0.05:.1f}s of world interactions)")
    print("==================================================================\n")

    realm = MockWorldRealm()
    miner = RealmGapMiner()
    bots: List[SimulatedBotAgent] = []

    # Register bots
    for i in range(num_bots):
        pid = 1000 + i
        pclass = ALL_9_CLASSES[i % len(ALL_9_CLASSES)]
        name = f"Bot_{pclass.capitalize()}_{i+1}"
        realm.register_player(pid, name, pclass)
        # Give some initial junk to test vendor selling
        realm.players[pid]["inventory"][14] = {"name": "Ruined Pelts", "kind": "misc", "rarity": "poor"}
        realm.players[pid]["inventory"][15] = {"name": "Cracked Shell", "kind": "misc", "rarity": "poor"}
        bot_agent = SimulatedBotAgent(pid, name, pclass, is_leader=(i == 0))
        bots.append(bot_agent)

    # Establish initial party
    leader_pid = bots[0].pid
    party_members = [{"pid": b.pid, "name": b.name, "class": b.pclass} for b in bots[:5]]
    party_struct = {"leader": leader_pid, "members": party_members}
    for b in bots[:5]:
        realm.players[b.pid]["party"] = party_struct

    # Fast-forward simulation loop
    start_wall_time = time.time()
    for tick_idx in range(ticks):
        realm.step(dt=0.05)

        for bot in bots:
            tracker = miner.get_or_create_tracker(bot.pid, bot.pclass)
            actions = bot.decide_tick_actions(realm, realm.time_sec)
            for act in actions:
                realm.process_command(bot.pid, act)
            p_state = realm.players[bot.pid]
            tracker.record_tick(p_state, actions)

    elapsed_wall = time.time() - start_wall_time
    report = miner.compile_gap_report()

    # Persist report
    telemetry_dir = os.path.join(_PYTHON_ROOT, "telemetry")
    os.makedirs(telemetry_dir, exist_ok=True)
    report_path = os.path.join(telemetry_dir, "gap_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"✨ Simulation finished in {elapsed_wall:.2f}s ({ticks / max(0.001, elapsed_wall):.0f} simulated ticks/sec)!")
    print(f"📊 Telemetry Gap Report written to: {report_path}\n")
    print(f"--- [Supervisor Summary] ---")
    print(f" - Quests Accepted  : {report['summary']['quests_accepted']}")
    print(f" - Quests Completed : {report['summary']['quests_turned_in']}")
    print(f" - Items Auto-Equip : {report['summary']['items_auto_equipped']}")
    print(f" - Vendor Junk Sold : {report['summary']['vendor_junk_disposals']}")
    print(f" - Stagnation Bugs  : {report['anomalies']['stagnation_incidents']}")
    print(f" - Coverage Rating  : {report['coverage_rating']}")

    if report["actionable_recommendations"]:
        print(f"\n💡 Recommendations for Next Expansion Loop:")
        for rec in report["actionable_recommendations"]:
            print(f"   • {rec}")
    else:
        print("\n✅ All core macro intent branches verified with 0 deadlocks!")

    return report


if __name__ == "__main__":
    num_bots = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    report = run_headless_simulation(num_bots=num_bots, ticks=300)
    sys.exit(0 if report["coverage_rating"] != "ATTENTION_REQUIRED" else 1)
