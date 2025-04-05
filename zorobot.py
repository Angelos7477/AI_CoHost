import os
import asyncio
from dotenv import load_dotenv
from twitchAPI.twitch import Twitch
from twitchAPI.eventsub.websocket import EventSubWebsocket
from twitchAPI.oauth import AuthScope
from twitchAPI.object.eventsub import ChannelRaidEvent
from collections import defaultdict, Counter
from twitchio.ext import commands
import pyttsx3
from datetime import datetime, timedelta, timezone
from openai import OpenAI
import concurrent.futures
from shutdown_hooks import setup_shutdown_hooks
from obs_controller import OBSController, log_obs_event
from overlay_ws_server import start_server as start_overlay_ws_server
from overlay_push import (push_askai_overlay,push_event_overlay,push_commentary_overlay,push_hide_overlay,
                push_askai_cooldown_notice,push_cost_overlay,push_cost_increment)
import requests
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from triggers.game_triggers import (HPDropTrigger, CSMilestoneTrigger, KillCountTrigger, DeathTrigger, GoldThresholdTrigger, FirstBloodTrigger,
             DragonKillTrigger, MultikillEventTrigger, GameEndTrigger, GoldDifferenceTrigger, AceTrigger, BaronTrigger, AtakhanKillTrigger, HeraldKillTrigger,
             FeatsOfStrengthTrigger)
from elevenlabs.client import ElevenLabs
from elevenlabs import play, VoiceSettings
import json
import random


# === Load Environment Variables ===
load_dotenv()
TOKEN = os.getenv("TWITCH_TOKEN")
NICK = os.getenv("TWITCH_NICK")
CHANNEL = os.getenv("TWITCH_CHANNEL")
print(f"Loaded channel from .env: {CHANNEL}")
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
USER_TOKEN = os.getenv("TWITCH_USER_TOKEN")
USER_REFRESH_TOKEN = os.getenv("TWITCH_REFRESH_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
eleven = ElevenLabs(api_key=os.getenv("ELEVEN_API_KEY"))
# === OpenAI Setup ===
client = OpenAI(api_key=OPENAI_API_KEY)
RIOT_API_KEY = os.getenv("RIOT_API_KEY") 
USE_ELEVENLABS = os.getenv("USE_ELEVENLABS", "true").lower() == "true"

# === Global Configs ===
VALID_MODES = ["hype", "coach", "sarcastic", "wholesome","troll","smartass","tsundere","edgelord","shakespeare","genz"]
# 🧠 Choose model and voice ID
ELEVEN_MODEL = "eleven_turbo_v2_5"
ELEVEN_VOICE_ID = "TxGEqnHWrfWFTfGW9XjX"  # ← keep only as default/fallback
# 🔊 Personality to Voice ID mapping
VOICE_BY_MODE = {
    "hype": "TxGEqnHWrfWFTfGW9XjX",       # Josh
    "smartass": "TxGEqnHWrfWFTfGW9XjX",   # Josh
    "shakespeare": "TxGEqnHWrfWFTfGW9XjX",# Josh
    "coach": "21m00Tcm4TlvDq8ikWAM",      # Rachel
    "wholesome": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "tsundere": "21m00Tcm4TlvDq8ikWAM",   # Rachel
    "genz": "21m00Tcm4TlvDq8ikWAM",       # Rachel
    "sarcastic": "2EiwWnXFnvU5JabPnv8n",  # Clyde
    "troll": "2EiwWnXFnvU5JabPnv8n",      # Clyde
    "edgelord": "2EiwWnXFnvU5JabPnv8n",   # Clyde
}
# Replace this with the actual ID Josh #TxGEqnHWrfWFTfGW9XjX | Clyde #2EiwWnXFnvU5JabPnv8n | Rachel #21m00Tcm4TlvDq8ikWAM
vote_counts = defaultdict(int)
voted_users = set()  # Track users who already voted this round
tts_lock = asyncio.Lock()
tts_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
tts_queue = asyncio.Queue()
ASKAI_COOLDOWN_SECONDS = 40
ASKAI_QUEUE_LIMIT = 10
ASKAI_QUEUE_DELAY = 10
VOTING_DURATION = 600
last_moodroll_time = 0  # Global cooldown timer
MOODROLL_COOLDOWN = 60  # seconds
MOOD_AUTO_SWITCH_INTERVAL = 120  # seconds (2 minutes)
askai_cooldowns = {}
askai_queue = asyncio.Queue()
current_mode_cache = "hype"  # default
commentator_paused = False  # New flag
eventsub_paused = False
# Global reference to bot instance (initialized later)
bot_instance = None
os.makedirs("logs", exist_ok=True)
MAX_TTS_QUEUE_SIZE = 10  # Prevents spam/flood
ASKAI_TTS_RESERVED_LIMIT = 7  # Maximum messages askai is allowed to use in TTS queue
EVENTSUB_RESERVED_SLOTS = MAX_TTS_QUEUE_SIZE - ASKAI_TTS_RESERVED_LIMIT
overlay_ws_task = None
# 💡 Adjustable polling interval (every 8s)
POLL_INTERVAL = 5
LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
# Basic state snapshot for change detection
previous_state = {}
triggers = [
    HPDropTrigger(threshold_percent=35, min_current_hp=70, cooldown=30),
    #CSMilestoneTrigger(step=70),
    KillCountTrigger(),
    DeathTrigger(),
    GoldThresholdTrigger(cooldown=300),  # ⏱️ 4-minute cooldown
    FirstBloodTrigger(),       # 🩸
    DragonKillTrigger(),        # 🐉
    GameEndTrigger(),
    AceTrigger(),
    AtakhanKillTrigger(),
    HeraldKillTrigger(),
    FeatsOfStrengthTrigger(),
    GoldDifferenceTrigger(threshold=4000, even_margin=1000, cooldown=600),
    BaronTrigger(),
    #MultikillEventTrigger(player_name="Zoro2000"),
]
# 🔥 TTS cooldown config
GAME_TTS_COOLDOWN = 4  # seconds
last_game_tts_time = 0  # global timestamp tracker
AUTO_RECAP_INTERVAL = 600  # every 10 minutes

ITEM_CACHE_FILE = "cached_item_prices.json"
ITEM_PRICES = None  # declare globally

# === Utility Functions ===
def debug_imports():
    print("\n=== DEBUG: Import Origins ===")
    try:
        print("TwitchAPI.Twitch:", Twitch.__module__)
    except Exception as e:
        print("❌ Error checking Twitch:", e)
    try:
        print("TwitchAPI.EventSubWebsocket:", EventSubWebsocket.__module__)
    except Exception as e:
        print("❌ Error checking EventSubWebsocket:", e)
    try:
        print("TwitchAPI.AuthScope:", AuthScope.__module__)
    except Exception as e:
        print("❌ Error checking AuthScope:", e)
    try:
        print("TwitchIO.commands.Bot:", commands.Bot.__module__)
    except Exception as e:
        print("❌ Error checking commands.Bot:", e)
    try:
        print("OpenAI.Client:", OpenAI.__module__)
    except Exception as e:
        print("❌ Error checking OpenAI client:", e)
    print("=== End of Import Debug ===\n")

def load_item_prices():
    url = "https://ddragon.leagueoflegends.com/cdn/15.7.1/data/en_US/item.json"
    response = requests.get(url)
    data = response.json()
    prices = {int(k): v["gold"]["total"] for k, v in data["data"].items()}
    # ✅ Save to disk cache
    with open(ITEM_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(prices, f)
    return prices

def load_item_prices_from_cache():
    try:
        if os.path.exists(ITEM_CACHE_FILE):
            with open(ITEM_CACHE_FILE, "r", encoding="utf-8") as f:
                return {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print("[ItemCache] Failed to load item cache:", e)
    return None

def ensure_item_prices_loaded():
    global ITEM_PRICES
    if ITEM_PRICES is None:
        ITEM_PRICES = load_item_prices_from_cache() or load_item_prices()
    return ITEM_PRICES

def get_current_mode():
    global current_mode_cache
    return current_mode_cache

def load_initial_mode():
    global current_mode_cache
    try:
        with open("current_mode.txt", "r") as f:
            mode = f.read().strip().lower()
            if mode in VALID_MODES:
                current_mode_cache = mode
            else:
                current_mode_cache = "hype"
    except FileNotFoundError:
        current_mode_cache = "hype"

def load_system_prompt(mode):
    try:
        with open(f"prompts/{mode}.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are a witty League of Legends commentator."
    
def get_ai_response(prompt, mode):
    system_prompt = load_system_prompt(mode)
    response = client.chat.completions.create(
        model="gpt-4o",  #gpt-4o , gpt-3.5-turbo
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=150,
        temperature=0.7,
        frequency_penalty=0.3,
        presence_penalty=0.3
    )
    # Log token usage & estimate cost
    usage = response.usage
    total_tokens = usage.total_tokens
    prompt_tokens = usage.prompt_tokens
    completion_tokens = usage.completion_tokens
    model = response.model
    # 💰 Cost estimation
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    log_event(f"[OpenAI] Model={model}, Prompt={prompt_tokens}, Completion={completion_tokens}, "
              f"Total={total_tokens}, Cost=${cost:.5f}")
    # ✅ Schedule overlay update (cost only)
    try:
        asyncio.create_task(push_cost_increment(cost))  # We’ll define this
    except Exception as e:
        log_error(f"[Overlay Cost Push ERROR] {e}")
    return response.choices[0].message.content

def estimate_cost(model, prompt_tokens, completion_tokens):
    if model.startswith("gpt-3.5-turbo"):
        return (prompt_tokens + completion_tokens) / 1000 * 0.001
    elif model.startswith("gpt-4o"):
        return (prompt_tokens + completion_tokens) / 1000 * 0.005
    elif model.startswith("gpt-4"):
        return (prompt_tokens / 1000 * 0.03) + (completion_tokens / 1000 * 0.06)
    return 0.0

def get_event_reaction(event_type, user):
    base_prompt = {
        "sub": f"{user} just subscribed! React with high-energy shoutcaster hype.",
        "resub": f"{user} resubbed! Hype it up like a dramatic League of Legends caster.",
        "raid": f"A raid is happening! {user} brought their viewers! React with explosive hype.",
        "cheer": f"{user} just sent bits! React like a caster pumped on adrenaline.",
        "gift": f"{user} gifted a sub! React like it’s a game-winning teamfight.",
        "giftmass": f"{user} just launched a gift sub train! React like the Nexus is exploding!",
    }.get(event_type, f"{user} triggered an unknown event. React accordingly.")
    return get_ai_response(base_prompt, get_current_mode())

def speak_sync(text, voice_id=ELEVEN_VOICE_ID):
    if USE_ELEVENLABS:
        try:
            audio = eleven.generate(
                text=text,
                voice=voice_id,
                model=ELEVEN_MODEL,
                voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.8)
            )
            play(audio)
            return
        except Exception as e:
            log_error(f"[TTS FALLBACK] ElevenLabs failed, falling back to pyttsx3. Reason: {e}")
    # Either flag is false OR ElevenLabs failed
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)
    engine.say(text)
    engine.runAndWait()

async def speak_text(text):
    loop = asyncio.get_running_loop()
    mode = get_current_mode()
    voice_id = VOICE_BY_MODE.get(mode, ELEVEN_VOICE_ID)
    await loop.run_in_executor(tts_executor, speak_sync, text, voice_id)

async def tts_worker():
    while True:
        item = await tts_queue.get()
        try:
            if isinstance(item, tuple) and item[0] in ("askai", "event", "game"):
                item_type = item[0]
                if item_type == "askai":
                    _, user, question, answer = item
                    chat_message = f"{user}, ZoroTheCaster says: {answer}"
                    if bot_instance:
                        async def delayed_chat():
                            await asyncio.sleep(0.5)
                            await bot_instance.send_to_chat(chat_message)
                        asyncio.create_task(delayed_chat())
                    # ✅ Delegate everything to the unified overlay method
                    if hasattr(bot_instance, "obs_controller"):
                        try:
                            bot_instance.obs_controller.update_ai_overlay(question, answer)
                            bot_instance.loop.create_task(bot_instance.auto_hide_askai_overlay())
                        except Exception as e:
                            log_error(f"[OBS AskAI Update Error] {e}")
                    # ✅ Push to Overlay WebSocket!
                    try:
                        await asyncio.sleep(1)
                        await push_askai_overlay(question, answer)
                    except Exception as e:
                        log_error(f"[Overlay Push AskAI ERROR] {e}"),
                    await speak_text(answer)
                    # NEW: Send hide event to WebSocket
                    try:
                        await push_hide_overlay("askai")
                    except Exception as e:
                        log_error(f"[Overlay AskAI Hide ERROR] {e}")
                elif item_type == "event":
                    _, user, text = item
                    chat_message = f"{user}, ZoroTheCaster says: {text}"
                    if bot_instance:
                        async def delayed_chat():
                            await asyncio.sleep(0.5)
                            await bot_instance.send_to_chat(chat_message)
                        asyncio.create_task(delayed_chat())
                    if hasattr(bot_instance, "obs_controller"):
                        try:
                            bot_instance.obs_controller.update_event_overlay(text)
                            bot_instance.loop.create_task(bot_instance.auto_hide_event_overlay())
                        except Exception as e:
                            log_error(f"[OBS Event Overlay Update Error] {e}")
                    # ✅ Push to Overlay WebSocket!
                    try:
                        await asyncio.sleep(1)
                        await push_event_overlay(text)
                    except Exception as e:
                        log_error(f"[Overlay Push Event ERROR] {e}")
                    await speak_text(text)
                    try:
                        await push_hide_overlay("event")
                    except Exception as e:
                        log_error(f"[Overlay Event Hide ERROR] {e}")
                elif item_type == "game":
                    _, user, text = item
                    chat_message = f"{user}, ZoroTheCaster says: {text}"
                    if bot_instance:
                        async def delayed_chat():
                            await asyncio.sleep(0.5)
                            await bot_instance.send_to_chat(chat_message)
                        asyncio.create_task(delayed_chat())
                    try:
                        await asyncio.sleep(1)
                        await push_commentary_overlay(text)
                    except Exception as e:
                        log_error(f"[Overlay Push Game ERROR] {e}")
                    await speak_text(text)
                    try:
                        await push_hide_overlay("commentary")
                    except Exception as e:
                        log_error(f"[Overlay Commentary Hide ERROR] {e}")
            else:
                # Plain system message
                await speak_text(item)
        except Exception as e:
            log_error(f"TTS ERROR: {e}")
        tts_queue.task_done()
        await asyncio.sleep(1.5)  # ⏱️ Small delay to avoid spammy speech


async def safe_add_to_tts_queue(item):
    queue_size = tts_queue.qsize()
    is_askai = isinstance(item, tuple) and item[0] == "askai"
    if is_askai and queue_size >= ASKAI_TTS_RESERVED_LIMIT:
        log_error(f"[ASKAI TTS SKIPPED] AskAI message dropped due to reserved space for EventSub.")
        return
    if not is_askai and queue_size >= MAX_TTS_QUEUE_SIZE:
        log_error(f"[EVENTSUB TTS SKIPPED] Queue full. EventSub message skipped: {item}")
        return
    await tts_queue.put(item)

def log_error(error_text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open("logs/errors.log", "a", encoding="utf-8") as error_file:
        error_file.write(f"[{timestamp}] {error_text}\n")
def log_event(text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open("logs/openai_usage.log", "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {text}\n")
def log_merged_prompt(text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open("logs/merged_prompts.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text.strip()}\n")

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

def estimate_team_gold(players):
    ensure_item_prices_loaded()
    team_gold = {}
    for player in players:
        team = player.get("team", "UNKNOWN")
        items = player.get("items", [])
        total = 0
        for item in items:
            item_id = item.get("itemID")
            real_price = ITEM_PRICES.get(item_id, 0)
            total += real_price * item.get("count", 1)
        team_gold[team] = team_gold.get(team, 0) + total
    return team_gold

def is_game_related(question: str):
    q = question.lower()
    return any(word in q for word in ["winnable", "win", "lose", "score", "comeback", "game", "match", "gold", "kills", "cs", "status"])

async def game_data_loop():
    global last_game_tts_time  # 🔥 Add this line!
    print("🕹️ Game Data Monitor started.")
    #initialized = False
    while True:
        try:
            response = requests.get(LIVE_CLIENT_URL, timeout=5, verify=False)
            if response.status_code != 200:
                await asyncio.sleep(POLL_INTERVAL)
                continue
            data = response.json()
            # 🟦 Get your Riot ID from activePlayer
            active_player = data.get("activePlayer", {})
            # ❌ Game ended? Clear previous_state
            if not active_player or not active_player.get("championStats"):
                if previous_state.get("initialized"):
                    print("🏁 Game ended. Clearing state.")
                    previous_state.clear()
                for trigger in triggers:
                    if hasattr(trigger, "reset"):
                        trigger.reset()
                await asyncio.sleep(POLL_INTERVAL)
                continue
            riot_id = active_player.get("riotId", None)
            events = data.get("events", {}).get("Events", [])
            dragon_kill_events = [e for e in events if e.get("EventName") == "DragonKill"]
            # 🟦 Get your HP from activePlayer (HP is only here!)
            hp = active_player.get("championStats", {}).get("currentHealth", 0)
            current_gold = active_player.get("currentGold", 0)
            # 🟦 Match your full player data in allPlayers[] by riotId
            all_players = data.get("allPlayers", [])
            your_player_data = next((p for p in all_players if p.get("riotId") == riot_id), None)
            if not your_player_data:
                print("[GameLoop] ⚠️ Could not find matching player in allPlayers.")
                await asyncio.sleep(POLL_INTERVAL)
                continue
            # ✅ Extract scores (kills, deaths, assists, cs)
            scores = your_player_data.get("scores", {})
            kills = scores.get("kills", 0)
            deaths = scores.get("deaths", 0)
            assists = scores.get("assists", 0)
            cs = scores.get("creepScore", 0)
            item_gold = sum(item.get("price", 0) * item.get("count", 1) for item in your_player_data.get("items", []))
            your_team = your_player_data.get("team", "ORDER")
            total_kills = sum(p.get("scores", {}).get("kills", 0) for p in all_players)
            teams_gold = estimate_team_gold(all_players)
            your_team_gold = teams_gold.get(your_team, 0)
            enemy_team_gold = sum(v for k, v in teams_gold.items() if k != your_team)
            print(f"[Gold Debug] ORDER total gold: {teams_gold.get('ORDER', 0)}")
            print(f"[Gold Debug] CHAOS total gold: {teams_gold.get('CHAOS', 0)}")
            gold_diff = your_team_gold - enemy_team_gold
            dragon_kills = {"ORDER": 0, "CHAOS": 0}
            for e in dragon_kill_events:
                killer = e.get("KillerName", "")
                killer_player = next((p for p in all_players if p.get("summonerName") == killer), None)
                if killer_player:
                    team = killer_player.get("team", "UNKNOWN")
                    dragon_kills[team] += 1
            timestamp_now = time.time()
            game_time_seconds = data.get("gameData", {}).get("gameTime", 0)
            # 🆕 Reset logic: detect new game if gameTime resets
            if game_time_seconds < 10 and previous_state.get("last_game_time", 9999) > 30:
                print("🔁 New game detected. Resetting previous_state.")
                previous_state.clear()
                for trigger in triggers:
                    if hasattr(trigger, "reset"):
                        trigger.reset()
                await asyncio.sleep(POLL_INTERVAL)
                continue
            previous_state["last_game_time"] = game_time_seconds  # always track current gameTime
            # 🆕 Initialize state from current game snapshot
            if not previous_state.get("initialized"):
                previous_state.update({
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "cs": cs,
                    "last_hp": hp,
                    "gold": current_gold,  # ✅ add this
                    "item_gold": item_gold,  # ✅ Add this
                    "last_damage_timestamp": timestamp_now,
                    "last_trigger_time": timestamp_now,
                    "last_cs_milestone": (cs // 70) * 70,
                    "total_kills": total_kills,
                    "your_team": your_team,
                    "dragon_kills": dragon_kills,
                    "last_game_time": game_time_seconds,  # ✅ Add this here
                    "initialized": True
                })
                # 🎯 Dynamically insert your name into the MultikillEventTrigger
                if not previous_state.get("multikill_trigger_set"):
                    your_name = your_player_data.get("summonerName")
                    triggers.append(MultikillEventTrigger(your_name=your_name))
                    previous_state["multikill_trigger_set"] = True
                print("📡 Initialized game_data_loop with current stats.")
                await asyncio.sleep(POLL_INTERVAL)
                continue
            # ✅ Build current_data dict to pass into triggers
            current_data = {
                "hp": hp,
                "cs": cs,
                "kills": kills,
                "deaths": deaths,
                "last_hp": hp,
                "gold": current_gold,  # ✅ add this
                "item_gold": item_gold,  # ✅ Add this
                "assists": assists,
                "timestamp": timestamp_now,
                "total_kills": total_kills,
                "your_team": your_team,
                "dragon_kills": dragon_kills,
                "last_game_time": game_time_seconds,  # ✅ Add this line
                "gold_diff": gold_diff,
                "allPlayers": all_players,  # ✅ Now triggers can access full player info!
                "events": data.get("events", {})  # ✅ Add this!
            }
            # Copy current_data just for debugging purposes
            debug_data = current_data.copy()
            debug_data.pop("allPlayers", None)
            debug_data.pop("events", None)
            print(f"[GameLoop] current_data (clean): {json.dumps(debug_data, indent=2)}")
            # ✅ Collect all triggered messages
            merged_results = []
            for trigger in triggers:
                result = trigger.check(current_data, previous_state)
                if result:
                    merged_results.append(result)
            # ✅ If there are any events, and cooldown passed, send single merged AI prompt
            if merged_results and (timestamp_now - last_game_tts_time) >= GAME_TTS_COOLDOWN:
                combined_prompt = "Commentate on the current game:\n" + "\n".join(merged_results)
                log_merged_prompt(combined_prompt)
                mode = get_current_mode()
                ai_text = get_ai_response(combined_prompt, mode)
                await safe_add_to_tts_queue(("game", "GameMonitor", ai_text))
                last_game_tts_time = timestamp_now
            # ✅ Auto recap every X seconds (e.g. 180s)
            if (timestamp_now - previous_state.get("last_recap_time", 0)) >= AUTO_RECAP_INTERVAL:
                    # 🛑 Skip recap if we're too early in the game
                if game_time_seconds < 300:
                    print("⏳ Skipping early-game recap (still in spawn phase).")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                last_snapshot = previous_state.get("last_recap_snapshot")
                if not last_snapshot:
                    last_snapshot = previous_state.copy()
                recap_text = generate_game_recap(data, your_player_data, active_player, last_snapshot, dragon_kills)
                recap_text = "Give a short, energetic recap of the current game:\n" + recap_text
                if recap_text:
                    ai_text = get_ai_response(recap_text, get_current_mode())
                    await safe_add_to_tts_queue(("game", "GameRecap", ai_text))
                    previous_state["last_recap_time"] = timestamp_now
                    previous_state["last_recap_snapshot"] = {
                        "kills": kills,
                        "deaths": deaths,
                        "assists": assists,
                        "cs": cs,
                        "items": your_player_data.get("items", []),
                        "total_kills": total_kills,
                        "your_team": your_team,
                        "dragon_kills": dragon_kills,
                        "gold": current_gold,  # ✅ add this
                        "item_gold": item_gold,  # ✅ Add this
                        "timestamp": timestamp_now,
                        "gold_diff": gold_diff,
                        "allPlayers": all_players,  # ✅ Now triggers can access full player info!
                        "events": data.get("events", {})  # ✅ Add this!
                    }
            # ✅ Update previous state
            previous_state.update({
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "cs": cs,
                "last_hp": hp,
                "total_kills": total_kills,
                "your_team": your_team,
                "dragon_kills": dragon_kills,
                "gold": current_gold,  # ✅ add this
                "item_gold": item_gold,  # ✅ Add this
                "last_game_time": game_time_seconds,  # ✅ Add this line
                "gold_diff": gold_diff,
                "allPlayers": all_players,  # ✅ Now triggers can access full player info!
                "events": data.get("events", {}),  # ✅ Add this!
            })
        except Exception as e:
            print(f"[GameMonitor Error]: {e}")
        await asyncio.sleep(POLL_INTERVAL)

# === AI Commentator Mode ===
async def start_commentator_mode(interval_sec=60):
    global commentator_paused
    previous_mode = None
    while True:
        if commentator_paused:
            await asyncio.sleep(interval_sec)
            continue
        mode = get_current_mode()
        if mode != previous_mode:
            await safe_add_to_tts_queue(f"Switching to {mode} mode.")
            previous_mode = mode
        prompt = "Comment on the current state of the game with your personality."
        try:
            ai_text = get_ai_response(prompt, mode)
            print(f"[ZoroTheCaster - {mode.upper()}]:", ai_text)
            await safe_add_to_tts_queue(ai_text)
        except Exception as e:
            error_msg = f"AI Commentator Error (mode={mode}): {e}"
            print("❌", error_msg)
            log_error(error_msg)  # 👈 Save to logs/errors.log
            await safe_add_to_tts_queue("Hmm... Something went wrong trying to comment. Try again soon.")
        await asyncio.sleep(interval_sec)

# === Twitch Bot ===
class ZoroTheCasterBot(commands.Bot):
    def __init__(self):
        super().__init__(token=TOKEN, prefix="!", initial_channels=[CHANNEL])
        self.twitch_api = None
        self.eventsub_ws = None
        self.obs_controller = OBSController()
        self.obs_controller.connect()

    async def event_ready(self):
        print(f"✅ Logged in as {self.nick}")
        print(f"📡 Connected to #{CHANNEL}")
        self.loop.create_task(self.personality_voting_timer())
        self.loop.create_task(self.periodic_commands_reminder())
        self.loop.create_task(self.process_askai_queue())
        asyncio.create_task(self.auto_mood_loop())
        #self.loop.create_task(start_commentator_mode(60))
        self.loop.create_task(tts_worker())
        await self.init_eventsub()
    
    async def init_eventsub(self):
        try:
            print("🔄 Initializing Twitch API client...")
            self.twitch_api = await Twitch(CLIENT_ID, CLIENT_SECRET)
            print("✅ Twitch API client created.")
            print("🔄 Setting user authentication...")
            if asyncio.iscoroutinefunction(self.twitch_api.set_user_authentication):
                print("⚠ set_user_authentication is async — awaiting it...")
                await self.twitch_api.set_user_authentication(
                    USER_TOKEN,
                    [AuthScope.BITS_READ, AuthScope.CHANNEL_READ_SUBSCRIPTIONS],
                    refresh_token=USER_REFRESH_TOKEN
                )
            else:
                self.twitch_api.set_user_authentication(
                    USER_TOKEN,
                    [AuthScope.BITS_READ, AuthScope.CHANNEL_READ_SUBSCRIPTIONS],
                    refresh_token=USER_REFRESH_TOKEN
                )
            print("✅ Authentication set successfully.")
            print("🔄 Fetching user ID from Twitch API...")
            user_id = None
            async for user in self.twitch_api.get_users(logins=[CHANNEL]):
                print(f"➡ Found user: {user.display_name}, ID: {user.id}")
                user_id = user.id
                break
            if not user_id:
                raise Exception("❌ Failed to retrieve user ID from Twitch API.")
            print(f"✅ Retrieved user ID: {user_id}")
            print("🔄 Creating EventSub WebSocket...")
            self.eventsub_ws = EventSubWebsocket(self.twitch_api)
            print("✅ EventSub WebSocket instance created.")
            print("🔄 Starting WebSocket session...")
            self.eventsub_ws.start()  # Not awaitable
            print("✅ WebSocket session started.")
            print("🔄 Subscribing to events...")
            await self.eventsub_ws.listen_channel_subscribe(user_id, self.on_subscribe_event)
            print("✅ Subscribed to channel_subscribe")
            await self.eventsub_ws.listen_channel_cheer(user_id, self.on_cheer_event)
            print("✅ Subscribed to channel_cheer")
            await self.eventsub_ws.listen_channel_subscription_gift(user_id, self.on_gift_event)
            print("✅ Subscribed to channel_subscription_gift")
            # ✅ RAID event: fix callback position
            await self.eventsub_ws.listen_channel_raid(
                callback=self.on_raid_event,
                to_broadcaster_user_id=user_id
            )
            print("✅ Subscribed to channel_raid")
            print("🎉 EventSub WebSocket fully connected and listening to events!")
        except Exception as e:
            log_error(f"[EVENTSUB INIT ERROR]: {repr(e)}")
            print(f"❌ EventSub connection failed. Reason: {e}. Retrying in 10 seconds...")
            await asyncio.sleep(10)
            await self.init_eventsub()

    async def auto_hide_event_overlay(self, delay=6):
        await asyncio.sleep(delay)
        if hasattr(self, "obs_controller"):
            self.obs_controller.set_text("Event_Display", "")

    async def on_subscribe_event(self, event):
        if eventsub_paused:
            return
        user = event['user_name']
        print(f"[SUB EVENT] {user} just subscribed!")
        ai_text = get_event_reaction("sub", user)
        await safe_add_to_tts_queue(("event", user, ai_text))
        await self.send_to_chat(f"🎉 {user} just subscribed! 💬 ZoroTheCaster is reacting...")
        if hasattr(self, "obs_controller"):
            self.obs_controller.update_event_overlay(f"🎉 {user} just subscribed!")
            self.loop.create_task(self.auto_hide_event_overlay())

    async def on_cheer_event(self, event):
        if eventsub_paused:
            return
        user = event['user_name']
        bits = event['bits']
        print(f"[CHEER EVENT] {user} sent {bits} bits!")
        ai_text = get_event_reaction("cheer", user)
        await safe_add_to_tts_queue(("event", user, ai_text))
        await self.send_to_chat(f"💎 {user} just cheered {bits} bits! 💬 ZoroTheCaster is reacting...")
        if hasattr(self, "obs_controller"):
            self.obs_controller.update_event_overlay(f"💎 {user} cheered {bits} bits!")
            self.loop.create_task(self.auto_hide_event_overlay())

    async def on_raid_event(self, event: ChannelRaidEvent):
        if eventsub_paused:
            return
        try:
            user = event.from_broadcaster_user_name
            viewers = event.viewers
            print(f"[RAID EVENT] {user} raided with {viewers} viewers!")
            ai_text = get_event_reaction("raid", user)
            await safe_add_to_tts_queue(("event", user, ai_text))
            await self.send_to_chat(f"⚔️ {user} just raided with {viewers} viewers! 💬 ZoroTheCaster is reacting...")
            if hasattr(self, "obs_controller"):
                self.obs_controller.update_event_overlay(f"⚔️ {user} raided with {viewers} viewers!")
                self.loop.create_task(self.auto_hide_event_overlay())
        except Exception as e:
            print("❌ Failed to process raid event:", e)
            log_error(f"[RAID EVENT ERROR]: {e}")

    async def on_gift_event(self, event):
        if eventsub_paused:
            return
        user = event['user_name']
        total = event['total']
        print(f"[GIFT EVENT] {user} gifted {total} sub(s)!")
        ai_text = get_event_reaction("gift", user)
        await safe_add_to_tts_queue(("event", user, ai_text))
        await self.send_to_chat(f"🎁 {user} just gifted {total} sub(s)! 💬 ZoroTheCaster is reacting...")
        if hasattr(self, "obs_controller"):
            self.obs_controller.update_event_overlay(f"🎁 {user} gifted {total} sub(s)!")
            self.loop.create_task(self.auto_hide_event_overlay())

    async def event_message(self, message):
        if not message.author:
            return
        if message.author.name.lower() == NICK.lower():
            return
        await self.handle_commands(message)

    async def auto_hide_askai_overlay(self, delay=10):
        await asyncio.sleep(delay)
        if hasattr(self, "obs_controller"):
            self.obs_controller.set_text("AskAI_Display", "")

    @commands.command(name="vote")
    async def vote(self, ctx):
        username = ctx.author.name.lower()
        content = ctx.message.content.strip().lower()
        parts = content.split()
        if len(parts) < 2:
            await ctx.send(f"Usage: !vote [mode] — Valid: {', '.join(VALID_MODES)}")
            return
        mood = parts[1]
        if username in voted_users:
            await ctx.send(f"⛔ {username}, you have already voted this round!")
            return
        if mood in VALID_MODES:
            vote_counts[mood] += 1
            voted_users.add(username)  # ✅ Add user to set
            total_votes = vote_counts[mood]
            await ctx.send(f"{ctx.author.name} voted for '{mood}'! Total votes for {mood}: {total_votes}")
        else:
            await ctx.send(f"❌ Invalid mood. Options: {', '.join(VALID_MODES)}")

    @commands.command(name="results")
    async def results(self, ctx):
        if not vote_counts:
            await ctx.send("No votes yet!")
        else:
            result_str = ', '.join([f"{mood}: {count}" for mood, count in vote_counts.items()])
            await ctx.send(f"🗳 Vote results so far: {result_str}")
    
    @commands.command(name="cooldown")
    async def cooldown(self, ctx):
        user = ctx.author.name
        now = datetime.now(timezone.utc)
        last_used = askai_cooldowns.get(user)
        if not last_used:
            await ctx.send(f"{user}, you have no active cooldown. You can use !askai.")
            return
        remaining = ASKAI_COOLDOWN_SECONDS - int((now - last_used).total_seconds())
        if remaining <= 0:
            await ctx.send(f"{user}, your cooldown has expired. You can use !askai now.")
        else:
            await ctx.send(f"{user}, you need to wait {remaining} more seconds to use !askai.")

    @commands.command(name="resetcooldowns")
    async def resetcooldowns(self, ctx):
        if not ctx.author.is_broadcaster:
            await ctx.send("❌ Only the streamer can reset cooldowns.")
            return

        askai_cooldowns.clear()
        await ctx.send("✅ All !askai cooldowns have been reset by the streamer.")

    @commands.command(name="commands")
    async def commands_list(self, ctx):
        commands_text = (
            "🤖 Commands: 🗳 `!vote` | 📊 `!results` | 🧠 `!askai` | 📚 `!askaihelp` | "
            "⏱ `!cooldown` | 📬 `!queue` | 🎲 `!moodroll` | ⏳ `!nextroll` | 📈 !status | 📄 `!commands` "
            #" ⏸ `!pause` | ▶ `!resume` | ♻ `!resetcooldowns` | 🗑 `!clearqueue`"
        )
        await ctx.send(commands_text)

    @commands.command(name="moodroll")
    async def moodroll(self, ctx):
        global last_moodroll_time
        global current_mode_cache  # ✅ Add this
        now = time.time()
        if now - last_moodroll_time < MOODROLL_COOLDOWN:
            #remaining = int(MOODROLL_COOLDOWN - (now - last_moodroll_time))
            #await ctx.send(f"⏳ Mood roll is on cooldown! Try again in {remaining} seconds.")
            return
        try:
            with open("current_mode.txt", "r") as f:
                current_mode = f.read().strip().lower()
        except:
            current_mode = None
        choices = [mode for mode in VALID_MODES if mode != current_mode]
        new_mode = random.choice(choices)
        with open("current_mode.txt", "w") as f:
            f.write(new_mode)
        current_mode_cache = new_mode
        last_moodroll_time = now
        await ctx.send(f"🎲 Mood roll! ZoroTheCaster is now in **{new_mode.upper()}** mode!")

    @commands.command(name="nextroll")
    async def nextroll(self, ctx):
        global last_moodroll_time
        now = time.time()
        remaining = int(MOODROLL_COOLDOWN - (now - last_moodroll_time))
        if remaining <= 0:
            await ctx.send("🎲 `!moodroll` is ready to use!")
        else:
            await ctx.send(f"⏳ Next mood roll available in {remaining} seconds.")

    @commands.command(name="pause")
    async def pause_commentator(self, ctx):
        global commentator_paused
        global eventsub_paused
        if ctx.author.is_broadcaster:
            commentator_paused = True
            eventsub_paused = True
            await ctx.send("⏸️ ZoroTheCaster commentary and event reactions are paused.")
        else:
            await ctx.send("❌ Only the streamer can pause the AI commentator.")

    @commands.command(name="resume")
    async def resume_commentator(self, ctx):
        global commentator_paused
        global eventsub_paused
        if ctx.author.is_broadcaster:
            commentator_paused = False
            eventsub_paused = False
            await ctx.send("▶️ ZoroTheCaster commentary and event reactions are resumed.")
        else:
            await ctx.send("❌ Only the streamer can resume the AI commentator.")

    @commands.command(name="queue")
    async def queue_length(self, ctx):
        length = askai_queue.qsize()
        if length == 0:
            await ctx.send("📭 The AI queue is currently empty.")
        else:
            await ctx.send(f"📬 There are currently {length} question(s) in the queue.")   

    @commands.command(name="askaihelp")
    async def askai_help(self, ctx):
        help_text = (
            "💬 To ask ZoroTheCaster something, use `!askai [your question]` | 🎮 To trigger in-game commentary, include the word 'commentate'."
        )
        await ctx.send(help_text)

    @commands.command(name="clearqueue")
    async def clear_queue(self, ctx):
        if not ctx.author.is_broadcaster:
            await ctx.send("❌ Only the streamer can clear the AI queue.")
            return
        # Clear the queue by emptying it
        cleared = 0
        while not askai_queue.empty():
            askai_queue.get_nowait()
            askai_queue.task_done()
            cleared += 1
        await ctx.send(f"🗑️ AI queue cleared by the streamer. {cleared} item(s) removed.")

    @commands.command(name="status")
    async def status(self, ctx):
        mode = get_current_mode()
        queue_size = askai_queue.qsize()
        paused_text = "⏸️ Paused" if commentator_paused else "▶️ Active"
        await ctx.send(
            f"📊 **ZoroTheCaster Status:**\n"
            f"🔸 Personality: {mode.upper()}\n"
            f"🔸 Commentary: {paused_text}\n"
            f"🔸 AskAI Queue: {queue_size} item(s)"
        )

    @commands.command(name="testcheer")
    async def test_cheer_command(self, ctx):
        print(f"🔥 TESTCHEER triggered by {ctx.author.name}")
        await self.send_to_chat(f"🎉 Simulating cheer event from {ctx.author.name}")
        fake_event = {'user_name': ctx.author.name, 'bits': 100}
        await self.on_cheer_event(fake_event)

    @commands.command(name="testgift")
    async def test_gift_command(self, ctx):
        print(f"🔥 TESTGIFT triggered by {ctx.author.name}")
        await self.send_to_chat(f"🎁 Simulating gift event from {ctx.author.name}")
        fake_event = {'user_name': ctx.author.name, 'total': 5}
        await self.on_gift_event(fake_event)

    @commands.command(name="testsub")
    async def test_sub_command(self, ctx):
        print(f"🔥 TESTSUB triggered by {ctx.author.name}")
        await self.send_to_chat(f"📢 Simulating subscription from {ctx.author.name}")
        await self.on_subscribe_event({'user_name': ctx.author.name})

    @commands.command(name="testraid")
    async def test_raid_command(self, ctx):
        print(f"🔥 TESTRAID triggered by {ctx.author.name}")
        await self.send_to_chat(f"⚔️ Simulating raid event from {ctx.author.name}")
        class FakeRaidEvent:
            from_broadcaster_user_name = ctx.author.name
            viewers = 42
        await self.on_raid_event(FakeRaidEvent())

    @commands.command(name="askai")
    async def askai(self, ctx):
        user = ctx.author.name
        now = datetime.now(timezone.utc)
        last_used = askai_cooldowns.get(user)
        if last_used and (now - last_used).total_seconds() < ASKAI_COOLDOWN_SECONDS:
            remaining = ASKAI_COOLDOWN_SECONDS - int((now - last_used).total_seconds())
            # ✅ Show only on overlay (not chat)
            overlay_text = f"{user}, wait {remaining}s before using !askai again!"
            print(f"[ASKAI BLOCKED] {overlay_text}")  # Optional: Log it silently
            try:
                cooldown_msg = f"wait {remaining}s before using !askai again."
                await push_askai_cooldown_notice(user, cooldown_msg)
            except Exception as e:
                log_error(f"[Overlay Cooldown Notice ERROR] {e}")
            return
        #if not (ctx.author.is_subscriber or ctx.author.is_mod or ctx.author.is_broadcaster):
        #    await ctx.send(f"❌ {user}, only subscribers, mods, or the streamer can use !askai.")
        #    return
        question = ctx.message.content.replace("!askai", "").strip()
        if not question:
            await ctx.send("Usage: !askai [your question]")
            return
        if askai_queue.qsize() >= ASKAI_TTS_RESERVED_LIMIT:
            await ctx.send("🚫 AskAI is currently overloaded with responses. Please try again soon.")
            return
        # Log question to file
        timestamp = datetime.now(timezone.utc).isoformat()
        with open("logs/askai_log.txt", "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {user}: {question}\n")
        if "commentate" in question.lower() or "comentate" in question.lower() or "commentary" in question.lower():
            full_prompt = f"Commentate on the current game:\n{self.build_game_context(previous_state)}\n\n🧠 {user} asked: {question}"
        else:
            full_prompt = f"{user} asked: {question}"
        await askai_queue.put((user, full_prompt))
        await ctx.send(f"🧠 {user}, your question is queued at position #{askai_queue.qsize()}")

    async def process_askai_queue(self):
        while True:
            user, question = await askai_queue.get()
            mode = get_current_mode()
            try:
                ai_text = get_ai_response(question, mode)
                print(f"[ZoroTheCaster AI Answer - {mode.upper()}]:", ai_text)
                # Send (user, ai_text) tuple to tts_queue instead of plain text
                await safe_add_to_tts_queue(("askai", user, question, ai_text))
            # ✅ Write to askai_data.txt for HTML/CSS Overlay (OBS Browser Source)
            except Exception as e:
                error_msg = f"Error in askai processing for {user}: {e}"
                print(f"❌ {error_msg}")
                log_error(error_msg)
                await self.send_to_chat(f"❌ {user}, something went wrong with the AI response.")
            askai_queue.task_done()
            await asyncio.sleep(ASKAI_QUEUE_DELAY)

    async def send_to_chat(self, message):
        try:
            if self.connected_channels:
                original_length = len(message)
                if original_length > 495:
                    message = message[:485] + "... (trimmed)"
                print(f"[DEBUG] Sending to chat: {message} (len={len(message)}/{original_length})")
                await self.connected_channels[0].send(message)
            else:
                print("[WARNING] No connected channel found to send message.")
                log_error("[WARNING] Tried to send message but no connected_channels.")
        except Exception as e:
            log_error(f"[SEND ERROR]: {e}")
            print(f"❌ Chat send error: {e}")

    def build_game_context(self, state):
        if not state or "kills" not in state:
            return "No game data available right now."
        k = state.get("kills", 0)
        d = state.get("deaths", 0)
        a = state.get("assists", 0)
        cs = state.get("cs", 0)
        gold = state.get("gold", 0)
        team = state.get("your_team", "UNKNOWN")
        dragons = state.get("dragon_kills", {}).get(team, 0)
        return (
            f"Current in-game stats:\n"
            f"K/D/A: {k}/{d}/{a}, CS: {cs}, Gold: {gold}\n"
            f"Your team: {team}, Dragons: {dragons}\n"
        )

    async def personality_voting_timer(self):
        global voted_users
        global current_mode_cache  # ✅ Add this
        previous_mode = get_current_mode()
        while True:
            await asyncio.sleep(VOTING_DURATION)
            if vote_counts:
                most_voted = Counter(vote_counts).most_common(1)[0]
                new_mode, count = most_voted
                with open("current_mode.txt", "w") as f:
                    f.write(new_mode)
                current_mode_cache = new_mode  # ✅ Update the cache
                await self.connected_channels[0].send(
                    f"✨ Voting closed! Winning AI personality: **{new_mode.upper()}** with {count} votes!")
                # ✅ Only announce if mode actually changed
                if new_mode != previous_mode:
                    await safe_add_to_tts_queue(f"The new AI personality is {new_mode} mode.")
                    previous_mode = new_mode  # Update tracking
                else:
                    await self.connected_channels[0].send(
                        f"🟰 Personality remains in {new_mode.upper()} mode.")
            else:
                await self.connected_channels[0].send("🕓 Voting ended, no votes were cast.")
            vote_counts.clear()
            voted_users.clear()  # ✅ Reset voted users for new round
            await self.connected_channels[0].send("🔄 Votes have been reset. Start voting again!")

    async def auto_mood_loop(self):
        global last_moodroll_time
        global current_mode_cache
        await asyncio.sleep(10)  # initial delay after startup
        while True:
            await asyncio.sleep(MOOD_AUTO_SWITCH_INTERVAL)
            try:
                with open("current_mode.txt", "r") as f:
                    current_mode = f.read().strip().lower()
            except:
                current_mode = None
            choices = [mode for mode in VALID_MODES if mode != current_mode]
            new_mode = random.choice(choices)
            with open("current_mode.txt", "w") as f:
                f.write(new_mode)
            current_mode_cache = new_mode  # ✅ update the in-memory cache
            last_moodroll_time = time.time()  # reset cooldown to prevent immediate roll after auto switch
            await self.connected_channels[0].send(
                f"🔁 Auto-switch activated! ZoroTheCaster is now in **{new_mode.upper()}** mode!")
            #if tts_queue.empty():
                #await safe_add_to_tts_queue(f"The mood has changed to {new_mode} mode.")
            #else:
                #print("[TTS] Skipping mood voice line — TTS is busy.")


    async def periodic_commands_reminder(self, interval=600):  # 600 sec = 10 minutes
        while True:
            try:
                if self.connected_channels:
                    commands_text = (
                        "🤖 Commands: 🗳 `!vote` | 📊 `!results` | 🧠 `!askai` | 📚 `!askaihelp` |  "
                        "⏱ `!cooldown` | 📬 `!queue` | 🎲 `!moodroll` | ⏳ `!nextroll` | 📈 `!status` | 📄 `!commands` "
                    )
                    await self.connected_channels[0].send(commands_text)
            except Exception as e:
                log_error(f"[Periodic Commands Reminder ERROR] {e}")
            await asyncio.sleep(interval)


# === Run the Bot ===
if __name__ == "__main__":
    debug_imports()
    setup_shutdown_hooks(bot_instance=None, executor=tts_executor)
    load_initial_mode()  # ✅ This loads the personality from file at startup
    # 🔧 Force item prices to load (and cache file to be created)
    #ensure_item_prices_loaded()
    #print("[DEBUG] Item prices loaded:", len(ITEM_PRICES), "items")
    async def startup_tasks():
        # Start WebSocket overlay server
        global overlay_ws_task
        overlay_ws_task = asyncio.create_task(start_overlay_ws_server())
        # ✅ Start Game Data Monitor (new line here!)
        asyncio.create_task(game_data_loop())
        # Start the Twitch bot
        bot = ZoroTheCasterBot()
        global bot_instance
        bot_instance = bot
        setup_shutdown_hooks(bot_instance=bot, executor=tts_executor)
        await bot.start()
    asyncio.run(startup_tasks())
