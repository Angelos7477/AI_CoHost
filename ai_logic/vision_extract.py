"""
vision_extract.py
- Extracts information from cropped regions of the frame.
- Stubs return plausible dummy values to let the pipeline run.
- Replace with real computer-vision and OCR later.
"""

from typing import Dict, Any
import random
import time

def ocr_killfeed(frame_crop) -> Dict[str, Any]:
    """
    Read killfeed text and interpret events.
    Return dict like: {"events": [{"type":"kill","killer_team":"us","shutdown":True}, ...]}
    """
    # Stub: randomly emit a kill event sometimes
    events = []
    if random.random() < 0.1:
        events.append({
            "type": "kill",
            "killer_team": random.choice(["us", "them"]),
            "shutdown": random.random() < 0.3
        })
    return {"events": events}

def read_game_timer(timer_crop) -> str:
    """OCR the game clock, like '12:45'. Stub increments time."""
    # In a real impl, OCR this region. Here we fake a timer based on wallclock seconds.
    t = int(time.time()) % (60*60)
    mm = (t // 60) % 60
    ss = t % 60
    return f"{mm:02d}:{ss:02d}"

def detect_minimap_counts(minimap_crop) -> Dict[str, Dict[str, int]]:
    """
    Count ally/enemy dots around certain zones (dragon, baron, mid river, bot river).
    """
    # Stub: random plausible counts
    def rr(): return random.randint(0, 4)
    return {
        "near_dragon": {"us": rr(), "them": rr()},
        "near_baron": {"us": rr(), "them": rr()},
        "near_mid_river": {"us": rr(), "them": rr()},
        "near_bot_lane_river": {"us": rr(), "them": rr()},
    }

def detect_mainview_features(main_crop) -> Dict[str, Any]:
    """
    Detect on-screen cues: our hp, nearest enemies, tower on screen, tower aggro, fight intensity.
    """
    hp = max(0.05, min(1.0, random.gauss(0.55, 0.2)))
    return {
        "our_champ_hp": round(hp, 2),
        "nearest_enemies_screen": random.randint(0, 3),
        "tower_on_screen": random.random() < 0.3,
        "tower_aggro_on_us": random.random() < 0.1,
        "fight_intensity": round(max(0.0, min(1.0, random.random())), 2),
        "we_are_under_enemy_tower": random.random() < 0.2,
    }
