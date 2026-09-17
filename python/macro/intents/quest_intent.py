"""
Full Quest Lifecycle & World Exploration Intent Module
Covers the entire 10-step tutorial quest chain on Proving Shore and dynamic randomized mainland quests.
"""

from __future__ import annotations
from typing import Dict, Any, Tuple, Optional, List
import random

# Proving Shore Gauntlet Checkpoints (Exact game coordinates from proving_shore.ts)
GAUNTLET_CHECKPOINTS = [
    (-308.0, -16.0),   # Flag 1
    (-308.0, -32.0),   # Flag 2
    (-334.0, -32.5),   # Flag 3
]

# Wreck Line Crates positions (Exact positions from proving_shore.ts)
WRECK_LINE_CRATES = [
    (-362.0, -8.0),
    (-352.0, -2.0),
    (-345.0, 4.0),
    (-334.0, 17.0),
    (-327.0, 24.0),
    (-320.0, 31.0),
]

# Proving Shore 10-step Quest Order
PROVING_SHORE_QUEST_ORDER = [
    "q_ps_the_gauntlet",
    "q_ps_strike_true",
    "q_ps_hone_the_edge",
    "q_ps_shell_and_claw",
    "q_ps_mother_of_pearl",
    "q_ps_the_wreck_line",
    "q_ps_pouch_and_purse",
    "q_ps_the_signpost",
    "q_ps_the_long_walk",
    "q_ps_set_sail",
]

# Class-specific level-1 ability for q_ps_hone_the_edge
CLASS_STARTER_ABILITIES: Dict[str, str] = {
    "warrior": "heroic_strike",
    "paladin": "hammer_of_grace",
    "rogue": "sinister_strike",
    "hunter": "raptor_strike",
    "mage": "fireball",
    "warlock": "shadow_bolt",
    "priest": "smite",
    "shaman": "lightning_bolt",
    "druid": "wrath",
}

# Canonical Proving Shore Quest Descriptors
PROVING_SHORE_QUESTS = {
    "q_ps_the_gauntlet": {
        "giver_pos": (-283.0, -21.0),   # Warden Tam
        "turnin_pos": (-337.0, -33.0),  # Overseer Pell
        "type": "gauntlet_run",
    },
    "q_ps_strike_true": {
        "giver_pos": (-337.0, -33.0),  # Overseer Pell
        "turnin_pos": (-345.0, -11.0),  # Drillmaster Rook
        "hunt_pos": (-336.0, -14.0),    # Training Effigies
        "target": "training_effigy",
        "type": "kill",
    },
    "q_ps_hone_the_edge": {
        "giver_pos": (-345.0, -11.0),  # Drillmaster Rook
        "turnin_pos": (-345.0, -11.0),  # Drillmaster Rook
        "hunt_pos": (-336.0, -14.0),    # Training Effigies
        "target": "training_effigy",
        "type": "ability_drill",
    },
    "q_ps_shell_and_claw": {
        "giver_pos": (-345.0, -11.0),  # Drillmaster Rook
        "turnin_pos": (-371.0, -13.0),  # Tidewarden Nel
        "hunt_pos": (-380.0, -42.0),    # Scuttler Strand
        "target": "shore_scuttler",
        "type": "kill",
    },
    "q_ps_mother_of_pearl": {
        "giver_pos": (-371.0, -13.0),  # Tidewarden Nel
        "turnin_pos": (-371.0, -13.0),  # Tidewarden Nel
        "hunt_pos": (-398.0, -17.0),    # Crab pool summon spot
        "target": "mister_crabs",
        "type": "crab_boss",
    },
    "q_ps_the_wreck_line": {
        "giver_pos": (-371.0, -13.0),   # Tidewarden Nel
        "turnin_pos": (-312.0, 57.2),   # Quartermaster Finch
        "type": "crates",
    },
    "q_ps_pouch_and_purse": {
        "giver_pos": (-312.0, 57.2),   # Quartermaster Finch
        "turnin_pos": (-299.0, 49.0),   # Instructor Maren
        "type": "buy_pouch",
    },
    "q_ps_the_signpost": {
        "giver_pos": (-299.0, 49.0),   # Instructor Maren
        "turnin_pos": (-299.0, 49.0),   # Instructor Maren
        "hunt_pos": (-312.0, 42.5),    # Signpost spot
        "target": "ps_guild_signpost",
        "type": "signpost",
    },
    "q_ps_the_long_walk": {
        "giver_pos": (-299.0, 49.0),   # Instructor Maren
        "turnin_pos": (-299.0, 49.0),   # Instructor Maren
        "type": "death_lesson",
    },
    "q_ps_set_sail": {
        "giver_pos": (-299.0, 49.0),   # Instructor Maren
        "turnin_pos": (-284.0, -9.0),   # Ferryman Odo
        "type": "ferry_handoff",
    },
}

# Mainland Starter Quests (Eastbrook Vale)
MAINLAND_STARTER_QUESTS: Dict[str, Dict[str, Any]] = {
    "q_wolves": {
        "name": "Wolves at the Door",
        "giver_pos": (4.0, 6.0),       # Marshal Redbrook
        "turnin_pos": (4.0, 6.0),      # Marshal Redbrook
        "hunt_pos": (-10.0, 6.0),      # North Woods Wolf Camp
        "target": "forest_wolf",
        "type": "kill",
    },
    "q_boars": {
        "name": "A Meal for the Fieldhands",
        "giver_pos": (52.0, -26.0),    # Farmer Ray
        "turnin_pos": (52.0, -26.0),   # Farmer Ray
        "hunt_pos": (75.0, -45.0),     # Boar Meadow
        "target": "meadow_boar",
        "type": "kill",
    },
    "q_spiders": {
        "name": "Spider Infestation",
        "giver_pos": (52.0, -26.0),    # Farmer Ray
        "turnin_pos": (52.0, -26.0),   # Farmer Ray
        "hunt_pos": (110.0, -30.0),    # Forest Edge Spiders
        "target": "forest_spider",
        "type": "kill",
    },
    "q_greyjaw": {
        "name": "The Old Wolf",
        "giver_pos": (4.0, 6.0),       # Marshal Redbrook
        "turnin_pos": (4.0, 6.0),      # Marshal Redbrook
        "hunt_pos": (0.0, 100.0),      # Deep Woods
        "target": "old_greyjaw",
        "type": "kill",
    },
    "q_bandits": {
        "name": "Bandits in the Vale",
        "giver_pos": (4.0, 6.0),       # Marshal Redbrook
        "turnin_pos": (4.0, 6.0),      # Marshal Redbrook
        "hunt_pos": (-55.0, 45.0),     # Bandit Camp
        "target": "vale_bandit",
        "type": "kill",
    },
}

EASTBROOK_WAYPOINTS = [

    (-4.5, -101.5),    # Town Ferry Arrival Pier
    (-10.0, -85.0),    # Crafting District
    (-25.0, -60.0),    # Ravenpost Mailbox & Inn
    (4.0, 6.0),        # Town Center / Marshal Redbrook
    (52.0, -26.0),     # Eastbrook Farmlands / Farmer Ray
    (75.0, -45.0),     # Meadow Boars
    (-10.0, 6.0),      # North Woods Wolves
    (0.0, 100.0),      # Deep Woods Old Greyjaw
]


class QuestNavigator:
    """Calculates active macro quest goals based on quest log and completed quests."""

    active_mainland_quest: Optional[str] = None

    @classmethod
    def resolve_macro_objective(
        cls,
        my_x: float,
        my_z: float,
        qdone: set,
        qlog: Dict[str, Any],
        waypoint_index: int = 0,
        player_class: str = "warrior",
        is_ghost: bool = False,
    ) -> Tuple[float, float, str, str]:
        """
        Determines the next strategic goal:
        Returns: (goal_x, goal_z, goal_action, goal_param)
        """
        # 1. On Proving Shore Island (x < -200)
        if my_x < -200.0:
            for q_id in PROVING_SHORE_QUEST_ORDER:
                if q_id not in qdone:
                    info = PROVING_SHORE_QUESTS.get(q_id, {})

                    # If not yet in quest log -> go accept
                    if q_id not in qlog:
                        gx, gz = info.get("giver_pos", (my_x, my_z))
                        return gx, gz, "accept", q_id

                    # In quest log
                    q_entry = qlog[q_id]
                    q_state = q_entry.get("state")

                    # If quest is ready for turn-in -> go deliver
                    if q_state == "ready":
                        gx, gz = info.get("turnin_pos", (my_x, my_z))
                        return gx, gz, "turnin", q_id

                    # Quest in progress
                    if q_id == "q_ps_the_gauntlet":
                        counts = q_entry.get("counts", [0])
                        next_flag = counts[0] if counts else 0
                        if next_flag < len(GAUNTLET_CHECKPOINTS):
                            gx, gz = GAUNTLET_CHECKPOINTS[next_flag]
                            return gx, gz, "waypoint", f"Flag #{next_flag + 1}"
                        else:
                            gx, gz = info.get("turnin_pos", (my_x, my_z))
                            return gx, gz, "turnin", q_id

                    elif q_id == "q_ps_strike_true":
                        gx, gz = info.get("hunt_pos", (-336.0, -14.0))
                        return gx, gz, "hunt", "training_effigy"

                    elif q_id == "q_ps_hone_the_edge":
                        gx, gz = info.get("hunt_pos", (-336.0, -14.0))
                        ability = CLASS_STARTER_ABILITIES.get(player_class.lower(), "heroic_strike")
                        return gx, gz, "ability_drill", ability

                    elif q_id == "q_ps_shell_and_claw":
                        gx, gz = info.get("hunt_pos", (-380.0, -42.0))
                        return gx, gz, "hunt", "shore_scuttler"

                    elif q_id == "q_ps_mother_of_pearl":
                        gx, gz = info.get("hunt_pos", (-398.0, -17.0))
                        return gx, gz, "crab_boss", "ps_briny_lure"

                    elif q_id == "q_ps_the_wreck_line":
                        counts = q_entry.get("counts", [0])
                        opened_count = counts[0] if counts else 0
                        crate_idx = min(opened_count, len(WRECK_LINE_CRATES) - 1)
                        cx, cz = WRECK_LINE_CRATES[crate_idx]
                        return cx, cz, "crate", f"Crate #{crate_idx + 1}"

                    elif q_id == "q_ps_pouch_and_purse":
                        gx, gz = info.get("giver_pos", (-312.0, 57.2))
                        return gx, gz, "buy_pouch", "linen_pouch"

                    elif q_id == "q_ps_the_signpost":
                        gx, gz = info.get("hunt_pos", (-312.0, 42.5))
                        return gx, gz, "signpost", "ps_guild_signpost"

                    elif q_id == "q_ps_the_long_walk":
                        gx, gz = info.get("giver_pos", (-299.0, 49.0))
                        return gx, gz, "death_lesson", "ps_passing_stone"

                    elif q_id == "q_ps_set_sail":
                        gx, gz = info.get("turnin_pos", (-284.0, -9.0))
                        return gx, gz, "turnin", "q_ps_set_sail"

            # All 10 tutorial quests completed -> take ferry to mainland
            return -279.0, -10.0, "ferry", "ps_ferry_bell"

        # 2. On Mainland Eastbrook Vale (my_x >= -200.0)
        # Check if any mainland quest in log is ready for turn-in
        for q_id, q_data in qlog.items():
            if q_id in MAINLAND_STARTER_QUESTS and q_data.get("state") == "ready":
                turnin_pos = MAINLAND_STARTER_QUESTS[q_id]["turnin_pos"]
                return turnin_pos[0], turnin_pos[1], "turnin", q_id

        # Check if there is an active mainland quest currently in progress
        active_in_log = None
        for q_id, q_data in qlog.items():
            if q_id in MAINLAND_STARTER_QUESTS and q_data.get("state") == "active":
                active_in_log = q_id
                break

        if active_in_log:
            cls.active_mainland_quest = active_in_log
            info = MAINLAND_STARTER_QUESTS[active_in_log]
            hx, hz = info["hunt_pos"]
            return hx, hz, "hunt", info["target"]

        # No active quest in log -> pick a random uncompleted mainland quest
        available_quests = [
            qid for qid in MAINLAND_STARTER_QUESTS
            if qid not in qdone and qid not in qlog
        ]

        if available_quests:
            if cls.active_mainland_quest not in available_quests:
                cls.active_mainland_quest = random.choice(available_quests)
            target_qid = cls.active_mainland_quest
            info = MAINLAND_STARTER_QUESTS[target_qid]
            gx, gz = info["giver_pos"]
            return gx, gz, "accept", target_qid

        # If all starter quests are completed, explore mainland highway
        cls.active_mainland_quest = None
        wp = EASTBROOK_WAYPOINTS[waypoint_index % len(EASTBROOK_WAYPOINTS)]
        return wp[0], wp[1], "explore", "Eastbrook Highway"
