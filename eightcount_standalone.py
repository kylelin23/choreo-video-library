#!/usr/bin/env python3
"""
8-count rhythm analysis - single-file edition.

Detects the beat grid, downbeats, and 8-count boundaries in a dance video or
audio file, and maps them to video frame numbers.

This is the whole pipeline in one file. The maintained, tested version lives at
https://github.com/PatrickKumar27/8count-rhythm-analysis (57 tests, Flask API,
correction endpoints). This file exists to be copied somewhere and run.

    pip install librosa soundfile numpy
    # plus ffmpeg on the system:
    #   Windows: winget install Gyan.FFmpeg
    #   macOS:   brew install ffmpeg
    #   Debian:  sudo apt install ffmpeg

Usage:
    python eightcount_standalone.py counts  clip.mp4
    python eightcount_standalone.py analyze clip.mp4 -o result.json
    python eightcount_standalone.py preview clip.mp4 -o preview.mp4

`preview` is the one that tells you whether it actually worked: it renders the
detected grid back over your audio as a click track, with a loud accent on the
"1" of every 8-count. If the accents land where you would say "one", the grid is
right. If they land on your "five", it is offset by half an 8-count.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

# --------------------------------------------------------------------------
# Tunables
# --------------------------------------------------------------------------

TARGET_SR = 22050      # librosa's native rate; keeps resampling out of the hot path
HOP_LENGTH = 512
DEFAULT_FPS = 30.0
BEATS_PER_EIGHT_COUNT = 8

# One hop at 22050Hz is ~23ms and tracked beat times sit ~18ms off the true
# transient, so reading the envelope exactly at the beat frame samples the frame
# before or after the peak at random. Taking the max over +/-1 frame fixes it.
ENVELOPE_WINDOW_FRAMES = 1

# The kick is the downbeat cue in dance music, and it lives here.
LOW_BAND_HZ = (30.0, 130.0)
# Low-band share of total energy required before trusting the kick cue. Realistic
# drum material measures 0.04-0.09; bass-free click tracks 0.013-0.018.
BASS_PRESENCE_MIN = 0.03
LOW_BAND_MIN_MARGIN = 0.05   # the two paths score on different scales, so they
FALLBACK_MIN_MARGIN = 0.02   # are calibrated separately

LOW_CONFIDENCE_THRESHOLD = 0.6
TEMPO_DISCONTINUITY_RATIO = 0.15


class FFmpegNotFound(RuntimeError):
    pass


class AudioExtractionError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# ffmpeg discovery and audio extraction
# --------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _binary(name: str) -> str:
    """Locate ffmpeg/ffprobe, falling back to well-known install locations.

    PATH alone is not enough on Windows: `winget install Gyan.FFmpeg` unpacks a
    portable build under WinGet\\Packages and writes no shims to WinGet\\Links, so
    the tools never reach PATH and "reopen your terminal" cannot help.
    """
    found = shutil.which(name)
    if found:
        return found

    exe = f"{name}.exe" if os.name == "nt" else name
    candidates: list[Path] = []

    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        if local.name:
            candidates.append(local / "Microsoft" / "WinGet" / "Links" / exe)
            packages = local / "Microsoft" / "WinGet" / "Packages"
            if packages.is_dir():
                candidates.extend(sorted(packages.glob(f"*/*/bin/{exe}"), reverse=True))
        candidates += [
            Path(r"C:\ProgramData\chocolatey\bin") / exe,
            Path(r"C:\Program Files\ffmpeg\bin") / exe,
        ]
    else:
        candidates += [Path("/opt/homebrew/bin") / exe, Path("/usr/local/bin") / exe]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FFmpegNotFound(
        f"{name} not found. Install it and reopen your terminal:\n"
        "  Windows:  winget install Gyan.FFmpeg\n"
        "  macOS:    brew install ffmpeg\n"
        "  Debian:   sudo apt install ffmpeg"
    )


@dataclass
class MediaInfo:
    duration_sec: float
    fps: float
    has_audio: bool
    has_video: bool = True

    def frame_at(self, timestamp_sec: float) -> int:
        return int(round(timestamp_sec * self.fps))


def probe(path: Path) -> MediaInfo:
    cmd = [_binary("ffprobe"), "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioExtractionError(f"ffprobe failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    fps = DEFAULT_FPS
    if video_streams:
        raw = video_streams[0].get("avg_frame_rate") or "0/0"   # e.g. "30000/1001"
        try:
            num, _, den = raw.partition("/")
            if float(den or 0) > 0 and float(num) > 0:
                fps = float(num) / float(den)
        except (ValueError, ZeroDivisionError):
            pass

    return MediaInfo(
        duration_sec=float(data.get("format", {}).get("duration", 0.0) or 0.0),
        fps=fps, has_audio=has_audio, has_video=bool(video_streams),
    )


def _measure_peak_db(path: Path) -> float:
    result = subprocess.run(
        [_binary("ffmpeg"), "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    match = re.search(r"max_volume:\s*(-?[\d.]+) dB", result.stderr)
    return float(match.group(1)) if match else 0.0


def extract_audio(path: Path, out_wav: Path, *, highpass_hz: int | None = 80,
                  target_peak_db: float = -1.0) -> Path:
    """Extract mono WAV at TARGET_SR, peak-normalised, optionally high-passed.

    Normalisation is deliberately *peak*, not loudness. ffmpeg's `loudnorm` is
    EBU R128 with dynamic range compression, which flattens the amplitude
    difference between the emphasised downbeat kick and the rest of the bar - and
    that difference is exactly the cue downbeat detection depends on. Measured on
    drum fixtures, loudnorm drops the downbeat phase margin below the review
    threshold while peak normalisation keeps it strong.
    """
    filters = []
    if highpass_hz:
        filters.append(f"highpass=f={highpass_hz}")
    filters.append(f"volume={target_peak_db - _measure_peak_db(path):.2f}dB")

    result = subprocess.run(
        [_binary("ffmpeg"), "-y", "-i", str(path), "-vn", "-ac", "1",
         "-ar", str(TARGET_SR), "-af", ",".join(filters), "-c:a", "pcm_s16le",
         str(out_wav)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AudioExtractionError(f"ffmpeg failed: {result.stderr.strip()[-800:]}")
    if not out_wav.exists() or out_wav.stat().st_size == 0:
        raise AudioExtractionError("no audio produced - does the file have an audio track?")
    return out_wav


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf
    audio, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, sr


# --------------------------------------------------------------------------
# Beat and downbeat detection
# --------------------------------------------------------------------------

@dataclass
class RawBeat:
    timestamp_sec: float
    beat_in_measure: int   # 1-indexed; 1 == downbeat
    confidence: float

    @property
    def is_downbeat(self) -> bool:
        return self.beat_in_measure == 1


def _sample_envelope(env: np.ndarray, frames: np.ndarray) -> np.ndarray:
    w, n = ENVELOPE_WINDOW_FRAMES, len(env)
    return np.array([
        env[max(0, f - w):min(n, f + w + 1)].max()
        if min(n, f + w + 1) > max(0, f - w) else 0.0
        for f in frames
    ])


def _low_band_energy(audio: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    import librosa
    spectrum = np.abs(librosa.stft(audio, hop_length=HOP_LENGTH))
    freqs = librosa.fft_frequencies(sr=sr)
    band = (freqs >= LOW_BAND_HZ[0]) & (freqs <= LOW_BAND_HZ[1])
    total = spectrum.sum()
    low = spectrum[band]
    return low.sum(axis=0), (float(low.sum() / total) if total > 0 else 0.0)


def detect_beats(audio: np.ndarray, sr: int, beats_per_measure: int = 4):
    """Return (beats, bpm, meter_confident, notes).

    Downbeat placement scores *low-band energy*, not full-band onset strength.
    That choice matters more than anything else here: a snare's broadband burst
    carries far more spectral flux than a low kick, so full-band onset selects
    beat 2 of a normal drum pattern. Measured across fixtures, full-band was
    correct 4 times in 9 (chance); low-band energy 8 in 9, and 5 of 5 on
    realistic drum patterns. On real footage the two cues actively disagree and
    the low-band pick is the correct one.
    """
    import librosa

    onset_env = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=HOP_LENGTH)
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr, hop_length=HOP_LENGTH, units="frames")
    beat_frames = np.asarray(beat_frames, dtype=int)
    bpm = float(np.atleast_1d(tempo)[0])

    if beat_frames.size == 0:
        return [], bpm, False, "no rhythmic pulse detected"

    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP_LENGTH)
    strengths = _sample_envelope(onset_env, beat_frames)

    low_env, bass_share = _low_band_energy(audio, sr)
    if bass_share >= BASS_PRESENCE_MIN:
        feature, cue, threshold = (_sample_envelope(low_env, beat_frames),
                                   "low-band kick", LOW_BAND_MIN_MARGIN)
    else:
        feature, cue, threshold = strengths, "full-band onset", FALLBACK_MIN_MARGIN

    n = beats_per_measure
    scores = np.array([feature[p::n].mean() if feature[p::n].size else 0.0
                       for p in range(n)])
    total = scores.sum()
    if total <= 0:
        phase, margin = 0, 0.0
    else:
        normalised = scores / total
        order = np.argsort(normalised)[::-1]
        phase = int(order[0])
        margin = float(normalised[order[0]] - normalised[order[1]]) if n > 1 else 1.0

    confidences = _score_beats(strengths, beat_times)
    beats = [
        RawBeat(float(t), int((i - phase) % n) + 1, float(c))
        for i, (t, c) in enumerate(zip(beat_times, confidences))
    ]

    confident = margin >= threshold
    notes = "" if confident else (
        f"downbeat is ambiguous ({cue} cue, margin {margin:.4f} < {threshold}). "
        "Beat positions are still reliable, but the count sheet may be offset. "
        "Re-anchor once and the rest of the grid follows."
    )
    return beats, bpm, confident, notes


def _score_beats(strengths: np.ndarray, beat_times: np.ndarray) -> np.ndarray:
    """Heuristic per-beat confidence in [0, 1].

    Unlike a trained model, librosa exposes no per-beat probability, so this is a
    derived proxy blending onset salience with local interval regularity. Treat it
    as a ranking, not a calibrated number.
    """
    ref = np.percentile(strengths, 90) if strengths.size else 0.0
    salience = np.clip(strengths / ref, 0.0, 1.0) if ref > 0 else np.zeros_like(strengths)
    if beat_times.size < 3:
        return salience

    intervals = np.diff(beat_times)
    median_ibi = float(np.median(intervals))
    if median_ibi <= 0:
        return salience

    padded = np.concatenate([[median_ibi], intervals, [median_ibi]])
    local_dev = np.minimum(np.abs(padded[:-1] - median_ibi),
                           np.abs(padded[1:] - median_ibi)) / median_ibi
    return np.clip(0.6 * salience + 0.4 * np.clip(1.0 - local_dev, 0.0, 1.0), 0.0, 1.0)


# --------------------------------------------------------------------------
# 8-count grouping
# --------------------------------------------------------------------------

def group_into_eight_counts(beats: list[RawBeat], beats_per_measure: int = 4,
                            anchor_sec: float | None = None) -> list[list[RawBeat]]:
    """Group beats into 8-counts, opening a group on every *other* downbeat.

    Note this differs from the obvious reading of the spec, which starts a new
    group at every downbeat - in 4/4 that yields 4-beat groups, i.e. one measure,
    not an 8-count. An 8-count is two measures.

    Grouping anchors on downbeat parity rather than chunking the list into eights,
    so a single dropped beat corrupts one group instead of shifting every group
    after it.
    """
    if not beats:
        return []

    measures_per_group = max(1, BEATS_PER_EIGHT_COUNT // beats_per_measure)
    downbeat_indices = [i for i, b in enumerate(beats) if b.is_downbeat]
    if not downbeat_indices:
        return [beats[i:i + BEATS_PER_EIGHT_COUNT]
                for i in range(0, len(beats), BEATS_PER_EIGHT_COUNT)]

    anchor_ordinal = 0
    if anchor_sec is not None:
        anchor_ordinal = min(
            range(len(downbeat_indices)),
            key=lambda k: abs(beats[downbeat_indices[k]].timestamp_sec - anchor_sec))

    openers = {idx for k, idx in enumerate(downbeat_indices)
               if (k - anchor_ordinal) % measures_per_group == 0}

    groups: list[list[RawBeat]] = []
    current: list[RawBeat] = []
    for i, beat in enumerate(beats[downbeat_indices[0]:], start=downbeat_indices[0]):
        if i in openers and current:
            groups.append(current)
            current = []
        current.append(beat)
    if current:
        groups.append(current)
    return groups


def reanchor(beats: list[RawBeat], anchor_sec: float,
             beats_per_measure: int = 4) -> list[RawBeat]:
    """Relabel beats so the one nearest anchor_sec becomes a downbeat.

    A pure relabel - detection never reruns, which is what makes correction
    instant.
    """
    if not beats:
        return []
    anchor_idx = min(range(len(beats)),
                     key=lambda i: abs(beats[i].timestamp_sec - anchor_sec))
    return [
        b if i < anchor_idx else
        RawBeat(b.timestamp_sec, (i - anchor_idx) % beats_per_measure + 1, b.confidence)
        for i, b in enumerate(beats)
    ]


# --------------------------------------------------------------------------
# Result assembly
# --------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    video_id: str
    duration_sec: float
    fps: float
    bpm_estimate: float
    meter: str
    beats: list[dict[str, Any]] = field(default_factory=list)
    eight_counts: list[dict[str, Any]] = field(default_factory=list)
    review_flags: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "duration_sec": round(self.duration_sec, 3),
            "fps": self.fps,
            "bpm_estimate": round(self.bpm_estimate, 2),
            "meter": self.meter,
            "beats": self.beats,
            "eight_counts": self.eight_counts,
            "review_flags": self.review_flags,
        }


def analyze(path: Path, *, fps_override: float | None = None,
            anchor_sec: float | None = None) -> AnalysisResult:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() in {".wav", ".flac", ".ogg"}:
        audio, sr = load_wav(path)
        media = MediaInfo(len(audio) / sr, fps_override or DEFAULT_FPS,
                          has_audio=True, has_video=False)
    else:
        media = probe(path)
        if not media.has_audio:
            raise ValueError(f"{path.name} has no audio track to analyse")
        if not media.has_video and fps_override:
            media = MediaInfo(media.duration_sec, fps_override, True, False)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            extract_audio(path, wav)
            audio, sr = load_wav(wav)

    beats, bpm, confident, notes = detect_beats(audio, sr)

    if anchor_sec is not None and beats:
        # Two distinct things have to move together, and doing only one is a
        # silent no-op whenever the anchor already happens to open a group:
        # relabel the beats so the anchor becomes a downbeat, *and* re-phase the
        # grouping so that downbeat opens an 8-count.
        beats = reanchor(beats, anchor_sec)
        anchor_sec = min(beats, key=lambda b: abs(b.timestamp_sec - anchor_sec)).timestamp_sec
        confident = True  # a hand-placed anchor overrides the detector's doubt

    groups = group_into_eight_counts(beats, 4, anchor_sec=anchor_sec)

    flags: list[dict[str, Any]] = []
    if not beats:
        flags.append({"count_index": -1, "reason": "no_beats_detected",
                      "detail": "no rhythmic pulse - ballad, a cappella, or rubato"})
    elif not confident:
        flags.append({"count_index": -1, "reason": "low_confidence", "detail": notes})

    eight_counts: list[dict[str, Any]] = []
    durations: list[tuple[int, float]] = []
    for idx, group in enumerate(groups):
        if not group:
            continue
        avg_conf = sum(b.confidence for b in group) / len(group)
        start = group[0].timestamp_sec
        end = group[-1].timestamp_sec
        if len(group) > 1:
            end += sum(group[i + 1].timestamp_sec - group[i].timestamp_sec
                       for i in range(len(group) - 1)) / (len(group) - 1)

        needs_review = False
        if len(group) != 8:
            flags.append({"count_index": idx, "reason": "wrong_beat_count",
                          "detail": f"group contains {len(group)} beats, expected 8",
                          "avg_confidence": round(avg_conf, 4)})
            needs_review = True
        if avg_conf < LOW_CONFIDENCE_THRESHOLD:
            flags.append({"count_index": idx, "reason": "low_confidence",
                          "detail": f"average beat confidence {avg_conf:.2f} below "
                                    f"{LOW_CONFIDENCE_THRESHOLD}",
                          "avg_confidence": round(avg_conf, 4)})
            needs_review = True

        if len(group) == 8 and end > start:
            durations.append((idx, end - start))

        eight_counts.append({
            "count_index": idx,
            "start_sec": round(start, 4), "end_sec": round(end, 4),
            "start_frame": media.frame_at(start), "end_frame": media.frame_at(end),
            "beat_count": len(group), "avg_confidence": round(avg_conf, 4),
            "needs_review": needs_review,
        })

    # Compare each group to its predecessor, not the track median: with a tempo
    # change near the midpoint the median sits between the two tempi and both
    # halves stay inside the threshold while the jump between them is obvious.
    for (prev_i, prev_d), (i, d) in zip(durations, durations[1:]):
        if prev_d > 0 and abs(d - prev_d) / prev_d > TEMPO_DISCONTINUITY_RATIO:
            flags.append({"count_index": i, "reason": "tempo_discontinuity",
                          "detail": f"8-count spans {d:.2f}s vs {prev_d:.2f}s for "
                                    f"#{prev_i} - possible tempo change"})
            eight_counts[i]["needs_review"] = True

    return AnalysisResult(
        video_id=str(uuid.uuid4()),
        duration_sec=media.duration_sec, fps=media.fps,
        bpm_estimate=bpm, meter="4/4",
        beats=[{"timestamp_sec": round(b.timestamp_sec, 4),
                "frame": media.frame_at(b.timestamp_sec),
                "beat_in_measure": b.beat_in_measure,
                "is_downbeat": b.is_downbeat,
                "confidence": round(b.confidence, 4)} for b in beats],
        eight_counts=eight_counts, review_flags=flags,
    )


# --------------------------------------------------------------------------
# Click-track preview
# --------------------------------------------------------------------------

def _tick(freq: float, amp: float, ms: float, sr: int) -> np.ndarray:
    n = int(ms / 1000 * sr)
    t = np.arange(n) / sr
    return (amp * np.sin(2 * np.pi * freq * t) * np.exp(-t * (5000 / ms))).astype(np.float32)


def write_preview(src: Path, out: Path, result: AnalysisResult,
                  music_level: float = 0.7, click_level: float = 0.9) -> Path:
    """Mux a click track onto the source so the grid can be checked by ear.

    Deliberately bypasses the analysis-path filtering (high-pass, mono, 22050Hz):
    this output is for listening, not detection.
    """
    import soundfile as sf

    sr = 44100
    ones = {c["start_sec"] for c in result.eight_counts}

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "src.wav"
        subprocess.run([_binary("ffmpeg"), "-y", "-i", str(src), "-vn", "-ac", "2",
                        "-ar", str(sr), "-c:a", "pcm_s16le", str(wav)],
                       capture_output=True, check=True)

        audio, sr = sf.read(str(wav), dtype="float32", always_2d=True)
        audio = audio * music_level
        accent = _tick(1800, click_level, 60, sr)
        tick = _tick(1100, click_level * 0.35, 35, sr)

        for beat in result.beats:
            click = accent if beat["timestamp_sec"] in ones else tick
            start = int(beat["timestamp_sec"] * sr)
            end = min(start + len(click), len(audio))
            if end > start:
                audio[start:end] += click[: end - start, None]

        peak = float(np.max(np.abs(audio)))
        if peak > 1.0:
            audio /= peak * 1.02

        mixed = Path(tmp) / "mixed.wav"
        sf.write(str(mixed), audio, sr)

        has_video = probe(src).has_video
        cmd = [_binary("ffmpeg"), "-y", "-i", str(src), "-i", str(mixed)]
        if has_video:
            cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"]
        else:
            cmd += ["-map", "1:a:0"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]
        subprocess.run(cmd, capture_output=True, check=True)

    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print_counts(result: AnalysisResult, limit: int, audio_only: bool) -> None:
    print(f"{result.bpm_estimate:.1f} BPM | {result.meter} | {len(result.beats)} beats "
          f"| {len(result.eight_counts)} eight-counts")
    note = "  (assumed - audio input has no frame rate)" if audio_only else ""
    print(f"duration {result.duration_sec:.2f}s @ {result.fps:.2f}fps{note}\n")

    for c in result.eight_counts[:limit]:
        mark = "!" if c["needs_review"] else " "
        print(f"{mark} #{c['count_index']:<4} {c['start_sec']:8.3f}s -> {c['end_sec']:8.3f}s  "
              f"frames {c['start_frame']:>6}-{c['end_frame']:<6} "
              f"beats={c['beat_count']} conf={c['avg_confidence']:.2f}")
    if len(result.eight_counts) > limit:
        print(f"  ... {len(result.eight_counts) - limit} more")

    if result.review_flags:
        print(f"\n{len(result.review_flags)} review flag(s):")
        for f in result.review_flags[:limit]:
            where = "track" if f["count_index"] < 0 else f"#{f['count_index']}"
            print(f"  [{f['reason']}] {where}: {f['detail']}")
    else:
        print("\nno review flags")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:                       # Windows consoles default to cp1252
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="eightcount_standalone",
        description="Detect beats, downbeats, and 8-counts in dance video or audio.")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("input", help="video or audio file")
    common.add_argument("--fps", type=float, default=None,
                        help="frame rate to assume for audio-only input. Ignored "
                             "for video, where the real rate is read from the file.")
    common.add_argument("--anchor", type=float, default=None,
                        help="treat the beat nearest this timestamp as a downbeat")

    p = sub.add_parser("counts", parents=[common], help="print a readable count sheet")
    p.add_argument("--limit", type=int, default=20)

    p = sub.add_parser("analyze", parents=[common], help="emit the full JSON timeline")
    p.add_argument("-o", "--output")

    p = sub.add_parser("preview", parents=[common],
                       help="render the grid as a click track for listening")
    p.add_argument("-o", "--output", default="preview.mp4")

    args = parser.parse_args(argv)

    try:
        src = Path(args.input)
        result = analyze(src, fps_override=args.fps, anchor_sec=args.anchor)

        if args.command == "counts":
            audio_only = src.suffix.lower() not in {
                ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}
            _print_counts(result, args.limit, audio_only)

        elif args.command == "analyze":
            payload = json.dumps(result.to_dict(), indent=2)
            if args.output:
                Path(args.output).write_text(payload, encoding="utf-8")
                print(f"wrote {args.output}")
            else:
                print(payload)

        elif args.command == "preview":
            print(f"analysing {src.name} ...")
            print(f"  {result.bpm_estimate:.1f} BPM, {len(result.beats)} beats, "
                  f"{len(result.eight_counts)} eight-counts")
            out = write_preview(src, Path(args.output), result)
            print(f"\nwrote {out}")
            print("The loud accent is the '1' of each 8-count.")
            print("  lands on your 'one'  -> grid is correct")
            print("  lands on your 'five' -> offset by half an 8-count, re-anchor once")
            print("  drifts out over time -> tempo problem")
        return 0

    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
