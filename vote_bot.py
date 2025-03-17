import os
import asyncio
from dotenv import load_dotenv
from twitchio.ext import commands
from collections import defaultdict, Counter
import pyttsx3
from main import get_ai_response, get_current_mode  # reuse your existing functions
import time
from datetime import datetime, timedelta, timezone
import asyncio

tts_lock = asyncio.Lock()
# Load environment variables
load_dotenv()
TOKEN = os.getenv("TWITCH_TOKEN")
NICK = os.getenv("TWITCH_NICK")
CHANNEL = os.getenv("TWITCH_CHANNEL")

# Personality vote options
VALID_MODES = ["hype", "coach", "sarcastic", "wholesome"]
vote_counts = defaultdict(int)

# Time (in seconds) for each voting period
VOTING_DURATION = 300  # 5 minutes
ASKAI_QUEUE_LIMIT = 10  # Max number of AI requests allowed in the queue
askai_cooldowns = {}  # Tracks last ask time per user
askai_queue = asyncio.Queue()  # Queue for pending requests
ASKAI_COOLDOWN_SECONDS = 180  # 3-minute cooldown (adjust as needed)
ASKAI_QUEUE_DELAY = 60  # Delay between answering askai questions


async def speak_text(text):
    async with tts_lock:
        engine = pyttsx3.init()
        engine.setProperty('rate', 160)
        engine.say(text)
        engine.runAndWait()

class ZoroTheCasterBot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TOKEN,
            prefix="!",
            initial_channels=[CHANNEL]
        )

    async def event_message(self, message):
        if message.author.name.lower() == NICK.lower():
            return
        await self.handle_commands(message)

    @commands.command(name='vote')
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

    @commands.command(name='results')
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
            "🤖 **ZoroTheCaster Commands:**\n"
            "🔹 `!vote [mode]` - Vote for AI personality (hype, coach, sarcastic, wholesome)\n"
            "🔹 `!results` - Show current votes\n"
            "🔹 `!askai [question]` - Ask the AI (subscribers & mods only)\n"
            "🔹 `!cooldown` - Check your !askai cooldown\n"
            "🔹 `!queue` - Shows the number of pending AI questions, Max limit 10\n"
            "🔹 `!resetcooldowns` - (Streamer only) Reset all cooldowns\n"
            "🔹 `!clearqueue` - (Streamer only) Clears the queue\n"
            "🔹 `!commands` - Show this list"
        )
        await ctx.send(commands_text)

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

    @commands.command(name="askai")
    async def askai(self, ctx):
        user = ctx.author.name
        is_mod = ctx.author.is_mod
        is_broadcaster = ctx.author.is_broadcaster
        is_sub = ctx.author.is_subscriber

        # ⏱ Check cooldown
        now = datetime.now(timezone.utc)
        last_used = askai_cooldowns.get(user)
        if last_used and (now - last_used).total_seconds() < ASKAI_COOLDOWN_SECONDS:
            remaining = ASKAI_COOLDOWN_SECONDS - int((now - last_used).total_seconds())
            await ctx.send(f"⏳ {user}, you need to wait {remaining}s before using !askai again.")
            return

        # ✅ Allow mods and broadcaster without sub
        if not (is_sub or is_mod or is_broadcaster):
            await ctx.send(f"❌ Sorry {user}, only subscribers, mods, or the streamer can use !askai.")
            return

        # Extract the question
        question = ctx.message.content.replace("!askai", "").strip()
        if not question:
            await ctx.send("Usage: !askai [your question]")
            return

        # Check if queue is full
        if askai_queue.qsize() >= ASKAI_QUEUE_LIMIT:
            await ctx.send("🚫 The AI queue is full right now. Please try again in a few minutes.")
            return
        await ctx.send(f"🧠 {user}, your question has been added to the queue!")

        # Update cooldown timestamp
        askai_cooldowns[user] = now

        # Add request to the queue
        await ctx.send(f"{user}, your question is queued at position #{askai_queue.qsize()}")

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
                await self.connected_channels[0].send(f"❌ Sorry {user}, something went wrong with the AI response.")

            # Mark task as complete
            askai_queue.task_done()
            # 🔸 Delay between processing next askai request
            await asyncio.sleep(ASKAI_QUEUE_DELAY)

    async def event_ready(self):
        print(f"✅ Logged in as {self.nick}")
        print(f"📡 Connected to #{CHANNEL}")
        # Start queue processor
        self.loop.create_task(self.personality_voting_timer())
        self.loop.create_task(self.process_askai_queue())


    async def personality_voting_timer(self):
        while True:
            await asyncio.sleep(VOTING_DURATION)

            if vote_counts:
                # Find most voted mode
                most_voted = Counter(vote_counts).most_common(1)[0]
                mode, count = most_voted
                print(f"💡 Switching AI mode to: {mode.upper()} ({count} votes)")
                 
                 # 🔥 Write the winning mode to a file
                try:
                    with open("current_mode.txt", "w") as f:
                        f.write(mode)
                except Exception as e:
                    print(f"❌ Error writing mode to file: {e}")

                # You can later pass this mode to your AI cohost script here
                # e.g., write to a file, call a function, etc.

                # Announce in chat
                await self.connected_channels[0].send(
                    f"✨ Voting closed! The winning AI personality is **{mode.upper()}** with {count} votes!"
                )
            else:
                await self.connected_channels[0].send("🕓 Voting period ended, but no votes were cast!")

            # Reset votes for next round
            vote_counts.clear()
            await self.connected_channels[0].send("🔄 Vote counts have been reset. You can start voting again!")

# Run the bot
if __name__ == "__main__":
    bot = ZoroTheCasterBot()
    bot.run()
