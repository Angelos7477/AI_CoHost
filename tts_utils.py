import asyncio
import pyttsx3
import concurrent.futures
from datetime import datetime, timezone
from log_utils import log_error

# TTS Configuration
tts_lock = asyncio.Lock()
tts_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
tts_queue = asyncio.Queue()
MAX_TTS_QUEUE_SIZE = 10  # Prevents spam/flood
ASKAI_TTS_RESERVED_LIMIT = 7  # Maximum messages askai is allowed to use in TTS queue
EVENTSUB_RESERVED_SLOTS = MAX_TTS_QUEUE_SIZE - ASKAI_TTS_RESERVED_LIMIT

async def speak_text(text):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(tts_executor, speak_sync, text)

def speak_sync(text):
    engine = pyttsx3.init()
    engine.setProperty('rate', 160)
    engine.say(text)
    engine.runAndWait()

async def tts_worker(bot_instance=None):
    while True:
        item = await tts_queue.get()
        try:
            if isinstance(item, tuple):
                user, text = item
                chat_message = f"{user}, ZoroTheCaster says: {text}"
                if bot_instance:
                    await bot_instance.send_to_chat(chat_message)
            else:
                text = item
            await speak_text(text)
        except Exception as e:
            log_error(f"TTS ERROR: {e}")
        tts_queue.task_done()

async def safe_add_to_tts_queue(item):
    queue_size = tts_queue.qsize()
    is_askai = isinstance(item, tuple) and isinstance(item[0], str)  # AskAI messages are (user, text)
    if is_askai and queue_size >= ASKAI_TTS_RESERVED_LIMIT:
        log_error(f"[ASKAI TTS SKIPPED] AskAI message dropped due to reserved space for EventSub.")
        return
    if not is_askai and queue_size >= MAX_TTS_QUEUE_SIZE:
        log_error(f"[EVENTSUB TTS SKIPPED] Queue full. EventSub message skipped: {item}")
        return
    await tts_queue.put(item)

def shutdown_tts_executor():
    try:
        tts_executor.shutdown(wait=False)
        print("✅ TTS executor shutdown complete.")
    except Exception as e:
        log_error(f"[TTS EXECUTOR SHUTDOWN ERROR]: {e}")
