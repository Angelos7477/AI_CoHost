"""
talk_policy.py
- Chooses whether to speak now and which topic, with simple cooldowns and priorities.
"""

from typing import Dict, Any, Tuple
import time

PRIORITY = ["clutch_escape", "great_kill", "dive_warning", "momentum"]
COOLDOWNS = {
    "clutch_escape": 12.0,
    "great_kill": 10.0,
    "dive_warning": 8.0,
    "momentum": 20.0,
}

def decide_topic(scores: Dict[str, Dict[str, Any]], last_spoken: Dict[str, float]) -> Tuple[bool, str, str]:
    """
    scores: {"great_kill":{"score":..,"reason":..}, "dive_warning":..., "clutch_escape":..., "momentum":...}
    last_spoken: topic->timestamp of last time spoken
    Returns (speak, topic, reason)
    """
    now = time.time()
    candidate = None
    best_priority = 999
    reason = ""

    for idx, topic in enumerate(PRIORITY):
        sc = scores.get(topic, {}).get("score", 0.0)
        if sc >= 0.7:  # threshold
            cd = COOLDOWNS.get(topic, 10.0)
            if (now - last_spoken.get(topic, 0.0)) >= cd:
                if idx < best_priority:
                    best_priority = idx
                    candidate = topic
                    reason = scores[topic]["reason"]

    if candidate:
        last_spoken[candidate] = now
        return True, candidate, reason
    return False, "", ""
