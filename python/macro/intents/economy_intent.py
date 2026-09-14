"""
Economy & Multi-Stage Human-like Vendor Interaction Module
Implements realistic player trading behavior with deliberate pauses:
Approach -> Open Window (hesitation) -> Browse Bags (inspection) -> Staggered Item Clicks -> Window Close
"""

from __future__ import annotations
import random
from typing import Dict, Any, List, Optional, Tuple


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
    return any(
        item and item.get("rarity") in ("poor", "junk", "gray")
        for item in inventory
        if isinstance(item, dict)
    )


def should_visit_vendor(inventory: list, in_combat: bool, free_threshold: int = 3, opportunist: bool = False) -> bool:
    """Decides if the bot needs to visit a merchant."""
    if in_combat:
        return False
    free_slots = count_free_inventory_slots(inventory)
    if free_slots <= free_threshold:
        return True
    if opportunist and has_junk(inventory):
        return True
    return False


def find_nearby_vendor(entities: Dict[Any, Any], my_x: float, my_z: float, max_dist: float = 35.0) -> Optional[Dict[str, Any]]:
    """Locates the nearest merchant/vendor NPC within reach."""
    best_vendor = None
    min_d = float("inf")

    for ent_id, ent in entities.items():
        if ent.get("k") != "npc":
            continue

        is_vendor = (
            bool(ent.get("vendor"))
            or bool(ent.get("merchant"))
            or "vendor" in str(ent.get("nm", "")).lower()
            or "merchant" in str(ent.get("nm", "")).lower()
            or "quartermaster" in str(ent.get("nm", "")).lower()
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


class HumanVendorInteractionFSM:
    """
    State machine that orchestrates authentic, human-paced interaction with an NPC merchant.
    States:
      IDLE -> APPROACHING -> OPENING_WINDOW -> BROWSING_INVENTORY -> SELLING_ITEMS -> CLOSING_WINDOW -> FINISHED
    """

    def __init__(self, bot_pid: int):
        self.bot_pid = bot_pid
        self.state = "IDLE"
        self.active_vendor_id: Optional[int] = None
        self.state_start_time = 0.0
        self.next_action_time = 0.0
        self.pending_sell_indices: List[int] = []
        self.current_sell_ptr = 0

    def is_busy(self) -> bool:
        """Returns True if bot is currently engaged in an active vendor transaction session."""
        return self.state not in ("IDLE", "FINISHED")

    def start_transaction(self, vendor_id: int, inventory: list, now: float):
        """Initiates a realistic multi-step vendor visit."""
        self.state = "OPENING_WINDOW"
        self.active_vendor_id = vendor_id
        self.state_start_time = now
        # Human hesitation to click NPC and wait for vendor dialog window to slide open
        self.next_action_time = now + random.uniform(0.8, 1.4)

        # Collect slots containing junk to sell
        self.pending_sell_indices = []
        for idx, item in enumerate(inventory):
            if item and isinstance(item, dict) and item.get("rarity") in ("poor", "junk", "gray"):
                self.pending_sell_indices.append(idx)
        self.current_sell_ptr = 0

    def step_transaction(self, now: float, inventory: list) -> Tuple[List[Dict[str, Any]], str]:
        """
        Advances the vendor interaction for the current tick.
        Returns: (commands_to_send, narrative_log)
        """
        if self.state == "IDLE" or self.state == "FINISHED":
            return [], ""

        # Waiting for next human deliberate action timestamp
        if now < self.next_action_time:
            # Player is standing still, visually examining the open vendor frame
            return [{"t": "input", "mi": {}}], f"Standing at merchant window ({self.state})"

        # 1. Window just finished opening -> Now browsing inventory
        if self.state == "OPENING_WINDOW":
            self.state = "BROWSING_INVENTORY"
            # Player scans their bags to identify which items are safe to sell
            inspect_duration = random.uniform(1.2, 2.2) if self.pending_sell_indices else 0.8
            self.next_action_time = now + inspect_duration
            return [{"t": "input", "mi": {}}], "Browsing bag items and reviewing vendor prices"

        # 2. Done inspecting -> Click items one-by-one with realistic mouse click intervals
        elif self.state == "BROWSING_INVENTORY":
            if not self.pending_sell_indices or self.current_sell_ptr >= len(self.pending_sell_indices):
                # Nothing to sell or already empty
                self.state = "CLOSING_WINDOW"
                self.next_action_time = now + random.uniform(0.5, 0.9)
                return [{"t": "input", "mi": {}}], "No further junk to liquidate"
            else:
                self.state = "SELLING_ITEMS"
                return self.step_transaction(now, inventory)

        # 3. Selling item-by-item (staggered right-clicks)
        elif self.state == "SELLING_ITEMS":
            if self.current_sell_ptr < len(self.pending_sell_indices):
                slot_idx = self.pending_sell_indices[self.current_sell_ptr]
                self.current_sell_ptr += 1

                # Generate single item sell packet
                cmd = {
                    "t": "cmd",
                    "cmd": "sell",
                    "slot": slot_idx,
                    "vendorId": self.active_vendor_id,
                }
                # Also include sell_all_junk if last item for safety
                cmds = [cmd]
                if self.current_sell_ptr >= len(self.pending_sell_indices):
                    cmds.append({"t": "cmd", "cmd": "sell_all_junk"})

                # Realistic click delay between items (0.35s ~ 0.70s)
                click_delay = random.uniform(0.35, 0.70)
                # Occasional slight hesitation (thinking pause)
                if random.random() < 0.20:
                    click_delay += random.uniform(0.4, 0.8)

                self.next_action_time = now + click_delay
                return cmds, f"Right-clicked item in bag slot #{slot_idx} to sell"
            else:
                # Sold everything
                self.state = "CLOSING_WINDOW"
                self.next_action_time = now + random.uniform(0.6, 1.1)
                return [{"t": "input", "mi": {}}], "Finished selling items; closing vendor window"

        # 4. Closing Window and stepping away
        elif self.state == "CLOSING_WINDOW":
            self.state = "FINISHED"
            self.active_vendor_id = None
            self.pending_sell_indices = []
            return [{"t": "input", "mi": {}}], "Closed vendor window, ready to resume adventure"

        return [], ""
