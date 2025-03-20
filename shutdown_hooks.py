import os
import signal
import asyncio
import threading

def list_all_threads():
    print("\n🧠 [DEBUG] Active Threads on shutdown:")
    for thread in threading.enumerate():
        print(f"➡ {thread.name} (Daemon: {thread.daemon})")

def setup_shutdown_hooks(bot_instance=None, executor=None):
    def graceful_shutdown(signum, frame):
        print("\n🛑 Ctrl+C or Termination Signal received! Shutting down...")
        if bot_instance and hasattr(bot_instance, "eventsub_ws"):
            print("🧹 Stopping EventSub WebSocket...")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(bot_instance.eventsub_ws.stop())
                else:
                    loop.run_until_complete(bot_instance.eventsub_ws.stop())
            except Exception as e:
                print(f"⚠️ WebSocket shutdown error: {e}")
        if hasattr(bot_instance, "obs_controller"):
            try:
                bot_instance.obs_controller.disconnect()
                print("🔌 OBS WebSocket disconnected.")
            except Exception as e:
                print(f"⚠ Failed to disconnect OBS cleanly: {e}")

        if executor:
            print("🧹 Shutting down TTS executor...")
            try:
                executor.shutdown(wait=False)
            except Exception as e:
                print(f"⚠️ TTS executor shutdown error: {e}")
                
        list_all_threads()
        os._exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
