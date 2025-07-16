# memory_manager.py

from chromadb import PersistentClient  # ✅ Use PersistentClient instead of Client
from chromadb.config import Settings
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
from openai import OpenAI
import uuid
import os
from datetime import datetime, timezone

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

def query_memory(query_text, game_id=None, type_filter=None, n_results=5):
    embedding = generate_embedding(query_text)
    filters = {}
    if game_id:
        filters["game_id"] = game_id
    if type_filter:
        filters["type"] = type_filter

    results = collection.query(
        query_embeddings=[embedding],
        n_results=n_results,
        where=filters if filters else None
    )
    return {
        "documents": results.get("documents", []),
        "metadatas": results.get("metadatas", [])
    }

def query_memory_relevant(prompt, user=None, top_k_user=2, top_k_global=1):
    try:
        results = []
        # 🧠 1. Try user-specific results
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
            results.extend(zip(user_docs, user_metas))
        # 🧠 2. Global results (initial)
        global_results = collection.query(
            query_texts=[prompt],
            n_results=top_k_global,
            where=None
        )
        global_docs = global_results.get("documents", [[]])[0]
        global_metas = global_results.get("metadatas", [[]])[0]
        results.extend(zip(global_docs, global_metas))
        # 🧠 3. Fallback: If no user results, get extra from global
        if user and not user_docs:
            fallback_results = collection.query(
                query_texts=[prompt],
                n_results=top_k_user,  # same as original user quota
                where=None
            )
            fallback_docs = fallback_results.get("documents", [[]])[0]
            fallback_metas = fallback_results.get("metadatas", [[]])[0]
            results.extend(zip(fallback_docs, fallback_metas))
        return results
    except Exception as e:
        log_error(f"[Memory Query ERROR] {e}")
        return []




#def get_relevant_memories(prompt, n=10):
 #   try:
  #      query_embedding = generate_embedding(prompt)
   #     results = collection.query(
    #        query_embeddings=[query_embedding],
     #       n_results=n,
     ##   )
     #   docs = results["documents"][0]
     #   metas = results["metadatas"][0]
     #   # Sort by timestamp descending
     #   sorted_pairs = sorted(
     #       zip(docs, metas),
     #       key=lambda x: x[1].get("timestamp", ""),
     #       reverse=True
#        )
#        return sorted_pairs[:5]  # Top 5 most recent relevant
 #   except Exception as e:
  ##      log_error(f"[Memory Query ERROR] {e}")
    #    return []
    
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

def should_store_memory(prompt):
    try:
        check_prompt = (
            "You are a memory manager. Determine if the following user message is important enough to store for later reference.\n"
            "Reply only with true or false.\n\n"
            f"User: {prompt}\n\nShould this be remembered?"
        )
        result = openai_client.chat.completions.create(
            model="gpt-4o",  #gpt-4o  ,gpt-3.5-turbo
            messages=[{"role": "user", "content": check_prompt}],
            max_tokens=25,
            temperature=0
        )
        answer = result.choices[0].message.content.strip().lower()
        log_event(f"[Memory Decision] Prompt: {prompt} → Store: {answer}")
        return "true" in answer
    except Exception as e:
        log_error(f"[should_store_memory ERROR] {e}")
        return False

def summarize_interaction(prompt):
    try:
        summary_prompt = (
            "You are a memory system. Summarize this user input clearly and extract facts when possible. Focus on identity, personal facts, or recurring themes.\n"
            "Be specific.\n\n"
            f"User: {prompt}\n\nSummary:"
        )
        result = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": summary_prompt}],
            max_tokens=100,
            temperature=0.5
        )
        summary = result.choices[0].message.content.strip()
        log_event(f"[Memory Summary] From: {prompt} → Summary: {summary}")
        return summary
    except Exception as e:
        log_error(f"[summarize_interaction ERROR] {e}")
        return prompt[:100]  # fallback: return trimmed user message
    
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

