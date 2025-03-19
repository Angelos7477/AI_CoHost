from datetime import datetime, timezone
import os

# Ensure logs folder exists
os.makedirs("logs", exist_ok=True)

def log_error(error_text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open("logs/errors.log", "a", encoding="utf-8") as error_file:
        error_file.write(f"[{timestamp}] {error_text}\n")

def log_event(event_text: str, filename="events.log"):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(f"logs/{filename}", "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {event_text}\n")

def log_askai_question(user: str, question: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    with open("logs/askai_log.txt", "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {user}: {question}\n")
