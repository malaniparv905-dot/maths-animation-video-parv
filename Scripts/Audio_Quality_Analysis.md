# Audio Quality & Synchronization Analysis

**Analyzed File:** `Video/Final_Video.mp4` (`301.79s`, 1920×1080 @ 24 fps, H.264 + AAC 48 kHz)  
**Source Voice Recordings:** `Voiceover/Scene_01_Cafe_Puzzle.wav` through `Voiceover/Scene_12_Conclusion.wav` (13 clips)  
**Analysis Method:** Direct listening across all 5 full-length audio segments (`0–302s`), FFmpeg `silencedetect` (`-38 dB` & `-32 dB`), FFmpeg `ebur128` loudness audit, and frame-by-frame OpenCV visual change scanning of `Final_Video.mp4`.

---

## Executive Summary

- **Loudness & Technical Health:** Overall loudness is well balanced (`-16.0 LUFS`, `LRA = 3.2 LU`, peak `-4.5 dB`, no digital clipping, zero background music).
- **21 Total Audio, Timing, and Synchronization Problems Detected:**
  - **1 visual-hold color-flash bug** affecting 6 static holds (`mae ≈ 13.3` brightness/contrast shift from PNG-to-YUV color-range mismatch).
  - **5 early/misaligned narration cues** where explanations began 2.2s–9.0s *before* their cards/orders appeared on screen (Scenes 01 and 08).
  - **10 oversized silent gaps** (`1.18s–4.58s`) at scene/step transitions and **1 awkward 1.23s mid-sentence hesitation** in Scene 06 (`"like ... falling dominoes"`).
  - **11 clipped opening words** + **4 pronunciation/wording slips** in the raw iPad Voice Memos recordings (documented honestly in `Narration_Reshoot_List.md`).

---

## Timestamped Problem & Fix Table (`Final_Video.mp4` Timeline)

| Timestamp | Problem | Severity | Recommended Fix |
| :--- | :--- | :---: | :--- |
| `00:00.00 – 00:00.99` | Opening word `"Imagine"` is clipped at the mic gate (`"...gine checking"`). | High | Flag in `Narration_Reshoot_List.md` for optional retake (cannot be synthesized without AI). |
| `00:12.80 – 00:16.93` | `"Order 102..."` narration begins ~3.0s *before* Order #102 card appears (`00:15.75`); minor handling rustle around `00:13–00:15`. | High | Split `Scene_01` at natural `1.1s` pause; delay Order 102 line to start after `00:15.75` and apply gentle de-rumble (`80 Hz`). |
| `00:18.13 – 00:22.26` | `"And Order 103..."` begins ~6.6s *before* Order #103 card appears (`00:24.75`). | High | Split and align Order 103 line to `~00:25.0` right after the card pops in. |
| `00:23.02 – 00:29.35` | `"We know each bundle total..."` begins ~9.0s *before* the Curiosity banner (`00:32.00`). | High | Align line to `00:32.2` and insert a seamless `+2.8s` hold on the settled Curiosity banner. |
| `00:30.45 – 00:36.00` | `"Let's call coffee x..."` begins ~5.8s *before* the `x, y, z` cards appear (`00:36.25`) and finishes before Scene 01 ends. | High | Align line to `~00:36.5` when variables appear and hold settled `x, y, z` frame so viewers can read it. |
| `00:36.00 – 00:40.58` | **4.58s dead silence** between end of Scene 01 speech and Scene 02 speech. | High | Resolved automatically by sub-cue alignment of `Scene_01` beats (transition reduced to `~0.45s`). |
| `00:40.58` | Scene 02 opening `"If we"` is clipped at source mic gate (`"...just guess"`). | High | Flag in `Narration_Reshoot_List.md` for reshoot. |
| `00:55.00 – 00:56.50` | Visible brightness/contrast jump (`mae = 13.3`) entering and exiting static hold. | Medium | Replace PNG re-encode hold with single-filtergraph `tpad=stop_mode=clone` to preserve exact color range. |
| `00:58.80 – 01:00.08` | `1.28s` transition gap into Scene 03; Scene 03 opens clipped (`"...high school elimination"` missing `"Sure,"`). | Medium / High | Tighten gap to `~0.45s`; flag `"Sure,"` clip in `Narration_Reshoot_List.md`. |
| `01:08.50 – 01:12.25` | Brightness/contrast jump (`mae = 12.7`) on Scene 03 hold (`+3.61s`). | Medium | Fix via `tpad=stop_mode=clone` in unified color space. |
| `01:14.57 – 01:15.80` | `1.23s` gap into Scene 04; Scene 04 opens clipped (`"...systematic algorithm"` missing `"We need one"`), plus `"looks"` vs `"look"`. | High | Tighten gap to `~0.45s`; flag `"We need one"` & grammar slip in `Narration_Reshoot_List.md`. |
| `01:22.25 – 01:24.25` | Brightness/contrast jump (`mae = 12.8`) on Scene 04 hold (`+1.97s`). | Medium | Fix via `tpad=stop_mode=clone`. |
| `01:25.94 – 01:27.89` | `1.85s` gap at Scene 05 → Scene 06; Scene 05 also opens clipped (`"...are three prices axes"`) and says `"sine"` for `"cyan"`. | Medium / High | Trim static tail to `~0.50s` transition; flag opening & `"cyan"` pronunciation in `Narration_Reshoot_List.md`. |
| `01:27.79` (Scene 06) | Scene 06 opens clipped (`"...elimination solves this into"` missing `"Gaussian"`). | High | Flag in `Narration_Reshoot_List.md`. |
| `01:39.25 – 01:40.75` | Brightness/contrast jump (`mae = 13.4`) on Scene 06 hold (`+1.36s`). | Medium | Fix via `tpad=stop_mode=clone`. |
| `01:41.16 – 01:41.93` | Awkward `0.77s` mid-phrase hesitation (`"like ... falling dominoes"`). | Medium | Tighten mid-phrase silence to a natural `~0.25s` with 20ms crossfade. |
| `01:43.02 – 01:44.20` | `1.18s` gap into Scene 07; Scene 07 opens clipped (`"...drop"` missing `"To"`) and says `"argumented"` for `"augmented"`. | High | Tighten gap to `~0.45s`; flag `"To"` & `"augmented"` in `Narration_Reshoot_List.md`. |
| `01:57.10 – 01:59.30` | `2.20s` gap into Scene 08; Scene 08 opens clipped (`"...ever use three legal rows operation"`). | High | Tighten Scene 07→08 gap to `~0.45s`; flag opening & `"row operations"` in `Narration_Reshoot_List.md`. |
| `02:49.04 – 02:51.25` | In Scene 08, `"and third, adding..."` starts `~2.2s` *before* Card 3 appears (`171.25s`), leaving a `2.11s` tail gap (`177.29s–179.40s`). | High | Split Scene 08 at `10.7s` so Card 3 narration starts right after Card 3 appears (`~163.1s` source), closing tail gap too. |
| `03:14.97 – 04:09.68` | Oversized pauses between Step 1→2 (`2.77s`), Step 2→3 (`2.74s`), Step 3→4 (`2.80s`), and Step 4→5 (`3.29s`); Step 3 opens clipped (`"...three"` missing `"In Step"`). | Medium / High | Trim excess static hold frames between steps so each transition flows cleanly (`0.55s–0.75s`), and flag Step 3 opening in `Narration_Reshoot_List.md`. |
| `04:20.37 – 04:47.47` | Hold color flash (`mae = 13.3`) in Step 5 & Scene 10; `1.39s` / `1.37s` / `1.36s` gaps around Scene 10, 11, 12; clipped openings on Scene 10 (`"...s verify"`), Scene 11 (`"...k in 3D"`), Scene 12 (`"...is Gaussian"`). | Medium / High | Fix holds via `tpad=stop_mode=clone`, tighten transitions (`0.5s–0.8s`), and flag clipped openings in `Narration_Reshoot_List.md`. |
