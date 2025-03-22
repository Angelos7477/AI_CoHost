import asyncio
import json
import time
import requests

# 💡 Adjustable polling interval (every 3s)
POLL_INTERVAL = 3
LIVE_CLIENT_URL = "http://127.0.0.1:2999/liveclientdata/allgamedata"

# Basic state snapshot for change detection
previous_state = {
    "kills": 0,
    "deaths": 0,
    "assists": 0,
    "cs": 0,
    "last_hp": 1000,
    "last_damage_timestamp": 0,
    "last_trigger_time": 0
}

async def game_data_loop():
    from zorobot import safe_add_to_tts_queue, get_current_mode, get_ai_response  # <- Reuse core logic

    print("🕹️ Game Data Monitor started.")
    while True:
        try:
            response = requests.get(LIVE_CLIENT_URL, timeout=2)
            if response.status_code != 200:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            data = response.json()
            player = data.get("activePlayer", {})
            scores = player.get("scores", {})
            hp = player.get("championStats", {}).get("currentHealth", 0)
            timestamp_now = time.time()

            kills = scores.get("kills", 0)
            deaths = scores.get("deaths", 0)
            assists = scores.get("assists", 0)
            cs = scores.get("creepScore", 0)

            # Check for new kill
            if kills > previous_state["kills"]:
                diff = kills - previous_state["kills"]
                mode = get_current_mode()
                prompt = f"React as a hype LoL caster to {diff} new kill(s)."
                ai_text = get_ai_response(prompt, mode)
                await safe_add_to_tts_queue(ai_text)

            # Clutch escape detection (big HP drop but survived)
            damage_taken = previous_state["last_hp"] - hp
            if damage_taken > 300 and hp > 100:
                if timestamp_now - previous_state["last_damage_timestamp"] > 20:
                    previous_state["last_damage_timestamp"] = timestamp_now
                    mode = get_current_mode()
                    prompt = "Player just barely escaped a fight with low HP. React like a caster to this clutch escape!"
                    ai_text = get_ai_response(prompt, mode)
                    await safe_add_to_tts_queue(ai_text)

            # CS Milestone
            if cs >= previous_state["cs"] + 30:
                mode = get_current_mode()
                prompt = f"Player just crossed {cs} CS. React as a caster about their farming power."
                ai_text = get_ai_response(prompt, mode)
                await safe_add_to_tts_queue(ai_text)

            # Update previous state
            previous_state.update({
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "cs": cs,
                "last_hp": hp
            })

        except Exception as e:
            print(f"[GameMonitor Error]: {e}")

        await asyncio.sleep(POLL_INTERVAL)

# Add this to zorobot.py like:
# loop.create_task(game_data_monitor.game_data_loop())
