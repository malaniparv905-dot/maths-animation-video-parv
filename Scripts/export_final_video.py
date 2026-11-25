#!/usr/bin/env python3
"""
Final Video Export & FFprobe Quality Control Script.

Runs `synchronize_audio.py` (unless `--skip-sync` is passed), encodes
`Video/Final_Video.mp4` at 1920x1080 16:9 H.264 + AAC 48 kHz stereo,
and runs automated FFprobe verification checks.
"""

import argparse
import json
import sys
from pathlib import Path

from synchronize_audio import ffprobe_info, run_cmd, synchronize_project


def verify_final_video(final_mp4: Path, target_specs: dict) -> bool:
    """Run automated FFprobe quality checks against required delivery specs."""
    info = ffprobe_info(final_mp4)
    streams = info.get("streams", [])
    v_streams = [s for s in streams if s.get("codec_type") == "video"]
    a_streams = [s for s in streams if s.get("codec_type") == "audio"]

    assert len(v_streams) == 1, f"Expected 1 video stream, got {len(v_streams)}"
    assert len(a_streams) == 1, f"Expected 1 audio stream, got {len(a_streams)}"

    v = v_streams[0]
    a = a_streams[0]
    duration = float(info["format"]["duration"])

    checks = [
        ("Video codec is H.264", v.get("codec_name") == "h264", v.get("codec_name")),
        ("Resolution is 1920x1080", (v.get("width"), v.get("height")) == (1920, 1080), f"{v.get('width')}x{v.get('height')}"),
        ("Aspect ratio is 16:9", v.get("display_aspect_ratio") == "16:9", v.get("display_aspect_ratio")),
        ("Frame rate is 24 fps", v.get("r_frame_rate") == "24/1", v.get("r_frame_rate")),
        ("Audio codec is AAC", a.get("codec_name") == "aac", a.get("codec_name")),
        ("Audio sample rate is 48 kHz", int(a.get("sample_rate", 0)) == 48000, a.get("sample_rate")),
        ("Duration <= 420s (7 min)", duration <= float(target_specs["max_duration_sec"]), f"{duration:.2f}s"),
    ]

    print("\n" + "=" * 72)
    print("FINAL VIDEO QUALITY CONTROL (FFprobe Verified)")
    print("=" * 72)
    all_ok = True
    for label, passed, actual in checks:
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {label:32s} -> {actual}")
        all_ok = all_ok and passed

    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Export and verify Video/Final_Video.mp4")
    parser.add_argument("--skip-sync", action="store_true", help="Use existing Synced_Silent_Timeline.mp4 & Synced_Master_Audio.wav")
    parser.add_argument("--trim-dead-space", action="store_true", help="Trim excess static hold during sync")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    project_root = scripts_dir.parent
    manifest = json.loads((scripts_dir / "scenes_manifest.json").read_text(encoding="utf-8"))

    if not args.skip_sync:
        synchronize_project(
            project_root,
            manifest,
            trim_dead_space=args.trim_dead_space,
            create_preview=True,
        )

    synced_video = project_root / "Video" / "Synced_Silent_Timeline.mp4"
    master_wav = project_root / "Voiceover" / "Synced_Master_Audio.wav"
    final_mp4 = project_root / "Video" / "Final_Video.mp4"

    if not synced_video.exists() or not master_wav.exists():
        print("Error: Synced timeline files not found. Run without --skip-sync once recordings are ready.", file=sys.stderr)
        return 1

    print("Encoding high-quality Final_Video.mp4 (1920x1080 H.264 + AAC 192 kbps)...")
    run_cmd([
        "ffmpeg", "-y", "-i", str(synced_video), "-i", str(master_wav),
        "-c:v", "libx264", "-crf", "18", "-preset", "slow",
        "-pix_fmt", "yuv420p", "-profile:v", "high",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart", "-shortest", str(final_mp4),
    ])

    ok = verify_final_video(final_mp4, manifest["target_specs"])
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
