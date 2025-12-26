import requests
import time
import json
import os

# ==============================
# CONFIG
# ==============================
CLIENT_ID = "47042"
CLIENT_SECRET = "2PPi45GCXx547ScpskA7MCXiuQ9JgT78GAaKsp8v"
MODE = "osu"

START_PAGE = 1   
MAX_PAGES = 1000  
PAGES_PER_RUN = 1000 
SLEEP_TIME = 0.1  # Sat en smule op for at undgå API rate limits ved mange kald

PROGRESS_FILE = 'specialist_progress.json'
DATA_FILE = 'specialist_leaderboard.json'

# Målkategorier
TARGET_CATS = ["EZ", "FL", "EZFL", "EZDT", "EZHD", "FLDT", "EZHDDT", "EZFLDT"]

# ==============================
# AUTH & HELPERS
# ==============================
def get_access_token():
    url = "https://osu.ppy.sh/oauth/token"
    data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "client_credentials", "scope": "public"}
    return requests.post(url, json=data).json()["access_token"]

def get_mod_list(score):
    return [m["acronym"] if isinstance(m, dict) else str(m) for m in score.get("mods", [])]

def get_specialist_category(score):
    mods = set(get_mod_list(score))
    # Konverter NC til DT internt for nemmere matching
    if "NC" in mods: 
        mods.remove("NC")
        mods.add("DT")
    
    # Sorteret tjek for præcise matches
    if mods == {"EZ"}: return "EZ"
    if mods == {"FL"}: return "FL"
    if mods == {"EZ", "FL"}: return "EZFL"
    if mods == {"EZ", "DT"}: return "EZDT"
    if mods == {"EZ", "HD"}: return "EZHD"
    if mods == {"FL", "DT"}: return "FLDT"
    if mods == {"EZ", "HD", "DT"}: return "EZHDDT"
    if mods == {"EZ", "FL", "DT"}: return "EZFLDT"
    return None

# ==============================
# LOAD / SAVE DATA
# ==============================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                # Håndterer både gammelt og nyt format
                return data.get("leaderboards", data) if isinstance(data, dict) and "leaderboards" in data else data
            except:
                pass
    return {cat: [] for cat in TARGET_CATS}

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f).get('next_page', START_PAGE)
    return START_PAGE

# ==============================
# MAIN SCANNER
# ==============================
token = get_access_token()
headers = {"Authorization": f"Bearer {token}"}
leaderboards = load_data()
current_page = load_progress()

print(f"--- Specialist Scanner startede ---")
print(f"Genoptager fra side {current_page}...")

end_page = current_page + PAGES_PER_RUN

try:
    for p in range(current_page, end_page):
        if p > MAX_PAGES:
            print("Mål nået!")
            break
            
        print(f"Scanner side {p}...")
        url_rank = f"https://osu.ppy.sh/api/v2/rankings/{MODE}/performance"
        
        r = requests.get(url_rank, headers=headers, params={"page": p})
        if r.status_code != 200: 
            print(f"Fejl ved hentning af ranking side {p}")
            break
            
        players = r.json().get('ranking', [])
        
        for player in players:
            user_id = player['user']['id']
            username = player['user']['username']
            country_code = player['user']['country_code']
            
            # Henter top 100 scores for hver spiller
            url_best = f"https://osu.ppy.sh/api/v2/users/{user_id}/scores/best"
            score_r = requests.get(url_best, headers=headers, params={"mode": MODE, "limit": 100})
            
            if score_r.status_code == 429: # Rate limit
                print("Rate limited! Venter 10 sekunder...")
                time.sleep(10)
                continue
            if score_r.status_code != 200: continue
            
            scores = score_r.json()
            for s in scores:
                cat = get_specialist_category(s)
                if cat:
                    new_score = {
                        "pp": round(s.get("pp", 0), 2) if s.get("pp") else 0,
                        "user": username,
                        "user_id": user_id,
                        "country": country_code,
                        "map": f"{s['beatmapset']['title']} [{s['beatmap']['version']}]",
                        "beatmap_id": s['beatmap']['id'],
                        "beatmapset_id": s['beatmapset']['id'], # Tilføjet til korrekt cover-billede
                        "mods": "".join(get_mod_list(s)),
                        "acc": round(s["accuracy"] * 100, 2)
                    }
                    leaderboards[cat].append(new_score)
            
            time.sleep(SLEEP_TIME)
            
        # --- RENSING OG STATISTIK EFTER HVER SIDE ---
        current_stats = {}
        for cat in TARGET_CATS:
            if cat not in leaderboards: continue
            
            # Sorter alle scores efter PP
            all_sorted = sorted(leaderboards[cat], key=lambda x: x["pp"], reverse=True)
            
            # Fjern dubletter (samme spiller på samme map)
            unique_scores = {}
            for sc in all_sorted:
                key = f"{sc['user_id']}_{sc['beatmap_id']}"
                if key not in unique_scores:
                    unique_scores[key] = sc
            
            # Tag top 100
            final_list = sorted(unique_scores.values(), key=lambda x: x["pp"], reverse=True)[:100]
            leaderboards[cat] = final_list

            # Beregn top 3 dominans
            player_counts = {}
            for sc in final_list:
                name = sc['user']
                player_counts[name] = player_counts.get(name, 0) + 1
            
            current_stats[cat] = sorted(player_counts.items(), key=lambda x: x[1], reverse=True)[:3]

        # --- GEM DATA LØBENDE ---
        output_data = {
            "leaderboards": leaderboards,
            "stats": current_stats
        }

        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({'next_page': p + 1}, f)

except Exception as e:
    print(f"Kritisk fejl: {e}")

print(f"Færdig! Scanneren har gemt fremdriften.")