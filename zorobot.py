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
from overlay_push import (push_askai_overlay,push_event_overlay,push_commentary_overlay,push_hide_overlay, push_toggle_power_overlay,
                push_askai_cooldown_notice,push_cost_overlay,push_cost_increment, push_mood_overlay,push_power_scores)
import requests
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from triggers.game_triggers import (HPDropTrigger, CSMilestoneTrigger, KillCountTrigger, DeathTrigger, GoldThresholdTrigger, FirstBloodTrigger,StreakTrigger,
             DragonKillTrigger, MultikillEventTrigger, GameEndTrigger, GoldDifferenceTrigger, AceTrigger, BaronTrigger, AtakhanKillTrigger, HeraldKillTrigger,
             FeatsOfStrengthTrigger)
from elevenlabs.client import ElevenLabs
from elevenlabs import play, VoiceSettings
import json
import random
from utils.game_utils import estimate_team_gold,ensure_item_prices_loaded
from game_data_monitor import set_callback, game_data_loop, generate_game_recap, get_previous_state, set_triggers, feats_trigger, streak_trigger
from shared_state import previous_state,inhib_respawn_timer, baron_expire, elder_expire, player_ratings,seen_inhib_events
from prompts.user_prompts import get_random_commentary_prompt, get_random_recap_prompt

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
VALID_MODES = ["hype", "rage", "sarcastic", "wholesome","troll","smartass","tsundere","edgelord","shakespeare","genz"]
# 🧠 Choose model and voice ID
ELEVEN_MODEL = "eleven_turbo_v2_5"
ELEVEN_VOICE_ID = "TxGEqnHWrfWFTfGW9XjX"  # ← keep only as default/fallback
# 🔊 Personality to Voice ID mapping
VOICE_BY_MODE = {
    "hype": "TxGEqnHWrfWFTfGW9XjX",       # Josh
    "smartass": "TxGEqnHWrfWFTfGW9XjX",   # Josh
    "shakespeare": "TxGEqnHWrfWFTfGW9XjX",# Josh
    "rage": "21m00Tcm4TlvDq8ikWAM",      # Rachel
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
VOTING_DURATION = 300
last_moodroll_time = 0  # Global cooldown timer
MOODROLL_COOLDOWN = 60  # seconds
askai_cooldowns = {}
askai_queue = asyncio.Queue()
current_mode_cache = "hype"  # default
commentator_paused = False  # New flag
eventsub_paused = False
power_score_visible = True  # default state
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
    GoldDifferenceTrigger(threshold=4000, even_margin=1000, cooldown=600),
    BaronTrigger(),
    #MultikillEventTrigger(player_name="Zoro2000"),
]
# 🔥 TTS cooldown config
GAME_TTS_COOLDOWN = 4  # seconds
last_game_tts_time = 0  # global timestamp tracker
AUTO_RECAP_INTERVAL = 600  # every 10 minutes
tts_busy = False
buffered_game_events = []
tts_monitor_task = None  # Will be assigned during startup

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
    global tts_busy
    while True:
        item = await tts_queue.get()
        try:
            tts_busy = True
            log_merged_prompt("🟠 TTS state changed: BUSY")
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
        finally:
            tts_queue.task_done()
            tts_busy = False
            log_merged_prompt(f"🟢 TTS state changed: IDLE | Queue size: {tts_queue.qsize()}")
            await asyncio.sleep(0.5)  # ⏱️ Small delay to avoid spammy speech

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

async def tts_monitor_loop():
    global tts_busy
    while True:
        await asyncio.sleep(0.4)
        if not tts_busy and buffered_game_events:
            print("🧹 TTS is free, flushing buffered game events...")
            mode = get_current_mode()
            # ✨ Use dynamic prompt
            personality_prompt = get_random_commentary_prompt(mode)
            numbered_debug = "\n".join(f"{i+1}. {line}" for i, line in enumerate(buffered_game_events))
            # 🧠 For AI
            combined_prompt = f"{personality_prompt}\n" + "\n".join(buffered_game_events)
            # 📄 For logs
            debug_prompt = f"{personality_prompt}\n{numbered_debug}"
            log_merged_prompt(debug_prompt)
            ai_text = get_ai_response(combined_prompt, mode)
            await safe_add_to_tts_queue(("game", "GameMonitor", ai_text))
            buffered_game_events.clear()

def _get_log_path(log_filename: str) -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_dir = os.path.join("logs", date_str)
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, log_filename)
def log_error(error_text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    path = _get_log_path("errors.log")
    with open(path, "a", encoding="utf-8") as error_file:
        error_file.write(f"[{timestamp}] {error_text}\n")
def log_event(text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    path = _get_log_path("openai_usage.log")
    with open(path, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {text}\n")
def log_merged_prompt(text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    path = _get_log_path("merged_prompts.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text.strip()}\n")
def log_recap_prompt(text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    path = _get_log_path("recaps.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text.strip()}\n")
def log_askai_commentary_prompt(text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    path = _get_log_path("askai_commentary.log")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text.strip()}\n")

def is_game_related(question: str):
    q = question.lower()
    return any(word in q for word in ["winnable", "win", "lose", "score", "comeback", "game", "match", "gold", "kills", "cs", "status"])

async def clear_state_after_delay(delay_seconds=6):
    await asyncio.sleep(delay_seconds)
    print("🧹 Delayed GameEnd cleanup triggered.")
    # Preserve game_ended flag
    game_ended = previous_state.get("game_ended", False)
    print("[Before Clear] previous_state =", previous_state)  # 🔍 Add this line for sanity check
    previous_state.clear()
    # Also clear buff/inhib timers
    inhib_respawn_timer["ORDER"].clear()
    inhib_respawn_timer["CHAOS"].clear()
    baron_expire.clear()
    elder_expire.clear()
    seen_inhib_events.clear()
    player_ratings.clear()
    # 🧽 Push cleared overlay state
    await push_power_scores({    # ✅ This clears the panel visually
        "players": [],
        "order_total": 0,
        "chaos_total": 0
    })
    if game_ended:
        previous_state["game_ended"] = True  # Restore it for AskAI checks
        print("[After Clear] Restored game_ended flag")
    for trigger in triggers:
        if hasattr(trigger, "reset"):
            trigger.reset()

def handle_game_data(data, your_player_data, current_data, merged_results):
    global last_game_tts_time, buffered_game_events, tts_busy
    timestamp_now = time.time()
    game_time_seconds = current_data["last_game_time"]
    mode = get_current_mode()
    # ✅ Now let TTS play as usual
    if merged_results:
        is_game_over = any("Game over" in msg for msg in merged_results)
        # ✅ NEW: Prioritize buffered lines first, even if TTS is free
        if buffered_game_events:
            buffered_game_events.extend(merged_results)
            print(f"🧠 Buffering {len(merged_results)} new lines — TTS is free but backlog exists.")
            return
        if not tts_busy and (timestamp_now - last_game_tts_time) >= GAME_TTS_COOLDOWN:
            combined_prompt = get_random_commentary_prompt(mode) +  "\n" + "\n".join(merged_results)
            log_merged_prompt(combined_prompt)
            ai_text = get_ai_response(combined_prompt, mode)
            asyncio.create_task(safe_add_to_tts_queue(("game", "GameMonitor", ai_text)))
            last_game_tts_time = timestamp_now
        elif tts_busy:
            buffered_game_events.extend(merged_results)
            print(f"🧠 TTS busy — buffering {len(merged_results)} merged game lines")
        # ✅ Always mark game ended if detected (even if we didn’t send TTS yet)
        if is_game_over and not previous_state.get("game_ended"):
            previous_state["game_ended"] = True
            print("🧹 GameEnd detected, starting delayed cleanup...")
            asyncio.create_task(clear_state_after_delay())
    # Recap logic
    if (timestamp_now - previous_state.get("last_recap_time", 0)) >= AUTO_RECAP_INTERVAL:
        if game_time_seconds < 300:
            print("⏳ Skipping early-game recap.")
            return
        last_snapshot = previous_state.get("last_recap_snapshot") or previous_state.copy()
        recap_text = generate_game_recap(data, your_player_data, data.get("activePlayer", {}), last_snapshot, current_data["dragon_kills"])
        if recap_text:
            recap_prompt = get_random_recap_prompt() + "\n" + recap_text
            log_recap_prompt(recap_prompt)  # 🧼 New log file!
            ai_text = get_ai_response(recap_prompt, mode)
            asyncio.create_task(safe_add_to_tts_queue(("game", "GameRecap", ai_text)))
            previous_state["last_recap_time"] = timestamp_now
            previous_state["last_recap_snapshot"] = {
                **current_data,
                "items": your_player_data.get("items", [])
            }

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

    @commands.command(name="testpower")
    async def test_power_overlay(self, ctx):
        if not ctx.author.is_broadcaster:
            await ctx.send("❌ Only the streamer can trigger test overlay.")
            return
        dummy_players = [
            {"name": "Garen", "score": 82.1, "team": "ORDER", "role": "top"},
            {"name": "Jax", "score": 78.4, "team": "CHAOS", "role": "top"},
            {"name": "Lee Sin", "score": 66.2, "team": "ORDER", "role": "jungle"},
            {"name": "Nidalee", "score": 72.5, "team": "CHAOS", "role": "jungle"},
            {"name": "Ahri", "score": 91.3, "team": "ORDER", "role": "middle"},
            {"name": "Zed", "score": 88.7, "team": "CHAOS", "role": "middle"},
            {"name": "Ashe", "score": 60.5, "team": "ORDER", "role": "bottom"},
            {"name": "Jhin", "score": 64.0, "team": "CHAOS", "role": "bottom"},
            {"name": "Thresh", "score": 49.3, "team": "ORDER", "role": "utility"},
            {"name": "Pyke", "score": 51.8, "team": "CHAOS", "role": "utility"},
        ]
        order_score = sum(p["score"] for p in dummy_players if p["team"] == "ORDER")
        chaos_score = sum(p["score"] for p in dummy_players if p["team"] == "CHAOS")

        await push_power_scores({
            "players": dummy_players,
            "order_total": round(order_score, 1),
            "chaos_total": round(chaos_score, 1)
        })
        await ctx.send("🧪 Dummy power score data sent to overlay.")

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
        try:
            await push_mood_overlay(new_mode)
        except Exception as e:
            log_error(f"[Overlay Mood Push ERROR] {e}")
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

    @commands.command(name='power')
    async def toggle_power(self, ctx):
        if not ctx.author.is_broadcaster:
            await ctx.send("❌ Only the streamer can toggle the power score overlay.")
            return
        global power_score_visible
        power_score_visible = not power_score_visible
    # ✅ Make sure broadcast is imported or accessible
        await push_toggle_power_overlay(power_score_visible)
        await ctx.send(f"🟢 Power score overlay {'enabled' if power_score_visible else 'disabled'}.")

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
            current_state = get_previous_state()
            full_prompt = f"Commentate on the current game:\n{self.build_game_context(current_state)}\n\n🧠 {user} asked: {question}"
            print("[ASKAI] current_state snapshot:", json.dumps(current_state, indent=2))
            log_askai_commentary_prompt(full_prompt)
        else:
            full_prompt = f"{user} asked: {question}"
        await askai_queue.put((user, full_prompt))
        # ✅ Set cooldown timestamp for this user
        askai_cooldowns[user] = now
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
        print("[ASKAI] current state for commentary:", state)
        if not state or "kills" not in state or state.get("game_ended"):
            return "🕹️ No game in progress. Ask again once the battle begins!"
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
        global current_mode_cache
        global last_moodroll_time
        await asyncio.sleep(10)  # Initial startup delay
        while True:
            await asyncio.sleep(VOTING_DURATION)
            if vote_counts:
                most_voted = Counter(vote_counts).most_common(1)[0]
                new_mode, count = most_voted
                await self.connected_channels[0].send(
                    f"✨ Voting closed! Winning AI personality: **{new_mode.upper()}** with {count} votes!"
                )
            else:
                current_mode = get_current_mode()
                choices = [mode for mode in VALID_MODES if mode != current_mode]
                new_mode = random.choice(choices)
                await self.connected_channels[0].send(
                    f"🔁 No votes cast. Auto-switching to **{new_mode.upper()}** mode!"
                )
            with open("current_mode.txt", "w") as f:
                f.write(new_mode)
            current_mode_cache = new_mode
            last_moodroll_time = time.time()
            try:
                await push_mood_overlay(new_mode)
            except Exception as e:
                log_error(f"[Overlay Mood Push ERROR] {e}")
            vote_counts.clear()
            voted_users.clear()
            await self.connected_channels[0].send("🔄 Votes have been reset. Start voting again!")

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
    #setup_shutdown_hooks(bot_instance=None, executor=tts_executor)
    load_initial_mode()  # ✅ This loads the personality from file at startup
    # 🔧 Force item prices to load (and cache file to be created)
    #ensure_item_prices_loaded()
    #print("[DEBUG] Item prices loaded:", len(ITEM_PRICES), "items")
    async def startup_tasks():
        # Start WebSocket overlay server
        global overlay_ws_task
        overlay_ws_task = asyncio.create_task(start_overlay_ws_server())
        set_triggers(triggers)  # ✅ This sends your trigger list to game_data_monitor
        set_callback(handle_game_data)  # ✅ now it's set just before the loop starts
        asyncio.create_task(game_data_loop())
        global tts_monitor_task
        tts_monitor_task = asyncio.create_task(tts_monitor_loop())
        # Start the Twitch bot
        bot = ZoroTheCasterBot()
        global bot_instance
        bot_instance = bot
        setup_shutdown_hooks(bot_instance=bot, executor=tts_executor)  
        await bot.start()
    asyncio.run(startup_tasks())
