"""
Telemetry Sampling, Human-Likeness Metrics & Gap Mining Engine
Monitors bot simulation streams, logs narrative human action timelines,
and computes human-likeness fidelity alongside stagnation detection.
"""

from __future__ import annotations
import json
import math
import os
from typing import Dict, Any, List, Optional


class BotTelemetryTracker:
    """Tracks a single bot's simulation trajectory, human mannerisms, and anomalies."""

    def __init__(self, pid: int, pclass: str):
        self.pid = pid
        self.pclass = pclass
        self.tick_count = 0
        self.positions: List[tuple] = []
        self.actions_logged: List[Dict[str, Any]] = []

        # Standard Metric counters
        self.quests_accepted = 0
        self.quests_turned_in = 0
        self.items_equipped = 0
        self.junk_sold = 0
        self.party_invites = 0
        self.party_leaves = 0
        self.combat_strikes = 0

        # Human-Likeness Behavioral Counters
        self.scenic_pauses = 0
        self.curiosity_diversions = 0
        self.vendor_sessions = 0
        self.gear_inspections = 0
        self.bunny_hops = 0

        # Narrative Action Log
        self.narrative_timeline: List[Dict[str, Any]] = []

        # Anomaly detectors
        self.stagnant_ticks = 0
        self.stagnation_events: List[Dict[str, Any]] = []

    def log_narrative(self, category: str, text: str, extra: Dict[str, Any] = None):
        """Appends a narrative life event to the audit trail."""
        entry = {
            "tick": self.tick_count,
            "sim_time": round(self.tick_count * 0.05, 2),
            "pid": self.pid,
            "class": self.pclass,
            "cat": category,
            "narrative": text,
        }
        if extra:
            entry.update(extra)
        self.narrative_timeline.append(entry)

    def record_tick(
        self,
        state: Dict[str, Any],
        actions_sent: List[Dict[str, Any]],
        narrative_note: str = "",
        is_legitimate_pause: bool = False,
    ):
        self.tick_count += 1
        x = state.get("x", 0.0)
        z = state.get("z", 0.0)

        if narrative_note:
            self.log_narrative("MANNERISM", narrative_note)

        # Movement & Stagnation check
        if self.positions:
            prev_x, prev_z = self.positions[-1]
            dist = math.hypot(x - prev_x, z - prev_z)
            # Legitimate pauses (sightseeing, vendor browsing, gear inspection, mob respawn wait) are not bugs
            if dist < 0.05 and not state.get("inCombat") and not actions_sent and not is_legitimate_pause:
                self.stagnant_ticks += 1
                if self.stagnant_ticks == 60:
                    self.stagnation_events.append({
                        "tick": self.tick_count,
                        "pos": (round(x, 2), round(z, 2)),
                        "reason": "Stationary with no active commands sent for 60 consecutive ticks",
                    })
            else:
                self.stagnant_ticks = 0
        self.positions.append((x, z))

        for act in actions_sent:
            self.actions_logged.append(act)
            cmd = act.get("cmd")
            if cmd == "accept":
                self.quests_accepted += 1
                self.log_narrative("QUEST", f"Accepted quest '{act.get('quest')}'")
            elif cmd == "turnin":
                self.quests_turned_in += 1
                self.log_narrative("QUEST", f"Turned in quest '{act.get('quest')}'")
            elif cmd == "equip":
                self.items_equipped += 1
                self.log_narrative("GEAR", f"Equipped upgrade to slot '{act.get('toSlot')}'")
            elif cmd in ("sell", "sell_all_junk"):
                self.junk_sold += 1
                self.log_narrative("ECONOMY", f"Sold item to merchant #{act.get('vendorId')}")
            elif cmd == "pinvite":
                self.party_invites += 1
                self.log_narrative("SOCIAL", f"Sent party invite to PID #{act.get('id')}")
            elif cmd == "pleave":
                self.party_leaves += 1
                self.log_narrative("SOCIAL", "Parted ways with squad and left group")
            elif cmd in ("attack", "cast"):
                self.combat_strikes += 1

            # Check jump action
            mi = act.get("mi", {})
            if mi.get("j"):
                self.bunny_hops += 1


class RealmGapMiner:
    """Aggregates telemetry from all bots, compiles human-likeness index and writes audit streams."""

    def __init__(self):
        self.trackers: Dict[int, BotTelemetryTracker] = {}

    def get_or_create_tracker(self, pid: int, pclass: str) -> BotTelemetryTracker:
        if pid not in self.trackers:
            self.trackers[pid] = BotTelemetryTracker(pid, pclass)
        return self.trackers[pid]

    def dump_audit_log(self, output_path: str):
        """Flushes full human-readable JSONL audit event stream."""
        all_events = []
        for t in self.trackers.values():
            all_events.extend(t.narrative_timeline)
        all_events.sort(key=lambda x: (x["tick"], x["pid"]))

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for ev in all_events:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")

    def compile_gap_report(self) -> Dict[str, Any]:
        """Synthesizes an actionable report on coverage, human mannerisms, and missing branches."""
        total_bots = len(self.trackers)
        total_quests_accepted = sum(t.quests_accepted for t in self.trackers.values())
        total_quests_turned_in = sum(t.quests_turned_in for t in self.trackers.values())
        total_equipped = sum(t.items_equipped for t in self.trackers.values())
        total_junk_sold = sum(t.junk_sold for t in self.trackers.values())
        total_party_leaves = sum(t.party_leaves for t in self.trackers.values())

        total_scenic = sum(t.scenic_pauses for t in self.trackers.values())
        total_curiosity = sum(t.curiosity_diversions for t in self.trackers.values())
        total_vendor_sessions = sum(t.vendor_sessions for t in self.trackers.values())
        total_gear_inspections = sum(t.gear_inspections for t in self.trackers.values())
        total_bunny_hops = sum(t.bunny_hops for t in self.trackers.values())

        stagnation_issues = []
        for t in self.trackers.values():
            if t.stagnation_events:
                stagnation_issues.append({
                    "bot_pid": t.pid,
                    "class": t.pclass,
                    "events": t.stagnation_events,
                })

        recommendations = []
        if total_scenic == 0:
            recommendations.append("Scenic pauses had 0 triggers: check scenic spot radii or pause triggers.")
        if total_curiosity == 0:
            recommendations.append("Curiosity diversions had 0 triggers: check roadside novelties spawn and distance.")
        if total_vendor_sessions == 0:
            recommendations.append("Multi-stage vendor sessions had 0 triggers: check bag fill threshold and vendor proximity.")
        if stagnation_issues:
            recommendations.append(f"Detected {len(stagnation_issues)} bot stagnation episodes: inspect stuck-recovery and quest positions.")

        # Compute Human-Likeness Fidelity Score (0 ~ 100)
        score = 60
        if total_vendor_sessions > 0:
            score += 10
        if total_scenic > 0:
            score += 10
        if total_curiosity > 0:
            score += 10
        if total_gear_inspections > 0:
            score += 5
        if total_bunny_hops > 0:
            score += 5
        if stagnation_issues:
            score -= 20
        human_likeness_score = max(0, min(100, score))

        report = {
            "summary": {
                "total_bots_sampled": total_bots,
                "quests_accepted": total_quests_accepted,
                "quests_turned_in": total_quests_turned_in,
                "items_auto_equipped": total_equipped,
                "vendor_junk_disposals": total_junk_sold,
                "party_lifecycle_departures": total_party_leaves,
            },
            "human_mannerisms": {
                "scenic_pauses": total_scenic,
                "curiosity_diversions": total_curiosity,
                "vendor_transaction_sessions": total_vendor_sessions,
                "gear_tooltip_inspections": total_gear_inspections,
                "bunny_hops_while_running": total_bunny_hops,
                "human_likeness_score": f"{human_likeness_score}/100",
            },
            "anomalies": {
                "stagnation_incidents": len(stagnation_issues),
                "details": stagnation_issues,
            },
            "coverage_rating": "EXCELLENT" if not stagnation_issues and human_likeness_score >= 80 else ("MODERATE" if not stagnation_issues else "ATTENTION_REQUIRED"),
            "actionable_recommendations": recommendations,
        }
        return report
