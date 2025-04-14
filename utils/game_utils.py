# utils/game_utils.py
import os
import json
import requests
from collections import Counter

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

def estimate_player_item_gold(player, prices):
    total = 0
    for item in player.get("items", []):
        item_id = item.get("itemID")
        total += prices.get(item_id, 0) * item.get("count", 1)
    return total

def infer_missing_roles(formatted_players):
    # Count current roles
    role_counts = Counter(p["role"] for p in formatted_players if p["role"] != "unknown")
    # Roles that have <2 players
    all_roles = ["top", "jungle", "middle", "bottom", "utility"]
    missing_roles = [role for role in all_roles if role_counts[role] < 2]
    # Assign missing roles to unknowns
    for player in formatted_players:
        if player["role"] == "unknown" and missing_roles:
            inferred = missing_roles.pop(0)
            player["role"] = inferred
            print(f"🧠 Inferred role for {player['name']}: {inferred}")
    return formatted_players

def power_score(player, enemy_laner=None, team_data=None, game_time_minutes=1, verbose=False):
    item_prices = ensure_item_prices_loaded()
    debug_log = []
    name = player.get("summonerName", "UNKNOWN")
    # Constants
    MAX_LEVEL_SCORE = 90
    MAX_ITEM_SCORE = 90
    LEVEL_LEAD_SCORE_PER_LEVEL = 5
    LEGENDARY_BONUS = 5
    DEATH_PENALTY_SCORE = 2
    CS_MAX_SCORE = 3
    VISION_MAX_SCORE = 2
    MAX_CS_PER_MIN = 10
    MAX_VISION_SCORE_PER_MIN = 4
    score = 0
    # 🧬 Level
    level = player.get("level", 1)
    level_score = (level / 18) * MAX_LEVEL_SCORE
    score += level_score
    debug_log.append(f"[{name}] Level {level} → +{level_score:.1f}")
    # 💰 Item score
    item_gold = estimate_player_item_gold(player, item_prices)
    full_build_gold = 15000
    item_score = min(item_gold / full_build_gold, 1) * MAX_ITEM_SCORE
    score += item_score
    debug_log.append(f"[{name}] Items {item_gold}g → +{item_score:.1f}")
    # 📈 Lane dominance
    if enemy_laner:
        level_lead = max(player.get("level", 1) - enemy_laner.get("level", 1), 0)
        lane_score = min(level_lead, 3) * LEVEL_LEAD_SCORE_PER_LEVEL
        score += lane_score
        debug_log.append(f"[{name}] Lane level lead {level_lead} → +{lane_score:.1f}")
    # 🔥 Kill streak
    deaths = player["scores"].get("deaths", 0)
    kills = player["scores"].get("kills", 0)
    assists = player["scores"].get("assists", 0)
    kill_streak = player.get("killStreak", 0)
    kda_ratio = (kills + assists) / max(deaths, 1)
    kda_score = round(kda_ratio, 1)
    score += kda_score
    if kill_streak >= 8:
        score += LEGENDARY_BONUS
        debug_log.append(f"[{name}] KDA ({kills}+{assists})/{deaths} → +{kda_score} + Legendary Bonus → +{LEGENDARY_BONUS}")
    elif kill_streak > 0:
        debug_log.append(f"[{name}] KDA ({kills}+{assists})/{deaths} → +{kda_score}")
    # 💀 Death penalty
    death_penalty = min(deaths * DEATH_PENALTY_SCORE, 20)
    score -= death_penalty
    debug_log.append(f"[{name}] Deaths {deaths} → -{death_penalty:.1f}")
    # 🐸 CS score
    creep_score = player["scores"].get("creepScore", 0)
    cs_per_min = creep_score / max(game_time_minutes, 1)
    cs_score = min(cs_per_min / MAX_CS_PER_MIN, 1) * CS_MAX_SCORE
    score += cs_score
    debug_log.append(f"[{name}] CS/min {cs_per_min:.1f} → +{cs_score:.1f}")
    # 👁️ Vision score
    vision_score = player["scores"].get("wardScore", 0)
    vision_per_min = vision_score / max(game_time_minutes, 1)
    vision_bonus = min(vision_per_min / MAX_VISION_SCORE_PER_MIN, 1) * VISION_MAX_SCORE
    score += vision_bonus
    debug_log.append(f"[{name}] Vision/min {vision_per_min:.1f} → +{vision_bonus:.1f}")
    # 🏆 Team globals
    if team_data:
        td = team_data  # Just a shortcut for easier typing
        dragons = td.get("dragons", 0)
        dragon_score = dragons * 3
        score += dragon_score
        if dragons:
            debug_log.append(f"[{name}] Dragons taken {dragons} → +{dragon_score}")
        if td.get("dragon_soul", False):
            score += 10
            debug_log.append(f"[{name}] Dragon Soul → +10")
        if td.get("elder_dragon", False):
            score += 15
            debug_log.append(f"[{name}] Elder Dragon → +15")
        if td.get("baron_buff", False):
            score += 15
            debug_log.append(f"[{name}] Baron Buff → +15")
        heralds = td.get("heralds", 0)
        if heralds:
            herald_score = heralds * 5
            score += herald_score
            debug_log.append(f"[{name}] Heralds {heralds} → +{herald_score}")
        if td.get("atakan_buff", False):
            score += 10
            debug_log.append(f"[{name}] Atakan Buff → +10")
        else:
            atakan_temp = td.get("atakan_temp", 0)
            atakan_score = atakan_temp * 5
            score += atakan_score
            if atakan_temp:
                debug_log.append(f"[{name}] Atakan (temp) {atakan_temp} → +{atakan_score}")
        void_grubs = td.get("void_grubs", 0)
        vg_score = void_grubs
        if void_grubs >= 4:
            vg_score += 3
        if void_grubs == 6:
            vg_score += 3
        score += vg_score
        if void_grubs:
            debug_log.append(f"[{name}] Void Grubs {void_grubs} → +{vg_score}")
        feats = td.get("feats_of_strength", 0) * 5
        score += feats
        if feats:
            debug_log.append(f"[{name}] Feats of Strength → +{feats}")
        towers = td.get("towers", {})
        t_score = towers.get("tier1", 0)*2 + towers.get("tier2", 0)*3 + towers.get("tier3", 0)*4
        score += t_score
        if t_score:
            debug_log.append(f"[{name}] Towers → +{t_score}")
        inhibs = td.get("inhibitors_down", 0)
        inhib_score = inhibs * 10
        score += inhib_score
        if inhibs:
            debug_log.append(f"[{name}] Inhibitors → +{inhib_score}")
    if verbose:
        print(f"🔍 Power Score Breakdown for {name}:")
        for line in debug_log:
            print("  ", line)
        print(f"🎯 Total Score: {round(score, 1)}\n")
    return round(score, 1)
