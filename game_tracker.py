# game_tracker.py

import os
import json
from datetime import datetime, date

STATE_FILE = "game_state.json"

class GameTracker:
    def __init__(self):
        self.stream_date = date.today().strftime("%Y-%m-%d")
        self.game_number = 0
        self._load_state()

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                    if data["stream_date"] == self.stream_date:
                        self.game_number = data["game_number"]
                    else:
                        self._reset_for_new_day()
            except Exception as e:
                print(f"Failed to load game state: {e}")
                self._reset_for_new_day()
        else:
            self._reset_for_new_day()

    def _reset_for_new_day(self):
        self.stream_date = date.today().strftime("%Y-%m-%d")
        self.game_number = 0
        self._save_state()

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump({
                "stream_date": self.stream_date,
                "game_number": self.game_number
            }, f)

    def increment_game_number(self):
        self.game_number += 1
        self._save_state()

    def get_game_id(self):
        if self.game_number == 0:
            return None
        date_str = self.stream_date.replace("-", "")
        return f"game_{date_str}_{self.game_number}"

    def get_game_number(self):
        return self.game_number

    def get_stream_date(self):
        return self.stream_date

# Example usage
# if __name__ == "__main__":
#     tracker = GameTracker()
#     print("Current Game ID:", tracker.get_game_id())
#     tracker.increment_game_number()
#     print("After increment:", tracker.get_game_id())