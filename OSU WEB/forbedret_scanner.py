import requests
import time
import json
import os

# ==============================
# CONFIG
# ==============================
CLIENT_ID = "47037"
CLIENT_SECRET = "DeClDWWlyMr21eXmWtNHQwMiGcsUC8digo2sQjeY"
MODE = "osu"
TOP_PLAYERS_TO_SCAN = 1000 
SLEEP = 0.1 

PROGRESS_FILE = 'leaderboard_progress.json'
DATA_FILE = 'leaderboard.json'

# ==============================
# AUTH & HELPERS
# ==============================
def get_access_token():
    url = "https://osu.ppy.sh/oauth/token"
    data = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "client_credentials", "scope": "public"}
    try:
        response = requests.post(url, json=data).json()
        return response["access_token"]
    except Exception as e:
        print(f"Kunne ikke hente token: {e}")
        return None

def get_mod_list(score):
    return [m["acronym"] if isinstance(m, dict) else str(m) for m in score.get("mods", [])]

def get_category(score):
    # Hent mods som et set for nem sammenligning
    mods = set(get_mod_list(score))
    
    # --- VIGTIG RETTELSE: Normaliser NC til DT ---
    # Hvis NC findes, fjerner vi det og lader som om det er DT i logikken herunder
    if "NC" in mods:
        mods.remove("NC")
        mods.add("DT")
    
    # Nu tjekker vi for kombinationer (NC tæller nu som DT her)
    if not mods: return "NM"
    if mods == {"HR"}: return "HR"
    if mods == {"HD"}: return "HD"
    if mods == {"DT"}: return "DT"
    if mods == {"EZ"}: return "EZ"
    if mods == {"FL"}: return "FL"
    if mods == {"HD", "HR"}: return "HDHR"
    if mods == {"HD", "DT"}: return "HDDT"
    if mods == {"HR", "DT"}: return "HRDT"
    if mods == {"HD", "DT", "HR"}: return "HDDTHR"
    if mods == {"HD", "DT", "HR", "FL"}: return "HDDTHRFL"
    
    return None

# ==============================
# LOAD / SAVE LOGIK
# ==============================
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                raw = json.load(f)
                return raw.get("leaderboards", raw) if isinstance(raw, dict) and "leaderboards" in raw else raw
            except:
                pass
    return { "OVERALL": [], "NM": [], "HD": [], "HR": [], "DT": [], "HDHR": [], 
             "HDDT": [], "HRDT": [], "HDDTHR": [], "HDDTHRFL": [], "EZ": [], "FL": [] }

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            try:
                return json.load(f).get('next_page', 1)
            except:
                pass
    return 1

# ==============================
# MAIN SCAN
# ==============================
token = get_access_token()
if not token: exit()

HEADERS = {"Authorization": f"Bearer {token}"}
leaderboards = load_data()
start_page = load_progress()
max_pages = TOP_PLAYERS_TO_SCAN // 50

print(f"--- Scanner startede (Nu med Beatmapset ID & NC-fix) ---")

try:
    for p in range(start_page, max_pages + 1):
        print(f"\n[Side {p}/{max_pages}] Henter spillere...")
        url_rank = f"https://osu.ppy.sh/api/v2/rankings/{MODE}/performance"
        
        r = requests.get(url_rank, headers=HEADERS, params={"page": p})
        if r.status_code != 200: break
            
        players = r.json().get("ranking", [])
        
        for i, player in enumerate(players):
            user_id = player["user"]["id"]
            username = player["user"]["username"]
            country_code = player["user"]["country_code"]
            
            if i % 10 == 0: print(f"  Scanning {i+1}/50: {username}")

            url_best = f"https://osu.ppy.sh/api/v2/users/{user_id}/scores/best"
            score_r = requests.get(url_best, headers=HEADERS, params={"mode": MODE, "limit": 100})
            
            if score_r.status_code == 200:
                scores = score_r.json()
                for s in scores:
                    pp_value = s.get("pp")
                    if pp_value:
                        acc_value = round(s.get("accuracy", 0) * 100, 2)
                        
                        # Vi gemmer den originale mod-liste til visning (beholder NC)
                        original_mods = get_mod_list(s)
                        
                        score_data = {
                            "pp": round(pp_value, 2),
                            "user": username,
                            "user_id": user_id,
                            "country": country_code,
                            "map": f"{s['beatmapset']['title']} [{s['beatmap']['version']}]",
                            "beatmap_id": s['beatmap']['id'],
                            "beatmapset_id": s['beatmapset']['id'],
                            "mods": "".join(original_mods), # Viser f.eks. HDNC
                            "acc": acc_value
                        }
                        
                        leaderboards["OVERALL"].append(score_data)
                        
                        # Finder kategorien (her lander HDNC i HDDT mappen)
                        cat = get_category(s)
                        if cat in leaderboards:
                            leaderboards[cat].append(score_data)
            time.sleep(SLEEP)

        # --- SMART RENSING OG STATISTIK ---
        stats = {}
        for cat in leaderboards:
            all_sorted = sorted(leaderboards[cat], key=lambda x: x["pp"], reverse=True)
            unique_scores = {}
            for sc in all_sorted:
                key = f"{sc['user_id']}_{sc['beatmap_id']}"
                if key not in unique_scores: unique_scores[key] = sc
            
            final_list = sorted(unique_scores.values(), key=lambda x: x["pp"], reverse=True)[:100]
            leaderboards[cat] = final_list

            player_counts = {}
            for sc in final_list:
                name = sc['user']
                player_counts[name] = player_counts.get(name, 0) + 1
            
            stats[cat] = sorted(player_counts.items(), key=lambda x: x[1], reverse=True)[:3]

        output_data = {
            "leaderboards": leaderboards,
            "stats": stats
        }

        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({'next_page': p + 1}, f)
            
        print(f"Side {p} færdig. Data gemt.")

except Exception as e:
    print(f"Fejl: {e}")

print("\nFærdig!")