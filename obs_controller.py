# obs_controller.py

import os
from dotenv import load_dotenv
from obswebsocket import obsws, requests
from obswebsocket.exceptions import ConnectionFailure
from datetime import datetime, timezone

# Load .env variables
load_dotenv()

def log_obs_event(text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    os.makedirs("logs", exist_ok=True)  # Ensure logs/ exists
    with open("logs/obs.log", "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {text}\n")

class OBSController:
    def __init__(self, host=None, port=None, password=None):
        self.host = host or os.getenv("OBS_HOST", "localhost")
        self.port = int(port or os.getenv("OBS_PORT", 4455))
        self.password = password or os.getenv("OBS_PASSWORD", "")
        self.ws = None

    def connect(self):
        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            print(f"✅ Connected to OBS WebSocket at ws://{self.host}:{self.port}")
            log_obs_event(f"Connected to OBS WebSocket at ws://{self.host}:{self.port}")
        except ConnectionFailure as e:
            print(f"❌ OBS connection failed: {e}")
            log_obs_event(f"❌ OBS connection failed: {e}")

    def disconnect(self):
        if self.ws:
            self.ws.disconnect()
            print("🔌 OBS WebSocket disconnected.")
            log_obs_event("OBS WebSocket disconnected.")

    def switch_scene(self, scene_name):
        try:
            self.ws.call(requests.SetCurrentProgramScene(scene_name))
            log_obs_event(f"Switched scene to '{scene_name}'")
        except Exception as e:
            print(f"❌ Failed to switch scene: {e}")
            log_obs_event(f"❌ Failed to switch scene: {e}")

    def show_source(self, source_name, scene=None):
        try:
            scene_name = scene or self.get_current_scene()
            scene_item_id = self.get_scene_item_id(source_name, scene_name)
            if scene_item_id:
                self.ws.call(requests.SetSceneItemEnabled(
                    sceneName=scene_name,
                    sceneItemId=scene_item_id,
                    sceneItemEnabled=True
                ))
        except Exception as e:
            print(f"❌ Failed to show source '{source_name}': {e}")

    def hide_source(self, source_name, scene=None):
        try:
            scene_name = scene or self.get_current_scene()
            scene_item_id = self.get_scene_item_id(source_name, scene_name)
            if scene_item_id:
                self.ws.call(requests.SetSceneItemEnabled(
                    sceneName=scene_name,
                    sceneItemId=scene_item_id,
                    sceneItemEnabled=False
                ))
        except Exception as e:
            print(f"❌ Failed to hide source '{source_name}': {e}")

    def set_text(self, source_name, text):
        try:
            self.ws.call(requests.SetInputSettings(
                inputName=source_name,
                inputSettings={"text": text},
                overlay=False
            ))
        except Exception as e:
            print(f"❌ Failed to set text on '{source_name}': {e}")

    def update_ai_overlay(self, question: str, answer: str, source_name="AskAI_Display"):
        try:
            display_text = f"🧠 AskAI Q: {question}\n💬 AI says: {answer}"
            self.set_text(source_name, display_text)
            log_obs_event(f"Updated AskAI text overlay (Q&A)")
        except Exception as e:
            print(f"❌ Failed to update AskAI overlay: {e}")

    def get_scene_item_id(self, source_name, scene_name):
        try:
            items = self.ws.call(requests.GetSceneItemList(sceneName=scene_name)).getSceneItems()
            for item in items:
                if item['sourceName'] == source_name:
                    return item['sceneItemId']
            raise ValueError(f"Scene item '{source_name}' not found in scene '{scene_name}'")
        except Exception as e:
            print(f"❌ Error getting scene item ID for '{source_name}': {e}")
            return None

    def get_current_scene(self):
        try:
            return self.ws.call(requests.GetCurrentProgramScene()).getName()
        except Exception as e:
            print(f"❌ Failed to get current scene: {e}")
            return None
