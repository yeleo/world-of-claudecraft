"""
Telemetry Sampling & Gap Mining Engine
Monitors bot simulation streams, identifies decision tree blindspots, and flags deadlocks.
"""

from __future__ import annotations
import json
import math
from typing import Dict, Any, List


class BotTelemetryTracker:
    """Tracks a single bot's simulation trajectory and anomalies."""

    def __init__(self, pid: int, pclass: str):
        self.pid = pid
        self.pclass = pclass
        self.tick_count = 0
        self.positions: List[tuple] = []
        self.actions_logged: List[Dict[str, Any]] = []

        # Metric counters
        self.quests_accepted = 0
        self.quests_turned_in = 0
        self.items_equipped = 0
        self.junk_sold = 0
        self.party_invites = 0
        self.party_leaves = 0
        self.combat_strikes = 0

        # Anomaly detectors
        self.stagnant_ticks = 0
        self.stagnation_events: List[Dict[str, Any]] = []
        self.unhandled_events: List[Dict[str, Any]] = []

    def record_tick(self, state: Dict[str, Any], actions_sent: List[Dict[str, Any]]):
        self.tick_count += 1
        x = state.get("x", 0.0)
        z = state.get("z", 0.0)

        if self.positions:
            prev_x, prev_z = self.positions[-1]
            dist = math.hypot(x - prev_x, z - prev_z)
            if dist < 0.05 and not state.get("inCombat") and not actions_sent:
                self.stagnant_ticks += 1
                if self.stagnant_ticks == 60:
                    self.stagnation_events.append({
                        "tick": self.tick_count,
                        "pos": (round(x, 2), round(z, 2)),
                        "reason": "Stationary with no active commands sent for 60 consecutive ticks"
                    })
            else:
                self.stagnant_ticks = 0
        self.positions.append((x, z))

        for act in actions_sent:
            self.actions_logged.append(act)
            cmd = act.get("cmd")
            if cmd == "accept":
                self.quests_accepted += 1
            elif cmd == "turnin":
                self.quests_turned_in += 1
            elif cmd == "equip":
                self.items_equipped += 1
            elif cmd == "sell_all_junk":
                self.junk_sold += 1
            elif cmd == "pinvite":
                self.party_invites += 1
            elif cmd == "pleave":
                self.party_leaves += 1
            elif cmd in ("attack", "cast"):
                self.combat_strikes += 1


class RealmGapMiner:
    """Aggregates telemetry from all bots and compiles a gap analysis report."""

    def __init__(self):
        self.trackers: Dict[int, BotTelemetryTracker] = {}

    def get_or_create_tracker(self, pid: int, pclass: str) -> BotTelemetryTracker:
        if pid not in self.trackers:
            self.trackers[pid] = BotTelemetryTracker(pid, pclass)
        return self.trackers[pid]

    def compile_gap_report(self) -> Dict[str, Any]:
        """Synthesizes an actionable report on coverage and missing branches."""
        total_bots = len(self.trackers)
        total_quests_accepted = sum(t.quests_accepted for t in self.trackers.values())
        total_quests_turned_in = sum(t.quests_turned_in for t in self.trackers.values())
        total_equipped = sum(t.items_equipped for t in self.trackers.values())
        total_junk_sold = sum(t.junk_sold for t in self.trackers.values())
        total_party_leaves = sum(t.party_leaves for t in self.trackers.values())

        stagnation_issues = []
        for t in self.trackers.values():
            if t.stagnation_events:
                stagnation_issues.append({
                    "bot_pid": t.pid,
                    "class": t.pclass,
                    "events": t.stagnation_events
                })

        # Recommendations based on mining
        recommendations = []
        if total_equipped == 0:
            recommendations.append("Gear auto-equipping has 0 triggers: check inventory acquisition or evaluator thresholds.")
        if total_junk_sold == 0:
            recommendations.append("Vendor junk disposal had 0 triggers: verify merchant proximity and threshold logic.")
        if stagnation_issues:
            recommendations.append(f"Detected {len(stagnation_issues)} bot stagnation episodes: inspect stuck-recovery and quest acceptance positions.")

        report = {
            "summary": {
                "total_bots_sampled": total_bots,
                "quests_accepted": total_quests_accepted,
                "quests_turned_in": total_quests_turned_in,
                "items_auto_equipped": total_equipped,
                "vendor_junk_disposals": total_junk_sold,
                "party_lifecycle_departures": total_party_leaves,
            },
            "anomalies": {
                "stagnation_incidents": len(stagnation_issues),
                "details": stagnation_issues,
            },
            "coverage_rating": "EXCELLENT" if not stagnation_issues and total_quests_turned_in > 0 else ("MODERATE" if not stagnation_issues else "ATTENTION_REQUIRED"),
            "actionable_recommendations": recommendations,
        }
        return report
