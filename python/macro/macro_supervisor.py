"""
Autonomous Long-Horizon Macro Supervisor & Self-Refining Telemetry Pipeline
Simulates lifelike multi-stage human behavior: deliberate pauses, merchant browsing,
gear tooltip inspection, curiosity-driven scenic excursions, and spontaneous mannerisms.
"""

from __future__ import annotations
import argparse
import json
import math
import os
import random
import sys
import time
from typing import List, Dict, Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_PYTHON_ROOT = os.path.dirname(_HERE)
if _PYTHON_ROOT not in sys.path:
    sys.path.insert(0, _PYTHON_ROOT)

from macro.sim_realm import MockWorldRealm
from macro.gap_miner import RealmGapMiner, BotTelemetryTracker
from macro.intents.gear_intent import evaluate_inventory_upgrades, HumanGearInspectionFSM
from macro.intents.session_intent import SessionLifecycleManager
from macro.intents.economy_intent import (
    count_free_inventory_slots,
    should_visit_vendor,
    find_nearby_vendor,
    has_junk,
    needs_equipment_repair,
    HumanVendorInteractionFSM,
)
from macro.intents.party_intent import PartyLifecycleManager
from macro.intents.quest_intent import QuestNavigator
from macro.intents.curiosity_intent import CuriosityIntentManager

ALL_9_CLASSES = [
    "warrior", "paladin", "hunter", "rogue", "priest",
    "shaman", "mage", "warlock", "druid"
]


class SimulatedBotAgent:
    """Agent executing human-like multi-stage state machines and spontaneous wandering."""

    def __init__(self, pid: int, name: str, pclass: str, is_leader: bool = False):
        self.pid = pid
        self.name = name
        self.pclass = pclass
        self.is_leader = is_leader

        # Modular Intent Managers & FSMs
        self.party_mgr = PartyLifecycleManager(pid, pclass, is_solo_personality=(pclass == "rogue"))
        self.session_mgr = SessionLifecycleManager(pid, pclass, target_session_seconds=180.0)
        self.vendor_fsm = HumanVendorInteractionFSM(pid)
        self.gear_fsm = HumanGearInspectionFSM(pid, pclass)
        self.curiosity_mgr = CuriosityIntentManager(pid, pclass)

        # Combat & Navigation state
        self.target_id: Optional[int] = None
        self.macro_goal_action = ""
        self.macro_goal_param = ""
        self.macro_goal_x = -283.0
        self.macro_goal_z = -21.0
        self.last_vendor_visit_time = -999.0
        self.last_coop_invite_time = -999.0

        # Legitimate pause marker
        self.last_narrative_note = ""
        self.is_legitimate_pause = False

    def decide_tick_actions(self, realm: MockWorldRealm, sim_time: float, tracker: BotTelemetryTracker) -> list:
        """Executes the macro decision tree for one simulation tick with realistic pacing."""
        actions = []
        self.last_narrative_note = ""
        self.is_legitimate_pause = False

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
        in_combat = bool(p_snap.get("inCombat"))

        # ----------------------------------------------------------------------
        # 0. Player Session Lifecycle & Rest Area Logout Ritual
        # ----------------------------------------------------------------------
        if p_snap.get("offline"):
            s_state, _ = self.session_mgr.step_session(0.05, my_x, my_z, in_combat=False)
            if s_state == "REJOIN":
                return [{"t": "cmd", "cmd": "rejoin"}]
            self.is_legitimate_pause = True
            return []

        session_state, session_goal = self.session_mgr.step_session(0.05, my_x, my_z, in_combat=in_combat)
        if session_state == "RESTING_LOGOUT":
            self.is_legitimate_pause = True
            self.last_narrative_note = "Sitting peacefully at campfire/inn for Rest XP and preparing to log out"
            return [{"t": "cmd", "cmd": "sit_rest"}]
        elif session_state == "LOGOUT_NOW":
            self.is_legitimate_pause = True
            self.last_narrative_note = "Resting ritual complete; gracefully logging out"
            return [{"t": "cmd", "cmd": "logout"}]
        elif session_state == "SEEKING_REST_AREA" and session_goal:
            rx, rz, _, r_note = session_goal
            dist_r = math.hypot(rx - my_x, rz - my_z)
            angle_r = math.atan2(rx - my_x, rz - my_z)
            self.last_narrative_note = r_note
            mi = {"f": 1}
            if self.curiosity_mgr.should_bunny_hop(sim_time, is_moving=True):
                mi["j"] = 1
            return [{"t": "input", "mi": mi, "facing": angle_r}]

        # ----------------------------------------------------------------------
        # 1. Multi-Stage Vendor Trading Session (Paced Human Interaction)
        # ----------------------------------------------------------------------
        if self.vendor_fsm.is_busy():
            v_cmds, note = self.vendor_fsm.step_transaction(sim_time, inventory, equipment)
            self.last_narrative_note = note
            self.is_legitimate_pause = True
            return v_cmds

        # Check if approaching a vendor to start trading / repair
        # If inventory is full (free_slots <= 3) or gear badly damaged, actively seek nearest vendor across zone (150m)
        free_slots = count_free_inventory_slots(inventory)
        is_urgent_vendor_need = (free_slots <= 3) or (equipment and needs_equipment_repair(equipment, durability_threshold=0.60))
        search_radius = 150.0 if is_urgent_vendor_need else 12.0

        nearby_vendor = find_nearby_vendor(realm.entities, my_x, my_z, max_dist=search_radius)
        if not in_combat and nearby_vendor and sim_time - self.last_vendor_visit_time > 15.0:
            wants_trade = should_visit_vendor(inventory, in_combat=False, opportunist=True, equipment=equipment)
            if wants_trade:
                dist_v = math.hypot(nearby_vendor["x"] - my_x, nearby_vendor["z"] - my_z)
                if dist_v <= 3.5:
                    # Arrived at merchant: initiate realistic trading FSM
                    self.vendor_fsm.start_transaction(nearby_vendor["id"], inventory, sim_time)
                    self.last_vendor_visit_time = sim_time
                    tracker.vendor_sessions += 1
                    self.last_narrative_note = f"Opened trade window with merchant '{nearby_vendor.get('nm')}'"
                    self.is_legitimate_pause = True
                    return [{"t": "input", "mi": {}}]
                else:
                    # Move directly towards vendor
                    angle_v = math.atan2(nearby_vendor["x"] - my_x, nearby_vendor["z"] - my_z)
                    self.last_narrative_note = f"Traveling to merchant '{nearby_vendor.get('nm')}' to empty bags & repair"
                    mi = {"f": 1}
                    if self.curiosity_mgr.should_bunny_hop(sim_time, is_moving=True):
                        mi["j"] = 1
                    return [{"t": "input", "mi": mi, "facing": angle_v}]

        # ----------------------------------------------------------------------
        # 2. Gear Tooltip Inspection & Comparison (Paced Equipment Swap)
        # ----------------------------------------------------------------------
        if self.gear_fsm.is_busy():
            g_cmds, note = self.gear_fsm.step(sim_time)
            self.last_narrative_note = note
            self.is_legitimate_pause = True
            return g_cmds

        if not in_combat:
            upgrade = evaluate_inventory_upgrades(inventory, equipment, self.pclass)
            if upgrade:
                started = self.gear_fsm.consider_upgrade(upgrade, sim_time, in_combat)
                if started:
                    tracker.gear_inspections += 1
                    self.last_narrative_note = "Hovering over newly acquired item to inspect stats"
                    self.is_legitimate_pause = True
                    return [{"t": "input", "mi": {}}]

        # ----------------------------------------------------------------------
        # 3. Combat & Engagement Branch with Crowd Conflict Resolution
        # ----------------------------------------------------------------------
        my_party = p_snap.get("party")
        party_pids = {m.get("pid") for m in my_party.get("members", [])} if my_party else {self.pid}

        # Select target, preferring untagged or party-tagged mobs
        if not self.target_id or self.target_id not in realm.entities or realm.entities[self.target_id].get("dead"):
            best_mob = None
            min_d = float("inf")
            for eid, ent in realm.entities.items():
                if ent.get("k") == "mob" and not ent.get("dead"):
                    d = math.hypot(ent.get("x", 0) - my_x, ent.get("z", 0) - my_z)
                    if d < 18.0:
                        # Prioritize untagged mobs
                        tag = ent.get("taggedBy")
                        is_friendly_tag = (tag is None or tag in party_pids)
                        effective_dist = d if is_friendly_tag else (d + 20.0)
                        if effective_dist < min_d:
                            min_d = effective_dist
                            best_mob = eid
            self.target_id = best_mob

        if self.target_id:
            tgt = realm.entities.get(self.target_id)
            if tgt and not tgt.get("dead"):
                tag = tgt.get("taggedBy")
                # If mob is already tagged by a stranger, negotiate co-op or yield
                if tag is not None and tag not in party_pids:
                    # Try to invite tagger to share quest credit if group has space
                    party_size = len(my_party.get("members", [])) if my_party else 1
                    if party_size < 5 and self.pclass != "rogue" and sim_time - self.last_coop_invite_time > 10.0:
                        self.last_coop_invite_time = sim_time
                        actions.append({"t": "cmd", "cmd": "pinvite", "id": tag, "reason": "mob_coop"})
                        self.last_narrative_note = f"Invited player #{tag} to party to share mob progress"

                dist = math.hypot(tgt.get("x", 0) - my_x, tgt.get("z", 0) - my_z)
                angle = math.atan2(tgt.get("x", 0) - my_x, tgt.get("z", 0) - my_z)
                if dist > 2.5:
                    actions.append({"t": "input", "mi": {"f": 1}, "facing": angle})
                else:
                    actions.append({"t": "cmd", "cmd": "attack", "target": self.target_id})
                    actions.append({"t": "cmd", "cmd": "cast", "ability": "strike", "target": self.target_id})
                return actions

        # ----------------------------------------------------------------------
        # 4. Curiosity, Scenic Wandering & Exploration Intent
        # ----------------------------------------------------------------------
        curiosity_goal = self.curiosity_mgr.evaluate_curiosity(sim_time, my_x, my_z, realm.entities, in_combat)
        if curiosity_goal:
            cx, cz, c_action, c_param = curiosity_goal
            dist_c = math.hypot(cx - my_x, cz - my_z)
            angle_c = math.atan2(cx - my_x, cz - my_z)

            if c_action == "sightseeing":
                if not getattr(self, "in_scenic_pause", False):
                    tracker.scenic_pauses += 1
                    self.in_scenic_pause = True
                self.in_curiosity_trip = False
                self.last_narrative_note = f"Admiring scenic vista at {c_param}"
                self.is_legitimate_pause = True
                look_angle = (sim_time * 0.5 + self.pid) % 6.28
                return [{"t": "input", "mi": {}, "facing": look_angle}]

            elif c_action == "investigate":
                if not getattr(self, "in_curiosity_trip", False):
                    tracker.curiosity_diversions += 1
                    self.in_curiosity_trip = True
                self.in_scenic_pause = False
                self.last_narrative_note = f"Curiously strayed off-path to check out '{c_param}'"
                if dist_c > 2.0:
                    mi = {"f": 1}
                    if self.curiosity_mgr.should_bunny_hop(sim_time, is_moving=True):
                        mi["j"] = 1
                    return [{"t": "input", "mi": mi, "facing": angle_c}]
                else:
                    self.is_legitimate_pause = True
                    return [{"t": "input", "mi": {}}]
        else:
            self.in_scenic_pause = False
            self.in_curiosity_trip = False

        # ----------------------------------------------------------------------
        # 4.5. Authentic Social Interaction (Class Buffs & Gestures)
        # ----------------------------------------------------------------------
        if not in_combat:
            nearby_peers = [e for eid, e in realm.players.items() if eid != self.pid]
            social_act = self.party_mgr.evaluate_social_flair(my_x, my_z, nearby_peers, sim_time)
            if social_act:
                s_cmd, s_note = social_act
                actions.append(s_cmd)
                self.last_narrative_note = s_note
                self.is_legitimate_pause = True
                return actions

        # ----------------------------------------------------------------------
        # 5. Quest Progression & World Navigation
        # ----------------------------------------------------------------------
        gx, gz, g_action, g_param = QuestNavigator.resolve_macro_objective(my_x, my_z, qdone, qlog)
        self.macro_goal_x, self.macro_goal_z = gx, gz
        self.macro_goal_action, self.macro_goal_param = g_action, g_param

        dist_to_goal = math.hypot(gx - my_x, gz - my_z)
        angle_to_goal = math.atan2(gx - my_x, gz - my_z)

        # Habitual casual bunny hop
        is_moving = dist_to_goal > 2.5
        need_hop = self.curiosity_mgr.should_bunny_hop(sim_time, is_moving)

        if dist_to_goal > 2.5:
            mi = {"f": 1}
            if need_hop:
                mi["j"] = 1
            actions.append({"t": "input", "mi": mi, "facing": angle_to_goal})
        else:
            if g_action == "accept":
                actions.append({"t": "cmd", "cmd": "accept", "quest": g_param})
            elif g_action == "turnin":
                actions.append({"t": "cmd", "cmd": "turnin", "quest": g_param})
            elif g_action == "waypoint":
                actions.append({"t": "input", "mi": {"f": 1}, "facing": angle_to_goal})
            elif g_action == "hunt":
                # Waiting for mob respawn with vigilant natural scanning
                look_angle = (sim_time * 2.0 + self.pid) % 6.28
                self.is_legitimate_pause = True
                actions.append({"t": "input", "mi": {}, "facing": look_angle})

        # ----------------------------------------------------------------------
        # 6. Party Lifecycle Departure Check
        # ----------------------------------------------------------------------
        if p_snap.get("party"):
            should_leave, _ = self.party_mgr.evaluate_departure_decision(
                p_snap.get("party"), qdone, milestone_quest="q_ps_the_gauntlet"
            )
            if should_leave:
                actions.append({"t": "cmd", "cmd": "pleave"})

        return actions


def run_long_horizon_simulation(cohorts: List[int] = [1, 3, 5, 9], ticks: int = 1500) -> dict:
    """
    Executes multiple multi-scale long-horizon simulation sweeps,
    streaming narrative audit logs and evaluating human-likeness fidelity.
    """
    print("==================================================================")
    print(" 🚀 World of ClaudeCraft - Autonomous Long-Horizon Macro Pipeline")
    print(f" Cohorts to Test   : {cohorts} Bots")
    print(f" Simulation Ticks  : {ticks} ticks/cohort (~{ticks*0.05:.1f}s world time each)")
    print("==================================================================\n")

    overall_reports = []
    miner = RealmGapMiner()

    for cohort_size in cohorts:
        print(f"\n--- [Simulating Cohort: {cohort_size} Bots for {ticks} ticks] ---")
        realm = MockWorldRealm()
        bots: List[SimulatedBotAgent] = []

        for i in range(cohort_size):
            pid = 2000 + i
            pclass = ALL_9_CLASSES[i % len(ALL_9_CLASSES)]
            name = f"Bot_{pclass.capitalize()}_{i+1}"
            realm.register_player(pid, name, pclass)
            # Equip initial junk
            realm.players[pid]["inventory"][14] = {"name": "Ruined Pelts", "kind": "misc", "rarity": "poor"}
            realm.players[pid]["inventory"][15] = {"name": "Cracked Shell", "kind": "misc", "rarity": "poor"}
            agent = SimulatedBotAgent(pid, name, pclass, is_leader=(i == 0))
            bots.append(agent)

        if cohort_size > 1:
            party_members = [{"pid": b.pid, "name": b.name, "class": b.pclass} for b in bots[:5]]
            party_struct = {"leader": bots[0].pid, "members": party_members}
            for b in bots[:5]:
                realm.players[b.pid]["party"] = party_struct

        start_wall = time.time()
        for tick_idx in range(ticks):
            realm.step(dt=0.05)
            for bot in bots:
                tracker = miner.get_or_create_tracker(bot.pid, bot.pclass)
                actions = bot.decide_tick_actions(realm, realm.time_sec, tracker)
                for act in actions:
                    realm.process_command(bot.pid, act)
                p_state = realm.players[bot.pid]
                tracker.record_tick(
                    p_state,
                    actions,
                    narrative_note=bot.last_narrative_note,
                    is_legitimate_pause=bot.is_legitimate_pause,
                )

        elapsed = time.time() - start_wall
        print(f"  Cohort of {cohort_size} bots completed in {elapsed:.2f}s ({ticks/max(0.001, elapsed):.0f} ticks/s)")

    # Compile aggregate report & audit log
    report = miner.compile_gap_report()

    telemetry_dir = os.path.join(_PYTHON_ROOT, "telemetry")
    os.makedirs(telemetry_dir, exist_ok=True)
    report_path = os.path.join(telemetry_dir, "gap_report.json")
    audit_log_path = os.path.join(telemetry_dir, "sim_audit_log.jsonl")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    miner.dump_audit_log(audit_log_path)

    print("\n==================================================================")
    print(" 📊 Comprehensive Simulation Telemetry Report")
    print(f" Total Bots Sampled          : {report['summary']['total_bots_sampled']}")
    print(f" Quests Accepted / Completed : {report['summary']['quests_accepted']} / {report['summary']['quests_turned_in']}")
    print(f" Items Auto-Equipped         : {report['summary']['items_auto_equipped']}")
    print(f" Junk Sold to Merchants      : {report['summary']['vendor_junk_disposals']}")
    print(f" Multi-Stage Vendor Sessions : {report['human_mannerisms']['vendor_transaction_sessions']}")
    print(f" Gear Tooltip Inspections    : {report['human_mannerisms']['gear_tooltip_inspections']}")
    print(f" Equipment Repairs At Vendor : {report['long_horizon_ecology']['equipment_repairs']}")
    print(f" Campfire/Inn Rested Logouts : {report['long_horizon_ecology']['rested_inn_logouts']}")
    print(f" Refreshed Session Rejoins   : {report['long_horizon_ecology']['refreshed_rejoins']}")
    print(f" Mob Co-op Share Resolutions : {report['long_horizon_ecology']['coop_mob_tag_resolutions']}")
    print(f" Class Buffs Shared with Peer: {report['long_horizon_ecology']['social_class_buffs_shared']}")
    print(f" Friendly Emotes Performed   : {report['long_horizon_ecology']['social_greetings_emoted']}")
    print(f" Scenic Vistas Pauses        : {report['human_mannerisms']['scenic_pauses']}")
    print(f" Curiosity Diversions        : {report['human_mannerisms']['curiosity_diversions']}")
    print(f" Spontaneous Bunny Hops      : {report['human_mannerisms']['bunny_hops_while_running']}")
    print(f" Human-Likeness Fidelity     : {report['human_mannerisms']['human_likeness_score']}")
    print(f" Stagnation Anomalies        : {report['anomalies']['stagnation_incidents']}")
    print(f" Coverage & Fidelity Rating  : {report['coverage_rating']}")
    print(f" Audit Log Dumped To         : {audit_log_path}")
    print("==================================================================\n")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohorts", type=str, default="1,3,5,9", help="Comma-separated cohort sizes")
    parser.add_argument("--ticks", type=int, default=1500, help="Simulation ticks per cohort")
    args = parser.parse_args()

    cohorts_list = [int(x.strip()) for x in args.cohorts.split(",") if x.strip()]
    rep = run_long_horizon_simulation(cohorts=cohorts_list, ticks=args.ticks)
    sys.exit(0 if rep["coverage_rating"] == "EXCELLENT" else 1)
