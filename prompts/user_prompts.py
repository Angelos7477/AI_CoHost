# prompts/user_prompts.py
import random

COMMENTARY_TEMPLATES = {
    "default": [
        "Commentate on the current game:",
        "Give your thoughts on the current in-game action:",
        "Describe what’s happening right now in the match:",
        "React to these recent events like you’re live on stream:",
        "Offer a play-by-play breakdown of this sequence:",
    ],
    "hype": [
        "🔥 You’re a hypecaster! Shout like it’s the LCS finals:",
        "Explode with excitement about the current game events:",
        "Pump up the audience with an intense reaction to these plays:",
    ],
    "rage": [
        "🔥 You're absolutely FURIOUS. Rip into what just happened like you're done with this team!",
        "You're tilted beyond reason. Yell at the team, flame the plays, scream about how bad this is:",
        "🧨 You're a rage-fueled caster watching a disaster unfold. Vent your frustration brutally:",
    ],
    "sarcastic": [
        "😏 Comment on the game with dry humor and snark:",
        "You're unimpressed. Roast these players casually:",
    ],
    "wholesome": [
        "💖 React with kindness and encouragement to these events:",
        "Cheer for the teams with a supportive, feel-good tone:",
    ],
    "troll": [
        "🃏 Say something wildly unhelpful but funny:",
        "Mock the game like you're messing with the viewers:",
    ],
    "smartass": [
        "🧠 Flex your big brain while describing what happened:",
        "Point out what everyone missed like a smug genius:",
    ],
    "tsundere": [
        "😤 Pretend you don’t care, but secretly you’re invested:",
        "React with cold sarcasm but let your concern slip through:",
    ],
    "edgelord": [
        "🗡️ Speak like the fate of the world depends on these plays:",
        "React like you're narrating an anime fight to the death:",
    ],
    "conspiracist": [
        "🕵️ React like everything happening is part of a grand conspiracy:",
        "Spin a wild theory about why that play just happened:",
        "Connect unrelated events like a mad genius uncovering the truth:",
    ],
    "genz": [
        "📱 React like a Zoomer TikToker casting this match:",
        "Comment using Gen Z slang and emoji reactions:",
    ],
}

RECAP_TEMPLATES = [
    "Give a quick recap of recent events:",
    "Summarize what’s been going on in the last few minutes:",
    "Give a short, energetic recap of the current game:",
    "Explain what’s changed since the last update:",
    "Catch the viewer up on what they missed:",
]

def get_random_commentary_prompt(mode):
    prompts = COMMENTARY_TEMPLATES.get(mode, COMMENTARY_TEMPLATES["default"])
    return random.choice(prompts)

def get_random_recap_prompt():
    return random.choice(RECAP_TEMPLATES)
