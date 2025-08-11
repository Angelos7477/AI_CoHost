"""
state_fuser.py
- Combines all extracted signals into a compact, caster-friendly game state snapshot.
"""

from typing import Dict, Any, List

def build_state(extracts: Dict[str, Any], history: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Basic structure
    state = {
        "t": extracts.get("timer", "00:00"),
        "minimap": extracts.get("minimap", {}),
        "screen": extracts.get("mainview", {}),
        "killfeed": extracts.get("killfeed", {"events":[]}),

        # Minimal counters to enable analyzers
        "ally_kills": _count_team_kills(history, "us"),
        "enemy_kills": _count_team_kills(history, "them"),
    }
    return state

def _count_team_kills(history, team):
    c = 0
    for s in history[-60:]:  # last ~window
        for ev in s.get("killfeed", {}).get("events", []):
            if ev.get("type") == "kill" and ev.get("killer_team") == team:
                c += 1
    return c
