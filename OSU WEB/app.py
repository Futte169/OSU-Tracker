from flask import Flask, render_template, request, session, redirect, url_for
import json
import os

app = Flask(__name__)
# Secret key er påkrævet for at bruge session (sprogvalg)
app.secret_key = "osu_specialist_bank_key_123" 

# Dynamisk sti så den virker både lokalt og på Render
basedir = os.path.abspath(os.path.dirname(__file__))

# --- OVERSÆTTELSES LOGIK ---
def load_translations():
    path = os.path.join(basedir, 'translations.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"FEJL: Kunne ikke læse translations.json: {e}")
    return {
        "da": {"Vores Proces": "Vores Proces"},
        "en": {"Vores Proces": "Our Process"}
    }

translations = load_translations()

@app.context_processor
def inject_translate():
    """Gør t(key) funktionen tilgængelig i alle HTML skabeloner via {{ t('nøgle') }}"""
    def t(key):
        lang = session.get('lang', 'da')
        return translations.get(lang, translations.get('da', {})).get(key, key)
    return dict(t=t)

@app.route('/set_lang/<lang>')
def set_lang(lang):
    """Skifter sprog og sender brugeren tilbage til hvor de kom fra"""
    session['lang'] = lang
    return redirect(request.referrer or url_for('home'))

# --- DATA LOGIK ---
def load_combined_data():
    """Henter data fra begge filer og sikrer unikke scores i hver kategori."""
    combined_leaderboards = {}
    combined_stats = {}
    data_files = ['leaderboard.json', 'specialist_leaderboard.json']
    
    for filename in data_files:
        path = os.path.join(basedir, filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Håndterer både gamle og nye JSON formater
                    current_lboards = data.get("leaderboards", data) if isinstance(data, dict) else {}
                    current_stats = data.get("stats", {}) if isinstance(data, dict) else {}

                    for cat, scores in current_lboards.items():
                        if cat not in combined_leaderboards:
                            combined_leaderboards[cat] = []
                        
                        existing_ids = {f"{s.get('user')}_{s.get('beatmap_id')}_{s.get('pp')}" for s in combined_leaderboards[cat]}
                        
                        for s in scores:
                            score_id = f"{s.get('user')}_{s.get('beatmap_id')}_{s.get('pp')}"
                            if score_id not in existing_ids:
                                combined_leaderboards[cat].append(s)
                                existing_ids.add(score_id)
                    
                    combined_stats.update(current_stats)
            except Exception as e:
                print(f"FEJL: Kunne ikke læse {filename}: {e}")
    
    # Sortér hver kategori efter PP
    for cat in combined_leaderboards:
        combined_leaderboards[cat] = sorted(combined_leaderboards[cat], key=lambda x: x.get('pp', 0), reverse=True)
        
    return combined_leaderboards, combined_stats

# --- FORSIDE ---
@app.route('/')
def home():
    all_leaderboards, _ = load_combined_data()
    all_players = set()
    unique_scores = {}
    recent_activity = []

    for mod_cat, scores in all_leaderboards.items():
        # Tag de 3 nyeste fra hver kategori til loggen
        cat_recent = scores[:3] 
        for s in cat_recent:
            if s.get('user'):
                r_meta = s.copy()
                r_meta['category'] = mod_cat
                recent_activity.append(r_meta)

        for s in scores:
            user = s.get('user')
            b_id = s.get('beatmap_id')
            pp_val = s.get('pp')
            if user and b_id:
                all_players.add(user)
                score_key = f"{user}_{b_id}_{pp_val}"
                if score_key not in unique_scores:
                    s_meta = s.copy()
                    s_meta['category'] = mod_cat
                    unique_scores[score_key] = s_meta

    sorted_unique_scores = sorted(unique_scores.values(), key=lambda x: x.get('pp', 0), reverse=True)
    overall_top_scores = sorted_unique_scores[:10]
    # Sortér aktivitet efter PP (som en pseudo-indikator for relevans)
    recent_activity = sorted(recent_activity, key=lambda x: x.get('pp', 0), reverse=True)[:8]

    return render_template(
        'home.html', 
        player_count=len(all_players), 
        score_count=len(unique_scores),
        top_scores=overall_top_scores,
        recent_scores=recent_activity,
        all_players=sorted(list(all_players))
    )

# --- LEADERBOARD SIDE ---
@app.route('/leaderboard/<mod_filter>')
def index(mod_filter="OVERALL"):
    mod_filter = mod_filter.upper()
    all_leaderboards, all_stats = load_combined_data()
    
    all_player_names = set()
    for cat in all_leaderboards.values():
        for s in cat:
            if s.get('user'):
                all_player_names.add(s['user'])
    
    scores = all_leaderboards.get(mod_filter, [])
    stats = all_stats.get(mod_filter, [])
    search_query = request.args.get('q', '').strip().lower()
    
    if search_query:
        filtered_scores = [s for s in scores if search_query in s.get('user', '').lower()]
    else:
        filtered_scores = scores[:100]
    
    return render_template(
        'index.html', 
        scores=filtered_scores, 
        stats=stats, 
        current_mod=mod_filter,
        search_query=search_query,
        all_players=sorted(list(all_player_names))
    )

# --- SPILLER PROFIL SIDE ---
@app.route('/player/<username>')
def player_profile(username):
    all_leaderboards, _ = load_combined_data()
    unique_player_scores = []
    seen_combinations = set()
    
    for mod_cat, scores in all_leaderboards.items():
        if mod_cat.upper() == 'OVERALL':
            continue 
            
        for index, s in enumerate(scores):
            current_user = s.get('user') or s.get('username') or ""
            if current_user.lower() == username.lower():
                score_id = f"{s.get('beatmap_id')}_{s.get('pp')}_{mod_cat}"
                if score_id not in seen_combinations:
                    s_meta = s.copy()
                    s_meta['category'] = mod_cat
                    s_meta['global_rank'] = index + 1
                    unique_player_scores.append(s_meta)
                    seen_combinations.add(score_id)

    player_scores = sorted(unique_player_scores, key=lambda x: x.get('pp', 0), reverse=True)
    return render_template('player.html', username=username, scores=player_scores)

# --- PROCES SIDE ---
@app.route('/process')
def process():
    return render_template('process.html')

if __name__ == '__main__':
    # Debug mode er god til lokal udvikling
    app.run(debug=True, host='0.0.0.0', port=5001)