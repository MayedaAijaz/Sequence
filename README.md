# Sequence (2–4 players) — Flask + Socket.IO

A real-time, multiplayer implementation of the board game **Sequence**, playable in the
browser. Built with Flask, Flask-SocketIO (websockets) and vanilla JS — no build step needed.

## Features implemented

- 2, 3, or 4 player games. With 4 players, players pick **Team A** or **Team B** (2 vs 2);
  with 2 or 3 players everyone plays individually.
- Two full 52-card decks (104 cards), correct deal counts (7 / 6 / 6 cards for 2 / 3 / 4 players).
- 10×10 board with the 4 free corners, each usable by any player/team.
- Two-eyed Jacks (wild — place a chip on any open space) and one-eyed Jacks
  (anti-wild — remove an opponent's chip, unless it's locked into a completed sequence).
- Dead-card detection and exchange (turn in a card whose two board spaces are both filled).
- Sequence detection in all 4 directions, including sequences that share a single
  intersecting chip. Cells in a completed sequence are locked and can't be removed.
- Draw pile reshuffles from discard piles automatically when depleted.
- Win condition: first to 2 sequences (2 players / 2 teams) or 1 sequence (3 players).
- Live lobby with room codes, a shared board, private hands, a game log, and a scoreboard.

## Project layout

```
app.py            Flask + Socket.IO server (rooms, events)
game.py           Game engine: board, deck, jacks, sequence logic (framework-free)
templates/index.html
static/style.css
static/game.js    Client rendering + interaction
requirements.txt
Procfile          Start command for Render/Heroku-style hosts
render.yaml        Optional one-click Render Blueprint
```

## Run locally

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in a couple of browser tabs (or share on your LAN) to play.

## Deploy to Render (free tier)

**Option A — Blueprint (fastest)**
1. Push this folder to a GitHub repository.
2. In the Render dashboard, choose **New > Blueprint**, point it at your repo. Render will
   read `render.yaml` and configure everything automatically.
3. Click **Apply** — Render builds and deploys on the free plan.

**Option B — Manual web service**
1. Push this folder to GitHub.
2. Render dashboard → **New > Web Service** → connect your repo.
3. Settings:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --worker-class gthread --threads 8 --workers 1 --bind 0.0.0.0:$PORT app:app`
   - **Instance Type**: Free
4. Deploy. Render provides a public HTTPS URL — websockets work out of the box on Render's
   free tier.

> Free-tier note: Render's free web services spin down after ~15 minutes of inactivity, and
> the game state is stored in-memory (not a database) — an active room will be lost if the
> service spins down/restarts. That's fine for casual play; for persistence across restarts
> you'd want to move `ROOMS` in `app.py` to Redis or another store.

## Why `gthread`, not `eventlet`

This app uses Flask-SocketIO's `threading` async mode with the `simple-websocket` package,
served by gunicorn's `gthread` worker. Earlier eventlet-based deployments broke on Render
once its default Python image moved to 3.14, because eventlet monkey-patches `threading` in
a way that depends on internals that changed between CPython versions. `gthread` + 
`simple-websocket` has no such dependency and works identically across Python versions, so
this setup is more future-proof for a "just deploy it" free-tier target.

## How to play

1. One player creates a room, choosing 2, 3, or 4 players, and shares the room code.
2. Others join with that code. In a 4-player game, everyone picks Team A or Team B
   (2 per team) before the host can start.
3. On your turn: click a card in your hand, then click a highlighted board cell:
   - A normal card highlights its two matching board spaces.
   - A two-eyed Jack (♦/♣) highlights every open space on the board.
   - A one-eyed Jack (♠/♥) highlights removable opponent chips.
   - If your selected card is "dead" (both its spaces are taken), a **Turn in Dead Card**
     button appears instead — use it to draw a replacement without ending your turn.
4. First player/team to complete the required number of sequences wins.
