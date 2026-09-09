const socket = io();

let myRoom = null;
let mySeat = null;
let myMode = null;
let latestState = null;
let myHand = [];
let selectedCardIndex = null;

const lobbyScreen = document.getElementById('lobby-screen');
const waitingScreen = document.getElementById('waiting-screen');
const gameScreen = document.getElementById('game-screen');
const errorBox = document.getElementById('error-box');

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.style.display = 'block';
  setTimeout(() => { errorBox.style.display = 'none'; }, 4000);
}

function showScreen(name) {
  lobbyScreen.style.display = name === 'lobby' ? 'flex' : 'none';
  waitingScreen.style.display = name === 'waiting' ? 'flex' : 'none';
  gameScreen.style.display = name === 'game' ? 'flex' : 'none';
}

// ---------------- LOBBY ----------------

document.getElementById('create-room-btn').addEventListener('click', () => {
  const name = document.getElementById('name-input').value || 'Player';
  const numPlayers = parseInt(document.getElementById('num-players-select').value, 10);
  socket.emit('create_room', { name, num_players: numPlayers });
});

document.getElementById('join-room-btn').addEventListener('click', () => {
  const name = document.getElementById('name-input').value || 'Player';
  const room = document.getElementById('room-code-input').value.trim().toUpperCase();
  if (!room) { showError('Enter a room code'); return; }
  socket.emit('join_room_event', { name, room });
});

socket.on('error_message', (data) => showError(data.message));

socket.on('room_joined', (data) => {
  myRoom = data.room;
  mySeat = data.seat;
  myMode = data.mode;
  document.getElementById('room-code-display').textContent = myRoom;
  showScreen('waiting');
});

document.getElementById('team-a-btn').addEventListener('click', () => socket.emit('choose_team', { team: 'A' }));
document.getElementById('team-b-btn').addEventListener('click', () => socket.emit('choose_team', { team: 'B' }));
document.getElementById('start-game-btn').addEventListener('click', () => socket.emit('start_game', {}));

// ---------------- STATE UPDATES ----------------

socket.on('state_update', (state) => {
  latestState = state;
  if (!state.started) {
    renderWaitingRoom(state);
  } else {
    showScreen('game');
    renderGame(state);
  }
});

socket.on('your_hand', (data) => {
  myHand = data.hand;
  if (latestState && latestState.started) renderHand();
});

function renderWaitingRoom(state) {
  showScreen('waiting');
  const list = document.getElementById('players-waiting-list');
  list.innerHTML = '';
  state.players.forEach((p) => {
    const div = document.createElement('div');
    div.className = 'waiting-player';
    const teamLabel = state.mode === 'teams' ? (p.team ? `Team ${p.team}` : 'No team yet') : '';
    div.innerHTML = `<span>${p.name}${p.seat === mySeat ? ' (you)' : ''}</span><span>${teamLabel}</span>`;
    list.appendChild(div);
  });

  const teamBox = document.getElementById('team-choice-box');
  teamBox.style.display = state.mode === 'teams' ? 'block' : 'none';

  const startBtn = document.getElementById('start-game-btn');
  const statusEl = document.getElementById('waiting-status');
  if (state.players.length === state.num_players) {
    if (state.mode === 'teams') {
      const aCount = state.players.filter(p => p.team === 'A').length;
      const bCount = state.players.filter(p => p.team === 'B').length;
      const balanced = aCount === state.num_players / 2 && bCount === state.num_players / 2;
      startBtn.style.display = mySeat === 0 && balanced ? 'block' : 'none';
      statusEl.textContent = balanced ? 'Ready to start!' : 'Waiting for teams to be balanced (2 vs 2)...';
    } else {
      startBtn.style.display = mySeat === 0 ? 'block' : 'none';
      statusEl.textContent = mySeat === 0 ? 'Ready to start!' : 'Waiting for host to start...';
    }
  } else {
    startBtn.style.display = 'none';
    statusEl.textContent = `Waiting for players (${state.players.length}/${state.num_players})...`;
  }
}

// ---------------- GAME RENDERING ----------------

function renderGame(state) {
  const myPlayer = state.players[mySeat];
  const isMyTurn = state.turn_seat === mySeat;

  const banner = document.getElementById('turn-banner');
  if (state.winner) {
    banner.textContent = `🏆 ${state.winner_display} wins!`;
  } else {
    const turnPlayer = state.players.find(p => p.seat === state.turn_seat);
    banner.textContent = isMyTurn ? "Your turn!" : `${turnPlayer ? turnPlayer.name : ''}'s turn...`;
  }
  banner.classList.toggle('my-turn', isMyTurn && !state.winner);

  renderBoard(state, isMyTurn);
  renderHand();
  renderScoreboard(state);
  renderPlayersPanel(state);
  renderLog(state);

  if (state.winner) {
    document.getElementById('winner-text').textContent = `${state.winner_display} wins the game!`;
    document.getElementById('winner-overlay').style.display = 'flex';
  }
}

function selectedCard() {
  if (selectedCardIndex === null || !myHand[selectedCardIndex]) return null;
  return myHand[selectedCardIndex];
}

function cardKind(code) {
  if (code === 'JD' || code === 'JC') return 'two-eyed';
  if (code === 'JS' || code === 'JH') return 'one-eyed';
  return 'normal';
}

function renderBoard(state, isMyTurn) {
  const board = document.getElementById('board');
  board.innerHTML = '';
  const myColor = state.players[mySeat] ? state.players[mySeat].color : null;
  const card = isMyTurn ? selectedCard() : null;
  const kind = card ? cardKind(card.code) : null;

  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 10; c++) {
      const layoutCode = state.board_layout[r][c];
      const chip = state.board_chips[r][c];
      const locked = state.board_locked[r][c];
      const cell = document.createElement('div');
      cell.className = 'cell';

      if (layoutCode === 'FREE') {
        cell.classList.add('free');
        cell.textContent = '★';
      } else {
        const isRed = layoutCode.endsWith('D') || layoutCode.endsWith('H');
        cell.textContent = labelFor(layoutCode);
        if (isRed) cell.style.color = '#c0575a';
      }

      if (chip) {
        const chipDiv = document.createElement('div');
        chipDiv.className = `chip chip-${chip}` + (locked ? ' locked' : '');
        cell.appendChild(chipDiv);
      }

      // interactivity
      if (isMyTurn && !state.winner && card) {
        if (kind === 'normal' && layoutCode === card.code && !chip) {
          cell.classList.add('playable');
          cell.addEventListener('click', () => playCard(r, c));
        } else if (kind === 'two-eyed' && layoutCode !== 'FREE' && !chip) {
          cell.classList.add('playable');
          cell.addEventListener('click', () => playCard(r, c));
        } else if (kind === 'one-eyed' && chip && chip !== myColor && !locked) {
          cell.classList.add('removable');
          cell.addEventListener('click', () => playCard(r, c));
        }
      }

      board.appendChild(cell);
    }
  }
}

function labelFor(code) {
  const suitSymbols = { S: '♠', H: '♥', D: '♦', C: '♣' };
  const rank = code.slice(0, -1);
  const suit = code.slice(-1);
  return rank + suitSymbols[suit];
}

function playCard(row, col) {
  socket.emit('play_card', { cardIndex: selectedCardIndex, row, col });
  selectedCardIndex = null;
}

function renderHand() {
  const handDiv = document.getElementById('hand');
  handDiv.innerHTML = '';
  const isMyTurn = latestState && latestState.turn_seat === mySeat && !latestState.winner;

  myHand.forEach((cardObj, idx) => {
    const div = document.createElement('div');
    const isRed = cardObj.code.endsWith('D') || cardObj.code.endsWith('H');
    div.className = 'playing-card' + (isRed ? ' red-suit' : '') + (cardObj.dead ? ' dead' : '') +
      (idx === selectedCardIndex ? ' selected' : '');
    div.textContent = cardObj.label;
    div.addEventListener('click', () => {
      selectedCardIndex = (selectedCardIndex === idx) ? null : idx;
      renderHand();
      if (latestState) renderBoard(latestState, isMyTurn);
      renderDeadCardButton();
    });
    handDiv.appendChild(div);
  });
  renderDeadCardButton();
}

function renderDeadCardButton() {
  const btn = document.getElementById('dead-card-btn');
  const isMyTurn = latestState && latestState.turn_seat === mySeat && !latestState.winner;
  const card = selectedCard();
  if (isMyTurn && card && card.dead) {
    btn.style.display = 'block';
    btn.onclick = () => {
      socket.emit('exchange_dead_card', { cardIndex: selectedCardIndex });
      selectedCardIndex = null;
    };
  } else {
    btn.style.display = 'none';
  }
}

function renderScoreboard(state) {
  const box = document.getElementById('scoreboard');
  box.innerHTML = '<h3>Sequences</h3>';
  Object.entries(state.sequence_counts).forEach(([teamKey, count]) => {
    const label = state.mode === 'teams' ? `Team ${teamKey}` :
      (state.players.find(p => String(p.team) === String(teamKey)) || {}).name || teamKey;
    const row = document.createElement('div');
    row.textContent = `${label}: ${count} / ${state.required_sequences}`;
    box.appendChild(row);
  });
  const drawRow = document.createElement('div');
  drawRow.style.marginTop = '8px';
  drawRow.style.color = '#9db4c7';
  drawRow.textContent = `Draw pile: ${state.draw_pile_count} cards`;
  box.appendChild(drawRow);
}

function renderPlayersPanel(state) {
  const box = document.getElementById('players-panel');
  box.innerHTML = '<h3>Players</h3>';
  state.players.forEach((p) => {
    const row = document.createElement('div');
    row.className = 'player-row' + (p.seat === state.turn_seat ? ' current' : '');
    const dot = document.createElement('div');
    dot.className = 'player-dot';
    dot.style.background = colorHex(p.color);
    row.appendChild(dot);
    const text = document.createElement('span');
    const teamTag = state.mode === 'teams' ? ` (Team ${p.team})` : '';
    text.textContent = `${p.name}${teamTag}${p.seat === mySeat ? ' (you)' : ''} — ${p.hand_count} cards${p.connected ? '' : ' [disconnected]'}`;
    row.appendChild(text);
    box.appendChild(row);
  });
}

function colorHex(name) {
  return { Blue: '#2f80ed', Green: '#27ae60', Red: '#eb5757' }[name] || '#888';
}

function renderLog(state) {
  const box = document.getElementById('log-panel');
  box.innerHTML = '<h3>Game Log</h3>';
  state.log.slice().reverse().forEach((entry) => {
    const div = document.createElement('div');
    div.textContent = entry;
    box.appendChild(div);
  });
}
