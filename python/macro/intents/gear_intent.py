"""
Gear Evaluation & Auto-Equipping Intent Module
Supports all 9 player classes with canonical WoW stat weightings and armor restrictions.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Tuple

# Allowed armor types per class
# Cloth (0), Leather (1), Mail (2), Plate (3)
CLASS_ARMOR_ALLOWANCE = {
    "mage": {"cloth"},
    "priest": {"cloth"},
    "warlock": {"cloth"},
    "rogue": {"cloth", "leather"},
    "druid": {"cloth", "leather"},
    "hunter": {"cloth", "leather", "mail"},
    "shaman": {"cloth", "leather", "mail"},
    "warrior": {"cloth", "leather", "mail", "plate"},
    "paladin": {"cloth", "leather", "mail", "plate"},
}

# Stat weight matrices per class (normalized relative weights)
STAT_WEIGHTS = {
    "warrior": {"str": 1.2, "sta": 1.0, "agi": 0.4, "armor": 0.05, "dps": 2.5, "ap": 0.5},
    "paladin": {"str": 1.0, "sta": 1.0, "int": 0.7, "spi": 0.4, "armor": 0.05, "dps": 2.0, "sp": 0.8},
    "hunter": {"agi": 1.3, "sta": 0.9, "int": 0.4, "dps": 2.6, "ap": 0.5, "ranged_dps": 3.0},
    "rogue": {"agi": 1.4, "sta": 0.9, "str": 0.5, "dps": 2.8, "ap": 0.5},
    "priest": {"int": 1.3, "spi": 1.1, "sta": 0.8, "sp": 1.4, "heal": 1.5},
    "shaman": {"int": 1.0, "agi": 0.8, "str": 0.8, "sta": 0.9, "sp": 1.2, "dps": 2.0},
    "mage": {"int": 1.4, "sta": 0.8, "spi": 0.6, "sp": 1.5},
    "warlock": {"int": 1.3, "sta": 1.1, "spi": 0.4, "sp": 1.5},
    "druid": {"int": 1.0, "agi": 1.0, "str": 0.7, "sta": 0.9, "spi": 0.7, "dps": 2.0, "sp": 1.1},
}


def score_item(item: Dict[str, Any], player_class: str) -> float:
    """Calculates a heuristic score for an item based on player's class."""
    if not isinstance(item, dict):
        return -1.0

    # Armor allowance verification
    kind = item.get("kind", "")
    armor_type = item.get("armorType")
    allowed_armors = CLASS_ARMOR_ALLOWANCE.get(player_class, set())

    if kind == "armor" and armor_type and armor_type not in allowed_armors:
        return -1.0  # Cannot equip

    weights = STAT_WEIGHTS.get(player_class, {"sta": 1.0, "str": 0.5, "agi": 0.5, "int": 0.5})
    score = 0.0

    # Base item level / rarity
    rarity = item.get("rarity", "common")
    rarity_mult = {"poor": 0.2, "common": 1.0, "uncommon": 1.4, "rare": 2.0, "epic": 3.0}.get(rarity, 1.0)

    # Primary stats
    stats = item.get("stats", {})
    if isinstance(stats, dict):
        for stat_key, stat_val in stats.items():
            if isinstance(stat_val, (int, float)):
                w = weights.get(stat_key, 0.1)
                score += stat_val * w

    # Direct properties
    armor_val = item.get("armor", 0)
    if armor_val:
        score += armor_val * weights.get("armor", 0.02)

    dps_val = item.get("dps", 0)
    if dps_val:
        score += dps_val * weights.get("dps", 2.0)

    return score * rarity_mult


def evaluate_inventory_upgrades(
    inventory: list,
    equipment: Dict[str, Any],
    player_class: str
) -> Optional[Tuple[int, str]]:
    """
    Scans the inventory to find the highest-value upgrade against currently equipped gear.
    Returns: (inv_slot_index, equip_slot_name) or None if no upgrade is found.
    """
    best_upgrade = None
    max_score_delta = 0.0

    for inv_idx, item in enumerate(inventory):
        if not item or not isinstance(item, dict):
            continue

        equip_slot = item.get("slot") or item.get("equipSlot")
        if not equip_slot:
            continue

        new_score = score_item(item, player_class)
        if new_score <= 0.0:
            continue

        current_item = equipment.get(equip_slot) if isinstance(equipment, dict) else None
        curr_score = score_item(current_item, player_class) if current_item else 0.0

        delta = new_score - curr_score
        if delta > max_score_delta:
            max_score_delta = delta
            best_upgrade = (inv_idx, equip_slot)

    return best_upgrade


def decide_loot_roll(item: Dict[str, Any], player_class: str) -> str:
    """
    Determines roll action when a group loot roll prompt appears:
    Returns: 'need', 'greed', or 'pass'
    """
    score = score_item(item, player_class)
    if score <= 0.0:
        # Cannot wear or useless -> Greed for vendor gold, or pass
        return "greed" if item.get("rarity") in ("uncommon", "rare", "epic") else "pass"
    elif score > 15.0:
        # Direct genuine upgrade for class kit
        return "need"
    else:
        return "greed"
