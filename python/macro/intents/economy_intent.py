"""
Economy & Bag Management Intent Module
Handles inventory thresholds, junk disposal at vendors, and equipment liquidation.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional


def count_free_inventory_slots(inventory: list, max_slots: int = 16) -> int:
    """Returns number of empty slots in the bag."""
    if not isinstance(inventory, list):
        return max_slots
    occupied = sum(1 for item in inventory if item is not None and isinstance(item, dict))
    return max(0, max_slots - occupied)


def has_junk(inventory: list) -> bool:
    """Checks whether the bag contains any poor/junk items that can be liquidated."""
    if not isinstance(inventory, list):
        return False
    return any(item and item.get("rarity") in ("poor", "junk", "gray") for item in inventory if isinstance(item, dict))


def should_visit_vendor(inventory: list, in_combat: bool, free_threshold: int = 3, opportunist: bool = False) -> bool:
    """Decides if the bot needs to visit a merchant (either bag full or has junk when nearby)."""
    if in_combat:
        return False
    free_slots = count_free_inventory_slots(inventory)
    if free_slots <= free_threshold:
        return True
    if opportunist and has_junk(inventory):
        return True
    return False


def find_nearby_vendor(entities: Dict[str, Any], my_x: float, my_z: float, max_dist: float = 35.0) -> Optional[Dict[str, Any]]:
    """Locates the nearest merchant/vendor NPC within reach."""
    best_vendor = None
    min_d = float("inf")

    for ent_id, ent in entities.items():
        if ent.get("k") != "npc":
            continue

        # Check vendor flags or merchant tags
        is_vendor = (
            bool(ent.get("vendor"))
            or bool(ent.get("merchant"))
            or "vendor" in str(ent.get("nm", "")).lower()
            or "merchant" in str(ent.get("nm", "")).lower()
            or "supply" in str(ent.get("nm", "")).lower()
        )
        if not is_vendor:
            continue

        ex = ent.get("x", 0.0)
        ez = ent.get("z", 0.0)
        d = ((ex - my_x) ** 2 + (ez - my_z) ** 2) ** 0.5
        if d <= max_dist and d < min_d:
            min_d = d
            best_vendor = ent

    return best_vendor


def get_vendor_disposal_actions(inventory: list, vendor_id: int) -> List[Dict[str, Any]]:
    """
    Generates command payloads to sell junk and obsolete gear.
    First prioritizes 'sell_all_junk', followed by specific gray/poor items.
    """
    actions = [{"t": "cmd", "cmd": "sell_all_junk"}]

    for idx, item in enumerate(inventory):
        if not item or not isinstance(item, dict):
            continue
        # Sell poor items directly if needed
        if item.get("rarity") == "poor" or item.get("quality") == 0:
            actions.append({"t": "cmd", "cmd": "sell", "slot": idx, "vendorId": vendor_id})

    return actions
