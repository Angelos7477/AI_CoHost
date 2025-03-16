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

# Get AI response (NEW SYNTAX for v1.0+)
def get_ai_response(prompt):
    response = client.chat.completions.create(
        model="gpt-4o",  # or gpt-4o , gpt-3.5-turbo
        messages=[
            {"role": "system", "content": "You are a witty game commentator for a League of Legends stream.Keep messages under 50 words."
            "Dont use emojis."},
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
def run_test_mode():
    print("🔹 Running Test Mode...")
    print("Comment on my girlfriend that doesnt know anything about gaming. Keep your response small")
    prompt = "Im feeding all game!!!"
    try:
        ai_text = get_ai_response(prompt)
        print("[AI Commentator]:", ai_text)
        speak_text(ai_text)
    except Exception as e:
        print("❌ ERROR:", e)

# Start it
run_test_mode()
