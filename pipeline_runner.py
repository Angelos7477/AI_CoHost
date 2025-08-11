"""
pipeline_runner.py
- Minimal loop that runs the perception/analyzer/policy pipeline.
- Safe to run; uses stubs that emit plausible events. Later, swap in real vision + OCR.
"""

import time, json, os, datetime
from typing import List, Dict, Any

from ai_logic.vision_ingest import ScreenGrabber, load_roi_config
import ai_logic.vision_extract as vx
from ai_logic.state_fuser import build_state
from ai_logic.play_analyzers import score_great_kill, score_tower_dive_risk, detect_clutch_escape, score_momentum_swing
from ai_logic.talk_policy import decide_topic
from ai_logic.commentary import generate_line

LOGS = os.path.join(os.path.dirname(__file__), "logs", "plays.jsonl")
OUT_TXT = os.path.join(os.path.dirname(__file__), "out", "overlay.txt")

def ensure_dirs():
    os.makedirs(os.path.dirname(LOGS), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_TXT), exist_ok=True)

def run_pipeline(iterations: int = 100):
    ensure_dirs()
    grabber = ScreenGrabber()
    _ = load_roi_config()  # reserved for when you crop real ROIs

    history: List[Dict[str, Any]] = []
    last_spoken = {}
    last_low_hp_tick = None
    persona = "chill"

    for _ in range(iterations):
        frame = grabber.get_frame()  # None in stub

        # Extract (use frame crops later)
        extracts = {
            "killfeed": vx.ocr_killfeed(None),
            "timer": vx.read_game_timer(None),
            "minimap": vx.detect_minimap_counts(None),
            "mainview": vx.detect_mainview_features(None),
        }

        # Build state and keep short history
        state = build_state(extracts, history)
        history.append(state)
        history = history[-120:]

        # Analyze
        gk_score, gk_reason = score_great_kill(state)
        dr_score, dr_reason = score_tower_dive_risk(state)
        ce_score, ce_reason, last_low_hp_tick = detect_clutch_escape(state, last_low_hp_tick)
        mo_score, mo_reason = score_momentum_swing(history)

        scores = {
            "great_kill": {"score": gk_score, "reason": gk_reason},
            "dive_warning": {"score": dr_score, "reason": dr_reason},
            "clutch_escape": {"score": ce_score, "reason": ce_reason},
            "momentum": {"score": mo_score, "reason": mo_reason},
        }

        speak, topic, reason = decide_topic(scores, last_spoken)

        if speak:
            line = generate_line(persona, topic, reason, state)
            print(f"[{state['t']}] {topic}: {line}")
            # Append to log
            with open(LOGS, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": datetime.datetime.utcnow().isoformat(),
                    "topic": topic,
                    "reason": reason,
                    "state": state,
                    "scores": scores,
                    "line": line,
                }) + "\n")
            # Write to out file (can be tailed by your overlay)
            with open(OUT_TXT, "w", encoding="utf-8") as f:
                f.write(line)

        time.sleep(0.4)

if __name__ == "__main__":
    run_pipeline(80)
