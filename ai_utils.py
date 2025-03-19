# ai_utils.py
import os
from openai import OpenAI

VALID_MODES = ["hype", "coach", "sarcastic", "wholesome"]
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
        model="gpt-3.5-turbo",  #gpt-4o , gpt-3.5-turbo
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
    return get_ai_response(base_prompt, get_current_mode())
