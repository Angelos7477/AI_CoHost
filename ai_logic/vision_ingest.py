"""
vision_ingest.py
- Handles screen/window capture (stubbed for now) and ROI (Region Of Interest) calibration.
- Replace the stub in `ScreenGrabber.get_frame()` with your actual capture method (OBS preview, window handle, etc.).
"""

from dataclasses import dataclass, asdict
from typing import Dict, Optional
import json
import time
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "roi_config.json")

@dataclass
class ROI:
    # x, y, width, height in pixels
    x: int
    y: int
    w: int
    h: int

@dataclass
class ROIConfig:
    minimap: ROI = ROI(0, 0, 0, 0)
    killfeed: ROI = ROI(0, 0, 0, 0)
    timerbar: ROI = ROI(0, 0, 0, 0)
    champ_hud: ROI = ROI(0, 0, 0, 0)
    main_view: ROI = ROI(0, 0, 0, 0)

    def to_json(self) -> Dict:
        return {
            "minimap": asdict(self.minimap),
            "killfeed": asdict(self.killfeed),
            "timerbar": asdict(self.timerbar),
            "champ_hud": asdict(self.champ_hud),
            "main_view": asdict(self.main_view),
        }

    @staticmethod
    def from_json(d: Dict) -> "ROIConfig":
        def _roi(k):
            r = d.get(k, {"x":0,"y":0,"w":0,"h":0})
            return ROI(r["x"], r["y"], r["w"], r["h"])
        return ROIConfig(
            minimap=_roi("minimap"),
            killfeed=_roi("killfeed"),
            timerbar=_roi("timerbar"),
            champ_hud=_roi("champ_hud"),
            main_view=_roi("main_view"),
        )

def load_roi_config() -> ROIConfig:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return ROIConfig.from_json(json.load(f))
    return ROIConfig()

def save_roi_config(cfg: ROIConfig):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg.to_json(), f, indent=2)

class ScreenGrabber:
    def __init__(self, target_window_title: Optional[str] = None):
        self.target = target_window_title

    def get_frame(self):
        """
        Return a frame (numpy array HxWx3, BGR or RGB). Stub returns None.
        Integrate with mss/DirectX/OBS capture here.
        """
        time.sleep(0.01)
        return None  # TODO: replace with actual frame
