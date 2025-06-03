# shared_state.py
from game_tracker import GameTracker
previous_state = {}
player_ratings = {}
inhib_respawn_timer = {"ORDER": [], "CHAOS": []}
baron_expire = {}
elder_expire = {}
seen_inhib_events = set()
tracker = GameTracker()