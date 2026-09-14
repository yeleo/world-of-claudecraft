"""
Party Lifecycle, Group Loot Roll & Social Cohesion Intent Module
Provides lifelike dynamic grouping, looting arbitration, and natural departure.
"""

from __future__ import annotations
import math
import random
from typing import Dict, Any, List, Optional, Tuple
from .gear_intent import decide_loot_roll

PARTY_FAREWELL_LINES = [
    "我先去城里把任务交了，大家有缘再会！",
    "辛苦各位！我先走一步去学新技能了，后会有期~",
    "背包满了，我回营地找商人清一下包，大家加油！",
    "感谢组队！这一趟打得很爽，咱们江湖再见！",
]

PARTY_RECRUIT_LINES = [
    "组队做任务吗？一起效率高！",
    "前面的朋友，要不要组个队一起清怪？",
    "战法牧小队差人，一起做新手任务走起！",
]


class PartyLifecycleManager:
    """Manages bot party formation, loot voting, and natural dispersal."""

    def __init__(self, bot_pid: int, player_class: str, is_solo_personality: bool = False):
        self.bot_pid = bot_pid
        self.player_class = player_class
        self.is_solo_personality = is_solo_personality
        self.last_invite_time = 0.0
        self.last_farewell_time = 0.0

    def should_accept_invite(self, inviter_name: str, in_combat: bool) -> bool:
        """Decides whether to accept incoming party invitation."""
        if in_combat:
            return False
        if self.is_solo_personality and random.random() < 0.65:
            # Lone wolves occasionally decline
            return False
        return True

    def evaluate_group_formation(
        self,
        party_data: Optional[Dict[str, Any]],
        nearby_players: List[Dict[str, Any]],
        now: float
    ) -> Optional[int]:
        """
        Periodically looks around to recruit lonely players/bots into party.
        Returns target PID to invite, or None.
        """
        if self.is_solo_personality:
            return None

        is_in_party = isinstance(party_data, dict) and len(party_data.get("members", [])) >= 2
        is_leader = (party_data.get("leader") == self.bot_pid) if is_in_party else True

        if is_in_party and not is_leader:
            return None  # Only leader or solo player initiates invites

        # Party size ceiling (5 members in WoW group)
        curr_size = len(party_data.get("members", [])) if is_in_party else 1
        if curr_size >= 5:
            return None

        if now - self.last_invite_time < 12.0:
            return None

        for p in nearby_players:
            pid = p.get("id") or p.get("pid")
            if pid and pid != self.bot_pid and not p.get("dead") and not p.get("party"):
                self.last_invite_time = now
                return pid

        return None

    def evaluate_departure_decision(
        self,
        party_data: Optional[Dict[str, Any]],
        quests_done: set,
        milestone_quest: str = "q_ps_set_sail"
    ) -> Tuple[bool, str]:
        """
        Decides if it's time to naturally leave group after completing milestones.
        Returns: (should_leave, farewell_message)
        """
        if not isinstance(party_data, dict) or len(party_data.get("members", [])) < 2:
            return False, ""

        # Leaving condition: Milestone reached, e.g., graduated tutorial island and arrived in town
        if milestone_quest in quests_done and random.random() < 0.85:
            farewell = random.choice(PARTY_FAREWELL_LINES)
            return True, farewell

        return False, ""

    def process_loot_roll_event(self, roll_id: int, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generates the loot roll command payload."""
        decision = decide_loot_roll(item_data, self.player_class)
        return {
            "t": "cmd",
            "cmd": "lootRoll",
            "rollId": roll_id,
            "roll": decision,
        }

    def resolve_mob_competition(
        self,
        target_mob: Dict[str, Any],
        party_data: Optional[Dict[str, Any]],
        now: float,
    ) -> Tuple[str, Optional[int]]:
        """
        Evaluates a contested mob to avoid bottleneck congestion:
        Returns: ('attack', None) | ('invite_coop', competitor_pid) | ('yield_and_switch', None)
        """
        if not target_mob.get("combat"):
            return "attack", None

        attacker_pid = target_mob.get("target") or target_mob.get("taggedBy")
        if not attacker_pid or attacker_pid == self.bot_pid:
            return "attack", None

        # Check if attacker is a party member
        if isinstance(party_data, dict):
            member_pids = {m.get("pid") for m in party_data.get("members", []) if isinstance(m, dict)}
            if attacker_pid in member_pids:
                return "attack", None

        # Contested by external competitor -> Attempt cooperative grouping
        is_in_party = isinstance(party_data, dict) and len(party_data.get("members", [])) >= 2
        is_leader = (party_data.get("leader") == self.bot_pid) if is_in_party else True
        party_size = len(party_data.get("members", [])) if is_in_party else 1

        if is_leader and party_size < 5 and now - self.last_invite_time > 8.0:
            self.last_invite_time = now
            return "invite_coop", attacker_pid

        # In crowded bottlenecks, smart players yield contested mobs to find alternatives
        return "yield_and_switch", None

    def evaluate_social_flair(
        self,
        my_x: float,
        my_z: float,
        nearby_players: List[Dict[str, Any]],
        now: float
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Simulates authentic MMORPG player mannerisms:
        - Passing by friends/strangers and sharing class buffs (Arcane Intellect, Mark of Wild, Fortitude)
        - Waving / nodding to peers at campfires and quest turn-in hubs
        """
        # 1. Class Buff Sharing
        CLASS_BUFFS = {
            "mage": ("arcane_intellect", "Arcane Intellect"),
            "priest": ("power_word_fortitude", "Power Word: Fortitude"),
            "druid": ("mark_of_the_wild", "Mark of the Wild"),
            "paladin": ("blessing_of_might", "Blessing of Might"),
        }
        if self.player_class in CLASS_BUFFS and (now - getattr(self, "last_buff_time", -999.0)) > 20.0:
            buff_key, buff_name = CLASS_BUFFS[self.player_class]
            for p in nearby_players:
                pid = p.get("id") or p.get("pid")
                if pid and pid != self.bot_pid and not p.get("dead") and not p.get("offline"):
                    p_buffs = p.get("buffs", [])
                    if buff_key not in p_buffs:
                        d = math.hypot(p.get("x", 0.0) - my_x, p.get("z", 0.0) - my_z)
                        if d <= 12.0:
                            self.last_buff_time = now
                            return (
                                {"t": "cmd", "cmd": "cast", "ability": buff_key, "target": pid},
                                f"Cast beneficial buff '{buff_name}' on peer #{pid}"
                            )

        # 2. Friendly Emotes at social hubs (Campfire, pell)
        if (now - getattr(self, "last_emote_time", -999.0)) > 35.0 and random.random() < 0.15:
            for p in nearby_players:
                pid = p.get("id") or p.get("pid")
                if pid and pid != self.bot_pid and not p.get("dead") and not p.get("offline"):
                    d = math.hypot(p.get("x", 0.0) - my_x, p.get("z", 0.0) - my_z)
                    if d <= 6.0:
                        self.last_emote_time = now
                        emote_type = random.choice(["wave", "nod", "cheer"])
                        return (
                            {"t": "cmd", "cmd": "emote", "emote": emote_type, "target": pid},
                            f"Friendly gesture /{emote_type} to fellow adventurer #{pid}"
                        )

        return None

