import os
import asyncio
from dotenv import load_dotenv
from twitchio.ext import commands
from collections import defaultdict, Counter
import time

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

class ZoroTheCasterBot(commands.Bot):

    def __init__(self):
        super().__init__(
            token=TOKEN,
            prefix="!",
            initial_channels=[CHANNEL]
        )

    async def event_ready(self):
        print(f"✅ Logged in as {self.nick}")
        print(f"📡 Connected to #{CHANNEL}")
        # Start background task after bot connects
        self.loop.create_task(self.personality_voting_timer())

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

    async def personality_voting_timer(self):
        while True:
            await asyncio.sleep(VOTING_DURATION)

            if vote_counts:
                # Find most voted mode
                most_voted = Counter(vote_counts).most_common(1)[0]
                mode, count = most_voted
                print(f"💡 Switching AI mode to: {mode.upper()} ({count} votes)")

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
