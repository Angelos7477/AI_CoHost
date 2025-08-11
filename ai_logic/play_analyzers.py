"""
play_analyzers.py
- Heuristic analyzers that return a score [0,1] and an explanation string.
- Replace pieces with learned models later.
"""

from typing import Dict, Any, Tuple
import math

def score_great_kill(state: Dict[str, Any]) -> Tuple[float, str]:
    # Look for our kills in the current tick
    events = state.get("killfeed", {}).get("events", [])
    if not any(e.get("type")=="kill" and e.get("killer_team")=="us" for e in events):
        return 0.0, ""

    screen = state.get("screen", {})
    them_near = screen.get("nearest_enemies_screen", 0)
    our_hp = screen.get("our_champ_hp", 1.0)

    # Components
    outnumbered = max(0, (them_near - 1)) / 3.0
    low_hp     = max(0, (0.25 - our_hp)) / 0.25
    tower      = 1.0 if screen.get("we_are_under_enemy_tower") else 0.0
    shutdown   = 1.0 if any(e.get("shutdown") for e in events if e.get("killer_team")=="us") else 0.0
    one_vs_many = 1.0 if (them_near >= 2) else 0.0

    score = (0.25*outnumbered + 0.25*low_hp + 0.2*tower + 0.2*shutdown + 0.1*one_vs_many)
    reasons = []
    if outnumbered>0: reasons.append("outnumbered")
    if low_hp>0: reasons.append("low HP")
    if tower>0: reasons.append("under tower")
    if shutdown>0: reasons.append("shutdown")
    if one_vs_many>0: reasons.append("1vX")
    return min(1.0, max(0.0, score)), ", ".join(reasons)

def score_tower_dive_risk(state: Dict[str, Any]) -> Tuple[float, str]:
    s = state.get("screen", {})
    in_tower = 1.0 if (s.get("tower_on_screen") and s.get("we_are_under_enemy_tower")) else 0.0
    no_wave  = 0.5  # TODO: derive from minimap lane dots near tower
    aggro    = 0.3 if s.get("tower_aggro_on_us") else 0.0
    enemy_rot = 0.2 if s.get("nearest_enemies_screen", 0) >= 2 else 0.0
    low_hp   = 0.2 if s.get("our_champ_hp", 1) < 0.35 else 0.0

    risk = 0.4*in_tower + 0.2*no_wave + aggro + enemy_rot + low_hp
    reasons = []
    if in_tower: reasons.append("in tower range")
    if no_wave>0: reasons.append("no wave")
    if aggro>0: reasons.append("tower aggro")
    if enemy_rot>0: reasons.append("enemies rotating")
    if low_hp>0: reasons.append("low HP")
    return min(1.0, risk), ", ".join(reasons)

def detect_clutch_escape(state: Dict[str, Any], last_low_hp_tick: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
    """
    Returns (score, reason, updated_last_low_hp_tick)
    - Track when HP < 0.15; if we survive ~5s and recover, call it clutch.
    """
    s = state.get("screen", {})
    hp = s.get("our_champ_hp", 1.0)

    # Start low-HP window
    if hp < 0.15 and (last_low_hp_tick is None or not last_low_hp_tick.get("active")):
        last_low_hp_tick = {"active": True, "t": state.get("t", "00:00")}

    # Resolve clutch if active and hp recovered
    if last_low_hp_tick and last_low_hp_tick.get("active") and hp > 0.30:
        last_low_hp_tick["active"] = False
        return 0.9, "hp recovered from critical; survived chase", last_low_hp_tick

    return 0.0, "", last_low_hp_tick

def score_momentum_swing(history) -> Tuple[float, str]:
    # Very simple proxy: compare team kills last ~30 ticks
    us = 0
    them = 0
    for st in history[-30:]:
        for ev in st.get("killfeed", {}).get("events", []):
            if ev.get("type")=="kill":
                if ev.get("killer_team")=="us": us += 1
                else: them += 1
    diff = us - them
    # Map diff to [0,1]
    score = 1/(1+math.exp(-diff))  # sigmoid
    if abs(diff) >= 2:
        reason = "our run" if diff>0 else "their run"
        return score, f"swing: {reason}"
    return 0.0, ""
