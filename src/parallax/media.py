"""Sense what a session actually received, when the evidence is not in the DOM.

The relational vocabulary can ask whether an element became visible or whether
an endpoint returned a value. Neither question reaches the thing a call is: a
participant who can hear leaves no mark on the page, and a participant who has
muted looks identical to one who is listening. "Did B hear A speak" is the same
shape of question as "did B see A's message" — one actor, several simultaneous
observers, each with its own expectation — and only the sensor differs.

Two problems stand between that and a measurement, and both are solved here.

A page's `RTCPeerConnection` objects are not reachable from outside unless the
application chose to expose them, and no application does. The constructor is
therefore wrapped before any page script runs, so every connection the
application creates registers itself. This observes; it never alters what is
sent, received, or negotiated.

And an audio track that exists is not an audio track that carries sound. A muted
microphone still produces a stream, still negotiates, still increments the
packet counters — so presence proves nothing. What separates hearing from
silence is energy, which `getStats` reports as `audioLevel` on the inbound
track, and which the Web Audio API can measure directly from the remote stream.
Both are read, and the louder answer wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Installed with add_init_script, so it runs before the application's own code in
# every page of every witness. Read-only: it records the connections and leaves
# their behaviour untouched.
INSTRUMENT_MEDIA = """
(() => {
  if (window.__parallaxMedia) return;
  const state = { connections: [], streams: [] };
  window.__parallaxMedia = state;

  const NativeRTC = window.RTCPeerConnection;
  if (NativeRTC) {
    const Wrapped = function (...args) {
      const connection = new NativeRTC(...args);
      state.connections.push(connection);
      connection.addEventListener('track', (event) => {
        if (event.streams && event.streams[0]) state.streams.push(event.streams[0]);
      });
      return connection;
    };
    Wrapped.prototype = NativeRTC.prototype;
    for (const key of Object.keys(NativeRTC)) Wrapped[key] = NativeRTC[key];
    window.RTCPeerConnection = Wrapped;
    if (window.webkitRTCPeerConnection === NativeRTC) window.webkitRTCPeerConnection = Wrapped;
  }
})();
"""


# Answers "is sound arriving now", not "is a track present". A muted participant
# negotiates and receives packets exactly like a listening one.
AUDIO_RECEIVED = """
async ({ minLevel, minPackets, windowMs }) => {
  const state = window.__parallaxMedia;
  const result = { level: 0, packets: 0, connections: 0, streams: 0, source: 'none' };

  // Energy, measured from the received signal. This is the only reading that
  // separates hearing from silence: a muted participant still negotiates, still
  // receives packets, and still has a track. `volume` is a playback setting and
  // reads 1.0 whether or not any sound is arriving, so it is never consulted.
  const peakOf = async (stream) => {
    let context;
    try {
      context = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      context.createMediaStreamSource(stream).connect(analyser);
      const buffer = new Float32Array(analyser.fftSize);
      let peak = 0;
      const deadline = performance.now() + windowMs;
      while (performance.now() < deadline) {
        analyser.getFloatTimeDomainData(buffer);
        for (let i = 0; i < buffer.length; i += 1) {
          const magnitude = Math.abs(buffer[i]);
          if (magnitude > peak) peak = magnitude;
        }
        await new Promise((done) => setTimeout(done, 20));
      }
      return peak;
    } catch (_) {
      return 0;
    } finally {
      if (context) { try { await context.close(); } catch (_) {} }
    }
  };

  const streams = [];
  if (state) {
    result.connections = state.connections.length;
    for (const stream of state.streams) {
      if (stream.getAudioTracks().length) streams.push(stream);
    }
    for (const connection of state.connections) {
      let report;
      try { report = await connection.getStats(); } catch (_) { continue; }
      report.forEach((entry) => {
        if (entry.type !== 'inbound-rtp' || entry.kind !== 'audio') return;
        result.packets = Math.max(result.packets, entry.packetsReceived || 0);
        if (typeof entry.audioLevel === 'number' && entry.audioLevel > result.level) {
          result.level = entry.audioLevel;
          result.source = 'getStats';
        }
      });
    }
  }
  for (const el of document.querySelectorAll('audio, video')) {
    if (el.paused || el.muted || !(el.currentTime > 0)) continue;
    if (el.srcObject && el.srcObject.getAudioTracks && el.srcObject.getAudioTracks().length) {
      streams.push(el.srcObject);
    }
  }
  result.streams = streams.length;
  for (const stream of streams.slice(0, 3)) {
    const peak = await peakOf(stream);
    if (peak > result.level) { result.level = peak; result.source = 'analyser'; }
  }

  result.heard = result.level >= minLevel && result.packets >= minPackets;
  return result;
}
"""


VIDEO_RECEIVED = """
async ({ minFrames }) => {
  const state = window.__parallaxMedia;
  const result = { frames: 0, playing: 0 };
  if (state) {
    for (const connection of state.connections) {
      let report;
      try { report = await connection.getStats(); } catch (_) { continue; }
      report.forEach((entry) => {
        if (entry.type === 'inbound-rtp' && entry.kind === 'video') {
          result.frames = Math.max(result.frames, entry.framesDecoded || 0);
        }
      });
    }
  }
  for (const el of document.querySelectorAll('video')) {
    // A <video> that is painting frames reports them whether or not WebRTC is
    // involved, so a plain player is measured the same way a call is.
    const quality = el.getVideoPlaybackQuality ? el.getVideoPlaybackQuality() : null;
    if (quality) result.frames = Math.max(result.frames, quality.totalVideoFrames || 0);
    if (!el.paused && el.currentTime > 0) result.playing += 1;
  }
  result.seen = result.frames >= minFrames || result.playing > 0;
  return result;
}
"""


@dataclass(frozen=True)
class MediaExpectation:
    """A declared media effect, kept in the same data-only shape as the rest."""

    kind: str  # "audio_received" | "video_received"
    min_level: float = 0.01
    min_packets: int = 5
    min_frames: int = 5
    # Long enough to catch a syllable, short enough that several observers can be
    # measured inside one scenario deadline.
    window_ms: int = 400

    def describe(self) -> str:
        if self.kind == "audio_received":
            return f"audio at level ≥ {self.min_level}"
        return f"video with ≥ {self.min_frames} decoded frames"


def media_probe(expectation: MediaExpectation) -> tuple[str, dict[str, Any]]:
    """The page-side measurement and its arguments for one declared expectation."""
    if expectation.kind == "audio_received":
        return AUDIO_RECEIVED, {
            "minLevel": expectation.min_level,
            "minPackets": expectation.min_packets,
            "windowMs": expectation.window_ms,
        }
    return VIDEO_RECEIVED, {"minFrames": expectation.min_frames}


def perceived(expectation: MediaExpectation, measurement: Any) -> bool:
    """Read one measurement, treating an unreadable page as silence."""
    if not isinstance(measurement, dict):
        return False
    return bool(measurement.get("heard" if expectation.kind == "audio_received" else "seen"))


# Chromium needs telling that it may use a synthetic microphone and play without
# a gesture. Without the last flag a headless page negotiates the call and then
# never starts the audio element, which measures as silence and looks like a bug
# in the application rather than in the harness.
MEDIA_BROWSER_ARGS = (
    "--use-fake-device-for-media-stream",
    "--use-fake-ui-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
)


def speaking_args(wav_path: str | None = None) -> list[str]:
    """Browser flags that make this session speak, rather than merely connect.

    A silent participant is indistinguishable from a muted one, so a call test
    that does not inject audio cannot fail for the right reason. The file is
    played on a loop into the fake microphone.
    """
    args = list(MEDIA_BROWSER_ARGS)
    if wav_path:
        args.append(f"--use-file-for-fake-audio-capture={wav_path}%noloop")
    return args
