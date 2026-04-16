import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
STATE_FILE = "combined_state.json"
ET = ZoneInfo("America/New_York")
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"

# 🔧 PUT YOUR REAL EMOJIS HERE
TEAM_EMOJIS = {
    "Los Angeles Angels": "<:angels:YOUR_ID>",
    "Texas Rangers": "<:rangers:YOUR_ID>",
    "Seattle Mariners": "<:mariners:YOUR_ID>",
    "Toronto Blue Jays": "<:bluejays:YOUR_ID>",
    "Arizona Diamondbacks": "<:dbacks:YOUR_ID>",
    "Chicago White Sox": "<:whitesox:YOUR_ID>",
    "Athletics": "<:athletics:YOUR_ID>",
    # add rest as needed
}

STAR_PLAYERS = {
    "Aaron Judge", "Shohei Ohtani", "Juan Soto", "Mookie Betts",
    "Ronald Acuña Jr.", "Bobby Witt Jr.", "Yordan Alvarez",
    "Fernando Tatis Jr.", "Freddie Freeman", "Corey Seager"
}

def team_label(team):
    return f"{TEAM_EMOJIS.get(team, '⚾')} {team}"

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def send(msg):
    requests.post(WEBHOOK_URL, json={"content": msg}, timeout=20)

def is_pregame(dt_iso):
    if not dt_iso:
        return True
    return datetime.now(ET) < datetime.fromisoformat(dt_iso)

def extract_lineup(team_data):
    players = team_data.get("players", {})
    order = team_data.get("battingOrder", [])
    return [
        players.get(f"ID{x}", {}).get("person", {}).get("fullName", "Unknown")
        for x in order
    ]

def get_games(date):
    r = requests.get(MLB_SCHEDULE_URL, params={
        "sportId": 1,
        "date": date.strftime("%Y-%m-%d"),
        "hydrate": "probablePitcher"
    })
    data = r.json()

    games = {}

    for d in data.get("dates", []):
        for g in d.get("games", []):
            pk = str(g["gamePk"])

            game_dt = datetime.fromisoformat(
                g["gameDate"].replace("Z", "+00:00")
            ).astimezone(ET)

            key = f"{g['teams']['away']['team']['name']} @ {g['teams']['home']['team']['name']} | {pk}"

            # get lineups
            try:
                box = requests.get(
                    f"https://statsapi.mlb.com/api/v1/game/{pk}/boxscore"
                ).json()
                away_lu = extract_lineup(box["teams"]["away"])
                home_lu = extract_lineup(box["teams"]["home"])
            except:
                away_lu, home_lu = [], []

            games[key] = {
                "away_team": g["teams"]["away"]["team"]["name"],
                "home_team": g["teams"]["home"]["team"]["name"],
                "away_pitcher": g["teams"]["away"].get("probablePitcher", {}).get("fullName", "TBD"),
                "home_pitcher": g["teams"]["home"].get("probablePitcher", {}).get("fullName", "TBD"),
                "away_lineup": away_lu,
                "home_lineup": home_lu,
                "game_time": game_dt.strftime("%I:%M %p ET"),
                "game_iso": game_dt.isoformat()
            }

    return games

# 🔥 PITCHER FIX (EMOJIS WORK HERE NOW)
def pitcher_changes(old, new):
    out = []

    for side in ["away", "home"]:
        ot = old.get(f"{side}_pitcher")
        nt = new.get(f"{side}_pitcher")
        team = team_label(new[f"{side}_team"])

        if ot != nt:
            if ot == "TBD":
                out.append(f"🆕 {team}: {nt}")
            else:
                out.append(f"🔄 {team}: {ot} → {nt}")

    return out

# 🔥 LINEUP LOGIC
def lineup_changes(old, new):
    labels, changes, stars = set(), [], []

    if not old and new:
        labels.add("LINEUP POSTED")
        for i, p in enumerate(new):
            if p in STAR_PLAYERS:
                stars.append(f"⭐ {p} at {i+1}")
        return labels, changes, stars, True

    old_pos = {p: i for i, p in enumerate(old)}
    new_pos = {p: i for i, p in enumerate(new)}

    for i in range(max(len(old), len(new))):
        o = old[i] if i < len(old) else None
        n = new[i] if i < len(new) else None

        if o and n and o != n and o not in new_pos and n not in old_pos:
            changes.append(f"🔄 {n} replaces {o} at {i+1}")
            labels.add("LINEUP SWITCH")

    for p in new:
        if p in old_pos and old_pos[p] != new_pos[p]:
            dir = "📈" if new_pos[p] < old_pos[p] else "📉"
            changes.append(f"{dir} {p} {old_pos[p]+1}→{new_pos[p]+1}")
            labels.add("LINEUP REARRANGED")

            if p in STAR_PLAYERS:
                stars.append(f"{dir} ⭐ {p}")

    for p in new:
        if p not in old_pos:
            changes.append(f"➕ {p}")
            labels.add("LINEUP SWITCH")

    for p in old:
        if p not in new_pos:
            changes.append(f"❌ {p}")
            labels.add("LINEUP SWITCH")

    return labels, changes, stars, False

def build(old, new):
    if not is_pregame(new["game_iso"]):
        return None

    labels, sections, stars = [], [], []

    pc = pitcher_changes(old, new)
    if pc:
        labels.append("PITCHER CHANGE")
        sections.append("**PITCHERS**\n" + "\n".join(pc))

    for side in ["away", "home"]:
        l, c, s, posted = lineup_changes(
            old.get(f"{side}_lineup", []),
            new[f"{side}_lineup"]
        )

        labels += list(l)
        stars += s

        if posted:
            sections.append(f"**{team_label(new[f'{side}_team'])} LINEUP POSTED**")
        elif c:
            sections.append(
                f"**{team_label(new[f'{side}_team'])}**\n" +
                "\n".join(c)
            )

    if stars:
        labels.append("STAR PLAYER ALERT")
        sections.append("**⭐ STAR PLAYER ALERT**\n" + "\n".join(stars))

    if not labels:
        return None

    labels = list(dict.fromkeys(labels))

    return (
        f"🚨 **{' + '.join(labels)}**\n\n"
        f"**{team_label(new['away_team'])} @ {team_label(new['home_team'])}**\n"
        f"First pitch: {new['game_time']}\n\n"
        + "\n\n".join(sections)
        + "\n\n🔥 DRIZZPLAYS"
    )

def run():
    state = load_state()
    today = datetime.now(ET).date()

    new_games = get_games(today)
    old_games = state.get(str(today), {})

    for k, g in new_games.items():
        alert = build(old_games.get(k, {}), g)
        if alert:
            send(alert)

    state[str(today)] = new_games
    save_state(state)

if __name__ == "__main__":
    run()
