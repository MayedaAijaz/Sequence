import os
from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit

from game import Game, GameError, generate_room_code

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sequence-dev-secret')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

ROOMS = {}          # room_code -> Game
SID_ROOM = {}        # sid -> room_code


def broadcast_state(room_code):
    game = ROOMS.get(room_code)
    if not game:
        return
    state = game.public_state()
    socketio.emit('state_update', state, room=room_code)
    if game.started:
        for p in game.players:
            socketio.emit('your_hand', {'hand': game.private_hand(p.sid)}, room=p.sid)


@app.route('/')
def index():
    return render_template('index.html')


@socketio.on('connect')
def on_connect():
    pass


@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    room_code = SID_ROOM.get(sid)
    if not room_code:
        return
    game = ROOMS.get(room_code)
    if not game:
        return
    p = game.player_by_sid(sid)
    if p:
        p.connected = False
        game._add_log(f"{p.name} disconnected.")
    broadcast_state(room_code)


@socketio.on('create_room')
def on_create_room(data):
    name = (data.get('name') or 'Player').strip()[:20] or 'Player'
    num_players = int(data.get('num_players', 2))
    if num_players not in (2, 3, 4):
        emit('error_message', {'message': 'Choose 2, 3 or 4 players'})
        return

    room_code = generate_room_code()
    while room_code in ROOMS:
        room_code = generate_room_code()

    game = Game(room_code, num_players)
    ROOMS[room_code] = game

    sid = request.sid
    try:
        player = game.add_player(sid, name)
    except GameError as e:
        emit('error_message', {'message': str(e)})
        return

    join_room(room_code)
    SID_ROOM[sid] = room_code
    emit('room_joined', {'room': room_code, 'seat': player.seat, 'mode': game.mode})
    broadcast_state(room_code)


@socketio.on('join_room_event')
def on_join_room(data):
    name = (data.get('name') or 'Player').strip()[:20] or 'Player'
    room_code = (data.get('room') or '').strip().upper()
    game = ROOMS.get(room_code)
    if not game:
        emit('error_message', {'message': 'Room not found'})
        return

    sid = request.sid
    try:
        player = game.add_player(sid, name)
    except GameError as e:
        emit('error_message', {'message': str(e)})
        return

    join_room(room_code)
    SID_ROOM[sid] = room_code
    emit('room_joined', {'room': room_code, 'seat': player.seat, 'mode': game.mode})
    broadcast_state(room_code)


@socketio.on('choose_team')
def on_choose_team(data):
    sid = request.sid
    room_code = SID_ROOM.get(sid)
    game = ROOMS.get(room_code)
    if not game:
        return
    try:
        game.choose_team(sid, data.get('team'))
    except GameError as e:
        emit('error_message', {'message': str(e)})
        return
    broadcast_state(room_code)


@socketio.on('start_game')
def on_start_game(_data):
    sid = request.sid
    room_code = SID_ROOM.get(sid)
    game = ROOMS.get(room_code)
    if not game:
        return
    try:
        game.start()
    except GameError as e:
        emit('error_message', {'message': str(e)})
        return
    broadcast_state(room_code)


@socketio.on('play_card')
def on_play_card(data):
    sid = request.sid
    room_code = SID_ROOM.get(sid)
    game = ROOMS.get(room_code)
    if not game:
        return
    try:
        game.play_card(sid, int(data['cardIndex']), (int(data['row']), int(data['col'])))
    except GameError as e:
        emit('error_message', {'message': str(e)})
        return
    except (KeyError, ValueError, TypeError):
        emit('error_message', {'message': 'Invalid move'})
        return
    broadcast_state(room_code)


@socketio.on('exchange_dead_card')
def on_exchange_dead_card(data):
    sid = request.sid
    room_code = SID_ROOM.get(sid)
    game = ROOMS.get(room_code)
    if not game:
        return
    try:
        game.exchange_dead_card(sid, int(data['cardIndex']))
    except GameError as e:
        emit('error_message', {'message': str(e)})
        return
    except (KeyError, ValueError, TypeError):
        emit('error_message', {'message': 'Invalid move'})
        return
    broadcast_state(room_code)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
