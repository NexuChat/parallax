"""Two players, one invitation, and a game with turns — a protocol to verify.

The other relational fixtures test a moment: one session acts, another should
see it. A game is an *order*. An invitation must arrive before it can be
accepted, a move belongs to one player and must be refused from the other, and a
win has to end the game for both sides rather than for the winner alone.

Each of those is a separate promise, and a test that only checks the final board
reports that somebody won while saying nothing about the illegal move that got
them there. So this site keeps the rules server-side, where they can actually be
broken by a client that tries: the turn is enforced, an occupied cell is
refused, and a finished game accepts nothing further.

Everything is polled, exactly like the workspace threads, so two live sessions
see each other's moves without either of them being the server.
"""

from __future__ import annotations

import json
import time
from html import escape
from typing import Any

from .base import FONT_FACE_CSS, Planted, Request, Response


_WINNING_LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
)


def _new_game() -> dict[str, Any]:
    return {
        "invite": None,      # {"from": ..., "to": ...}
        "players": {},       # name -> "X" | "O"
        "board": [""] * 9,
        "turn": None,
        "winner": None,
        "state": "idle",     # idle | invited | playing | won
        "seq": 0,
        "rejected": [],      # every refused move, so a test can prove enforcement
        "touched": time.monotonic(),
    }


# A finished or abandoned game must not make the next run unplayable. Both are
# ordinary "play again" behaviour rather than test scaffolding: a room that
# cannot start a second game is a worse fixture, not a purer one.
_STALE_AFTER_S = 120.0


_ARENA: dict[str, Any] = _new_game()


def _move(label: str, actor: str, cell: int, mark: str, watcher: str) -> dict[str, Any]:
    """One move, and the promise that the other board shows it."""
    return {
        "label": label,
        "actor": actor,
        "action": {"type": "click", "selector": f"#cell-{cell}"},
        "expect": [{
            "participant": watcher,
            "effect": {"type": "text_equals", "selector": f"#cell-{cell}", "equals": mark},
            "note": f"{actor}'s move must appear on {watcher}'s board",
        }],
    }


# The protocol, in order. Each step is verified from both boards before the next
# one is allowed to run, so the finding names the first promise that broke rather
# than the wreckage downstream of it.
_INVITE_AND_PLAY = {
    "label": "invite, play, and win",
    "surface": "/game-legacy",
    "participants": [
        {"name": "amira", "surface": "/game-legacy?me=amira&vs=samir"},
        {"name": "samir", "surface": "/game-legacy?me=samir&vs=amira"},
    ],
    "steps": [
        {
            "label": "amira invites samir",
            "actor": "amira",
            "action": {"type": "click", "selector": "#send-invite"},
            "expect": [
                {"participant": "samir", "effect": {"type": "visible", "selector": "#accept"},
                 "note": "the invitation must reach its recipient"},
                # An invitation everybody can see is not an invitation. The
                # negative expectation is checked in the same moment as the
                # positive one, from a different session.
                {"participant": "amira", "effect": {"type": "visible", "selector": "#accept"},
                 "visible": False, "note": "and must not be offered to its sender"},
            ],
        },
        {
            "label": "samir accepts",
            "actor": "samir",
            "action": {"type": "click", "selector": "#accept"},
            "expect": [{"participant": "amira",
                        "effect": {"type": "text_equals", "selector": "#status", "equals": "playing"},
                        "note": "accepting starts the game for both players"}],
        },
        _move("amira takes the centre", "amira", 4, "X", "samir"),
        _move("samir takes a corner", "samir", 0, "O", "amira"),
        _move("amira takes the left of the middle row", "amira", 3, "X", "samir"),
        _move("samir takes the top", "samir", 1, "O", "amira"),
        {
            "label": "amira completes the middle row and wins",
            "actor": "amira",
            "action": {"type": "click", "selector": "#cell-5"},
            "expect": [
                {"participant": "amira", "effect": {"type": "visible", "selector": "#winner"},
                 "note": "the winner is told they won"},
                # The whole point. A game's ending is not a private fact, and
                # this is the step the legacy route breaks.
                {"participant": "samir", "effect": {"type": "visible", "selector": "#winner"},
                 "note": "and so is the player who lost"},
            ],
            "deadline_ms": 4000,
        },
    ],
}


class ArenaSite:
    name = "arena"
    title = "Parallax arena"
    # `/game` is played correctly and plants nothing, so a sequence that fails
    # there is testing Parallax rather than the fixture. `/game-legacy` serves
    # the identical game with one promise broken, and it is the only thing
    # graded here.
    planted = [
        Planted(
            "propagation", "relational", "/game-legacy",
            "A win ends the game for the winner alone; the loser is still told it is their turn.",
        ),
    ]
    accounts: list[Any] = []
    choreographies = [_INVITE_AND_PLAY]

    blurb = "Two players, one invitation, and a game with turns — an ordered protocol played by two live sessions. /game is correct; /game-legacy ends the game for the winner alone."
    entry = "/game-legacy?me=amira&vs=samir"

    def handle(self, request: Request) -> Response:
        if request.path == "/api/reset":
            _ARENA.update(_new_game())
            return Response.json({"ok": True})
        if request.path == "/api/state":
            return Response.json(self._state_for(request.query.get("me", ""), request.query.get("legacy") == "1"))
        if request.path == "/api/invite":
            return self._invite(request)
        if request.path == "/api/accept":
            return self._accept(request)
        if request.path == "/api/move":
            return self._move(request)
        if request.path in {"/", "/game", "/game-legacy"}:
            return Response.html(self._page(request, legacy=request.path == "/game-legacy"))
        return Response.not_found()

    def _state_for(self, viewer: str, legacy: bool) -> dict[str, Any]:
        """What one player is told the game looks like.

        The correct route tells everyone the same thing, because a game's
        outcome is not a private fact. The legacy route reports the win to the
        winner and keeps telling everybody else that play continues and the turn
        is theirs — the ending propagates to one session and not the other.

        This is invisible to every single-session tool: the winner's page is
        completely correct, and the loser's page is a perfectly plausible game
        in progress. It is only wrong in the disagreement between them, and only
        *after* a specific ordered sequence of moves has happened.
        """
        if not legacy or _ARENA["state"] != "won" or viewer == _ARENA["winner"]:
            return _ARENA
        return {**_ARENA, "state": "playing", "winner": None, "turn": viewer}

    def _invite(self, request: Request) -> Response:
        body = _body(request)
        if _ARENA["state"] == "won" or time.monotonic() - _ARENA["touched"] > _STALE_AFTER_S:
            # Play again, or recover a room somebody abandoned mid-game.
            _ARENA.update(_new_game())
        if _ARENA["state"] != "idle":
            return Response.json({"error": "a game is already in progress"}, status=409)
        _ARENA.update(
            invite={"from": body.get("from"), "to": body.get("to")},
            state="invited",
            seq=_ARENA["seq"] + 1,
            touched=time.monotonic(),
        )
        return Response.json(_ARENA)

    def _accept(self, request: Request) -> Response:
        body = _body(request)
        invite = _ARENA["invite"]
        if _ARENA["state"] != "invited" or not invite:
            return Response.json({"error": "there is no invitation to accept"}, status=409)
        if body.get("player") != invite["to"]:
            # Only the invited player may accept. An application that let anyone
            # accept would pass a test that never tried.
            return Response.json({"error": "this invitation is addressed to someone else"}, status=403)
        _ARENA.update(
            players={invite["from"]: "X", invite["to"]: "O"},
            turn=invite["from"],
            state="playing",
            seq=_ARENA["seq"] + 1,
            touched=time.monotonic(),
        )
        return Response.json(_ARENA)

    def _move(self, request: Request) -> Response:
        body = _body(request)
        player, cell = body.get("player"), body.get("cell")
        if _ARENA["state"] != "playing":
            return self._refuse(player, cell, "the game is not in play")
        if player not in _ARENA["players"]:
            return self._refuse(player, cell, "not a player in this game")
        if player != _ARENA["turn"]:
            return self._refuse(player, cell, "not this player's turn")
        if not isinstance(cell, int) or not 0 <= cell < 9:
            return self._refuse(player, cell, "cell is off the board")
        if _ARENA["board"][cell]:
            return self._refuse(player, cell, "cell is already taken")

        mark = _ARENA["players"][player]
        _ARENA["board"][cell] = mark
        _ARENA["seq"] += 1
        _ARENA["touched"] = time.monotonic()
        if any(all(_ARENA["board"][i] == mark for i in line) for line in _WINNING_LINES):
            _ARENA.update(winner=player, state="won", turn=None)
        elif all(_ARENA["board"]):
            _ARENA.update(state="won", winner=None, turn=None)
        else:
            _ARENA["turn"] = next(name for name in _ARENA["players"] if name != player)
        return Response.json(_ARENA)

    def _refuse(self, player: Any, cell: Any, reason: str) -> Response:
        _ARENA["rejected"].append({"player": player, "cell": cell, "reason": reason})
        return Response.json({"error": reason}, status=409)

    def _page(self, request: Request, *, legacy: bool = False) -> str:
        lang = request.query.get("lang", "en")
        direction = "rtl" if lang == "ar" else "ltr"
        cells = "".join(
            f'<button class="cell" id="cell-{index}" data-cell="{index}" '
            f'aria-label="cell {index}"></button>'
            for index in range(9)
        )
        return (
            f'<!doctype html><html lang="{escape(lang)}" dir="{direction}"><head>'
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(self.title)}</title><style>{FONT_FACE_CSS}"
            'body{margin:0;font:16px/1.5 "Parallax Serif",serif;background:#fbfbfa;color:#16211f}'
            '.shell{max-inline-size:760px;margin-inline:auto;padding:clamp(16px,4vw,44px)}'
            'h1{font:700 26px/1.2 "Parallax Sans",sans-serif}'
            '#status{font:650 13px/1 "Parallax Mono",monospace;border:1px solid #cfd8d6;border-radius:8px;'
            'padding:12px 16px;display:inline-flex;align-items:center;min-block-size:44px;margin-block:14px}'
            '.board{display:grid;grid-template-columns:repeat(3,88px);gap:8px}'
            '.cell{inline-size:88px;block-size:88px;font:700 30px/1 "Parallax Sans",sans-serif;'
            'background:#fff;border:1px solid #cfd8d6;border-radius:10px;cursor:pointer}'
            '#invite,#winner{font:650 14px/1.4 "Parallax Sans",sans-serif;margin-block:10px}'
            # The graded sweep caught these at 44px on its first run, which is
            # the fixture being held to the same rule as the sites it grades.
            '#send-invite,#accept{font:650 14px/1 "Parallax Sans",sans-serif;background:#fff;'
            'border:1px solid #cfd8d6;border-radius:8px;cursor:pointer;min-block-size:44px;'
            'min-inline-size:44px;padding:10px 18px}'
            "</style></head><body><main class=\"shell\">"
            f"<h1>{escape(self.title)}</h1>"
            '<p id="status" data-state="idle">idle</p>'
            '<p id="invite" hidden></p>'
            '<button id="send-invite">Invite</button> '
            '<button id="accept" hidden>Accept</button>'
            '<p id="winner" hidden></p>'
            f'<div class="board">{cells}</div>'
            f"{_CLIENT.replace('__MOUNT__', escape(request.mount)).replace('__LEGACY__', '1' if legacy else '')}"
            "</main></body></html>"
        )


def _body(request: Request) -> dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


_CLIENT = """<script>
const MOUNT = "__MOUNT__";
const LEGACY = "__LEGACY__";
let me = null;

const post = (path, body) => fetch(MOUNT + path, {
  method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
}).then(async (r) => ({ok: r.ok, data: await r.json()}));

const render = (state) => {
  document.getElementById('status').textContent = state.state;
  document.getElementById('status').dataset.state = state.state;
  document.getElementById('status').dataset.turn = state.turn || '';
  state.board.forEach((mark, index) => {
    document.getElementById('cell-' + index).textContent = mark;
  });
  const invite = document.getElementById('invite');
  // The invitation is only shown to its recipient, which is itself a promise
  // worth testing: an invitation everybody can see is not an invitation.
  const mine = state.state === 'invited' && state.invite && state.invite.to === me;
  invite.hidden = !mine;
  document.getElementById('accept').hidden = !mine;
  if (mine) {
    invite.textContent = state.invite.from + ' invited you to play';
    invite.dataset.from = state.invite.from;
  }
  const winner = document.getElementById('winner');
  if (state.winner) {
    winner.hidden = false;
    winner.textContent = state.winner + ' wins';
    winner.dataset.winner = state.winner;
  } else {
    winner.hidden = true;
  }
};

const poll = async () => {
  const url = `${MOUNT}/api/state?me=${encodeURIComponent(me || '')}&legacy=${LEGACY}`;
  const state = await fetch(url).then((r) => r.json());
  render(state);
};

window.enterRoom = (name) => { me = name; setInterval(poll, 250); poll(); return me; };

// The page drives itself from the query string, so a session is a URL rather
// than an injected script: ?me=amira&vs=samir is one player at their own board.
const params = new URLSearchParams(location.search);
if (params.get('me')) window.enterRoom(params.get('me'));

document.getElementById('send-invite').addEventListener('click', () => invite(params.get('vs')));
document.getElementById('accept').addEventListener('click', () => accept());
document.querySelectorAll('.cell').forEach((button) => {
  button.addEventListener('click', () => play(Number(button.dataset.cell)));
});
window.invite = (to) => post('/api/invite', {from: me, to});
window.accept = () => post('/api/accept', {player: me});
window.play = (cell) => post('/api/move', {player: me, cell});
</script>"""
