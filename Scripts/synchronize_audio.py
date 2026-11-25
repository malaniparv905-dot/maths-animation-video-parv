#!/usr/bin/env python3
"""
Scene-Based Voiceover Synchronization & Natural Audio Processing Pipeline.

Reads `Scripts/scenes_manifest.json`, inspects every user-recorded scene audio
file in `Voiceover/`, applies gentle, natural audio engineering (no voice
alteration or speed-up), adjusts visual scene timing via unified-colorspace
`tpad=stop_mode=clone` holds (or static tail trims), and outputs a continuous
synchronized master audio + preview MP4 ready for final export.
"""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple


SUPPORTED_EXTS = (".wav", ".m4a", ".mp3", ".flac", ".aac")


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Execute a subprocess command and capture text output."""
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def ffprobe_info(path: Path) -> Dict:
    """Return parsed JSON format & stream metadata from ffprobe."""
    res = run_cmd([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    return json.loads(res.stdout)


def get_duration(path: Path) -> float:
    """Return media duration in seconds using ffprobe."""
    info = ffprobe_info(path)
    return float(info["format"]["duration"])


def find_scene_audio(voiceover_dir: Path, stem: str) -> Optional[Path]:
    """Locate a scene recording matching `stem` across supported audio formats."""
    for ext in SUPPORTED_EXTS:
        candidate = voiceover_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def detect_speech_bounds(
    audio_path: Path,
    seg_start: float,
    seg_end: float,
    margin_sec: float = 0.08,
) -> Tuple[float, float]:
    """
    Detect leading and trailing silence inside [seg_start, seg_end] via ffmpeg
    silencedetect and return safe trim bounds preserving `margin_sec` of breath.
    """
    seg_dur = max(0.1, seg_end - seg_start)
    res = run_cmd([
        "ffmpeg", "-hide_banner", "-ss", f"{seg_start:.4f}", "-t", f"{seg_dur:.4f}",
        "-i", str(audio_path),
        "-af", "silencedetect=noise=-42dB:d=0.20",
        "-f", "null", "-",
    ], check=False)
    stderr = res.stderr
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", stderr)]

    trim_start = 0.0
    if starts and starts[0] < 0.15 and ends:
        trim_start = max(0.0, ends[0] - margin_sec)

    trim_end = seg_dur
    if starts and (len(starts) > len(ends) or (ends and abs(ends[-1] - seg_dur) < 0.25)):
        last_silence_start = starts[-1]
        if last_silence_start > trim_start + 0.4:
            trim_end = min(seg_dur, last_silence_start + margin_sec)

    if trim_end - trim_start < 0.35:
        return seg_start, seg_end
    return seg_start + trim_start, seg_start + trim_end


def apply_internal_cuts(
    src_audio: Path,
    seg_start: float,
    seg_end: float,
    cut_ranges: Optional[List[List[float]]],
    work_dir: Path,
    scene_id: str,
) -> Tuple[Path, float, float]:
    """
    Remove specified internal hesitation intervals inside [seg_start, seg_end]
    using smooth 25ms crossfades (`acrossfade`) so speech sounds continuous.
    """
    if not cut_ranges:
        return src_audio, seg_start, seg_end

    # Collect kept intervals within [seg_start, seg_end]
    kept: List[Tuple[float, float]] = []
    cursor = seg_start
    for c_start, c_end in sorted(cut_ranges):
        if c_end <= seg_start or c_start >= seg_end:
            continue
        a = max(cursor, seg_start)
        b = min(c_start, seg_end)
        if b - a > 0.15:
            kept.append((a, b))
        cursor = max(cursor, min(c_end, seg_end))
    if seg_end - cursor > 0.15:
        kept.append((cursor, seg_end))

    if len(kept) <= 1:
        return src_audio, seg_start, seg_end

    part_wavs: List[Path] = []
    for idx, (a, b) in enumerate(kept):
        part = work_dir / f"{scene_id}_cutpart_{idx}.wav"
        run_cmd([
            "ffmpeg", "-y", "-ss", f"{a:.4f}", "-t", f"{b - a:.4f}",
            "-i", str(src_audio), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
            str(part),
        ])
        part_wavs.append(part)

    merged = work_dir / f"{scene_id}_cutmerged.wav"
    cur_wav = part_wavs[0]
    for idx in range(1, len(part_wavs)):
        nxt = work_dir / f"{scene_id}_cutstep_{idx}.wav"
        run_cmd([
            "ffmpeg", "-y", "-i", str(cur_wav), "-i", str(part_wavs[idx]),
            "-filter_complex", "acrossfade=d=0.025:c1=tri:c2=tri",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(nxt),
        ])
        cur_wav = nxt
    cur_wav.replace(merged)
    return merged, 0.0, get_duration(merged)


def process_voice_clip(
    src_audio: Path,
    dst_wav: Path,
    work_dir: Path,
    scene_id: str,
    audio_start_sec: Optional[float] = None,
    audio_end_sec: Optional[float] = None,
    cut_ranges: Optional[List[List[float]]] = None,
) -> Dict[str, float]:
    """
    Clean and normalize a raw voice recording (or sub-slice) while keeping
    vocal timbre completely natural and authentic (no pitch/speed change).
    """
    raw_dur = get_duration(src_audio)
    seg_start = float(audio_start_sec) if audio_start_sec is not None else 0.0
    seg_end = min(raw_dur, float(audio_end_sec)) if audio_end_sec is not None else raw_dur

    eff_src, eff_start, eff_end = apply_internal_cuts(
        src_audio, seg_start, seg_end, cut_ranges, work_dir, scene_id
    )
    trim_start, trim_end = detect_speech_bounds(eff_src, eff_start, eff_end)
    trimmed_dur = max(0.1, trim_end - trim_start)
    fade_out_start = max(0.0, trimmed_dur - 0.045)

    # Natural, cohesive student-voice processing chain:
    # - 80 Hz high-pass removes room/handling rumble without thinning voice
    # - Gentle 2.8 kHz presence (+1.0 dB) improves consonant/math clarity
    # - Light FFT denoise (-26 dB) preserves room naturalness
    # - Transparent 2.0:1 compressor + EBU R128 loudnorm (-16 LUFS, LRA=7)
    # - Smooth 45ms fade-in/out avoids abrupt boundary cuts
    af_chain = (
        "highpass=f=80,"
        "equalizer=f=2800:t=q:w=1.5:g=1.0,"
        "afftdn=nf=-26,"
        "acompressor=threshold=-20dB:ratio=2.0:attack=15:release=150:makeup=1.5,"
        "loudnorm=I=-16:TP=-1.5:LRA=7,"
        f"afade=t=in:st=0:d=0.045,afade=t=out:st={fade_out_start:.4f}:d=0.045"
    )

    run_cmd([
        "ffmpeg", "-y", "-ss", f"{trim_start:.4f}", "-t", f"{trimmed_dur:.4f}",
        "-i", str(eff_src),
        "-af", af_chain,
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
        str(dst_wav),
    ])
    final_dur = get_duration(dst_wav)
    return {
        "raw_duration_sec": round(raw_dur, 3),
        "trimmed_duration_sec": round(final_dur, 3),
        "trim_start_sec": round(trim_start, 3),
        "trim_end_sec": round(trim_end, 3),
    }


def pad_audio_to_slot(
    clip_wav: Path,
    dst_wav: Path,
    lead_in_sec: float,
    target_slot_dur: float,
) -> None:
    """Place `clip_wav` at `lead_in_sec` inside a `target_slot_dur` stereo WAV."""
    delay_ms = int(round(lead_in_sec * 1000))
    run_cmd([
        "ffmpeg", "-y", "-i", str(clip_wav),
        "-af", f"adelay={delay_ms}|{delay_ms},apad,atrim=0:{target_slot_dur:.4f}",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
        str(dst_wav),
    ])


def build_scene_video_segment(
    silent_video: Path,
    scene: Dict,
    target_dur: float,
    fps: int,
    dst_mp4: Path,
    allow_trim_dead_space: bool = False,
) -> Tuple[float, str]:
    """
    Create the video segment for a single scene in a unified colorspace
    (`yuv420p`) so static holds have zero brightness/contrast flashes.
    """
    start = float(scene["start_sec"])
    end = float(scene["end_sec"])
    orig_dur = end - start
    hold_t = float(scene["hold_frame_sec"])
    max_trim = float(scene.get("max_trim_sec", 0.0))

    # Case 1: Narration fits inside original scene (or trims excess static hold)
    if target_dur <= orig_dur + 0.05:
        excess = orig_dur - target_dur
        if allow_trim_dead_space and excess > 0.6 and max_trim > 0.0:
            trim_amt = min(excess - 0.15, max_trim)
            if trim_amt > 0.25:
                # Trim static hold around hold_t while preserving pre-hold animation & tail fade
                cut_start = max(start + 0.5, hold_t - trim_amt)
                cut_end = min(end - 0.25, cut_start + trim_amt)
                if cut_end - cut_start > 0.2 and (end - cut_end) > 0.1:
                    fc = (
                        f"[0:v]trim=start={start:.4f}:end={cut_start:.4f},setpts=PTS-STARTPTS,format=yuv420p[v0];"
                        f"[0:v]trim=start={cut_end:.4f}:end={end:.4f},setpts=PTS-STARTPTS,format=yuv420p[v1];"
                        "[v0][v1]concat=n=2:v=1:a=0[vout]"
                    )
                    run_cmd([
                        "ffmpeg", "-y", "-i", str(silent_video),
                        "-filter_complex", fc, "-map", "[vout]",
                        "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(dst_mp4),
                    ])
                    actual = get_duration(dst_mp4)
                    return actual, f"trimmed_static_hold (-{cut_end - cut_start:.2f}s at t={cut_start:.1f}s)"

        run_cmd([
            "ffmpeg", "-y", "-i", str(silent_video),
            "-vf", f"trim=start={start:.4f}:end={end:.4f},setpts=PTS-STARTPTS,format=yuv420p",
            "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(dst_mp4),
        ])
        actual = get_duration(dst_mp4)
        return actual, "original_timing"

    # Case 2: Narration is longer -> clone hold frame directly inside same filtergraph (tpad)
    hold_dur = target_dur - orig_dur
    if end - hold_t > 0.08:
        fc = (
            f"[0:v]trim=start={start:.4f}:end={hold_t:.4f},setpts=PTS-STARTPTS,"
            f"format=yuv420p,tpad=stop_duration={hold_dur:.4f}:stop_mode=clone[v0];"
            f"[0:v]trim=start={hold_t:.4f}:end={end:.4f},setpts=PTS-STARTPTS,format=yuv420p[v1];"
            "[v0][v1]concat=n=2:v=1:a=0[vout]"
        )
    else:
        fc = (
            f"[0:v]trim=start={start:.4f}:end={end:.4f},setpts=PTS-STARTPTS,"
            f"format=yuv420p,tpad=stop_duration={hold_dur:.4f}:stop_mode=clone[vout]"
        )

    run_cmd([
        "ffmpeg", "-y", "-i", str(silent_video),
        "-filter_complex", fc, "-map", "[vout]",
        "-c:v", "libx264", "-crf", "16", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(dst_mp4),
    ])
    actual = get_duration(dst_mp4)
    return actual, f"extended_hold (+{hold_dur:.2f}s at t={hold_t:.1f}s)"


def check_readiness(project_root: Path, manifest: Dict) -> int:
    """Verify silent video and list expected vs. found scene voice recordings."""
    silent_video = project_root / manifest["source_video"]
    voiceover_dir = project_root / "Voiceover"
    print("=" * 72)
    print("VOICEOVER SYNCHRONIZATION READINESS CHECK")
    print("=" * 72)
    if silent_video.exists():
        dur = get_duration(silent_video)
        print(f"Source Silent Video : {silent_video} (OK, {dur:.2f}s)")
    else:
        print(f"Source Silent Video : MISSING ({silent_video})")
        return 1

    seen_stems = set()
    found_count = 0
    for sc in manifest["scenes"]:
        stem = sc["audio_stem"]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        rec = find_scene_audio(voiceover_dir, stem)
        if rec:
            found_count += 1
            rec_dur = get_duration(rec)
            print(f"  [FOUND]   {rec.name} ({rec_dur:.2f}s)")
        else:
            print(f"  [PENDING] {stem}.wav")

    print(f"\nSummary: {found_count}/{len(seen_stems)} unique source recordings present.")
    return 0


def synchronize_project(
    project_root: Path,
    manifest: Dict,
    trim_dead_space: bool = False,
    create_preview: bool = True,
) -> Dict:
    """Run full audio processing, timeline sync, and preview assembly."""
    silent_video = project_root / manifest["source_video"]
    voiceover_dir = project_root / "Voiceover"
    video_dir = project_root / "Video"
    scripts_dir = project_root / "Scripts"
    fps = int(manifest["target_specs"]["fps"])
    max_dur = float(manifest["target_specs"]["max_duration_sec"])

    missing = sorted({
        sc["audio_stem"]
        for sc in manifest["scenes"]
        if find_scene_audio(voiceover_dir, sc["audio_stem"]) is None
    })
    if missing:
        raise FileNotFoundError(
            "Missing voiceover files in Voiceover/: " + ", ".join(f"{m}.wav" for m in missing)
        )

    report_scenes = []
    with tempfile.TemporaryDirectory(prefix="m3_sync_") as tmp:
        work = Path(tmp)
        video_parts: List[Path] = []
        audio_parts: List[Path] = []
        running_time = 0.0

        for sc in manifest["scenes"]:
            src_audio = find_scene_audio(voiceover_dir, sc["audio_stem"])
            assert src_audio is not None
            orig_dur = float(sc["end_sec"]) - float(sc["start_sec"])
            lead_in = float(sc["lead_in_sec"])
            tail_pad = float(sc["tail_pad_sec"])

            clean_wav = work / f"{sc['id']}_clean.wav"
            audio_stats = process_voice_clip(
                src_audio,
                clean_wav,
                work,
                sc["id"],
                audio_start_sec=sc.get("audio_start_sec"),
                audio_end_sec=sc.get("audio_end_sec"),
                cut_ranges=sc.get("audio_cut_ranges_sec"),
            )
            needed_dur = lead_in + audio_stats["trimmed_duration_sec"] + tail_pad

            seg_mp4 = work / f"{sc['id']}.mp4"
            actual_vid_dur, action = build_scene_video_segment(
                silent_video, sc, needed_dur, fps, seg_mp4,
                allow_trim_dead_space=trim_dead_space,
            )

            slot_wav = work / f"{sc['id']}_slot.wav"
            pad_audio_to_slot(clean_wav, slot_wav, lead_in, actual_vid_dur)

            video_parts.append(seg_mp4)
            audio_parts.append(slot_wav)

            report_scenes.append({
                "id": sc["id"],
                "title": sc["title"],
                "source_audio": src_audio.name,
                "original_slot_sec": round(orig_dur, 3),
                "final_slot_sec": round(actual_vid_dur, 3),
                "timeline_start_sec": round(running_time, 3),
                "timeline_end_sec": round(running_time + actual_vid_dur, 3),
                "speech_start_sec": round(running_time + lead_in, 3),
                "speech_end_sec": round(running_time + lead_in + audio_stats["trimmed_duration_sec"], 3),
                "timing_action": action,
                **audio_stats,
            })
            running_time += actual_vid_dur

        if running_time > max_dur:
            raise ValueError(
                f"Synchronized duration {running_time:.2f}s exceeds maximum {max_dur:.1f}s (7 minutes)."
            )

        v_list = work / "video_concat.txt"
        a_list = work / "audio_concat.txt"
        v_list.write_text("".join(f"file '{p}'\n" for p in video_parts), encoding="utf-8")
        a_list.write_text("".join(f"file '{p}'\n" for p in audio_parts), encoding="utf-8")

        synced_video = video_dir / "Synced_Silent_Timeline.mp4"
        master_wav = voiceover_dir / "Synced_Master_Audio.wav"

        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(v_list), "-c", "copy", str(synced_video)])
        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(a_list), "-c", "copy", str(master_wav)])

        if create_preview:
            preview_mp4 = video_dir / "Preview.mp4"
            run_cmd([
                "ffmpeg", "-y", "-i", str(synced_video), "-i", str(master_wav),
                "-vf", "scale=1280:720", "-c:v", "libx264", "-crf", "23", "-preset", "veryfast",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", "-shortest", str(preview_mp4),
            ])

    report = {
        "total_duration_sec": round(running_time, 3),
        "within_7min_limit": running_time <= max_dur,
        "scenes": report_scenes,
    }
    report_path = scripts_dir / "sync_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Synchronization complete: {running_time:.2f}s total. Report saved to {report_path}.")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize scene voiceovers with Silent_Animation.mp4")
    parser.add_argument("--check", action="store_true", help="Check readiness and list missing/found audio files")
    parser.add_argument("--trim-dead-space", action="store_true", help="Trim excess static hold when voice is much shorter")
    parser.add_argument("--no-preview", action="store_true", help="Skip generating 720p Video/Preview.mp4")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    project_root = scripts_dir.parent
    manifest = json.loads((scripts_dir / "scenes_manifest.json").read_text(encoding="utf-8"))

    if args.check:
        return check_readiness(project_root, manifest)

    synchronize_project(
        project_root,
        manifest,
        trim_dead_space=args.trim_dead_space,
        create_preview=not args.no_preview,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
