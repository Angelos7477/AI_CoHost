from memory_manager import add_to_memory

add_to_memory(
    content="This is a test memory item.",
    type_="test",
    stream_date="2025-06-02",
    game_number=1,
    metadata={"note": "manual test"}
)

print("✅ Added test memory.")
