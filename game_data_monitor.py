# game_data_monitor.py
import asyncio
import os
import requests
import time
import json
from utils.game_utils import estimate_team_gold,  power_score
from triggers.game_triggers import MultikillEventTrigger,FeatsOfStrengthTrigger, StreakTrigger
from shared_state import previous_state, player_ratings
import copy
from overlay_push import push_power_scores


POLL_INTERVAL = 5
LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
triggers = []
callback_from_zorobot = None
feats_trigger = FeatsOfStrengthTrigger()
streak_trigger = StreakTrigger()

def set_triggers(trigger_list):
    global triggers
    triggers = trigger_list + [feats_trigger, streak_trigger]  # they are declared globally above
    print(f"✅ Triggers loaded: {[t.__class__.__name__ for t in triggers]}")

def get_previous_state():
    return copy.deepcopy(previous_state)

def get_team_of_killer(event, all_players):
    killer = event.get("KillerName", "")
    player = next((p for p in all_players if p.get("summonerName") == killer), None)
    return player.get("team") if player else None

def find_enemy_laner(player, all_players):
    role = player.get("position", "")
    team = player.get("team", "")
    for enemy in all_players:
        if enemy.get("team") != team and enemy.get("position", "") == role:
            return enemy
    return None  # fallback if no match found

def generate_game_recap(all_data, you, active_player, last_snapshot=None, dragon_kills=None):
    your_name = you.get("summonerName", "You")
    scores = you.get("scores", {})
    gold = active_player.get("currentGold", 0)
    team = you.get("team", "ORDER")
    all_players = all_data.get("allPlayers", [])
    item_gold = sum(item.get("price", 0) * item.get("count", 1) for item in you.get("items", []))
    your_team = [p for p in all_players if p.get("team") == team]
    enemy_team = [p for p in all_players if p.get("team") != team]
    # Team kills
    your_team_kills = sum(p.get("scores", {}).get("kills", 0) for p in your_team)
    enemy_team_kills = sum(p.get("scores", {}).get("kills", 0) for p in enemy_team)
    # Team gold
    teams_gold = estimate_team_gold(all_players)
    your_team_gold = teams_gold.get(team, 0)
    enemy_team_gold = sum(v for k, v in teams_gold.items() if k != team)
    gold_diff = your_team_gold - enemy_team_gold
    status = "ahead" if gold_diff > 0 else "behind"
    # Recap changes
    recap_lines = []
    if last_snapshot:
        delta_kills = scores.get("kills", 0) - last_snapshot.get("kills", 0)
        delta_deaths = scores.get("deaths", 0) - last_snapshot.get("deaths", 0)
        delta_assists = scores.get("assists", 0) - last_snapshot.get("assists", 0)
        delta_cs = scores.get("creepScore", 0) - last_snapshot.get("cs", 0)
        if delta_kills > 0:
            recap_lines.append(f"⚔️ You scored {delta_kills} kill(s)")
        if delta_deaths > 0:
            recap_lines.append(f"💀 You died {delta_deaths} time(s)")
        if delta_assists > 0:
            recap_lines.append(f"🧩 You assisted {delta_assists} time(s)")
        if delta_cs > 0:
            current_time = time.time()
            prev_time = last_snapshot.get("timestamp", current_time)
            delta_time = current_time - prev_time
            if delta_time >= 30:  # only calculate if > 30 seconds passed
                cs_per_min = delta_cs / (delta_time / 60)
                recap_lines.append(f"🐸 You farmed {delta_cs} CS ({cs_per_min:.1f}/min)")
            else:
                recap_lines.append(f"🐸 You farmed {delta_cs} CS")
        # Optional: detect item changes
        prev_items = {item["displayName"] for item in last_snapshot.get("items", [])}
        curr_items = {item["displayName"] for item in you.get("items", [])}
        new_items = curr_items - prev_items
        if new_items:
            item_list = ", ".join(new_items)
            recap_lines.append(f"🛒 New items: {item_list}")
    # ✅ New: dragon check
        prev_dragons = last_snapshot.get("dragon_kills", {}).get(team, 0)
        curr_dragons = dragon_kills.get(team, 0)
        if curr_dragons > prev_dragons:
            recap_lines.append(f"🔥 Your team secured {curr_dragons - prev_dragons} dragon(s)!")
    else:
        recap_lines.append("📡 First recap of the match.")
    summary = (
        f"{your_name} is now {scores.get('kills', 0)}/{scores.get('deaths', 0)}/"
        f"{scores.get('assists', 0)} with {scores.get('creepScore', 0)} CS and "
        f"{gold:.0f} gold. You've spent {item_gold:,} gold on items. "
        f"Your team has {your_team_kills} kills vs {enemy_team_kills}. "
        f"You're {status} by {abs(gold_diff):,} gold in items."
    )
    return "Since the last update:\n" + "\n".join(recap_lines) + "\n" + summary

async def monitor_game_data(callback):
    print("🕹️ Game Data Monitor started.")
    while True:
        try:
            response = requests.get(LIVE_CLIENT_URL, timeout=5, verify=False)
            if response.status_code != 200:
                await asyncio.sleep(POLL_INTERVAL)
                continue
            data = response.json()
            active_player = data.get("activePlayer", {})
            # 🛑 INSERT THIS BLOCK HERE
            if not active_player or not active_player.get("championStats"):
                if previous_state.get("game_ended"):
                    print("✅ Clean disconnect after GameEnd. Final cleanup.")
                    previous_state.clear()
                    previous_state["game_ended"] = True  # So AskAI still sees "game is over"
                    for trigger in triggers:
                        if hasattr(trigger, "reset"):
                            trigger.reset()
                elif previous_state.get("initialized"):
                    print("⚠️ Unexpected disconnect while game was active. Holding state.")
                await asyncio.sleep(POLL_INTERVAL)
                continue
            riot_id = active_player.get("riotId", None)
            all_players = data.get("allPlayers", [])
            your_player_data = next((p for p in all_players if p.get("riotId") == riot_id), None)
            if not your_player_data:
                await asyncio.sleep(POLL_INTERVAL)
                continue
            if not any(isinstance(t, MultikillEventTrigger) for t in triggers):
                your_name = your_player_data.get("summonerName")
                triggers.append(MultikillEventTrigger(your_name=your_name))
                print(f"🆕 Injected MultikillEventTrigger for {your_name}")
            # Extract data
            scores = your_player_data.get("scores", {})
            kills = scores.get("kills", 0)
            deaths = scores.get("deaths", 0)
            assists = scores.get("assists", 0)
            cs = scores.get("creepScore", 0)
            hp = active_player.get("championStats", {}).get("currentHealth", 0)
            current_gold = active_player.get("currentGold", 0)
            item_gold = sum(item.get("price", 0) * item.get("count", 1) for item in your_player_data.get("items", []))
            your_team = your_player_data.get("team", "ORDER")
            timestamp_now = time.time()
            game_time_seconds = data.get("gameData", {}).get("gameTime", 0)
            events = data.get("events", {}).get("Events", [])
            total_kills = sum(p.get("scores", {}).get("kills", 0) for p in all_players)
            teams_gold = estimate_team_gold(all_players)
            your_team_gold = teams_gold.get(your_team, 0)
            enemy_team_gold = sum(v for k, v in teams_gold.items() if k != your_team)
            gold_diff = your_team_gold - enemy_team_gold
            dragon_kills = {"ORDER": 0, "CHAOS": 0}
            for e in events:
                if e.get("EventName") == "DragonKill":
                    killer = e.get("KillerName", "")
                    killer_player = next((p for p in all_players if p.get("summonerName") == killer), None)
                    if killer_player:
                        team = killer_player.get("team", "UNKNOWN")
                        dragon_kills[team] += 1
            # Inject streaks
            for player in all_players:
                summoner_name = player.get("summonerName")
                player["killStreak"] = streak_trigger.get_player_streak(summoner_name)
            # 🧠 Collect enhanced data for power_score
            game_time_minutes = max(game_time_seconds / 60, 1)
            for player in all_players:
                player_team = player.get("team", "UNKNOWN")
                player_team_data = {
                    "dragons": dragon_kills.get(player_team, 0),
                    "dragon_soul": data.get("events", {}).get("DragonSoulTeam") == player_team,
                    "elder_dragon": any(e["EventName"] == "ElderKill" and get_team_of_killer(e, all_players) == player_team for e in events),
                    "baron_buff": any(e["EventName"] == "BaronKill" and get_team_of_killer(e, all_players) == player_team for e in events),
                    "heralds": sum(1 for e in events if e["EventName"] == "HeraldKill" and get_team_of_killer(e, all_players) == player_team),
                    "atakan_buff": any(e["EventName"] == "AtakhanKill" and get_team_of_killer(e, all_players) == player_team for e in events),
                    "atakan_temp": sum(1 for e in events if e["EventName"] == "AtakhanKill" and get_team_of_killer(e, all_players) == player_team),
                    "void_grubs": feats_trigger.voidgrub_objective_counts.get(player_team, 0),
                    "feats_of_strength": 1 if feats_trigger.get_triggered_team() == player_team else 0,
                    "towers": {
                        "tier1": sum(1 for e in events if e["EventName"] == "TurretKilled" and "T1" in e["TurretKilled"] and get_team_of_killer(e, all_players) == player_team ),
                        "tier2": sum(1 for e in events if e["EventName"] == "TurretKilled" and "T2" in e["TurretKilled"] and get_team_of_killer(e, all_players) == player_team),
                        "tier3": sum(1 for e in events if e["EventName"] == "TurretKilled" and "T3" in e["TurretKilled"] and get_team_of_killer(e, all_players) == player_team),
                    },
                    "inhibitors_down": sum(1 for e in events if e["EventName"] == "InhibKilled" and get_team_of_killer(e, all_players) == player_team)
                }
                lane_opponent = find_enemy_laner(player, all_players)  # You'll define this
                score = power_score(player, enemy_laner=lane_opponent, team_data=player_team_data, game_time_minutes=game_time_minutes, verbose=True)
                player_ratings[player.get("summonerName", "UNKNOWN")] = score
                await push_power_scores(player_ratings)
            # Detect game start or reset
            if game_time_seconds < 10 and previous_state.get("last_game_time", 9999) > 30:
                print("🔁 New game detected. Resetting state.")
                previous_state.clear()
                for trigger in triggers:
                    if hasattr(trigger, "reset"):
                        trigger.reset()
                await asyncio.sleep(POLL_INTERVAL)
                continue
            # First-time init
            if not previous_state.get("initialized"):
                previous_state.update({
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "cs": cs,
                    "last_hp": hp,
                    "gold": current_gold,
                    "item_gold": item_gold,
                    "last_damage_timestamp": timestamp_now,
                    "last_trigger_time": timestamp_now,
                    "last_cs_milestone": (cs // 70) * 70,
                    "total_kills": total_kills,
                    "your_team": your_team,
                    "dragon_kills": dragon_kills,
                    "last_game_time": game_time_seconds,
                    "initialized": True,
                    "game_ended": False,  # ✅ Reset here too
                })
                print("📡 Initialized game_data_loop with current stats.")
                await asyncio.sleep(POLL_INTERVAL)
                continue
            # Build current_data snapshot
            current_data = {
                "hp": hp,
                "cs": cs,
                "kills": kills,
                "deaths": deaths,
                "last_hp": hp,
                "gold": current_gold,
                "item_gold": item_gold,
                "assists": assists,
                "timestamp": timestamp_now,
                "total_kills": total_kills,
                "your_team": your_team,
                "dragon_kills": dragon_kills,
                "last_game_time": game_time_seconds,
                "gold_diff": gold_diff,
                "allPlayers": all_players,
                "events": data.get("events", {})
            }
            # Copy current_data just for debugging purposes
            debug_data = current_data.copy()
            debug_data.pop("allPlayers", None)
            debug_data.pop("events", None)
            print(f"[GameLoop] current_data (clean): {json.dumps(debug_data, indent=2)}")
            # Trigger evaluation
            merged_results = []
            for trigger in triggers:
                print(f"[DEBUG] Checking trigger: {trigger.__class__.__name__}")
                result = trigger.check(current_data, previous_state)
                if result:
                    merged_results.append(result)
            # 🔁 Send results to zorobot
            if not callable(callback):
                print("❌ Invalid callback provided to monitor_game_data.")
                return
            result = callback(data, your_player_data, current_data, merged_results)
            if asyncio.iscoroutine(result):
                await result
            # Update state
            if not previous_state.get("game_ended"):
                previous_state.update(current_data)
                previous_state["last_game_time"] = game_time_seconds
        except Exception as e:
            print(f"[GameMonitor Error]: {e}")
        await asyncio.sleep(POLL_INTERVAL)

def set_callback(func):
    global callback_from_zorobot
    callback_from_zorobot = func

def get_callback():
    return callback_from_zorobot

async def game_data_loop():
    cb = get_callback()
    if cb:
        print(f"[DEBUG] Game loop callback is: {cb}, type: {type(cb)}")
        await monitor_game_data(cb)
    else:
        print("⚠️ No callback set for game_data_loop.")
