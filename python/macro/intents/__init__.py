"""
Macro Intents Package
Modular autonomous behaviors for living MMO bots.
"""

from .gear_intent import score_item, evaluate_inventory_upgrades, decide_loot_roll, HumanGearInspectionFSM
from .economy_intent import count_free_inventory_slots, should_visit_vendor, find_nearby_vendor, HumanVendorInteractionFSM
from .party_intent import PartyLifecycleManager
from .quest_intent import QuestNavigator, PROVING_SHORE_QUEST_ORDER, PROVING_SHORE_QUESTS, GAUNTLET_CHECKPOINTS, EASTBROOK_WAYPOINTS
from .curiosity_intent import CuriosityIntentManager, SCENIC_POINTS
