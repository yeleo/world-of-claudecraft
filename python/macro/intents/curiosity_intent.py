"""
Curiosity, Scenic Wandering & Human Mannerisms Intent Module
Imbues MMORPG bots with realistic wandering drives, scenic pausing, curiosity diversions,
and spontaneous player mannerisms (jumping, strafing, idling).
"""

from __future__ import annotations
import math
import random
from typing import Dict, Any, List, Optional, Tuple

# Scenic spots where real players love to pause and admire the landscape
SCENIC_POINTS = [
    {"name": "Tam's Pier Sea Vista", "x": -282.0, "z": -18.0, "radius": 15.0},
    {"name": "Gauntlet Turn Cliff Overlook", "x": -310.0, "z": -30.0, "radius": 15.0},
    {"name": "Practice Yard West Lookout", "x": -342.0, "z": -15.0, "radius": 15.0},
    {"name": "Old Pier Sunset Pier", "x": -278.0, "z": -8.0, "radius": 15.0},
]


class CuriosityIntentManager:
    """Manages player curiosity, spontaneous side excursions, and idle sightseeing."""

    def __init__(self, bot_pid: int, player_class: str):
        self.bot_pid = bot_pid
        self.player_class = player_class

        # State tracking
        self.curiosity_target: Optional[Dict[str, Any]] = None
        self.curiosity_start_time = 0.0
        self.curiosity_duration = 0.0
        self.last_diversion_time = random.uniform(-10.0, 5.0)

        # Scenic pause (allow early scenic appreciation after spawn)
        self.is_sightseeing = False
        self.sightseeing_until = 0.0
        self.last_scenic_time = random.uniform(-15.0, 5.0)

        # Spontaneous movement mannerisms
        self.last_bunny_hop_time = 0.0
        self.next_hop_interval = random.uniform(8.0, 20.0)

    def evaluate_curiosity(
        self,
        now: float,
        my_x: float,
        my_z: float,
        nearby_entities: Dict[int, Dict[str, Any]],
        in_combat: bool,
    ) -> Optional[Tuple[float, float, str, str]]:
        """
        Evaluates whether the bot gets distracted by a curious roadside object or scenic vista.
        Returns: (goal_x, goal_z, action_tag, param) or None.
        """
        if in_combat:
            self.curiosity_target = None
            self.is_sightseeing = False
            return None

        # 1. Currently in scenic pause
        if self.is_sightseeing:
            if now < self.sightseeing_until:
                # Slowly turn to look at scenery
                look_angle = (now * 0.4 + self.bot_pid) % (2 * math.pi)
                return my_x, my_z, "sightseeing", f"Admiring scenery (facing {look_angle:.2f})"
            else:
                self.is_sightseeing = False
                self.last_scenic_time = now

        # 2. Currently pursuing a curiosity diversion
        if self.curiosity_target:
            cx = self.curiosity_target.get("x", my_x)
            cz = self.curiosity_target.get("z", my_z)
            dist = math.hypot(cx - my_x, cz - my_z)
            if dist < 2.0 or (now - self.curiosity_start_time > self.curiosity_duration):
                # Done investigating!
                self.curiosity_target = None
                self.last_diversion_time = now
            else:
                return cx, cz, "investigate", self.curiosity_target.get("nm", "roadside novelty")

        # 3. Check for nearby Scenic Vista (within sight range of 15m)
        if now - self.last_scenic_time > random.uniform(25.0, 50.0):
            for spot in SCENIC_POINTS:
                d = math.hypot(spot["x"] - my_x, spot["z"] - my_z)
                if d <= 15.0:
                    if random.random() < 0.70:
                        self.is_sightseeing = True
                        self.sightseeing_until = now + random.uniform(3.0, 6.0)
                        self.last_scenic_time = now
                        return spot["x"], spot["z"], "sightseeing", spot["name"]

        # 4. Spontaneous Curiosity Diversion towards roadside environmental objects
        if now - self.last_diversion_time > random.uniform(20.0, 45.0):
            novelties = []
            for eid, ent in nearby_entities.items():
                if eid == self.bot_pid:
                    continue
                k = ent.get("k")
                # Crates, monuments, scenic objects only (do not distract on essential quest givers)
                if k == "obj" or (k == "npc" and not ent.get("questGiver") and not ent.get("vendor")):
                    ex = ent.get("x", 0.0)
                    ez = ent.get("z", 0.0)
                    d = math.hypot(ex - my_x, ez - my_z)
                    if 3.0 < d < 16.0:
                        novelties.append(ent)

            if novelties and random.random() < 0.50:
                chosen = random.choice(novelties)
                self.curiosity_target = chosen
                self.curiosity_start_time = now
                self.curiosity_duration = random.uniform(3.5, 6.0)
                self.last_diversion_time = now
                return chosen["x"], chosen["z"], "investigate", chosen.get("nm", "interesting point")

        return None

    def should_bunny_hop(self, now: float, is_moving: bool) -> bool:
        """Returns true if bot performs a habitual casual jump while running."""
        if is_moving and now - self.last_bunny_hop_time > self.next_hop_interval:
            self.last_bunny_hop_time = now
            self.next_hop_interval = random.uniform(9.0, 22.0)
            return True
        return False
