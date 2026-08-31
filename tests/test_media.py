from __future__ import annotations

from parallax.media import (
    AUDIO_RECEIVED,
    INSTRUMENT_MEDIA,
    MEDIA_BROWSER_ARGS,
    VIDEO_RECEIVED,
    MediaExpectation,
    media_probe,
    perceived,
    speaking_args,
)


def test_audio_is_judged_on_energy_and_never_on_a_volume_setting() -> None:
    """`volume` reads 1.0 whether or not sound is arriving; it is a setting.

    Measured live on a two-peer call: speaking reported level 1.0254 and muted
    reported 0.0000, while packetsReceived was 175 and 174. Packet counting
    cannot separate the two — a muted participant negotiates and receives
    exactly like a listening one — so energy is the only reading that decides.
    """
    # Volume is a legitimate *gate* — it decides whether an element would play
    # at all — and never a *level*. The level always comes from the signal.
    assert "Math.max(result.level, el.volume)" not in AUDIO_RECEIVED
    assert "el.volume > 0) audible.push" in AUDIO_RECEIVED
    assert "getFloatTimeDomainData" in AUDIO_RECEIVED
    assert "result.level >= minLevel && result.packets >= minPackets" in AUDIO_RECEIVED


def test_silence_is_not_perceived_however_many_packets_arrived() -> None:
    expectation = MediaExpectation("audio_received")

    assert perceived(expectation, {"heard": False, "level": 0.0, "packets": 174}) is False
    assert perceived(expectation, {"heard": True, "level": 1.02, "packets": 175}) is True


def test_an_unreadable_page_measures_as_silence_rather_than_as_success() -> None:
    expectation = MediaExpectation("audio_received")

    assert perceived(expectation, None) is False
    assert perceived(expectation, "boom") is False
    assert perceived(expectation, {}) is False


def test_video_is_judged_on_decoded_frames() -> None:
    expectation = MediaExpectation("video_received", min_frames=5)

    assert perceived(expectation, {"seen": True, "frames": 30}) is True
    assert perceived(expectation, {"seen": False, "frames": 0}) is False


def test_each_expectation_carries_its_own_thresholds_to_the_page() -> None:
    script, arguments = media_probe(MediaExpectation("audio_received", min_level=0.2, min_packets=9))

    assert script is AUDIO_RECEIVED
    assert arguments == {"minLevel": 0.2, "minPackets": 9, "windowMs": 400, "passes": 3}

    script, arguments = media_probe(MediaExpectation("video_received", min_frames=12))

    assert script is VIDEO_RECEIVED
    assert arguments == {"minFrames": 12}


def test_the_instrumentation_observes_and_never_substitutes_behaviour() -> None:
    """Wrapping the constructor is how connections become reachable at all.

    It must remain a recording: a wrapper that dropped a method or changed the
    prototype would alter the call it is supposed to be watching.
    """
    assert "Wrapped.prototype = NativeRTC.prototype" in INSTRUMENT_MEDIA
    assert "for (const key of Object.keys(NativeRTC)) Wrapped[key] = NativeRTC[key]" in INSTRUMENT_MEDIA
    assert "state.connections.push(connection)" in INSTRUMENT_MEDIA
    assert "if (window.__parallaxMedia) return" in INSTRUMENT_MEDIA


def test_a_speaking_session_is_given_a_microphone_and_permission_to_play() -> None:
    """A silent participant is indistinguishable from a muted one."""
    args = speaking_args()

    assert set(MEDIA_BROWSER_ARGS) <= set(args)
    assert "--autoplay-policy=no-user-gesture-required" in args


def test_a_supplied_recording_is_played_into_the_fake_microphone() -> None:
    args = speaking_args("/tmp/speech.wav")

    assert any(arg.startswith("--use-file-for-fake-audio-capture=/tmp/speech.wav") for arg in args)


def test_arriving_and_being_heard_are_different_questions() -> None:
    """A listener who mutes their speaker still receives everything.

    Measured on a live two-peer call with the listener's speaker muted: the
    received signal carried a peak of 1.0282 while the audible peak was 0.0000.
    Muting a speaker is a decision about playback, so a check that conflated the
    two would report a working mute as a propagation failure.
    """
    measurement = {"heard": True, "audible": False, "level": 1.0282, "audibleLevel": 0.0}

    assert perceived(MediaExpectation("audio_received"), measurement) is True
    assert perceived(MediaExpectation("audio_audible"), measurement) is False


def test_a_muted_microphone_stops_both_of_them() -> None:
    """Nothing arrives, so nothing can be played — packets keep climbing anyway."""
    measurement = {"heard": False, "audible": False, "level": 0.0, "packets": 567}

    assert perceived(MediaExpectation("audio_received"), measurement) is False
    assert perceived(MediaExpectation("audio_audible"), measurement) is False


def test_both_audio_kinds_share_one_page_measurement() -> None:
    received, _ = media_probe(MediaExpectation("audio_received"))
    audible, _ = media_probe(MediaExpectation("audio_audible"))

    assert received is audible is AUDIO_RECEIVED
