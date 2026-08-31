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
    }


_ARENA: dict[str, Any] = _new_game()


class ArenaSite:
    name = "arena"
    title = "Parallax arena"
    # Nothing planted: this fixture exists to be played correctly, so that a
    # sequence test which fails is testing Parallax rather than the fixture.
    planted: list[Planted] = []
    accounts: list[Any] = []

    def handle(self, request: Request) -> Response:
        if request.path == "/api/reset":
            _ARENA.update(_new_game())
            return Response.json({"ok": True})
        if request.path == "/api/state":
            return Response.json(_ARENA)
        if request.path == "/api/invite":
            return self._invite(request)
        if request.path == "/api/accept":
            return self._accept(request)
        if request.path == "/api/move":
            return self._move(request)
        if request.path in {"/", "/game"}:
            return Response.html(self._page(request))
        return Response.not_found()

    def _invite(self, request: Request) -> Response:
        body = _body(request)
        if _ARENA["state"] != "idle":
            return Response.json({"error": "a game is already in progress"}, status=409)
        _ARENA.update(
            invite={"from": body.get("from"), "to": body.get("to")},
            state="invited",
            seq=_ARENA["seq"] + 1,
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

    def _page(self, request: Request) -> str:
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
            "</style></head><body><main class=\"shell\">"
            f"<h1>{escape(self.title)}</h1>"
            '<p id="status" data-state="idle">idle</p>'
            '<p id="invite" hidden></p><p id="winner" hidden></p>'
            f'<div class="board">{cells}</div>'
            f"{_CLIENT.replace('__MOUNT__', escape(request.mount))}"
            "</main></body></html>"
        )


def _body(request: Request) -> dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


_CLIENT = """<script>
const MOUNT = "__MOUNT__";
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
  if (state.state === 'invited' && state.invite && state.invite.to === me) {
    invite.hidden = false;
    invite.id = 'invite';
    invite.textContent = state.invite.from + ' invited you to play';
    invite.dataset.from = state.invite.from;
  } else {
    invite.hidden = true;
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
  const state = await fetch(MOUNT + '/api/state').then((r) => r.json());
  render(state);
};

window.enterRoom = (name) => { me = name; setInterval(poll, 250); poll(); return me; };
window.invite = (to) => post('/api/invite', {from: me, to});
window.accept = () => post('/api/accept', {player: me});
window.play = (cell) => post('/api/move', {player: me, cell});
</script>"""
