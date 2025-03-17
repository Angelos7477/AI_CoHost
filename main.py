from dotenv import load_dotenv
import os
import pyttsx3
import time
from openai import OpenAI
import asyncio

tts_lock = asyncio.Lock()
# Load API Key from .env
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# 🔥 Dynamically load current personality mode from file
def get_current_mode():
    valid_modes = ["hype", "coach", "sarcastic", "wholesome"]
    try:
        with open("current_mode.txt", "r") as f:
            mode = f.read().strip().lower()
            if mode in valid_modes:
                return mode
            else:
                print(f"⚠️ Warning: Invalid mode '{mode}' found in file. Falling back to 'hype'.")
                return "hype"
    except FileNotFoundError:
        print("⚠️ Warning: current_mode.txt not found. Falling back to 'hype'.")
        return "hype"


# Load system prompt from /prompts folder
def load_system_prompt(mode):
    try:
        with open(f"prompts/{mode}.txt", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are a witty League of Legends commentator."

# Get AI response
def get_ai_response(prompt, mode):
    system_prompt = load_system_prompt(mode)
    response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ],
    max_tokens=100,
    temperature=0.7  # ← More creative personality
)
    return response.choices[0].message.content

# Speak out loud
async def speak_text(text):
    async with tts_lock:
        engine = pyttsx3.init()
        engine.setProperty('rate', 160)
        engine.say(text)
        engine.runAndWait()

# Commentator loop — speaks every X seconds with updated mood
async def start_commentator_mode(interval_sec=60):
    previous_mode = None
    while True:
        mode = get_current_mode()

        if mode != previous_mode:
            await speak_text(f"Switching to {mode} mode.")
            previous_mode = mode

        prompt = "Comment on the current state of the game with your personality."
        print(f"🗣 ZoroTheCaster ({mode} mode): Thinking...")

        try:
            ai_text = get_ai_response(prompt, mode)
            print(f"[ZoroTheCaster - {mode.upper()}]:", ai_text)
            await speak_text(ai_text)
        except Exception as e:
            print("❌ ERROR:", e)
            await speak_text("Hmm... Something went wrong trying to comment. Try again soon.")

        await asyncio.sleep(interval_sec)



# Start commentator
if __name__ == "__main__":
    asyncio.run(start_commentator_mode(60))
