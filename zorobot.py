import os
import asyncio
from dotenv import load_dotenv
from twitchio.ext import commands
from collections import defaultdict, Counter
import pyttsx3
from datetime import datetime, timedelta, timezone
from openai import OpenAI

# === Load Environment Variables ===
load_dotenv()
TOKEN = os.getenv("TWITCH_TOKEN")
NICK = os.getenv("TWITCH_NICK")
CHANNEL = os.getenv("TWITCH_CHANNEL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# === OpenAI Setup ===
client = OpenAI(api_key=OPENAI_API_KEY)

# === Global Configs ===
tts_lock = asyncio.Lock()
vote_counts = defaultdict(int)
ASKAI_COOLDOWN_SECONDS = 180
ASKAI_QUEUE_LIMIT = 10
ASKAI_QUEUE_DELAY = 60
VOTING_DURATION = 300
askai_cooldowns = {}
askai_queue = asyncio.Queue()
VALID_MODES = ["hype", "coach", "sarcastic", "wholesome"]

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

async def speak_text(text):
    async with tts_lock:
        engine = pyttsx3.init()
        engine.setProperty('rate', 160)
        engine.say(text)
        engine.runAndWait()

# === AI Commentator Mode ===
async def start_commentator_mode(interval_sec=60):
    previous_mode = None
    while True:
        mode = get_current_mode()
        if mode != previous_mode:
            await speak_text(f"Switching to {mode} mode.")
            previous_mode = mode
        prompt = "Comment on the current state of the game with your personality."
        try:
            ai_text = get_ai_response(prompt, mode)
            print(f"[ZoroTheCaster - {mode.upper()}]:", ai_text)
            await speak_text(ai_text)
        except Exception as e:
            print("❌ AI Error:", e)
            await speak_text("Hmm... Something went wrong trying to comment. Try again soon.")
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
        self.loop.create_task(start_commentator_mode(60))

    async def event_message(self, message):
        if message.author.name.lower() == NICK.lower():
            return
        await self.handle_commands(message)

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
            await ctx.send(f"{ctx.author.name} voted for '{mood}'! 👍")
        else:
            await ctx.send(f"❌ Invalid mood. Options: {', '.join(VALID_MODES)}")

    @commands.command(name="results")
    async def results(self, ctx):
        if not vote_counts:
            await ctx.send("No votes yet!")
        else:
            result_str = ', '.join([f"{mood}: {count}" for mood, count in vote_counts.items()])
            await ctx.send(f"🗳 Vote results so far: {result_str}")

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
        await ctx.send(f"🧠 {user}, your question is in the queue!")
        askai_cooldowns[user] = now
        await askai_queue.put((user, question))

    async def process_askai_queue(self):
        while True:
            user, question = await askai_queue.get()
            mode = get_current_mode()
            try:
                ai_text = get_ai_response(question, mode)
                print(f"[ZoroTheCaster AI Answer - {mode.upper()}]:", ai_text)
                await speak_text(ai_text)
                if len(ai_text) <= 200:
                    await self.connected_channels[0].send(f"{user}, ZoroTheCaster says: {ai_text}")
                else:
                    await self.connected_channels[0].send(f"{user}, ZoroTheCaster answered out loud! (Too long for chat)")
            except Exception as e:
                print(f"❌ Error in askai: {e}")
                await self.connected_channels[0].send(f"❌ {user}, something went wrong with the AI response.")
            askai_queue.task_done()
            await asyncio.sleep(ASKAI_QUEUE_DELAY)

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
            else:
                await self.connected_channels[0].send("🕓 Voting ended, no votes were cast.")
            vote_counts.clear()
            await self.connected_channels[0].send("🔄 Votes have been reset. Start voting again!")

# === Run the Bot ===
if __name__ == "__main__":
    bot = ZoroTheCasterBot()
    bot.run()
