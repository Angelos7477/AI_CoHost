from overlay_ws_server import broadcast
import asyncio

# === Overlay Push Utilities ===
recent_cooldown_popups = set()
session_cost_total = 0.0

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

async def push_hide_overlay(source_type: str):
    """Send hide signal to any overlay type (askai, event, commentary)."""
    await broadcast({
        "type": f"{source_type}_hide"
    })

async def push_askai_cooldown_notice(user: str, text: str, duration: float = 2.0):
    """
    Show a cooldown popup for a user, but only once per cooldown window.
    """
    if user in recent_cooldown_popups:
        return  # Don't show again for the same user right away
    recent_cooldown_popups.add(user)
    try:
        await broadcast({
            "type": "cooldown",
            "message": f"{user}: {text}"
        })
        await asyncio.sleep(duration)
        await push_hide_overlay("cooldown")
    except Exception as e:
        print(f"[Overlay Cooldown Notice Error] {e}")
    finally:
        # Allow this user to trigger the message again after the cooldown delay
        await asyncio.sleep(5.0)  # Small buffer to avoid flicker spam
        recent_cooldown_popups.discard(user)

async def push_cost_overlay(amount):
    await broadcast({
        "type": "cost",
        "amount": amount
    })

async def push_cost_increment(cost):
    global session_cost_total
    session_cost_total += cost
    await push_cost_overlay(session_cost_total)