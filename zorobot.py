import os
import asyncio
from dotenv import load_dotenv
from twitchio.ext import commands
from collections import defaultdict, Counter
import pyttsx3
from datetime import datetime, timedelta, timezone
from openai import OpenAI
import concurrent.futures

# === Load Environment Variables ===
load_dotenv()
TOKEN = os.getenv("TWITCH_TOKEN")
NICK = os.getenv("TWITCH_NICK")
CHANNEL = os.getenv("TWITCH_CHANNEL")
print(f"Loaded channel from .env: {CHANNEL}")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === OpenAI Setup ===
client = OpenAI(api_key=OPENAI_API_KEY)

# === Global Configs ===
tts_lock = asyncio.Lock()
tts_queue = asyncio.Queue()
vote_counts = defaultdict(int)
ASKAI_COOLDOWN_SECONDS = 10
ASKAI_QUEUE_LIMIT = 10
ASKAI_QUEUE_DELAY = 10
VOTING_DURATION = 300
askai_cooldowns = {}
askai_queue = asyncio.Queue()
VALID_MODES = ["hype", "coach", "sarcastic", "wholesome"]
tts_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
commentator_paused = False  # New flag
# Global reference to bot instance (initialized later)
bot_instance = None
MAX_TTS_QUEUE_SIZE = 10  # Prevents spam/flood
os.makedirs("logs", exist_ok=True)  # Create logs folder if not exist

# === Utility Functions ===
def get_current_mode():
    try:
        with open("current_mode.txt", "r") as f:
            mode = f.read().strip().lower()
            return mode if mode in VALID_MODES else "hype"
    except FileNotFoundError:
        return "hype"

def load_system_prompt(mode):
    try:
        with open(f"prompts/{mode}.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are a witty League of Legends commentator."

def get_ai_response(prompt, mode):
    system_prompt = load_system_prompt(mode)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=100,
        temperature=0.7
    )
    return response.choices[0].message.content

def get_event_reaction(event_type, user):
    base_prompt = {
        "sub": f"{user} just subscribed! React as a hype League of Legends commentator.",
        "resub": f"{user} just resubscribed! Celebrate it like a shoutcaster.",
        "raid": f"A raid is happening! {user} brought their viewers! React dramatically.",
        "cheer": f"{user} just sent some bits! React with high energy and excitement.",
        "gift": f"{user} just gifted a sub! Celebrate like a caster going wild during a pentakill.",
        "giftmass": f"{user} started a mass gift sub train! React like the arena is exploding with hype.",
    }.get(event_type, f"{user} triggered an unknown event. React accordingly.")
    mode = get_current_mode()
    return get_ai_response(base_prompt, mode)

def log_error(error_text):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open("logs/errors.log", "a", encoding="utf-8") as error_file:
        error_file.write(f"[{timestamp}] {error_text}\n")

def speak_sync(text):
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)
    engine.say(text)
    engine.runAndWait()

async def speak_text(text):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(tts_executor, speak_sync, text)

async def tts_worker():
    while True:
        item = await tts_queue.get()
        try:
            if isinstance(item, tuple):
                user, text = item
                chat_message = f"{user}, ZoroTheCaster says: {text}"
                if bot_instance:
                    await bot_instance.send_to_chat(chat_message)
            else:
                text = item  # System message, no user
            await speak_text(text)
        except Exception as e:
            log_error(f"TTS ERROR: {e}")
        tts_queue.task_done()

async def safe_add_to_tts_queue(item):
    if tts_queue.qsize() < MAX_TTS_QUEUE_SIZE:
        await tts_queue.put(item)
    else:
        log_error(f"[TTS SKIPPED] Queue full. Message skipped: {item}")

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

    async def event_ready(self):
        print(f"✅ Logged in as {self.nick}")
        print(f"📡 Connected to #{CHANNEL}")
        self.loop.create_task(self.personality_voting_timer())
        self.loop.create_task(self.process_askai_queue())
        #self.loop.create_task(start_commentator_mode(60))
        self.loop.create_task(tts_worker())

    async def event_message(self, message):
        if not message.author:
            return
        if message.author.name.lower() == NICK.lower():
            return
        # 🎁 Detect Gift Sub
        msg_id = message.tags.get("msg-id")
        if msg_id == "subgift":
            user = message.tags.get("login") or message.author.name
            print(f"🎁 {user} just gifted a sub!")
            await self.handle_twitch_event("gift", user)
        # Detect Mass Gift Sub (optional for later)
        if msg_id == "submysterygift":
            user = message.tags.get("login") or message.author.name
            print(f"🎁 {user} started a mass gift sub train!")
            await self.handle_twitch_event("giftmass", user)
        # 🔥 Detect Cheers (bits)
        bits = message.tags.get("bits")
        if bits:
            try:
                bits = int(bits)
                user = message.author.name
                print(f"🎉 {user} just sent {bits} bits!")
                await self.handle_twitch_cheer_event(user, bits) 
            except Exception as e:
                log_error(f"[BITS ERROR] Failed to parse bits cheer: {e}")
        await self.handle_commands(message)
   
    async def handle_twitch_cheer_event(self, user, bits):
        try:
            # Choose hype level based on bits amount
            if bits < 100:
                hype_level = "React excitedly but modestly."
            elif bits < 500:
                hype_level = "React with hype and enthusiasm, make it sound like a mini-victory!"
            elif bits < 1000:
                hype_level = "React dramatically, shoutcaster style! Bring energy and awe!"
            else:
                hype_level = "React like it's the biggest moment of the tournament — full hype, over-the-top, explosive excitement!"
            # Build prompt
            prompt = f"{user} just sent {bits} bits! {hype_level}"
            mode = get_current_mode()
            ai_text = get_ai_response(prompt, mode)
            print(f"[ZoroTheCaster - BITS REACTION]: {ai_text}")
            await safe_add_to_tts_queue(ai_text)
        except Exception as e:
            log_error(f"[CHEER EVENT ERROR] {e}")

    async def handle_twitch_event(self, event_type, user):
        try:
            reaction_text = get_event_reaction(event_type, user)
            await safe_add_to_tts_queue(reaction_text)
        except Exception as e:
            log_error(f"[EVENT ERROR] {event_type} from {user}: {e}")

    @commands.command(name="vote")
    async def vote(self, ctx):
        content = ctx.message.content.strip().lower()
        parts = content.split()
        if len(parts) < 2:
            await ctx.send(f"Usage: !vote [mode] — Valid: {', '.join(VALID_MODES)}")
            return
        mood = parts[1]
        if mood in VALID_MODES:
            vote_counts[mood] += 1
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
            "🤖 Commands: "
            "🗳 `!vote` | 📊 `!results` | 🧠 `!askai` | ⏱ `!cooldown` | 📬 `!queue` | 📈 !status | 📄 `!commands` "
            #" ⏸ `!pause` | ▶ `!resume` | ♻ `!resetcooldowns` | 🗑 `!clearqueue`"
        )
        await ctx.send(commands_text)

    @commands.command(name="hello")
    async def hello(self, ctx):
        await ctx.send(f"Hello {ctx.author.name}! I'm ZoroTheCaster. 😊")

    @commands.command(name="pause")
    async def pause_commentator(self, ctx):
        global commentator_paused
        if ctx.author.is_broadcaster:
            commentator_paused = True
            await ctx.send("⏸️ ZoroTheCaster commentary has been paused.")
        else:
            await ctx.send("❌ Only the streamer can pause the AI commentator.")

    @commands.command(name="resume")
    async def resume_commentator(self, ctx):
        global commentator_paused
        if ctx.author.is_broadcaster:
            commentator_paused = False
            await ctx.send("▶️ ZoroTheCaster commentary has been resumed.")
        else:
            await ctx.send("❌ Only the streamer can resume the AI commentator.")

    @commands.command(name="queue")
    async def queue_length(self, ctx):
        length = askai_queue.qsize()
        if length == 0:
            await ctx.send("📭 The AI queue is currently empty.")
        else:
            await ctx.send(f"📬 There are currently {length} question(s) in the queue.")       
   
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

    @commands.command(name="askai")
    async def askai(self, ctx):
        user = ctx.author.name
        now = datetime.now(timezone.utc)
        last_used = askai_cooldowns.get(user)
        if last_used and (now - last_used).total_seconds() < ASKAI_COOLDOWN_SECONDS:
            remaining = ASKAI_COOLDOWN_SECONDS - int((now - last_used).total_seconds())
            await ctx.send(f"⏳ {user}, wait {remaining}s before using !askai again.")
            return
        if not (ctx.author.is_subscriber or ctx.author.is_mod or ctx.author.is_broadcaster):
            await ctx.send(f"❌ {user}, only subscribers, mods, or the streamer can use !askai.")
            return
        question = ctx.message.content.replace("!askai", "").strip()
        if not question:
            await ctx.send("Usage: !askai [your question]")
            return
        if askai_queue.qsize() >= ASKAI_QUEUE_LIMIT:
            await ctx.send("🚫 AI queue is full. Try again later.")
            return
        # Log question to file
        timestamp = datetime.now(timezone.utc).isoformat()
        with open("logs/askai_log.txt", "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {user}: {question}\n")
        askai_cooldowns[user] = now
        await askai_queue.put((user, question))
        await ctx.send(f"🧠 {user}, your question is queued at position #{askai_queue.qsize()}")

    async def process_askai_queue(self):
        while True:
            user, question = await askai_queue.get()
            mode = get_current_mode()
            try:
                ai_text = get_ai_response(question, mode)
                print(f"[ZoroTheCaster AI Answer - {mode.upper()}]:", ai_text)
                # Send (user, ai_text) tuple to tts_queue instead of plain text
                await safe_add_to_tts_queue((user, ai_text))
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
                if original_length > 460:
                    message = message[:445] + "... (trimmed)"
                print(f"[DEBUG] Sending to chat: {message} (len={len(message)}/{original_length})")
                await self.connected_channels[0].send(message)
            else:
                print("[WARNING] No connected channel found to send message.")
                log_error("[WARNING] Tried to send message but no connected_channels.")
        except Exception as e:
            log_error(f"[SEND ERROR]: {e}")
            print(f"❌ Chat send error: {e}")

    async def personality_voting_timer(self):
        while True:
            await asyncio.sleep(VOTING_DURATION)
            if vote_counts:
                most_voted = Counter(vote_counts).most_common(1)[0]
                mode, count = most_voted
                with open("current_mode.txt", "w") as f:
                    f.write(mode)
                await self.connected_channels[0].send(
                    f"✨ Voting closed! Winning AI personality: **{mode.upper()}** with {count} votes!")
                await safe_add_to_tts_queue(f"The new AI personality is {mode} mode.")
            else:
                await self.connected_channels[0].send("🕓 Voting ended, no votes were cast.")
                await safe_add_to_tts_queue("The voting period ended with no votes.")
            vote_counts.clear()
            await self.connected_channels[0].send("🔄 Votes have been reset. Start voting again!")

# === Run the Bot ===
if __name__ == "__main__":
    bot = ZoroTheCasterBot()
    bot_instance = bot  # Set global reference so tts_worker can use it
    bot.run()
