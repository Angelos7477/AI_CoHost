from dotenv import load_dotenv
import os
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")


import openai

openai.api_key = openai_api_key

def get_ai_response(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # or "gpt-4o"
        messages=[
            {"role": "system", "content": "You are a witty game commentator for a League of Legends stream."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=150
    )
    return response.choices[0].message["content"]


import pyttsx3

def speak_text(text):
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)  # speed
    engine.say(text)
    engine.runAndWait()

    import time

def start_commentator_mode(interval_sec=60):
    while True:
        prompt = "Comment on the current state of the game with a funny or sarcastic tone."
        ai_text = get_ai_response(prompt)
        print("[AI Commentator]:", ai_text)
        speak_text(ai_text)
        time.sleep(interval_sec)