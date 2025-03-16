from dotenv import load_dotenv
import os
import pyttsx3
import time
from openai import OpenAI  # NEW import

# Load .env and API key
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
#print("API Key Loaded:", openai_api_key[:8] + "...")

# Set up OpenAI client (NEW SYNTAX for v1.0+)
client = OpenAI(api_key=openai_api_key)

def load_system_prompt(mode="hype"):
    with open(f"prompts/{mode}.txt", "r", encoding="utf-8") as f:
        return f.read()

# Get AI response (NEW SYNTAX for v1.0+)
def get_ai_response(prompt, mode="hype"):
    system_prompt = load_system_prompt(mode)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        max_tokens=100
    )
    return response.choices[0].message.content

# Speak text (TTS)
def speak_text(text):
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)
    engine.say(text)
    engine.runAndWait()

# Test Mode (Run Once)
def run_test_mode(mode="hype"):
    print("🔹 Running Test Mode...")
    prompt = "Im feeding all game!!!"
    try:
        ai_text = get_ai_response(prompt, mode)
        print("[AI Commentator]:", ai_text)
        speak_text(ai_text)
    except Exception as e:
        print("❌ ERROR:", e)

# Start it
run_test_mode(mode="sarcastic")
