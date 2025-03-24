# triggers/game_triggers.py

import time
import random

class GameTrigger:
    """Base class for all game triggers."""
    def check(self, current_data: dict, previous_data: dict) -> str | None:
        return None


class HPDropTrigger(GameTrigger):
    """Trigger when HP drops by a certain percentage in one loop."""
    def __init__(self, threshold_percent=25, cooldown=20):
        self.threshold = threshold_percent
        self.cooldown = cooldown
        self.last_trigger_time = 0

    def check(self, current_data, previous_data):
        now = time.time()
        if now - self.last_trigger_time < self.cooldown:
            return None

        prev_hp = previous_data.get("last_hp", 0)
        curr_hp = current_data.get("hp", 0)

        if prev_hp <= 0 or curr_hp <= 0:
            return None

        drop = ((prev_hp - curr_hp) / max(prev_hp, 1)) * 100
        if drop >= self.threshold:
            self.last_trigger_time = now
            return f"Player just took a big hit! Lost {int(drop)}% HP."
        return None


class CSMilestoneTrigger(GameTrigger):
    """Trigger when a new CS milestone is reached (30, 60, etc)."""
    def __init__(self, step=30):
        self.step = step
        self.last_milestone = 0

    def check(self, current_data, previous_data):
        cs = current_data.get("cs", 0)
        milestone = (cs // self.step) * self.step
        if milestone > self.last_milestone:
            self.last_milestone = milestone
            return f"CS milestone reached — {milestone} minions down!"
        return None


class KillCountTrigger(GameTrigger):
    """Trigger when kills increase."""
    def __init__(self):
        self.last_kills = 0

    def check(self, current_data, previous_data):
        kills = current_data.get("kills", 0)
        if kills > self.last_kills:
            diff = kills - self.last_kills
            self.last_kills = kills
            return f"Player scored {diff} new kill(s)!"
        return None

class DeathTrigger(GameTrigger):
    """Trigger when player dies (death count increases)."""
    def __init__(self):
        self.last_deaths = 0

    def check(self, current_data, previous_data):
        deaths = current_data.get("deaths", 0)
        if deaths > self.last_deaths:
            diff = deaths - self.last_deaths
            self.last_deaths = deaths
            messages = [
                f"Oof... Player just died {diff} time(s).",
                f"Another death on the board. That’s {deaths} now!",
                f"Tough luck! Player went down again.",
                f"The caster's getting worried — another death logged."
            ]
            return random.choice(messages)
        return None
