# triggers/game_triggers.py

import time
import random
from collections import defaultdict, Counter

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
            messages = [
                f"⚠️ Massive damage incoming! Took a brutal {int(drop)}% hit — only {curr_hp} HP left!",
                f"Oof, you planning to tank with that {curr_hp} HP left? Took a {int(drop)}% smack to the face.",
                f"💀 HP bar just got *Thanos snapped* — down {int(drop)}%! {curr_hp} HP is a lifestyle, not a number."
            ]
            return random.choice(messages)
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
            messages = [
                f"🎯 CS check: {milestone} minions farmed. Clean mechanics!",
                f"💼 Farming like a pro — {milestone} CS and counting.",
                f"🌾 That’s {milestone} minions in the dirt. Gold stacking on point!"
            ]
            return random.choice(messages)
        return None


class KillCountTrigger(GameTrigger):
    """Trigger when kills increase, with milestone memory."""
    def __init__(self):
        self.last_kills = 0
        self.kill_milestones = [5, 10, 15]
        self.triggered_milestones = set()
    def reset(self):
        self.last_kills = 0
        self.triggered_milestones.clear()
    def check(self, current_data, previous_data):
        kills = current_data.get("kills", 0)
        messages = []
        # Basic kill delta
        if kills > self.last_kills:
            diff = kills - self.last_kills
            kill_lines = [
                f"💀 Picked up {diff} kill{'s' if diff > 1 else ''}! Keep the pressure on!",
                f"🧨 Boom! {diff} more on the scoreboard.",
                f"⚔️ Racking up kills — {diff} just now!"
            ]
            messages.append(random.choice(kill_lines))
            self.last_kills = kills
        # Check kill milestones
        for milestone in self.kill_milestones:
            if kills >= milestone and milestone not in self.triggered_milestones:
                self.triggered_milestones.add(milestone)
                if milestone == 5:
                    lines = [
                        "🔥 You're on a hot streak! 5 kills!",
                        "⚡ Dominating! 5 takedowns already!",
                        "💣 Mid-game menace — 5 kills in!"
                    ]
                elif milestone == 10:
                    lines = [
                        "💥 Double digits! 10 kills and climbing!",
                        "🛡️ Unstoppable — 10 enemies down.",
                        "🏹 10 kills? That’s main character energy."
                    ]
                elif milestone == 15:
                    lines = [
                        "👑 Absolute domination — 15 kills and counting!",
                        "🎯 15 confirmed kills. Are you even human?",
                        "🚀 You’re breaking the scoreboard — 15 kills!"
                    ]
                messages.append(random.choice(lines))
        return "\n".join(messages) if messages else None


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
            death_lines = [
                f"💀 Oof... went down again. That’s {deaths} total.",
                f"☠️ RIP! Death #{deaths}. Shake it off!",
                f"⚰️ Another one bites the dust. Count: {deaths}.",
                f"📉 That's {deaths} deaths... let’s turn this around.",
                f"🔻 Things are getting rough. {deaths} deaths now.",
                f"😵‍💫 You're feeding faster than the minions.",
                f"😬 Yikes! {deaths} deaths. Time for a strategy shift?"
            ]
            return random.choice(death_lines)
        return None

class GoldThresholdTrigger:
    def __init__(self, cooldown=300):  # default 5 minutes
        self.cooldown = cooldown
        self.last_triggered = 0  # store timestamp of last trigger
    def reset(self):
        self.last_triggered = 0
    def check(self, current, previous):
        gold = current.get("gold", 0)
        now = current.get("timestamp", time.time())
        if gold >= 3500 and previous.get("gold", 0) < 3500:
            if (now - self.last_triggered) >= self.cooldown:
                self.last_triggered = now
                messages = [
                    "💰 You're sitting on a mountain of gold! Time to shop before they catch you out.",
                    "🛍️ 3.5k+ gold? Go treat yourself to some serious power-ups!",
                    "🪙 You're rich! Recall and spend that gold before it's too late.",
                    "⚠️ Holding onto 3.5k gold is risky — spend it before you donate it in a teamfight.",
                    "📦 That's enough gold for a big item spike. Don't forget to cash in!"
                ]
                return random.choice(messages)
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
        self.last_event_time = 0
        self.last_dragon_kills = {"ORDER": 0, "CHAOS": 0}
    def reset(self):
        self.last_event_time = 0
        self.last_dragon_kills = {"ORDER": 0, "CHAOS": 0}
    def check(self, current, previous):
        events = current.get("events", {}).get("Events", [])
        your_team = current.get("your_team", "ORDER")
        all_players = current.get("allPlayers", [])
        for event in reversed(events):
            if event.get("EventName") != "DragonKill":
                continue
            event_time = event.get("EventTime", 0)
            if event_time <= self.last_event_time:
                continue
            self.last_event_time = event_time
            dragon_type = event.get("DragonType", "Unknown")
            is_stolen = event.get("Stolen", "False") == "True"
            killer_name = event.get("KillerName", "")
            killer_player = next((p for p in all_players if p.get("summonerName") == killer_name), None)
            if not killer_player:
                continue
            team = killer_player.get("team", "UNKNOWN")
            self.last_dragon_kills[team] = self.last_dragon_kills.get(team, 0) + 1
            dragon_count = self.last_dragon_kills[team]
            # 🎯 Elder dragon (high priority)
            if dragon_type == "Elder":
                if team == your_team:
                    return "🌟 Elder Dragon secured! Your team just got a major buff!"
                else:
                    return "💀 The enemy team got Elder Dragon! This could swing the game!"
            # 🎯 Dragon steal
            if is_stolen:
                if team == your_team:
                    return f"😎 You stole the {dragon_type} dragon right under their noses!"
                else:
                    return f"⚠️ The enemy team **stole** the {dragon_type} dragon!"
            # 🎯 Dragon Soul logic
            if dragon_count == 4:
                if team == your_team:
                    return f"🔥 Your team has taken their 4th dragon — Dragon Soul unlocked!"
                else:
                    return f"🚨 Enemy team now has the Dragon Soul. Be very careful!"
            # 🎯 Dragon point logic (3rd dragon)
            if dragon_count == 3:
                if team == your_team:
                    return f"⏳ That’s your 3rd dragon — one more to soul!"
                else:
                    return f"⚠️ Enemy team just got their 3rd dragon — one more for soul!"
            # 🎯 Default messaging
            if team == your_team:
                return f"🐉 Your team took the {dragon_type} dragon!"
            else:
                return f"⚠️ Enemy team took the {dragon_type} dragon!"
        return None


class MultikillEventTrigger(GameTrigger):
    def __init__(self, your_name: str, your_team: str = None):
        self.your_name = your_name
        self.your_team = your_team
        self.last_seen_event_ids = set()  # ✅ Track handled EventIDs
    def reset(self):
        self.last_seen_event_ids.clear()
    def check(self, current_data, previous_data):
        events = current_data.get("events", {}).get("Events", [])
        all_players = current_data.get("allPlayers", [])
        your_team = self.your_team or current_data.get("your_team", "ORDER")
        for event in reversed(events):
            if event.get("EventName") != "Multikill":
                continue
            event_id = event.get("EventID")
            if not event_id or event_id in self.last_seen_event_ids:
                continue  # ✅ Already seen or missing ID
            self.last_seen_event_ids.add(event_id)  # ✅ Mark as seen
            # ✅ Memory cleanup: trim if too large
            if len(self.last_seen_event_ids) > 100:
                self.last_seen_event_ids = set(list(self.last_seen_event_ids)[-50:])
            killer = event.get("KillerName")
            streak = event.get("KillStreak", 2)
            if not killer:
                continue
            killer_player = next((p for p in all_players if p.get("summonerName") == killer), None)
            if not killer_player:
                continue
            team = killer_player.get("team", "UNKNOWN")
            if killer == self.your_name:
                return self._message_for_streak(streak, "self")
            elif team == your_team:
                return self._message_for_streak(streak, "ally", killer)
            else:
                return self._message_for_streak(streak, "enemy", killer)
        return None
    def _message_for_streak(self, streak, role, name=None):
        you = "You" if role == "self" else name
        base = {
            2: "Double Kill!",
            3: "Triple Kill!",
            4: "QUADRA KILL!",
            5: "PENTAKILL!!"
        }.get(streak, "Multikill!")
        if role == "self":
            return f"⚔️ {base} Well played!"
        elif role == "ally":
            return f"🎉 {you} got a {base} for our team!"
        elif role == "enemy":
            return f"🚨 WARNING: {you} just secured a {base}!"

class GameEndTrigger(GameTrigger):
    """Trigger at end of game with win/loss recap."""
    def __init__(self):
        self.triggered = False
        self.result = None
    def reset(self):
        self.triggered = False
        self.result = None
    def check(self, current_data, previous_data):
        if self.triggered:
            return None
        events = current_data.get("events", {}).get("Events", [])
        for event in reversed(events):
            if event.get("EventName") == "GameEnd":
                self.triggered = True
                self.result = event.get("Result", "Unknown").upper()
                print("[GameEndTrigger] GameEnd event detected")
                return f"🎬 Game over! Result: {self.result}"
        return None

class GoldDifferenceTrigger(GameTrigger):
    def __init__(self, threshold=4000, even_margin=1000, cooldown=600):  # 10 min cooldown
        self.threshold = threshold
        self.cooldown = cooldown
        self.even_margin = even_margin  # 🔸 Gold difference under this is treated as "even"
        self.last_trigger_diff = 0
        self.last_trigger_time = 0
        self.trigger_count = 0  # ✅ Count how many times we've triggered
        self.has_triggered_once = False  # ✅ NEW
    def reset(self):
        self.last_trigger_diff = 0
        self.last_trigger_time = 0
        self.trigger_count = 0  # ✅ Reset the counter too
        self.has_triggered_once = False
    def check(self, current, previous):
        now = time.time()
        gold_diff = current.get("gold_diff", 0)
        delta = abs(gold_diff - self.last_trigger_diff)
        # 🎯 Major change in gold difference
        if delta >= self.threshold:
            self.last_trigger_diff = gold_diff
            self.last_trigger_time = now
            self.trigger_count += 1 # ✅ Track trigger
            self.has_triggered_once = True  # ✅ Mark it
            if gold_diff > self.even_margin:
                return f"💰 Your team is ahead by {abs(gold_diff):,} gold!"
            elif gold_diff < -self.even_margin:
                return f"😬 They’re ahead by {abs(gold_diff):,} gold. Be careful!"
            else:
                return "💥 The gold is dead even again! What a rollercoaster!"
        # 🕐 Passive nudge after cooldown
        if self.has_triggered_once and (now - self.last_trigger_time >= self.cooldown):
            self.last_trigger_time = now  # ✅ reset timer
            self.trigger_count += 1  # ✅ Passive nudges count too
            if gold_diff > self.even_margin:
                return "🕐 You’ve been ahead for a while. What’s stopping you from ending it?"
            elif gold_diff < -self.even_margin:
                return "🕐 Still trailing... can your team find a way back in?"
            else:
                return "😐 It’s still even after all this time. Who’s going to make a move?"
        return None


class AceTrigger(GameTrigger):
    def __init__(self):
        self.last_ace_time = 0
    def reset(self):
        self.last_ace_time = 0
    def check(self, current, previous):
        events = current.get("events", {}).get("Events", [])
        your_team = current.get("your_team", "ORDER")
        for event in reversed(events):
            if event.get("EventName") != "Ace":
                continue
            event_time = event.get("EventTime", 0)
            if event_time <= self.last_ace_time:
                continue
            self.last_ace_time = event_time
            acing_team = event.get("AcingTeam", "UNKNOWN")
            if acing_team == your_team:
                return "🔥 ACE! Your team just wiped them out!"
            else:
                return "💀 Your team just got **aced**! Be careful!"
        return None

class BaronTrigger(GameTrigger):
    def __init__(self):
        self.last_event_time = 0
    def reset(self):
        self.last_event_time = 0
    def check(self, current, previous):
        events = current.get("events", {}).get("Events", [])
        your_team = current.get("your_team", "ORDER")
        all_players = current.get("allPlayers", []) 
        for event in reversed(events):
            if event.get("EventName") != "BaronKill":
                continue
            event_time = event.get("EventTime", 0)
            if event_time <= self.last_event_time:
                continue
            self.last_event_time = event_time
            killer_name = event.get("KillerName", "")
            is_stolen = event.get("Stolen", "False") == "True"
            killer_player = next((p for p in all_players if p.get("summonerName") == killer_name), None)
            if not killer_player:
                continue
            team = killer_player.get("team", "UNKNOWN")
            if is_stolen:
                if team == your_team:
                    return "🛑 Incredible! Your team **stole** Baron Nashor!"
                else:
                    return "😵 They just stole Baron Nashor from under your nose!"
            if team == your_team:
                return "💥 Your team secured Baron Nashor!"
            else:
                return "⚠️ The enemy team got Baron Nashor — expect a big push!"
        return None

class AtakhanKillTrigger(GameTrigger):
    def __init__(self):
        self.last_event_time = 0
    def reset(self):
        self.last_event_time = 0
    def check(self, current, previous):
        events = current.get("events", {}).get("Events", [])
        your_team = current.get("your_team", "ORDER")
        all_players = current.get("allPlayers", [])
        for event in reversed(events):
            if event.get("EventName") != "AtakhanKill":
                continue
            event_time = event.get("EventTime", 0)
            if event_time <= self.last_event_time:
                continue
            self.last_event_time = event_time
            killer_name = event.get("KillerName", "")
            killer_player = next((p for p in all_players if p.get("summonerName") == killer_name), None)
            if not killer_player:
                continue
            team = killer_player.get("team", "UNKNOWN")
            if team == your_team:
                return "🌌 Your team has slain **Atakhan**, the Void King! Huge power spike!"
            else:
                return "💥 The enemy has taken **Atakhan**! Watch out!"
        return None

class HeraldKillTrigger(GameTrigger):
    def __init__(self):
        self.last_event_time = 0
    def reset(self):
        self.last_event_time = 0
    def check(self, current, previous):
        events = current.get("events", {}).get("Events", [])
        your_team = current.get("your_team", "ORDER")
        all_players = current.get("allPlayers", [])
        for event in reversed(events):
            if event.get("EventName") != "HeraldKill":
                continue
            event_time = event.get("EventTime", 0)
            if event_time <= self.last_event_time:
                continue
            self.last_event_time = event_time
            killer_name = event.get("KillerName", "")
            killer_player = next((p for p in all_players if p.get("summonerName") == killer_name), None)
            if not killer_player:
                continue
            team = killer_player.get("team", "UNKNOWN")
            if team == your_team:
                return "💪 Your team secured the Rift Herald!"
            else:
                return "🛑 The enemy took the Rift Herald!"
        return None

class FeatsOfStrengthTrigger(GameTrigger):
    def __init__(self):
        self.triggered = False
        self.triggered_team = None
        self.voidgrub_sets_checked = 0
        self.voidgrub_objective_counts = defaultdict(int)
        self.horde_kill_buffer = []
        self.team_objectives = defaultdict(Counter)
        self.locked_slots = {  # ✅ NEW: lock slots once achieved by a team
            "kills": None,
            "first_brick": None,
            "objectives": None
        }
    def reset(self):
        self.triggered = False
        self.triggered_team = None
        self.voidgrub_sets_checked = 0
        self.voidgrub_objective_counts.clear()
        self.horde_kill_buffer.clear()
        self.team_objectives.clear()
        self.locked_slots = {
            "kills": None,
            "first_brick": None,
            "objectives": None
        }
    def check(self, current, previous):
        if self.triggered:
            return None
        events = current.get("events", {}).get("Events", [])
        all_players = current.get("allPlayers", [])
        your_team = current.get("your_team", "ORDER")
        # ✅ Load persistent DragonKill count
        for team_name, count in current.get("dragon_kills", {}).items():
            if count > 0:
                self.team_objectives[team_name]["DragonKill"] = count
        team_progress = {}
        for event in events:
            killer_name = event.get("KillerName", "")
            killer_player = next((p for p in all_players if p.get("summonerName") == killer_name), None)
            team = killer_player.get("team", "UNKNOWN") if killer_player else None
            # Special case: Minion first brick
            if event["EventName"] == "FirstBrick" and not killer_player:
                if killer_name.startswith("Minion_T100"):
                    team = "ORDER"
                elif killer_name.startswith("Minion_T200"):
                    team = "CHAOS"
            if not team:
                continue
            if team not in team_progress:
                team_progress[team] = {
                    "kills": 0,
                    "first_brick": False,
                    "objectives": Counter(self.team_objectives[team])
                }
            # === Track team progress ===
            if event["EventName"] == "ChampionKill":
                team_progress[team]["kills"] += 1
            elif event["EventName"] == "FirstBrick":
                team_progress[team]["first_brick"] = True
            elif event["EventName"] in ["HeraldKill", "BaronKill", "AtakhanKill"]:
                team_progress[team]["objectives"][event["EventName"]] += 1
                self.team_objectives[team][event["EventName"]] += 1
            elif event["EventName"] == "HordeKill":
                self._add_horde_kill(event, team)
        # === Evaluate completed Voidgrub sets ===
        new_sets = len(self.horde_kill_buffer) // 3
        while self.voidgrub_sets_checked < new_sets:
            start = self.voidgrub_sets_checked * 3
            set_kills = self.horde_kill_buffer[start:start+3]
            teams = {entry["team"] for entry in set_kills}
            if len(teams) == 1:
                team = next(iter(teams))
                if self.voidgrub_objective_counts[team] < 2:
                    self.voidgrub_objective_counts[team] += 1
                    self.team_objectives[team]["Voidgrub"] += 1
            self.voidgrub_sets_checked += 1
        # ✅ Ensure progress is present for both teams
        for team in ["ORDER", "CHAOS"]:
            if team not in team_progress:
                team_progress[team] = {
                    "kills": 0,
                    "first_brick": False,
                    "objectives": Counter(self.team_objectives[team])
                }
        print("[Voidgrub Debug] Completed sets:", dict(self.voidgrub_objective_counts))
        print("[Feats Debug] ORDER progress:", team_progress.get("ORDER", {}))
        print("[Feats Debug] CHAOS progress:", team_progress.get("CHAOS", {}))
        # === Evaluate trigger ===
        for team, progress in team_progress.items():
            total_objectives = sum(progress["objectives"].values())
            conditions_met = 0
            # 🔒 Lock per slot when achieved
            if self.locked_slots["kills"] in (None, team) and progress["kills"] >= 3:
                self.locked_slots["kills"] = team
                conditions_met += 1
            if self.locked_slots["first_brick"] in (None, team) and progress["first_brick"]:
                self.locked_slots["first_brick"] = team
                conditions_met += 1
            if self.locked_slots["objectives"] in (None, team) and total_objectives >= 3:
                self.locked_slots["objectives"] = team
                conditions_met += 1
            if conditions_met >= 2:
                self.triggered = True
                self.triggered_team = team
                if team == your_team:
                    return "🏆 Feats of Strength achieved! Your team is claiming serious map control!"
                else:
                    return "⚠️ Enemy team just pulled off a Feats of Strength — they’re taking control!"
        return None
    def _add_horde_kill(self, event, team):
        if any(e["EventID"] == event["EventID"] for e in self.horde_kill_buffer):
            return
        self.horde_kill_buffer.append({
            "event_time": event.get("EventTime", 0),
            "team": team,
            "EventID": event.get("EventID")
        })
