#!/usr/bin/env python3
"""
Scene-Based Voiceover Synchronization & Natural Audio Processing Pipeline.

Reads `Scripts/scenes_manifest.json`, optionally prepends a 2-second opening
title card, processes every user-recorded scene clip naturally (no pitch or
speed change), locks every segment to exact integer frame counts at 24 fps
(48,000 Hz audio sample-locked), and supports exact total runtime targeting
(e.g. exactly 300.000s / 7,200 frames) with zero audio/video drift.
"""

import argparse
import json
import math
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


def get_frame_count(path: Path) -> int:
    """Return exact video frame count from stream metadata or nb_read_frames."""
    info = ffprobe_info(path)
    v = [s for s in info["streams"] if s.get("codec_type") == "video"][0]
    if "nb_frames" in v:
        return int(v["nb_frames"])
    return int(round(float(info["format"]["duration"]) * 24))


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


def pad_audio_to_frames(
    clip_wav: Optional[Path],
    dst_wav: Path,
    lead_in_sec: float,
    n_frames: int,
    fps: int,
) -> None:
    """
    Create an exact sample-locked stereo 48 kHz WAV of `n_frames / fps` seconds
    (2000 samples per video frame at 24 fps / 48 kHz) so A/V never drifts.
    """
    samples_per_frame = 48000 // fps
    total_samples = n_frames * samples_per_frame
    if clip_wav is None:
        run_cmd([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-af", f"atrim=end_sample={total_samples}",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
            str(dst_wav),
        ])
        return

    delay_ms = int(round(lead_in_sec * 1000))
    run_cmd([
        "ffmpeg", "-y", "-i", str(clip_wav),
        "-af", f"adelay={delay_ms}|{delay_ms},apad,atrim=end_sample={total_samples}",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
        str(dst_wav),
    ])


def build_intro_title_segment(
    intro_cfg: Dict,
    project_root: Path,
    fps: int,
    dst_mp4: Path,
) -> int:
    """Render the opening title card clip with clean fade-in/out and exact frames."""
    img_path = project_root / intro_cfg["image"]
    dur_sec = float(intro_cfg["duration_sec"])
    n_frames = int(round(dur_sec * fps))
    fade_out_st = max(0.1, (n_frames / fps) - 0.25)

    run_cmd([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_path),
        "-vf", f"fps={fps},format=yuv420p,setsar=1,setdar=16/9,fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out_st:.4f}:d=0.25",
        "-frames:v", str(n_frames),
        "-c:v", "libx264", "-crf", "16", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(dst_mp4),
    ])
    return get_frame_count(dst_mp4)


def compute_scene_target_frames(
    scene: Dict,
    needed_dur: float,
    fps: int,
    allow_trim_dead_space: bool,
) -> Tuple[int, str]:
    """Determine exact integer target frame count for a scene before rendering."""
    start = float(scene["start_sec"])
    end = float(scene["end_sec"])
    orig_dur = end - start
    orig_frames = int(round(orig_dur * fps))
    needed_frames = int(math.ceil(needed_dur * fps))
    max_trim = float(scene.get("max_trim_sec", 0.0))

    if needed_frames <= orig_frames:
        excess_sec = (orig_frames - needed_frames) / fps
        if allow_trim_dead_space and excess_sec > 0.6 and max_trim > 0.0:
            trim_sec = min(excess_sec - 0.15, max_trim)
            trim_frames = int(round(trim_sec * fps))
            if trim_frames >= 6 and (orig_frames - trim_frames) >= needed_frames:
                return orig_frames - trim_frames, f"trimmed_static_hold (-{trim_frames / fps:.2f}s)"
        return orig_frames, "original_timing"

    hold_frames = needed_frames - orig_frames
    return needed_frames, f"extended_hold (+{hold_frames / fps:.2f}s at t={scene['hold_frame_sec']}s)"


def render_scene_video_to_frames(
    silent_video: Path,
    scene: Dict,
    target_frames: int,
    fps: int,
    dst_mp4: Path,
) -> int:
    """
    Render a scene clip to an EXACT integer frame count `target_frames` inside
    a single unified `yuv420p` filtergraph (zero brightness flashes).
    """
    start = float(scene["start_sec"])
    end = float(scene["end_sec"])
    orig_frames = int(round((end - start) * fps))
    hold_t = float(scene["hold_frame_sec"])

    if target_frames == orig_frames:
        fc = (
            f"[0:v]trim=start={start:.4f}:end={end:.4f},setpts=PTS-STARTPTS,"
            f"format=yuv420p,fps={fps}[vout]"
        )
    elif target_frames < orig_frames:
        trim_sec = (orig_frames - target_frames) / fps
        cut_start = max(start + 0.4, hold_t - trim_sec)
        cut_end = min(end - 0.2, cut_start + trim_sec)
        fc = (
            f"[0:v]trim=start={start:.4f}:end={cut_start:.4f},setpts=PTS-STARTPTS,format=yuv420p[v0];"
            f"[0:v]trim=start={cut_end:.4f}:end={end:.4f},setpts=PTS-STARTPTS,format=yuv420p[v1];"
            f"[v0][v1]concat=n=2:v=1:a=0,fps={fps}[vout]"
        )
    else:
        hold_frames = target_frames - orig_frames
        hold_dur = (hold_frames + 1) / fps  # slight pad, exact cut via -frames:v
        if end - hold_t > 0.08:
            fc = (
                f"[0:v]trim=start={start:.4f}:end={hold_t:.4f},setpts=PTS-STARTPTS,"
                f"format=yuv420p,tpad=stop_duration={hold_dur:.4f}:stop_mode=clone[v0];"
                f"[0:v]trim=start={hold_t:.4f}:end={end:.4f},setpts=PTS-STARTPTS,format=yuv420p[v1];"
                f"[v0][v1]concat=n=2:v=1:a=0,fps={fps}[vout]"
            )
        else:
            fc = (
                f"[0:v]trim=start={start:.4f}:end={end:.4f},setpts=PTS-STARTPTS,"
                f"format=yuv420p,tpad=stop_duration={hold_dur:.4f}:stop_mode=clone,fps={fps}[vout]"
            )

    run_cmd([
        "ffmpeg", "-y", "-i", str(silent_video),
        "-filter_complex", fc, "-map", "[vout]",
        "-frames:v", str(target_frames),
        "-c:v", "libx264", "-crf", "16", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(dst_mp4),
    ])
    return get_frame_count(dst_mp4)


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
    """Run full audio processing, frame-locked timeline sync, and preview assembly."""
    silent_video = project_root / manifest["source_video"]
    voiceover_dir = project_root / "Voiceover"
    video_dir = project_root / "Video"
    scripts_dir = project_root / "Scripts"
    fps = int(manifest["target_specs"]["fps"])
    max_dur = float(manifest["target_specs"]["max_duration_sec"])
    exact_total = manifest.get("exact_total_duration_sec")

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
        running_frames = 0

        # Optional 2s opening title card
        intro_cfg = manifest.get("intro_title_card")
        if intro_cfg:
            intro_mp4 = work / "00_intro_card.mp4"
            intro_wav = work / "00_intro_card.wav"
            intro_frames = build_intro_title_segment(intro_cfg, project_root, fps, intro_mp4)
            pad_audio_to_frames(None, intro_wav, 0.0, intro_frames, fps)
            video_parts.append(intro_mp4)
            audio_parts.append(intro_wav)
            report_scenes.append({
                "id": "Intro_Title_Card",
                "title": "Topic: Gaussian Elimination / Made by Parv Malani",
                "source_audio": None,
                "original_slot_sec": 0.0,
                "final_slot_sec": round(intro_frames / fps, 3),
                "timeline_start_sec": 0.0,
                "timeline_end_sec": round(intro_frames / fps, 3),
                "speech_start_sec": None,
                "speech_end_sec": None,
                "timing_action": f"prepended_title_card ({intro_frames} frames)",
            })
            running_frames += intro_frames

        # Stage 1: Process all scene audio and plan exact frame counts
        planned = []
        for sc in manifest["scenes"]:
            src_audio = find_scene_audio(voiceover_dir, sc["audio_stem"])
            assert src_audio is not None
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
            target_frames, action = compute_scene_target_frames(
                sc, needed_dur, fps, allow_trim_dead_space=trim_dead_space
            )
            planned.append({
                "sc": sc,
                "src_audio": src_audio,
                "clean_wav": clean_wav,
                "audio_stats": audio_stats,
                "needed_frames": int(math.ceil((lead_in + audio_stats["trimmed_duration_sec"] + 0.35) * fps)),
                "target_frames": target_frames,
                "action": action,
            })

        # Stage 2: Balance frame count to exact_total_duration_sec if requested
        if exact_total is not None:
            goal_frames = int(round(float(exact_total) * fps))
            current_total_frames = running_frames + sum(p["target_frames"] for p in planned)
            delta = goal_frames - current_total_frames
            if delta > 0:
                # Distribute extra gentle breathing frames across key pause scenes + conclusion
                targets = ["Scene_01_5_Curiosity", "Scene_05", "Scene_09b_Step4", "Scene_10", "Scene_12"]
                idx = 0
                while delta > 0:
                    tid = targets[idx % len(targets)]
                    for p in planned:
                        if p["sc"]["id"] == tid and delta > 0:
                            p["target_frames"] += 1
                            p["action"] += " (+1f exact-300s)"
                            delta -= 1
                    idx += 1
            elif delta < 0:
                # Trim small surplus from tail holds safely without clipping speech
                need_cut = -delta
                for p in reversed(planned):
                    slack = p["target_frames"] - p["needed_frames"]
                    if slack > 0 and need_cut > 0:
                        take = min(slack, need_cut)
                        p["target_frames"] -= take
                        p["action"] += f" (-{take}f exact-300s)"
                        need_cut -= take
                if need_cut > 0:
                    raise ValueError(f"Cannot trim {need_cut} frames without clipping speech.")

        # Stage 3: Render frame-locked video segments & sample-locked audio slots
        for p in planned:
            sc = p["sc"]
            lead_in = float(sc["lead_in_sec"])
            orig_dur = float(sc["end_sec"]) - float(sc["start_sec"])
            seg_mp4 = work / f"{sc['id']}.mp4"
            actual_frames = render_scene_video_to_frames(
                silent_video, sc, p["target_frames"], fps, seg_mp4
            )

            slot_wav = work / f"{sc['id']}_slot.wav"
            pad_audio_to_frames(p["clean_wav"], slot_wav, lead_in, actual_frames, fps)

            video_parts.append(seg_mp4)
            audio_parts.append(slot_wav)

            t_start = running_frames / fps
            t_end = (running_frames + actual_frames) / fps
            report_scenes.append({
                "id": sc["id"],
                "title": sc["title"],
                "source_audio": p["src_audio"].name,
                "original_slot_sec": round(orig_dur, 3),
                "final_slot_sec": round(actual_frames / fps, 3),
                "frames": actual_frames,
                "timeline_start_sec": round(t_start, 3),
                "timeline_end_sec": round(t_end, 3),
                "speech_start_sec": round(t_start + lead_in, 3),
                "speech_end_sec": round(t_start + lead_in + p["audio_stats"]["trimmed_duration_sec"], 3),
                "timing_action": p["action"],
                **p["audio_stats"],
            })
            running_frames += actual_frames

        total_sec = running_frames / fps
        if total_sec > max_dur:
            raise ValueError(
                f"Synchronized duration {total_sec:.2f}s exceeds maximum {max_dur:.1f}s (7 minutes)."
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
        "total_frames": running_frames,
        "total_duration_sec": round(total_sec, 3),
        "within_7min_limit": total_sec <= max_dur,
        "scenes": report_scenes,
    }
    report_path = scripts_dir / "sync_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Synchronization complete: {running_frames} frames ({total_sec:.3f}s). Report saved to {report_path}.")
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
