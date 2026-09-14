"""
Full Quest Lifecycle & World Exploration Intent Module
Covers the entire 10-step tutorial quest chain and mainland waypoints.
"""

from __future__ import annotations
from typing import Dict, Any, Tuple, Optional

# Proving Shore Gauntlet Checkpoints (Exact game coordinates from proving_shore.ts)
GAUNTLET_CHECKPOINTS = [
    (-308.0, -16.0),   # Flag 1
    (-308.0, -32.0),   # Flag 2
    (-334.0, -32.5),   # Flag 3 (Red Flag)
]

# Canonical Quest Descriptors (giver_coords, turnin_coords, hunt_coords, target_entity)
PROVING_SHORE_QUESTS = {
    "q_ps_the_gauntlet": {
        "giver_pos": (-283.0, -21.0),   # Warden Tam
        "turnin_pos": (-337.0, -33.0),  # Overseer Pell
        "type": "waypoints",
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
        "hunt_pos": (-336.0, -14.0),
        "target": "training_effigy",
        "type": "ability_drill",
    },
    "q_ps_shell_and_claw": {
        "giver_pos": (-345.0, -11.0),  # Drillmaster Rook
        "turnin_pos": (-371.0, -13.0),  # Tidewarden Nel
        "hunt_pos": (-360.0, 15.0),
        "target": "shore_scuttler",
        "type": "kill",
    },
    "q_ps_mother_of_pearl": {
        "giver_pos": (-371.0, -13.0),  # Tidewarden Nel
        "turnin_pos": (-371.0, -13.0),  # Tidewarden Nel
        "hunt_pos": (-375.0, 30.0),
        "target": "mister_crabs",
        "type": "loot",
    },
    "q_ps_the_wreck_line": {
        "giver_pos": (-345.0, -11.0),
        "turnin_pos": (-310.0, 25.0),
        "hunt_pos": (-325.0, 35.0),
        "target": "salvage_cargo",
        "type": "interact",
    },
    "q_ps_pouch_and_purse": {
        "giver_pos": (-310.0, 25.0),
        "turnin_pos": (-310.0, 25.0),
        "hunt_pos": (-295.0, 20.0),
        "target": "castaway_crate",
        "type": "loot",
    },
    "q_ps_the_signpost": {
        "giver_pos": (-310.0, 25.0),
        "turnin_pos": (-290.0, 5.0),
        "hunt_pos": (-290.0, 5.0),
        "target": "wooden_signpost",
        "type": "interact",
    },
    "q_ps_the_long_walk": {
        "giver_pos": (-290.0, 5.0),
        "turnin_pos": (-279.0, -10.0),
        "type": "travel",
    },
    "q_ps_set_sail": {
        "giver_pos": (-279.0, -10.0),
        "turnin_pos": (-4.5, -101.5),
        "hunt_pos": (-279.0, -10.0),
        "target": "ps_ferry_bell",
        "type": "ferry",
    },
}

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

EASTBROOK_WAYPOINTS = [
    (-4.5, -101.5),    # Town Ferry Arrival Pier
    (-10.0, -85.0),    # Crafting District
    (-25.0, -60.0),    # Ravenpost Mailbox & Inn
    (15.0, -40.0),     # Town Gate / Bridge
    (60.0, 10.0),      # Eastbrook Farmlands
    (120.0, 50.0),     # River Crossing
    (80.0, 120.0),     # Forest Outpost
]


class QuestNavigator:
    """Calculates active macro quest goals based on quest log and completed quests."""

    @staticmethod
    def resolve_macro_objective(
        my_x: float,
        my_z: float,
        qdone: set,
        qlog: Dict[str, Any],
        waypoint_index: int = 0
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
                    if q_id not in qlog:
                        # Need to accept
                        gx, gz = info.get("giver_pos", (my_x, my_z))
                        return gx, gz, "accept", q_id
                    else:
                        q_entry = qlog[q_id]
                        if q_entry.get("state") == "ready":
                            # Ready to turn in
                            gx, gz = info.get("turnin_pos", (my_x, my_z))
                            return gx, gz, "turnin", q_id
                        else:
                            # In progress
                            if q_id == "q_ps_the_gauntlet":
                                counts = q_entry.get("counts", [0])
                                next_flag = counts[0] if counts else 0
                                if next_flag < len(GAUNTLET_CHECKPOINTS):
                                    gx, gz = GAUNTLET_CHECKPOINTS[next_flag]
                                    return gx, gz, "waypoint", f"Flag #{next_flag + 1}"
                                else:
                                    gx, gz = info.get("turnin_pos", (my_x, my_z))
                                    return gx, gz, "turnin", q_id
                            elif q_id == "q_ps_set_sail":
                                return -279.0, -10.0, "ferry", "ps_ferry_bell"
                            else:
                                # Hunt / interact objective
                                gx, gz = info.get("hunt_pos", (my_x, my_z))
                                target_mob = info.get("target", "mob")
                                return gx, gz, "hunt", target_mob

            # Default if all island quests done -> sail to mainland
            return -279.0, -10.0, "ferry", "ps_ferry_bell"

        # 2. On Mainland Eastbrook Vale (x >= -200)
        wp = EASTBROOK_WAYPOINTS[waypoint_index % len(EASTBROOK_WAYPOINTS)]
        return wp[0], wp[1], "explore", "Eastbrook Highway"
