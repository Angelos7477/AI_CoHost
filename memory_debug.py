#python memory_debug.py
from memory_manager import collection

print("🔍 Memory count:", collection.count())

results = collection.get()
for doc, meta in zip(results["documents"], results["metadatas"]):
    print("🧠", doc)
    print("📎 Metadata:", meta)
    print("–––")
