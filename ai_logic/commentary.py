"""
commentary.py
- Builds a concise human line. LLM hook is stubbed here; replace with your real model call later.
"""

from typing import Dict

def generate_line(persona: str, topic: str, reason: str, state: Dict) -> str:
    # Keep it short and on-brand. Persona could be "rage", "chill", etc.
    prefix = {
        "clutch_escape": "CLUTCH!",
        "great_kill": "Nasty!",
        "dive_warning": "Careful—",
        "momentum": "Momentum shift:"
    }.get(topic, "Info:")

    return f"{prefix} {reason or 'good read.'}"
