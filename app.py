#!/usr/bin/env python3
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import os, json, tempfile
from copy import deepcopy
from threading import Lock

app = Flask(__name__)
app.secret_key = "CHANGE_THIS_IN_PRODUCTION"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ----------------------------
# File paths
# ----------------------------
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TEAMS_FILE = os.path.join(DATA_DIR, "teams.json")
PLAYERS_FILE = os.path.join(DATA_DIR, "players.json")
SOLD_FILE = os.path.join(DATA_DIR, "sold.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

DEFAULT_IMAGE_URL = "https://playerimages-1.s3.us-east-1.amazonaws.com/defaultPlayer.jpg"
POLL_INTERVAL_MS = 500
DEFAULT_BASE_PRICE = 0

lock = Lock()

# ----------------------------
# Defaults
# ----------------------------
DEFAULT_USERS = [
    {"username": "auctioneer1", "password": "admin", "role": "auctioneer"},
    {"username": "bidder1", "password": "pass1", "role": "bidder", "team_name": "Chaitu Cheetahs"},
    {"username": "bidder2", "password": "pass2", "role": "bidder", "team_name": "Sai Warriors"}
]

DEFAULT_TEAMS = [
    {"team_name": "Chaitu Cheetahs", "purse": 10000, "default_purse": 10000, "players": [], "logos": [], "sponsors": []},
    {"team_name": "Sai Warriors", "purse": 10000, "default_purse": 10000, "players": [], "logos": [], "sponsors": []}
]

DEFAULT_PLAYERS = [
    {"id": 1, "name": "Srinu Dantuluri", "age": 45, "role": "Bowler",
     "base_price": 1000, "grade": "V", "image": "", "sold": False, "sold_to": "", "final_price": 0}
]
MAINTENANCE_MODE = True
DEFAULT_SOLD = []
DEFAULT_HISTORY = []
DEFAULT_STATE = {
    "current_player_index": -1,
    "auction_active": False,
    "current_bid": {"amount": None, "bidder": "", "team_name": ""},
    "last_bid_team": "",
    "sold_to": "",
    "current_bid_history": {}
}

# ----------------------------
# File utilities
# ----------------------------
def read_json(path, default):
    if not os.path.exists(path):
        write_json(path, default)
        return deepcopy(default)
    try:
        with open(path, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception:
        return deepcopy(default)

def write_json(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

# Ensure default files exist
read_json(USERS_FILE, DEFAULT_USERS)
read_json(TEAMS_FILE, DEFAULT_TEAMS)
read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
read_json(SOLD_FILE, DEFAULT_SOLD)
read_json(HISTORY_FILE, DEFAULT_HISTORY)
read_json(STATE_FILE, DEFAULT_STATE)

# ----------------------------
# Helper functions
# ----------------------------
def find_user(username):
    users = read_json(USERS_FILE, DEFAULT_USERS)
    return next((u for u in users if u.get("username") == username), None)

def find_team_by_name(name):
    teams = read_json(TEAMS_FILE, DEFAULT_TEAMS)
    return next((t for t in teams if t.get("team_name") == name), None)

def compute_min_increment(base_price):
    try:
        bp = int(base_price)
    except:
        bp = DEFAULT_BASE_PRICE
    inc = max(1, bp // 20)
    if inc >= 100:
        inc = (inc // 10) * 10
    return inc

# ----------------------------
# Auth & pages
# ----------------------------
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.before_request
def check_maintenance_mode():
    global MAINTENANCE_MODE
    # Only block bidder and viewer pages
    blocked_paths = ['/bidder', '/viewer']
    if MAINTENANCE_MODE and request.path in blocked_paths:
        return redirect(url_for('maintenance'))

@app.route('/maintenance')
def maintenance():
    video_urls = [
        "https://playerimages-1.s3.us-east-1.amazonaws.com/WhatsApp+Video+2025-11-17+at+12.15.49+AM.mp4",
        # add more S3 videos if needed
    ]
    return render_template("maintenance.html", video_urls=video_urls)

@app.route("/login", methods=["GET","POST"])
def login():
    error = ""
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        user = find_user(username)
        if user and user.get("password") == password:
            session["username"] = username
            session["role"] = user.get("role")
            session["team_name"] = user.get("team_name", "Team")
            return redirect(url_for(user.get("role","bidder")))
        error = "Invalid credentials"
    return render_template("login.html", error=error)

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/auctioneer")
def auctioneer():
    if session.get("role") != "auctioneer":
        return redirect(url_for("login"))
    return render_template("auctioneer.html", poll_interval_ms=POLL_INTERVAL_MS, default_image_url=DEFAULT_IMAGE_URL)

@app.route("/bidder")
def bidder():
    if session.get("role") != "bidder":
        return redirect(url_for("login"))
    return render_template("bidder.html", poll_interval_ms=POLL_INTERVAL_MS, default_image_url=DEFAULT_IMAGE_URL)

@app.route("/viewer")
def viewer():
    video_urls = [
        "https://playerimages-1.s3.us-east-1.amazonaws.com/WhatsApp+Video+2025-11-17+at+12.15.49+AM.mp4",
        "https://playerimages-1.s3.us-east-1.amazonaws.com/WhatsApp+Video+2025-11-17+at+12.15.49+AM.mp4"
        # add more URLs if needed
    ]
    return render_template("viewer.html", poll_interval_ms=POLL_INTERVAL_MS, default_image_url=DEFAULT_IMAGE_URL,video_urls=video_urls)

# ----------------------------
# APIs
# ----------------------------
@app.route("/api/players")
def api_players():
    players = read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
    available = [p for p in players if not p.get("sold", False)]
    return jsonify({"players": available})

@app.route("/api/auction/select", methods=["POST"])
def api_select_player():
    if session.get("role") != "auctioneer":
        return jsonify({"success": False, "error": "Unauthorized"})

    data = request.get_json()
    player_id = data.get("player_id")

    players = read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
    player = next((p for p in players if p["id"] == player_id and not p.get("sold", False)), None)

    if not player:
        return jsonify({"success": False, "error": "Player not found or already sold"})

    state = read_json(STATE_FILE, DEFAULT_STATE)

    state["current_player_index"] = next((i for i,p in enumerate(players) if p["id"]==player_id), -1)
    state["auction_active"] = True
    state["current_bid"] = {"amount": None, "bidder": "", "team_name": ""}
    state["last_bid_team"] = ""
    state["sold_to"] = ""

    # CLEAR previous history
    state["current_bid_history"] = {}

    write_json(STATE_FILE, state)
    return jsonify({"success": True, "current_player": player})

@app.route("/api/state")
def api_state():
    players = read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
    teams = read_json(TEAMS_FILE, DEFAULT_TEAMS)
    state = read_json(STATE_FILE, DEFAULT_STATE)

    idx = state.get("current_player_index", -1)
    current_player = players[idx] if 0 <= idx < len(players) else None
    highest_bid = state.get("current_bid", {}).get("amount") or ""

    bid_history = []
    if current_player:
        pid_key = str(current_player.get("id", ""))
        bid_history = state.get("current_bid_history", {}).get(pid_key, [])

    if not current_player:
        current_player = {"name":"Waiting for next player...","role":"---","age":"---",
                          "base_price":"---","image":DEFAULT_IMAGE_URL}
        highest_bid = "---"
        bid_history = []

    teams_view = []
    for t in teams:
        sold_players = [
            {"id":p["id"],"name":p["name"],"final_price":p["final_price"]}
            for p in players if p.get("sold_to") == t.get("team_name")
        ]
        t_copy = deepcopy(t)
        t_copy["players"] = sold_players
        teams_view.append(t_copy)

    return jsonify({
        "success": True,
        "state": {
            "current_player": current_player,
            "highest_bid": highest_bid,
            "teams": teams_view,
            "auction_active": state.get("auction_active", False),
            "min_increment": compute_min_increment(current_player.get("base_price", DEFAULT_BASE_PRICE)),
            "current_bid_history": state.get("current_bid_history", {}),
            "current_bid": state.get("current_bid"),
            "last_bid_team": state.get("last_bid_team", ""),
            "sold_to": state.get("sold_to", "")
        }
    })

# ----------------------------
# Bidding
# ----------------------------
@app.route("/api/bid", methods=["POST"])
def api_bid():
    if session.get("role") != "bidder":
        return jsonify({"success": False, "error": "Unauthorized"})

    data = request.get_json()
    player_id = data.get("player_id")

    try:
        bid_amount = int(data.get("bid_amount", 0))
    except:
        return jsonify({"success": False, "error": "Invalid bid amount"})

    state = read_json(STATE_FILE, DEFAULT_STATE)
    players = read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
    teams = read_json(TEAMS_FILE, DEFAULT_TEAMS)

    idx = state.get("current_player_index", -1)
    current_player = players[idx] if 0 <= idx < len(players) else None

    if not state.get("auction_active", False):
        return jsonify({"success": False, "error": "Auction not active"})

    if not current_player or current_player.get("id") != player_id:
        return jsonify({"success": False, "error": "Player mismatch"})

    # bidder's team
    user = find_user(session.get("username"))
    team = find_team_by_name(user.get("team_name"))

    if not team:
        return jsonify({"success": False, "error": "Team not found"})

    # ----- FIX: ALLOW base price as first bid -----
    current_amount = state.get("current_bid", {}).get("amount")

    if current_amount is None:
        min_required = current_player.get("base_price", 0)
    else:
        min_required = current_amount + compute_min_increment(current_player.get("base_price"))

    if bid_amount < min_required:
        return jsonify({"success": False, "error": f"Minimum bid {min_required}"})

    if team.get("purse",0) < bid_amount:
        return jsonify({"success": False, "error": "Insufficient purse"})

    # Update bid
    state["current_bid"] = {
        "amount": bid_amount,
        "bidder": session.get("username"),
        "team_name": team.get("team_name")
    }

    state["last_bid_team"] = team.get("team_name")

    # Store bid history
    pid_str = str(current_player.get("id"))

    if "current_bid_history" not in state:
        state["current_bid_history"] = {}

    state["current_bid_history"].setdefault(pid_str, [])
    state["current_bid_history"][pid_str].append({
        "bidder": session.get("username"),
        "team_name": team.get("team_name"),
        "amount": bid_amount
    })

    write_json(STATE_FILE, state)

    return jsonify({"success": True, "bid_by": team.get("team_name"), "amount": bid_amount})

# ----------------------------
# Sell Player
# ----------------------------
@app.route("/api/auction/sell", methods=["POST"])
def api_auction_sell():
    if session.get("role") != "auctioneer":
        return jsonify({"success": False, "error": "Unauthorized"})

    state = read_json(STATE_FILE, DEFAULT_STATE)
    players = read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
    teams = read_json(TEAMS_FILE, DEFAULT_TEAMS)

    idx = state.get("current_player_index", -1)
    if idx == -1:
        return jsonify({"success": False, "error": "No player selected"})

    player = players[idx]
    current_bid = state.get("current_bid", {})

    if not current_bid.get("amount"):
        return jsonify({"success": False, "error": "No bids placed yet"})

    # Apply sale
    player["sold"] = True
    player["sold_to"] = current_bid.get("team_name")
    player["final_price"] = current_bid.get("amount")

    sold_team_name = player["sold_to"]

    # Decrease purse
    for t in teams:
        if t.get("team_name") == sold_team_name:
            t["purse"] = max(0, t.get("purse", 0) - player["final_price"])
            break

    # Save sold record
    sold = read_json(SOLD_FILE, DEFAULT_SOLD)
    sold.append({
        "player": player,
        "team_name": sold_team_name,
        "final_price": player["final_price"]
    })
    write_json(SOLD_FILE, sold)

    # Save sale history
    history = read_json(HISTORY_FILE, DEFAULT_HISTORY)
    history.append({
        "action": "sell",
        "player_id": player["id"],
        "team": sold_team_name,
        "price": player["final_price"]
    })
    write_json(HISTORY_FILE, history)

    # DO NOT CLEAR anything except auction_active
    state["auction_active"] = False
    state["sold_to"] = sold_team_name

    write_json(STATE_FILE, state)
    write_json(PLAYERS_FILE, players)
    write_json(TEAMS_FILE, teams)

    return jsonify({
        "success": True,
        "player_sold": player,
        "sold_to": player["sold_to"],
        "final_price": player["final_price"]
    })


# ----------------------------
# Next Player (Pass)
# ----------------------------
@app.route("/api/auction/next", methods=["POST"])
def api_auction_next():
    if session.get("role") != "auctioneer":
        return jsonify({"success": False, "error": "Unauthorized"})

    state = read_json(STATE_FILE, DEFAULT_STATE)

    state["current_player_index"] = -1
    state["auction_active"] = False
    state["current_bid"] = {"amount": None, "bidder": "", "team_name": ""}
    state["sold_to"] = ""
    state["last_bid_team"] = ""

    # ----- FIX: CLEAR BID HISTORY -----
    state["current_bid_history"] = {}

    write_json(STATE_FILE, state)
    return jsonify({"success": True})

# ----------------------------
# Rollback
# ----------------------------
@app.route("/api/auction/rollback", methods=["POST"])
def api_auction_rollback():
    if session.get("role") != "auctioneer":
        return jsonify({"success": False, "error": "Unauthorized"})

    history = read_json(HISTORY_FILE, DEFAULT_HISTORY)
    if not history:
        return jsonify({"success": False, "error": "Nothing to rollback"})

    last = history.pop()
    players = read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
    teams = read_json(TEAMS_FILE, DEFAULT_TEAMS)

    # Undo sale
    if last.get("action") == "sell":
        player = next((p for p in players if p["id"] == last["player_id"]), None)

        if player:
            team = next((t for t in teams if t.get("team_name") == player.get("sold_to")), None)

            if team:
                team["purse"] = team.get("purse", 0) + player.get("final_price", 0)

            player["sold"] = False
            player["sold_to"] = ""
            player["final_price"] = 0

        write_json(PLAYERS_FILE, players)
        write_json(TEAMS_FILE, teams)

    write_json(HISTORY_FILE, history)

    # Reset state
    state = read_json(STATE_FILE, DEFAULT_STATE)
    state["current_bid"] = {"amount": None, "bidder": "", "team_name": ""}
    state["auction_active"] = False
    state["sold_to"] = ""
    state["last_bid_team"] = ""
    state["current_bid_history"] = {}

    write_json(STATE_FILE, state)

    return jsonify({"success": True})

# ----------------------------
# Reset whole auction
# ----------------------------
@app.route("/api/auction/reset", methods=["POST"])
def api_auction_reset():
    if session.get("role") != "auctioneer":
        return jsonify({"success": False, "error": "Unauthorized"})

    write_json(STATE_FILE, deepcopy(DEFAULT_STATE))
    write_json(SOLD_FILE, deepcopy(DEFAULT_SOLD))
    write_json(HISTORY_FILE, deepcopy(DEFAULT_HISTORY))

    players = read_json(PLAYERS_FILE, DEFAULT_PLAYERS)
    for p in players:
        p["sold"] = False
        p["sold_to"] = ""
        p["final_price"] = 0
    write_json(PLAYERS_FILE, players)

    teams = read_json(TEAMS_FILE, DEFAULT_TEAMS)
    default_purse = {t["team_name"]: t.get("default_purse", 10000) for t in DEFAULT_TEAMS}

    for t in teams:
        t["purse"] = default_purse.get(t["team_name"], 10000)
        t["players"] = []
    write_json(TEAMS_FILE, teams)

    return jsonify({"success": True})

# ----------------------------
# RUN
# ----------------------------
if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
