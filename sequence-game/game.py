"""
Core game engine for Sequence (2-4 players / 2-3 teams).
Server-authoritative, no rendering here - pure game state + rules.
"""
import random
import string

RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']
SUITS = ['S', 'H', 'D', 'C']
NON_JACK_RANKS = [r for r in RANKS if r != 'J']

TWO_EYED_JACKS = {'JD', 'JC'}   # wild - place chip anywhere open
ONE_EYED_JACKS = {'JS', 'JH'}   # anti-wild - remove opponent chip

DEAL_COUNTS = {2: 7, 3: 6, 4: 6}
BOARD_SIZE = 10
CORNERS = {(0, 0), (0, 9), (9, 0), (9, 9)}


def card_label(code):
    """'10D' -> '10♦'  'JC' -> 'J♣'"""
    suit_symbols = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
    rank = code[:-1]
    suit = code[-1]
    return f"{rank}{suit_symbols[suit]}"


def build_full_deck():
    """Two standard 52-card decks (no jokers) = 104 cards."""
    deck = []
    for _ in range(2):
        for s in SUITS:
            for r in RANKS:
                deck.append(r + s)
    return deck


def build_board_layout():
    """
    Deterministic 10x10 board layout. Corners are FREE spaces.
    The remaining 96 cells hold each of the 48 non-jack cards exactly twice.
    """
    board_cards = [r + s for r in NON_JACK_RANKS for s in SUITS]  # 48 unique
    cells = board_cards * 2  # 96
    rnd = random.Random(20240601)  # fixed seed -> same board layout every game
    rnd.shuffle(cells)

    layout = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    idx = 0
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if (r, c) in CORNERS:
                layout[r][c] = 'FREE'
            else:
                layout[r][c] = cells[idx]
                idx += 1
    return layout


BOARD_LAYOUT = build_board_layout()

# Card -> list of (r, c) cells where it appears on the board
CARD_CELLS = {}
for r in range(BOARD_SIZE):
    for c in range(BOARD_SIZE):
        code = BOARD_LAYOUT[r][c]
        if code != 'FREE':
            CARD_CELLS.setdefault(code, []).append((r, c))

# Pre-compute every straight line of 5 consecutive cells (horiz/vert/2 diag)
ALL_WINDOWS = []
_DIRS = [(0, 1), (1, 0), (1, 1), (1, -1)]
for r in range(BOARD_SIZE):
    for c in range(BOARD_SIZE):
        for dr, dc in _DIRS:
            cells = []
            ok = True
            for k in range(5):
                rr, cc = r + dr * k, c + dc * k
                if not (0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE):
                    ok = False
                    break
                cells.append((rr, cc))
            if ok:
                ALL_WINDOWS.append(cells)


def team_setup(num_players):
    """
    Returns (mode, color_list, required_sequences)
    mode: 'individual' or 'teams'
    """
    if num_players == 2:
        return 'individual', ['Blue', 'Green'], 2
    if num_players == 3:
        return 'individual', ['Blue', 'Green', 'Red'], 1
    if num_players == 4:
        return 'teams', ['Blue', 'Green'], 2
    raise ValueError('num_players must be 2, 3 or 4')


class Player:
    def __init__(self, sid, name, seat):
        self.sid = sid
        self.name = name
        self.seat = seat
        self.team = None      # 'A' / 'B' for 4p teams mode; else own color acts as team key
        self.color = None
        self.hand = []
        self.discard = []
        self.connected = True


class GameError(Exception):
    pass


class Game:
    def __init__(self, room_code, num_players):
        self.room_code = room_code
        self.num_players = num_players
        self.mode, self.colors, self.required_sequences = team_setup(num_players)
        self.players = []           # list[Player] in seat order
        self.started = False
        self.winner = None
        self.log = []

        self.board_chips = [[None] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.board_locked = [[False] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        self.sequences = {}          # team_key -> list[frozenset(cells)]
        self.sequence_counts = {}    # team_key -> int
        self.draw_pile = []
        self.turn_index = 0

    # ---------- lobby ----------
    def add_player(self, sid, name):
        if self.started:
            raise GameError('Game already started')
        if len(self.players) >= self.num_players:
            raise GameError('Room is full')
        p = Player(sid, name, seat=len(self.players))
        if self.mode == 'individual':
            p.team = p.seat  # each player is their own "team"
            p.color = self.colors[p.seat]
        self.players.append(p)
        return p

    def player_by_sid(self, sid):
        for p in self.players:
            if p.sid == sid:
                return p
        return None

    def choose_team(self, sid, team_letter):
        if self.mode != 'teams':
            raise GameError('Team choice not applicable')
        if team_letter not in ('A', 'B'):
            raise GameError('Invalid team')
        p = self.player_by_sid(sid)
        if not p:
            raise GameError('Player not found')
        current_count = sum(1 for pl in self.players if pl.team == team_letter)
        if current_count >= self.num_players // 2:
            raise GameError(f'Team {team_letter} is already full')
        p.team = team_letter

    def ready_to_start(self):
        if len(self.players) != self.num_players:
            return False, 'Waiting for more players to join'
        if self.mode == 'teams':
            for t in ('A', 'B'):
                if sum(1 for p in self.players if p.team == t) != self.num_players // 2:
                    return False, 'Teams must be balanced before starting'
        return True, ''

    def team_key(self, player):
        return player.team

    def team_color(self, team_key):
        if self.mode == 'individual':
            return self.colors[team_key]
        return self.colors[0] if team_key == 'A' else self.colors[1]

    # ---------- setup ----------
    def start(self):
        ok, reason = self.ready_to_start()
        if not ok:
            raise GameError(reason)

        if self.mode == 'teams':
            # reorder seats so teams alternate A,B,A,B for fair turn order
            a_players = [p for p in self.players if p.team == 'A']
            b_players = [p for p in self.players if p.team == 'B']
            ordered = []
            for i in range(max(len(a_players), len(b_players))):
                if i < len(a_players):
                    ordered.append(a_players[i])
                if i < len(b_players):
                    ordered.append(b_players[i])
            self.players = ordered
            for i, p in enumerate(self.players):
                p.seat = i
                p.color = self.team_color(p.team)

        for team_key in set(p.team for p in self.players):
            self.sequence_counts[team_key] = 0
            self.sequences[team_key] = []

        deck = build_full_deck()
        random.shuffle(deck)
        self.draw_pile = deck

        deal_n = DEAL_COUNTS[self.num_players]
        for p in self.players:
            p.hand = [self.draw_pile.pop() for _ in range(deal_n)]

        self.turn_index = 0
        self.started = True
        self._add_log(f"Game started! {self.current_player().name}'s turn.")

    # ---------- helpers ----------
    def current_player(self):
        return self.players[self.turn_index]

    def _add_log(self, msg):
        self.log.append(msg)
        self.log = self.log[-50:]

    def _draw_card(self, player):
        if not self.draw_pile:
            self._reshuffle_discards()
        if self.draw_pile:
            player.hand.append(self.draw_pile.pop())

    def _reshuffle_discards(self):
        pool = []
        for p in self.players:
            pool.extend(p.discard)
            p.discard = []
        random.shuffle(pool)
        self.draw_pile = pool
        self._add_log("Draw pile depleted - discard piles reshuffled.")

    def _advance_turn(self):
        self.turn_index = (self.turn_index + 1) % len(self.players)

    def _open_cells_for(self, code):
        cells = CARD_CELLS.get(code, [])
        return [(r, c) for (r, c) in cells if self.board_chips[r][c] is None]

    def is_dead_card(self, code):
        if code[:-1] == 'J':
            return False
        return len(self._open_cells_for(code)) == 0

    # ---------- sequence detection ----------
    def _check_new_sequences(self, team_key):
        color = self.team_color(team_key)
        current = list(self.sequences[team_key])
        new_seqs = []
        for window in ALL_WINDOWS:
            cells_set = frozenset(window)
            if cells_set in current:
                continue
            match = True
            for (r, c) in window:
                if BOARD_LAYOUT[r][c] == 'FREE':
                    continue
                if self.board_chips[r][c] != color:
                    match = False
                    break
            if not match:
                continue
            overlap_ok = True
            for seq in current:
                if len(cells_set & seq) > 1:
                    overlap_ok = False
                    break
            if overlap_ok:
                new_seqs.append(cells_set)
                current.append(cells_set)
        if new_seqs:
            self.sequences[team_key].extend(new_seqs)
            self.sequence_counts[team_key] += len(new_seqs)
            for cells_set in new_seqs:
                for (r, c) in cells_set:
                    self.board_locked[r][c] = True
        return new_seqs

    def _check_winner(self):
        for team_key, count in self.sequence_counts.items():
            if count >= self.required_sequences:
                self.winner = team_key
                return True
        return False

    # ---------- actions ----------
    def exchange_dead_card(self, sid, card_index):
        player = self._validate_turn(sid)
        if card_index < 0 or card_index >= len(player.hand):
            raise GameError('Invalid card index')
        code = player.hand[card_index]
        if not self.is_dead_card(code):
            raise GameError('That card is not dead (an open space is still available)')
        player.hand.pop(card_index)
        player.discard.append(code)
        self._draw_card(player)
        self._add_log(f"{player.name} exchanged a dead card ({card_label(code)}).")
        # does NOT advance turn

    def play_card(self, sid, card_index, target_cell):
        player = self._validate_turn(sid)
        if card_index < 0 or card_index >= len(player.hand):
            raise GameError('Invalid card index')
        code = player.hand[card_index]
        r, c = target_cell

        if code in TWO_EYED_JACKS:
            self._play_two_eyed_jack(player, code, card_index, r, c)
        elif code in ONE_EYED_JACKS:
            self._play_one_eyed_jack(player, code, card_index, r, c)
        else:
            self._play_normal_card(player, code, card_index, r, c)

        self._draw_card(player)
        self._advance_turn()
        if not self.winner:
            self._check_winner()
        if self.winner:
            self._add_log(f"Team/Player {self._display_team(self.winner)} wins the game!")
        else:
            self._add_log(f"{self.current_player().name}'s turn.")

    def _display_team(self, team_key):
        if self.mode == 'individual':
            for p in self.players:
                if p.team == team_key:
                    return p.name
            return str(team_key)
        return f"Team {team_key}"

    def _validate_turn(self, sid):
        player = self.player_by_sid(sid)
        if not player:
            raise GameError('Player not in this game')
        if self.winner:
            raise GameError('Game already finished')
        if self.current_player().sid != sid:
            raise GameError('Not your turn')
        return player

    def _play_normal_card(self, player, code, card_index, r, c):
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            raise GameError('Cell out of range')
        if BOARD_LAYOUT[r][c] != code:
            raise GameError('That cell does not match the card played')
        if self.board_chips[r][c] is not None:
            raise GameError('That cell is already occupied')
        self.board_chips[r][c] = player.color
        player.hand.pop(card_index)
        player.discard.append(code)
        self._add_log(f"{player.name} played {card_label(code)}.")
        self._check_new_sequences(player.team)

    def _play_two_eyed_jack(self, player, code, card_index, r, c):
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            raise GameError('Cell out of range')
        if (r, c) in CORNERS:
            raise GameError('Corners are already free spaces')
        if self.board_chips[r][c] is not None:
            raise GameError('That cell is already occupied')
        self.board_chips[r][c] = player.color
        player.hand.pop(card_index)
        player.discard.append(code)
        self._add_log(f"{player.name} played a two-eyed Jack ({card_label(code)}) - wild placement.")
        self._check_new_sequences(player.team)

    def _play_one_eyed_jack(self, player, code, card_index, r, c):
        if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
            raise GameError('Cell out of range')
        if (r, c) in CORNERS:
            raise GameError('Corner spaces cannot be removed')
        chip = self.board_chips[r][c]
        if chip is None:
            raise GameError('That cell has no chip to remove')
        if chip == player.color:
            raise GameError("You can't remove your own team's chip")
        if self.board_locked[r][c]:
            raise GameError('That chip is part of a completed sequence and is protected')
        self.board_chips[r][c] = None
        player.hand.pop(card_index)
        player.discard.append(code)
        self._add_log(f"{player.name} played a one-eyed Jack ({card_label(code)}) - removed an opponent chip.")

    # ---------- serialization ----------
    def public_state(self):
        return {
            'room': self.room_code,
            'started': self.started,
            'winner': self.winner,
            'winner_display': self._display_team(self.winner) if self.winner else None,
            'mode': self.mode,
            'num_players': self.num_players,
            'required_sequences': self.required_sequences,
            'board_layout': BOARD_LAYOUT,
            'board_chips': self.board_chips,
            'board_locked': self.board_locked,
            'sequence_counts': self.sequence_counts,
            'draw_pile_count': len(self.draw_pile),
            'turn_seat': self.players[self.turn_index].seat if self.players and self.started else None,
            'log': self.log,
            'players': [
                {
                    'seat': p.seat,
                    'name': p.name,
                    'team': p.team,
                    'color': p.color,
                    'hand_count': len(p.hand),
                    'top_discard': p.discard[-1] if p.discard else None,
                    'connected': p.connected,
                }
                for p in self.players
            ],
        }

    def private_hand(self, sid):
        p = self.player_by_sid(sid)
        if not p:
            return []
        return [{'code': code, 'label': card_label(code), 'dead': self.is_dead_card(code)} for code in p.hand]


def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
