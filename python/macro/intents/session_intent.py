"""
Session Lifecycle, Fatigue Decay & Rest Area Logout Intent Module
Simulates realistic player play sessions, fatigue accumulation,
and the ritual of traveling to an inn/campfire to rest and log out.
"""

from __future__ import annotations
import math
import random
from typing import Dict, Any, List, Optional, Tuple

# Established Rest Areas (Inns, Campfires) where players gain Rest XP and log out safely
REST_AREAS = [
    {"name": "Dawnrest Campfire", "x": -346.0, "z": 24.0, "radius": 8.0},
    {"name": "Tam's Watch Station", "x": -283.0, "z": -25.0, "radius": 6.0},
    {"name": "Ravenpost Inn", "x": -25.0, "z": -60.0, "radius": 10.0},
]

FAREWELL_LOGOUT_MESSAGES = [
    "时间不早了，我先在营地回个精力下线了，明天见！",
    "包清完了，跑回旅店吃双倍经验下线，各位先撤啦~",
    "有点打累了，坐下烤个火休息，大家晚安！",
    "先在营地歇会儿，明天再继续冲级，兄弟们加油！",
]


class SessionLifecycleManager:
    """
    Manages a bot's overall daily session lifecycle:
    ONLINE_ACTIVE -> FATIGUED -> SEEKING_REST_AREA -> RESTING_LOGOUT -> OFFLINE_SLEEP -> REJOIN
    """

    def __init__(self, bot_pid: int, player_class: str, target_session_seconds: float = 80.0):
        self.bot_pid = bot_pid
        self.player_class = player_class

        # Session time configuration
        self.target_session_duration = target_session_seconds + random.uniform(-15.0, 25.0)
        self.session_elapsed = 0.0
        self.offline_duration = random.uniform(15.0, 30.0)
        self.offline_elapsed = 0.0

        # State machine
        self.state = "ONLINE_ACTIVE"  # ONLINE_ACTIVE, FATIGUED, SEEKING_REST_AREA, RESTING_LOGOUT, OFFLINE_SLEEP
        self.fatigue = 0.0  # 0.0 (fresh) -> 1.0 (exhausted)
        self.target_rest_area: Optional[Dict[str, Any]] = None
        self.logout_initiated_time = 0.0

        # Session Metrics
        self.sessions_completed = 0
        self.rested_logouts = 0

    def step_session(self, dt: float, my_x: float, my_z: float, in_combat: bool) -> Tuple[str, Optional[Tuple[float, float, str, str]]]:
        """
        Advances the session clock and evaluates fatigue/logout requirements.
        Returns: (session_state, goal_override_or_None)
        """
        # 1. Currently Offline
        if self.state == "OFFLINE_SLEEP":
            self.offline_elapsed += dt
            if self.offline_elapsed >= self.offline_duration:
                # Wake up refreshed!
                self.state = "ONLINE_ACTIVE"
                self.session_elapsed = 0.0
                self.offline_elapsed = 0.0
                self.fatigue = 0.0
                self.sessions_completed += 1
                return "REJOIN", None
            return "OFFLINE_SLEEP", None

        # 2. Currently in Resting Logout Ceremony (sitting at campfire/inn)
        if self.state == "RESTING_LOGOUT":
            self.logout_initiated_time += dt
            if self.logout_initiated_time >= 4.0:  # 4 seconds logout timer
                self.state = "OFFLINE_SLEEP"
                self.rested_logouts += 1
                return "LOGOUT_NOW", None
            return "RESTING_LOGOUT", (my_x, my_z, "sit_rest", "Resting at campfire before disconnect")

        # Advance active session clock
        self.session_elapsed += dt
        # Fatigue grows linearly towards 1.0 as session reaches duration
        self.fatigue = min(1.0, self.session_elapsed / max(1.0, self.target_session_duration))

        # Check if fatigued enough to wrap up session
        if self.fatigue >= 1.0 and not in_combat and self.state == "ONLINE_ACTIVE":
            self.state = "FATIGUED"

        # 3. Seeking closest rest area to log out
        if self.state in ("FATIGUED", "SEEKING_REST_AREA"):
            if in_combat:
                return "ONLINE_ACTIVE", None

            # Find nearest rest area
            if not self.target_rest_area:
                closest = None
                min_d = float("inf")
                for area in REST_AREAS:
                    d = math.hypot(area["x"] - my_x, area["z"] - my_z)
                    if d < min_d:
                        min_d = d
                        closest = area
                self.target_rest_area = closest

            if self.target_rest_area:
                rx = self.target_rest_area["x"]
                rz = self.target_rest_area["z"]
                dist = math.hypot(rx - my_x, rz - my_z)

                if dist <= self.target_rest_area["radius"]:
                    # Arrived at rest area! Start logout ceremony
                    self.state = "RESTING_LOGOUT"
                    self.logout_initiated_time = 0.0
                    self.target_rest_area = None
                    return "RESTING_LOGOUT", (my_x, my_z, "sit_rest", "Arrived at rest area, initiating logout")
                else:
                    self.state = "SEEKING_REST_AREA"
                    return "SEEKING_REST_AREA", (rx, rz, "travel", f"Traveling to rest at {self.target_rest_area['name']}")

        return "ONLINE_ACTIVE", None

    def get_fatigue_idle_chance(self) -> float:
        """Returns the probability of experiencing a brief distracted pause due to fatigue."""
        if self.fatigue < 0.5:
            return 0.02
        elif self.fatigue < 0.8:
            return 0.08
        else:
            return 0.22  # Heavy fatigue increases zoning-out frequency
