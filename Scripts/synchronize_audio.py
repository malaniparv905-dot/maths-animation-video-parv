#!/usr/bin/env python3
"""
Scene-Based Voiceover Synchronization & Natural Audio Processing Pipeline.

Reads `Scripts/scenes_manifest.json`, inspects every user-recorded scene audio
file in `Voiceover/`, applies gentle, natural audio engineering (no voice
alteration or speed-up), adjusts visual scene timing via clean settled-frame
holds whenever narration exceeds a scene slot, and outputs a synchronized
master audio + preview MP4 ready for final export.
"""

import argparse
import json
import os
import re
import shutil
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


def detect_speech_bounds(audio_path: Path, total_dur: float, margin_sec: float = 0.15) -> Tuple[float, float]:
    """
    Detect leading and trailing silence via ffmpeg silencedetect and return
    safe trim bounds [start, end] preserving `margin_sec` of natural breath.
    """
    res = run_cmd([
        "ffmpeg", "-hide_banner", "-i", str(audio_path),
        "-af", "silencedetect=noise=-42dB:d=0.25",
        "-f", "null", "-",
    ], check=False)
    stderr = res.stderr
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", stderr)]

    trim_start = 0.0
    if starts and starts[0] < 0.15 and ends:
        trim_start = max(0.0, ends[0] - margin_sec)

    trim_end = total_dur
    if starts and (len(starts) > len(ends) or (ends and abs(ends[-1] - total_dur) < 0.25)):
        last_silence_start = starts[-1]
        if last_silence_start > trim_start + 0.5:
            trim_end = min(total_dur, last_silence_start + margin_sec)

    if trim_end - trim_start < 0.4:
        return 0.0, total_dur
    return trim_start, trim_end


def process_voice_clip(src_audio: Path, dst_wav: Path) -> Dict[str, float]:
    """
    Clean and normalize a raw voice recording while keeping vocal timbre
    completely natural and authentic (no pitch shift, no time stretch).
    """
    raw_dur = get_duration(src_audio)
    trim_start, trim_end = detect_speech_bounds(src_audio, raw_dur)
    trimmed_dur = max(0.1, trim_end - trim_start)
    fade_out_start = max(0.0, trimmed_dur - 0.03)

    # Gentle, transparent vocal chain:
    # 1. High-pass at 75 Hz (remove mic handling rumble / AC hum)
    # 2. Mild FFT denoise (-25 dB floor) preserving natural air
    # 3. Gentle 2.2:1 compression to tame peaks
    # 4. EBU R128 loudness normalization (-16 LUFS, -1.5 dBTP)
    # 5. Smooth 30ms fade-in/out to prevent clicks
    af_chain = (
        "highpass=f=75,"
        "afftdn=nf=-25,"
        "acompressor=threshold=-20dB:ratio=2.2:attack=15:release=150:makeup=1.5,"
        "loudnorm=I=-16:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.4f}:d=0.03"
    )

    run_cmd([
        "ffmpeg", "-y", "-ss", f"{trim_start:.4f}", "-t", f"{trimmed_dur:.4f}",
        "-i", str(src_audio),
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
    work_dir: Path,
    allow_trim_dead_space: bool = False,
) -> Tuple[float, str]:
    """
    Create the video segment for a single scene, preserving all visual quality.
    If `target_dur` exceeds the original scene length, inserts a seamless hold
    at `hold_frame_sec` (never freezing mid-animation or during a fade).
    """
    start = float(scene["start_sec"])
    end = float(scene["end_sec"])
    orig_dur = end - start
    hold_t = float(scene["hold_frame_sec"])
    max_trim = float(scene.get("max_trim_sec", 0.0))

    # Case 1: Narration fits inside original scene
    if target_dur <= orig_dur + 0.05:
        excess = orig_dur - target_dur
        if allow_trim_dead_space and excess > 3.0 and max_trim > 0.0:
            trim_amt = min(excess - 1.0, max_trim)
            new_end = end - trim_amt
            run_cmd([
                "ffmpeg", "-y", "-ss", f"{start:.4f}", "-to", f"{new_end:.4f}",
                "-i", str(silent_video),
                "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-an",
                str(dst_mp4),
            ])
            actual = get_duration(dst_mp4)
            return actual, f"trimmed_dead_space (-{trim_amt:.2f}s)"

        run_cmd([
            "ffmpeg", "-y", "-ss", f"{start:.4f}", "-to", f"{end:.4f}",
            "-i", str(silent_video),
            "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-an",
            str(dst_mp4),
        ])
        actual = get_duration(dst_mp4)
        return actual, "original_timing"

    # Case 2: Narration is longer -> insert clean still-frame hold at hold_frame_sec
    hold_dur = target_dur - orig_dur
    hold_img = work_dir / f"{scene['id']}_hold.png"
    part_pre = work_dir / f"{scene['id']}_pre.mp4"
    part_hold = work_dir / f"{scene['id']}_hold.mp4"
    part_post = work_dir / f"{scene['id']}_post.mp4"
    concat_txt = work_dir / f"{scene['id']}_concat.txt"

    run_cmd([
        "ffmpeg", "-y", "-ss", f"{hold_t:.4f}", "-i", str(silent_video),
        "-frames:v", "1", str(hold_img),
    ])

    seg_files: List[Path] = []
    if hold_t - start > 0.05:
        run_cmd([
            "ffmpeg", "-y", "-ss", f"{start:.4f}", "-to", f"{hold_t:.4f}",
            "-i", str(silent_video),
            "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(part_pre),
        ])
        seg_files.append(part_pre)

    run_cmd([
        "ffmpeg", "-y", "-loop", "1", "-t", f"{hold_dur:.4f}", "-i", str(hold_img),
        "-c:v", "libx264", "-crf", "16", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(part_hold),
    ])
    seg_files.append(part_hold)

    if end - hold_t > 0.05:
        run_cmd([
            "ffmpeg", "-y", "-ss", f"{hold_t:.4f}", "-to", f"{end:.4f}",
            "-i", str(silent_video),
            "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-pix_fmt", "yuv420p", "-r", str(fps), "-an", str(part_post),
        ])
        seg_files.append(part_post)

    concat_txt.write_text("".join(f"file '{p}'\n" for p in seg_files), encoding="utf-8")
    run_cmd([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c", "copy", str(dst_mp4),
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

    found_count = 0
    print("\nScene Recording Status:")
    for sc in manifest["scenes"]:
        orig_dur = float(sc["end_sec"]) - float(sc["start_sec"])
        rec = find_scene_audio(voiceover_dir, sc["audio_stem"])
        if rec:
            found_count += 1
            rec_dur = get_duration(rec)
            status = f"FOUND ({rec.name}, {rec_dur:.2f}s vs slot {orig_dur:.1f}s)"
        else:
            status = f"PENDING ({sc['audio_stem']}.wav, slot {orig_dur:.1f}s)"
        print(f"  {sc['id']:9s} | {sc['start_sec']:5.1f}s-{sc['end_sec']:5.1f}s | {status}")

    print(f"\nSummary: {found_count}/{len(manifest['scenes'])} scene recordings present.")
    if found_count == 0:
        print("Next step: Record the 13 scene .wav files in Voiceover/ per Scripts/Recording_Guide.txt.")
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

    missing = [
        sc["audio_stem"]
        for sc in manifest["scenes"]
        if find_scene_audio(voiceover_dir, sc["audio_stem"]) is None
    ]
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
            audio_stats = process_voice_clip(src_audio, clean_wav)
            needed_dur = lead_in + audio_stats["trimmed_duration_sec"] + tail_pad

            seg_mp4 = work / f"{sc['id']}.mp4"
            actual_vid_dur, action = build_scene_video_segment(
                silent_video, sc, needed_dur, fps, seg_mp4, work,
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
                "timing_action": action,
                **audio_stats,
            })
            running_time += actual_vid_dur

        if running_time > max_dur:
            raise ValueError(
                f"Synchronized duration {running_time:.2f}s exceeds maximum {max_dur:.1f}s (7 minutes)."
            )

        # Concatenate synced video and synced master audio
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
