from overlay_ws_server import broadcast

# === Overlay Push Utilities ===

async def push_askai_overlay(question: str, answer: str):
    """Send AskAI Question & Answer to overlay via WebSocket."""
    await broadcast({
        "type": "askai",
        "question": question,
        "answer": answer
    })

async def push_event_overlay(content: str):
    """Send Twitch Event text to overlay (e.g., sub/gift/cheer)."""
    await broadcast({
        "type": "event",
        "content": content
    })

async def push_mood_overlay(text: str):
    """Send Mood / Personality update to overlay."""
    await broadcast({
        "type": "mood",
        "text": text
    })

async def push_commentary_overlay(text: str):
    """Send Game Commentary line to overlay."""
    await broadcast({
        "type": "commentary",
        "text": text
    })
