# memory_manager.py

from chromadb import PersistentClient  # ✅ Use PersistentClient instead of Client
from chromadb.config import Settings
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from openai import OpenAI
import uuid
import os
from datetime import datetime, timezone, timedelta
import time
import asyncio
from shared_state import previous_state
import json
from dotenv import load_dotenv

# Cooldown map to prevent redundant summaries
load_dotenv()
_memory_summary_cooldowns = {}
SUMMARY_COOLDOWN_SECONDS = 300  # 5 minutes

openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)

# ✅ Use PersistentClient to enable .persist()
chroma_client = PersistentClient(path="./chromadb_memory")  # ✅ Stores data here
embedding_fn = OpenAIEmbeddingFunction(
    api_key=openai_api_key,
    model_name="text-embedding-3-small"  # Make sure this matches what you use in generate_embedding()
)
collection = chroma_client.get_or_create_collection(
    name="zorobot_memory",
    embedding_function=embedding_fn
)

# ---- UTILITY ----

def generate_embedding(text):
    response = openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=[text]
    )
    return response.data[0].embedding

def get_current_game_id(stream_date, game_number):
    date_str = stream_date.replace("-", "")
    return f"game_{date_str}_{game_number}"

def _get_log_path(log_filename: str) -> str:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_dir = os.path.join("logs", date_str)
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, log_filename)
def log_error(error_text: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    path = _get_log_path("errors.log")
    with open(path, "a", encoding="utf-8") as error_file:
        error_file.write(f"[{timestamp}] {error_text}\n")
def log_event(message: str):
    timestamp = datetime.now(timezone.utc).isoformat()
    path = _get_log_path("events.log")
    with open(path, "a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] {message}\n")

# ---- CORE FUNCTIONS ----

def add_to_memory(content, type_, stream_date, game_number, metadata=None):
    game_id = get_current_game_id(stream_date, game_number)
    embedding = generate_embedding(content)
    entry_id = str(uuid.uuid4())
    full_metadata = {
        "type": type_,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "game_id": game_id,
        "stream_date": stream_date,
        "game_number": game_number,
    }
    if metadata:
        full_metadata.update(metadata)
    collection.add(
        documents=[content],
        metadatas=[full_metadata],
        ids=[entry_id],
        embeddings=[embedding]
    )

def add_game_memory(content, stream_date, game_number, metadata=None):
    game_id = get_current_game_id(stream_date, game_number)
    embedding = generate_embedding(content)
    entry_id = str(uuid.uuid4())
    # ⏱ Format game time
    seconds = previous_state.get("last_game_time", 0)
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    game_time = f"{minutes}:{sec:02d}"
    # 🧠 Get team scores
    team_scores = previous_state.get("team_scores", {})
    your_team = previous_state.get("your_team", "ORDER")
    enemy_team = "CHAOS" if your_team == "ORDER" else "ORDER"
    order_score = team_scores.get("ORDER", "?")
    chaos_score = team_scores.get("CHAOS", "?")
    formatted_players = previous_state.get("formatted_players", [])
    def full_team_summary(team_name):
        role_order = ["top", "jungle", "middle", "bottom", "utility"]
        pretty_roles = {
            "top": "Top",
            "jungle": "Jungle",
            "middle": "Mid",
            "bottom": "ADC",
            "utility": "Support"
        }
        players = [p for p in formatted_players if p["team"] == team_name]
        player_map = {p["role"]: p for p in players}
        return [
            f"{pretty_roles[role]}: {player_map[role]['name']} ({player_map[role]['score']})"
            for role in role_order if role in player_map
        ]
    order_summary = ", ".join(full_team_summary("ORDER"))
    chaos_summary = ", ".join(full_team_summary("CHAOS"))
    top_str = (
        f"\nORDER: {order_summary}"
        f"\nCHAOS: {chaos_summary}"
    )
    # 👤 Add your summoner name if available
    your_name = previous_state.get("your_name")
    if your_name:
        top_str += f"\nYou are playing as: {your_name}"
    # 📌 Final memory content
    full_content = (
        f"🕒 {game_time} | Your Team ({your_team}): {team_scores.get(your_team, '?')}, "
        f"Enemy Team ({enemy_team}): {team_scores.get(enemy_team, '?')}{top_str} | Event: {content}"
    )
    full_metadata = {
        "type": "game",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "game_id": game_id,
        "stream_date": stream_date,
        "game_number": game_number,
    }
    if metadata:
        full_metadata.update(metadata)
    collection.add(
        documents=[full_content],
        metadatas=[full_metadata],
        ids=[entry_id],
        embeddings=[embedding]
    )

def query_memory_relevant(prompt, user=None, top_k_user=4, top_k_global=2):
    try:
        results = []
        seen_docs = set()  # track to avoid duplicates
        # 🧠 1. User-specific results
        user_docs = []
        user_metas = []
        if user:
            user_results = collection.query(
                query_texts=[prompt],
                n_results=top_k_user,
                where={"user": user}
            )
            user_docs = user_results.get("documents", [[]])[0]
            user_metas = user_results.get("metadatas", [[]])[0]
            for doc, meta in zip(user_docs, user_metas):
                if doc not in seen_docs:
                    results.append((doc, meta))
                    seen_docs.add(doc)
        # 🧠 2. Global results (skip duplicates)
        global_results = collection.query(
            query_texts=[prompt],
            n_results=top_k_global + 3,  # overfetch in case of duplicates
            where={
                "type": {"$nin": ["game", "recap", "game_event"]}
            }
        )
        global_docs = global_results.get("documents", [[]])[0]
        global_metas = global_results.get("metadatas", [[]])[0]
        for doc, meta in zip(global_docs, global_metas):
            if doc not in seen_docs:
                results.append((doc, meta))
                seen_docs.add(doc)
            if len(seen_docs) >= top_k_user + top_k_global:
                break
        # 🧠 3. Fallback (only if user returned nothing)
        if user and not user_docs:
            fallback_results = collection.query(
                query_texts=[prompt],
                n_results=top_k_user,
                where={
                "type": {"$nin": ["game", "recap", "game_event"]}
                }
            )
            fallback_docs = fallback_results.get("documents", [[]])[0]
            fallback_metas = fallback_results.get("metadatas", [[]])[0]
            for doc, meta in zip(fallback_docs, fallback_metas):
                if doc not in seen_docs:
                    results.append((doc, meta))
                    seen_docs.add(doc)
                if len(seen_docs) >= top_k_user + top_k_global:
                    break
        return results
    except Exception as e:
        log_error(f"[Memory Query ERROR] {e}")
        return []

def clear_memory():
    collection.delete(where={})  # Clears all entries

def close_memory():
    try:
        chroma_client.persist()
        print("💾 Memory changes persisted.")
    except Exception as e:
        print(f"⚠️ Failed to persist memory: {e}")

def debug_print_memory(n=10):
    try:
        results = collection.get(limit=n)
        for i, doc in enumerate(results["documents"]):
            print(f"\n🧠 Entry #{i+1}")
            print(f"ID: {results['ids'][i]}")
            print(f"Metadata: {results['metadatas'][i]}")
            print(f"Content: {doc}")
    except Exception as e:
        print(f"⚠️ Failed to print memory: {e}")
    
def should_query_memory(prompt):
    try:
        check_prompt = (
            "You're deciding whether to search memory to answer this.\n"
            "When being asked something with ? try and search memory.\n"
            "Reply ONLY with true or false.\n\n"
            f"User: {prompt}\n\nShould you search memory?"
        )
        result = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": check_prompt}],
            max_tokens=30,
            temperature=0
        )
        decision = result.choices[0].message.content.strip().lower()
        log_event(f"[Memory Query Decision] Prompt: {prompt} → Search Memory: {decision}")
        return "true" in decision
    except Exception as e:
        log_error(f"[should_query_memory ERROR] {e}")
        return False

def count_user_memories(user, type_="askai"):
    try:
        # Step 1: filter only by user (one field max)
        results = collection.get(where={"user": user})
        # Step 2: manually filter by type
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        # Only keep those with the correct type
        filtered = [
            doc for doc, meta in zip(docs, metas)
            if meta.get("type") == type_
        ]
        return len(filtered)
    except Exception as e:
        log_error(f"[count_user_memories ERROR] {e}")
        return 0

def summarize_and_replace_user_memories(user, type_="askai"):
    try:
        # Step 1: Fetch all memories for this user (one filter only)
        results = collection.get(where={"user": user})
        docs = results.get("documents", [])
        ids = results.get("ids", [])
        metas = results.get("metadatas", [])
        # Step 2: Filter by type manually
        filtered = [
            (doc, id_, meta) for doc, id_, meta in zip(docs, ids, metas)
            if meta.get("type") == type_
        ]
        if len(filtered) < 5:
            return  # no need to summarize 4 or fewer memories
        memory_blob = "\n".join([f"- {doc}" for doc, _, _ in filtered])
        log_event(f"[Memory Summary Source] For {user}:\n{memory_blob}")
        summarization_prompt = (
            "Summarize the following user facts into a single memory entry. "
            "Keep only useful or recurring facts.\n\n"
            f"{memory_blob}\n\n"
            "Return a concise bullet-point list of facts (e.g., name, partner, TTS mode, preferences)."
        )
        result = openai_client.chat.completions.create(
            model="gpt-4.1-mini-2025-04-14",   # gpt-4o-mini-2024-07-18 , gpt-3.5-turbo , gpt-4.1-mini-2025-04-14
            messages=[{"role": "user", "content": summarization_prompt}],
            max_tokens=200,
            temperature=0.3
        )
        summary = result.choices[0].message.content.strip()
        # Step 3: Delete old memories
        delete_ids = [id_ for _, id_, _ in filtered]
        collection.delete(ids=delete_ids)
        # Step 4: Store summarized memory
        add_to_memory(
            content=summary,
            type_=type_,
            stream_date=datetime.now().date().isoformat(),
            game_number=0,
            metadata={"user": user, "source": type_}
        )
        log_event(f"[Memory Summary] Created summary for {user}: {summary}")
    except Exception as e:
        log_error(f"[summarize_and_replace_user_memories ERROR] {e}")

async def summarize_and_replace_user_memories_async(user, type_="askai"):
    now_ts = time.time()
    last_ts = _memory_summary_cooldowns.get(user)
    if last_ts and now_ts - last_ts < SUMMARY_COOLDOWN_SECONDS:
        return  # 🕒 Still cooling down
    _memory_summary_cooldowns[user] = now_ts
    await asyncio.to_thread(summarize_and_replace_user_memories, user, type_)

def query_memory_for_game(prompt, game_id, top_k=5):
    try:
        # Step 1: Query only using game_id
        results = collection.query(
            query_texts=[prompt],
            n_results=top_k *3,  # Fetch extra to allow filtering
            where={"game_id": game_id}
        )
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        # Step 2: Filter to allowed users
        allowed_users = {"GameMonitor", "RecapEngine"}
        filtered = [
            (doc, meta)
            for doc, meta in zip(docs, metas)
            if meta.get("user") in allowed_users and meta.get("game_id") == game_id
        ]
        # Step 3: Sort by timestamp (newest first)
        filtered.sort(key=lambda x: x[1].get("timestamp", ""), reverse=True)
        return filtered[:top_k]
    except Exception as e:
        log_error(f"[Game Memory Query ERROR] {e}")
        return []

def query_memory_for_askai(prompt, user, top_k_user=4, top_k_global=2):
    return query_memory_relevant(prompt, user=user, top_k_user=top_k_user, top_k_global=top_k_global)

def query_memory_for_type(prompt, type_, user, game_id=None):
    if type_ in ["game", "recap"]:
        return query_memory_for_game(prompt, game_id)
    return query_memory_for_askai(prompt, user)

def delete_old_game_memories(days_old=0, types_to_delete=("game", "game_event", "recap","Game")):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
    results = collection.get(include=["metadatas"])
    to_delete = []
    for doc_id, meta in zip(results["ids"], results["metadatas"]):
        memory_type = meta.get("type")
        timestamp_str = meta.get("timestamp")
        if memory_type in types_to_delete and timestamp_str:
            try:
                entry_time = datetime.fromisoformat(timestamp_str)
                if entry_time < cutoff:
                    to_delete.append(doc_id)
            except Exception as e:
                log_error(f"[Memory Cleanup] Failed to parse timestamp: {e}")
    if to_delete:
        collection.delete(ids=to_delete)
        log_event(f"🧹 Deleted {len(to_delete)} old memory entries: {types_to_delete}")
    else:
        log_event("🧹 No old memories found for deletion.")
