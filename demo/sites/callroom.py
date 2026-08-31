"""A real WebRTC room, so multi-party call behaviour can be measured.

Every other demo site plants a defect in markup. This one plants nothing and
exists for a different reason: the audio sensors need something that genuinely
carries sound between browser sessions, and a fixture that fakes it would prove
only that the fake works.

So this is a mesh. Each participant opens a peer connection to every other
participant, offers and answers travel through the polling endpoints below, and
the audio is Chromium's synthetic microphone. Nothing is simulated except the
microphone, which is the one thing a headless browser cannot have.

The room models the four states the question actually turns on:

* **in the call, speaking** — the others must hear it
* **in the call, microphone off** — the others must not, and this is the case
  that separates a real sensor from a hopeful one, because a muted participant
  still negotiates and still receives packets
* **in the room, not in the call** — hears the call, because being in the room
  is what "listening in" means
* **in the room, speaker off** — hears nothing by choice, and must not be
  reported as a propagation failure for it

`?members=` bounds the mesh. Eight participants is 28 connections, which is more
than a headless run needs to prove the point but is what a real room asks for.
"""

from __future__ import annotations

import json
import time
from html import escape
from typing import Any

from .base import FONT_FACE_CSS, Planted, Request, Response


# Signalling state lives in memory for the lifetime of the process, exactly like
# the other demo sites. A restart is a new room, which is the correct behaviour
# for a fixture that must not accumulate state between graded runs.
_ROOM: dict[str, Any] = {"members": {}, "signals": [], "seq": 0}


def _now() -> float:
    return time.time()


class CallRoomSite:
    name = "call"
    title = "Parallax call room"
    # Nothing is planted. This site exists to be measured, not to be graded, and
    # the suite records it with an empty expectation so a stray finding here is
    # still counted as a false positive.
    planted: list[Planted] = []
    accounts: list[Any] = []

    def handle(self, request: Request) -> Response:
        if request.path == "/api/join":
            return self._join(request)
        if request.path == "/api/signal":
            return self._signal(request)
        if request.path == "/api/poll":
            return self._poll(request)
        if request.path == "/api/reset":
            _ROOM.update(members={}, signals=[], seq=0)
            return Response.json({"ok": True})
        if request.path in {"/", "/room"}:
            return self._page(request)
        return Response.not_found()

    # ------------------------------------------------------------- signalling

    def _join(self, request: Request) -> Response:
        payload = _body(request)
        peer = str(payload.get("peer") or "")
        if not peer:
            return Response.json({"error": "peer required"}, status=400)
        _ROOM["members"][peer] = {"joined": _now(), "in_call": bool(payload.get("in_call"))}
        return Response.json({
            "peer": peer,
            "peers": [name for name in _ROOM["members"] if name != peer],
        })

    def _signal(self, request: Request) -> Response:
        payload = _body(request)
        _ROOM["seq"] += 1
        _ROOM["signals"].append({
            "seq": _ROOM["seq"],
            "from": payload.get("from"),
            "to": payload.get("to"),
            "kind": payload.get("kind"),
            "data": payload.get("data"),
        })
        # An unbounded log would make a long room slow rather than wrong; the
        # tail is all any late joiner needs.
        if len(_ROOM["signals"]) > 400:
            del _ROOM["signals"][:200]
        return Response.json({"seq": _ROOM["seq"]})

    def _poll(self, request: Request) -> Response:
        peer = request.query.get("peer", "")
        since = int(request.query.get("since", "0") or 0)
        waiting = [
            signal for signal in _ROOM["signals"]
            if signal["seq"] > since and signal["to"] in (peer, "*") and signal["from"] != peer
        ]
        return Response.json({
            "signals": waiting,
            "seq": _ROOM["seq"],
            "peers": [name for name in _ROOM["members"] if name != peer],
        })

    # ------------------------------------------------------------------- page

    def _page(self, request: Request) -> Response:
        lang = request.query.get("lang", "en")
        direction = "rtl" if lang == "ar" else "ltr"
        return Response.html(
            f'<!doctype html><html lang="{escape(lang)}" dir="{direction}"><head>'
            f'<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(self.title)}</title><style>{FONT_FACE_CSS}"
            'body{margin:0;font:16px/1.5 "Parallax Serif",serif;background:#fbfbfa;color:#16211f}'
            '.shell{max-inline-size:840px;margin-inline:auto;padding:clamp(16px,4vw,44px)}'
            'h1{font:700 26px/1.2 "Parallax Sans",sans-serif}'
            '.state{font:650 13px/1 "Parallax Mono",monospace;padding:10px 14px;border:1px solid #cfd8d6;'
            'border-radius:8px;display:inline-block;margin-block:12px;min-block-size:44px;'
            'display:inline-flex;align-items:center}'
            '.peer{border:1px solid #cfd8d6;border-radius:10px;padding:12px;margin-block:8px}'
            "</style></head><body><main class=\"shell\">"
            f"<h1>{escape(self.title)}</h1>"
            '<p class="state" id="state" data-state="idle">idle</p>'
            '<div id="peers"></div><div id="audio"></div>'
            f"{_CLIENT_SCRIPT.replace('__MOUNT__', escape(request.mount))}"
            "</main></body></html>"
        )


def _body(request: Request) -> dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


# Driven entirely from the page: a test names itself, says whether it is joining
# the call or only the room, and the mesh forms itself. Parallax then measures
# what each session received.
_CLIENT_SCRIPT = """<script>
const MOUNT = "__MOUNT__";
const connections = new Map();
let me = null, since = 0, micOn = true, speakerOn = true, localStream = null;

const setState = (value) => {
  const el = document.getElementById('state');
  el.textContent = value; el.dataset.state = value;
};

const post = (path, body) => fetch(MOUNT + path, {
  method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
}).then((r) => r.json());

const attach = (peer, stream) => {
  let el = document.getElementById('audio-' + peer);
  if (!el) {
    el = document.createElement('audio');
    el.id = 'audio-' + peer; el.autoplay = true;
    document.getElementById('audio').appendChild(el);
  }
  el.srcObject = stream;
  // Speaker mute is the receiving end's choice, and is deliberately distinct
  // from the sender's microphone: one is "I will not send", the other is
  // "I will not listen", and a test must be able to tell them apart.
  el.muted = !speakerOn;
};

const connect = async (peer, initiate) => {
  if (connections.has(peer)) return connections.get(peer);
  const pc = new RTCPeerConnection();
  connections.set(peer, pc);
  if (localStream) localStream.getTracks().forEach((t) => pc.addTrack(t, localStream));
  pc.ontrack = (event) => attach(peer, event.streams[0]);
  pc.onicecandidate = (event) => {
    if (event.candidate) post('/api/signal', {from: me, to: peer, kind: 'ice', data: event.candidate});
  };
  if (initiate) {
    const offer = await pc.createOffer({offerToReceiveAudio: true});
    await pc.setLocalDescription(offer);
    await post('/api/signal', {from: me, to: peer, kind: 'offer', data: offer});
  }
  return pc;
};

const pump = async () => {
  const state = await fetch(`${MOUNT}/api/poll?peer=${encodeURIComponent(me)}&since=${since}`).then((r) => r.json());
  since = state.seq;
  for (const signal of state.signals) {
    const pc = await connect(signal.from, false);
    if (signal.kind === 'offer') {
      await pc.setRemoteDescription(signal.data);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      await post('/api/signal', {from: me, to: signal.from, kind: 'answer', data: answer});
    } else if (signal.kind === 'answer') {
      if (!pc.currentRemoteDescription) await pc.setRemoteDescription(signal.data);
    } else if (signal.kind === 'ice') {
      try { await pc.addIceCandidate(signal.data); } catch (_) {}
    }
  }
};

window.joinRoom = async ({peer, inCall = true, mic = true, speaker = true}) => {
  me = peer; micOn = mic; speakerOn = speaker;
  if (inCall) {
    localStream = await navigator.mediaDevices.getUserMedia({audio: true});
    localStream.getAudioTracks().forEach((t) => { t.enabled = micOn; });
  }
  const joined = await post('/api/join', {peer, in_call: inCall});
  for (const other of joined.peers) await connect(other, true);
  setInterval(pump, 250);
  setState(inCall ? (micOn ? 'speaking' : 'mic-off') : (speakerOn ? 'listening' : 'speaker-off'));
  return joined.peers.length;
};

// Toggling is a live change on an established call, which is the only way to
// test that muting works rather than that a session started muted.
window.setMic = (on) => {
  micOn = on;
  if (localStream) localStream.getAudioTracks().forEach((t) => { t.enabled = on; });
  setState(on ? 'speaking' : 'mic-off');
  return micOn;
};

window.setSpeaker = (on) => {
  speakerOn = on;
  document.querySelectorAll('#audio audio').forEach((el) => { el.muted = !on; });
  setState(on ? 'listening' : 'speaker-off');
  return speakerOn;
};
</script>"""
