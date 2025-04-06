# utils/game_utils.py
import os
import json
import requests

ITEM_CACHE_FILE = "cached_item_prices.json"
ITEM_PRICES = None

def load_item_prices():
    url = "https://ddragon.leagueoflegends.com/cdn/15.7.1/data/en_US/item.json"
    import requests
    response = requests.get(url)
    data = response.json()
    prices = {int(k): v["gold"]["total"] for k, v in data["data"].items()}
    with open(ITEM_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(prices, f)
    return prices

def load_item_prices_from_cache():
    try:
        if os.path.exists(ITEM_CACHE_FILE):
            with open(ITEM_CACHE_FILE, "r", encoding="utf-8") as f:
                return {int(k): v for k, v in json.load(f).items()}
    except Exception as e:
        print("[ItemCache] Failed to load item cache:", e)
    return None

def ensure_item_prices_loaded():
    global ITEM_PRICES
    if ITEM_PRICES is None:
        ITEM_PRICES = load_item_prices_from_cache() or load_item_prices()
    return ITEM_PRICES

def estimate_team_gold(players):
    prices = ensure_item_prices_loaded()
    team_gold = {}
    for player in players:
        team = player.get("team", "UNKNOWN")
        items = player.get("items", [])
        total = 0
        for item in items:
            item_id = item.get("itemID")
            real_price = prices.get(item_id, 0)
            total += real_price * item.get("count", 1)
        team_gold[team] = team_gold.get(team, 0) + total
    return team_gold
