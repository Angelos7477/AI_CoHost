#overlay_ws_server.py
import asyncio
import websockets
import json
import os

PORT = int(os.getenv("OVERLAY_WS_PORT", 8765))
# Set of all connected overlay clients
connected_clients = set()
print("💡 overlay_ws_server.py loaded")

def get_current_mood():
    try:
        with open("current_mode.txt", "r") as f:
            return f.read().strip()
    except:
        return "hype"  # Default fallback

async def handler(websocket):
    client_id = id(websocket)
    print(f"[WS] Overlay connected - ID: {id(websocket)} | Total: {len(connected_clients)}")
    connected_clients.add(websocket)
        # 🧠 Immediately send current mood to the just-connected overlay
    try:
        current_mood = get_current_mood()
        await websocket.send(json.dumps({
            "type": "mood",
            "text": current_mood
        }))
        print(f"[WS] Sent initial mood '{current_mood}' to client {client_id}")
    except Exception as e:
        print(f"[WS] Failed to send initial mood to {client_id}: {e}")
    try:
        async for message in websocket:
            print("Received from overlay:", message)
    except websockets.exceptions.ConnectionClosed:
        print("[WS] Overlay disconnected")
    finally:
        connected_clients.discard(websocket)

async def broadcast(data):
    if connected_clients:
        message = json.dumps(data)
        disconnected = set()
        for client in connected_clients:
            try:
                await client.send(message)
            except Exception as e:
                print(f"[WS BROADCAST ERROR] Client send failed: {e}")
                disconnected.add(client)
        connected_clients.difference_update(disconnected)

async def start_server():
    print(f"Starting WebSocket server on ws://localhost:{PORT}")
    print("💡 start_server() launched")
    try:
        async with websockets.serve(handler, "localhost", PORT):
            await asyncio.Future()
    except asyncio.CancelledError:
        print("🛑 Overlay WebSocket server shutdown cleanly.")

# Helper to send test messages manually
async def send_test_messages():
    await asyncio.sleep(2)
    await broadcast({"type": "mood", "text": "Energetic"})
    await asyncio.sleep(2)
    await broadcast({"type": "event", "content": "User123 just subbed!"})
    await asyncio.sleep(2)
    await broadcast({"type": "askai", "question": "What’s the best top lane champ?", "answer": "Try Darius or Camille."})
    await asyncio.sleep(2)
    await broadcast({"type": "commentary", "text": "Huge gank in midlane!"})

if __name__ == "__main__":
    async def main():
        server_task = asyncio.create_task(start_server())
        # Optional: Test messages (can be removed in production)
        test_task = asyncio.create_task(send_test_messages())
        try:
            await asyncio.gather(server_task, test_task)
        except asyncio.CancelledError:
            print("🛑 Server tasks cancelled cleanly.")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down WebSocket server.")
