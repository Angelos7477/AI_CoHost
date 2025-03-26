# triggers/game_triggers.py

import time
import random

class GameTrigger:
    """Base class for all game triggers."""
    def check(self, current_data: dict, previous_data: dict) -> str | None:
        return None


class HPDropTrigger(GameTrigger):
    """Trigger when HP drops by a certain percentage AND is under a critical HP value."""
    def __init__(self, threshold_percent=35, min_current_hp=70, cooldown=30):
        self.threshold = threshold_percent
        self.min_current_hp = min_current_hp
        self.cooldown = cooldown
        self.last_trigger_time = 0
    def reset(self):
        self.last_trigger_time = 0
    def check(self, current_data, previous_data):
        now = time.time()
        if now - self.last_trigger_time < self.cooldown:
            return None
        prev_hp = previous_data.get("last_hp", 0)
        curr_hp = current_data.get("hp", 0)
        if prev_hp <= 0 or curr_hp <= 0:
            return None
        # ✅ Only trigger if current HP is below min threshold
        if curr_hp > self.min_current_hp:
            return None
        drop = ((prev_hp - curr_hp) / max(prev_hp, 1)) * 100
        if drop >= self.threshold:
            self.last_trigger_time = now
            return f"🩸 Player took a big hit! Lost {int(drop)}% and is now critically low at {curr_hp} HP."
        return None


class CSMilestoneTrigger(GameTrigger):
    """Trigger when a new CS milestone is reached (30, 60, etc)."""
    def __init__(self, step=70):
        self.step = step
        self.last_milestone = 0
    def reset(self):
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
    def reset(self):
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
    def reset(self):
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

class GoldThresholdTrigger:
    def __init__(self, cooldown=180):  # default 3 minutes
        self.cooldown = cooldown
        self.last_triggered = 0  # store timestamp of last trigger
    def reset(self):
        self.last_triggered = 0
    def check(self, current, previous):
        gold = current.get("gold", 0)
        now = current.get("timestamp", time.time())
        if gold >= 2500 and previous.get("gold", 0) < 2500:
            if (now - self.last_triggered) >= self.cooldown:
                self.last_triggered = now
                return "You have over 2.5k gold! Time to consider recalling and spending it."
        return None

class FirstBloodTrigger:
    def __init__(self):
        self.triggered = False
    def reset(self):
        self.triggered = False
    def check(self, current, previous):
        if self.triggered:
            return None
        # First blood = when total kills go from 0 to 1
        total_kills_before = previous.get("total_kills", 0)
        total_kills_now = current.get("total_kills", 0)
        if total_kills_before == 0 and total_kills_now > 0:
            self.triggered = True
            return "🩸 First blood has been drawn! The fight begins!"
        return None

class DragonKillTrigger:
    def __init__(self):
        self.last_dragon_kills = {"ORDER": 0, "CHAOS": 0}
    def reset(self):
        self.last_dragon_kills = {"ORDER": 0, "CHAOS": 0}
    def check(self, current, previous):
        team_dragon_kills = current.get("dragon_kills", {})
        for team, count in team_dragon_kills.items():
            if count > self.last_dragon_kills.get(team, 0):
                self.last_dragon_kills[team] = count
                if team == current.get("your_team"):
                    return "🐉 Your team has slain a dragon!"
                else:
                    return "⚠️ The enemy team has taken a dragon!"
        return None
