# M3 Mathematics Internal Assessment — Gaussian Elimination

## Project Information
- **Project Title:** Gaussian Elimination — Solving a 3×3 System of Linear Equations (Personal Voiceover & Synchronization Pipeline)
- **Student Name:** Parv Malani
- **Student ID:** E25B070827
- **Batch:** Ramanujan
- **Subject:** Mathematics 3 — Linear Algebra and Calculus
- **Topic:** Gaussian Elimination — Solving a 3×3 System of Linear Equations
- **Repository:** https://github.com/malaniparv905-dot/maths-animation-video-parv.git

---

## Learning Objective
To explain and visualize how Gaussian elimination systematically transforms an arbitrary 3×3 system of linear equations into Row Echelon Form (REF) and Reduced Row Echelon Form (RREF) via elementary row operations—preserving the geometric intersection of the three planes—and solve it cleanly via back-substitution.

---

## Mathematical System Covered in the Video
The existing animation illustrates a **Campus Café & Mess Pricing Mystery** with three unknown item prices:
- Let $x$ = Coffee price, $y$ = Tea price, $z$ = Sandwich price:
  1. **Order #101 (Coffee + Tea):** $x + y = 5$
  2. **Order #102 (Coffee + Sandwich):** $x + z = 8$
  3. **Order #103 (Tea + Sandwich):** $y + z = 7$

### Augmented Matrix & Elimination Steps Shown
$$\left[\begin{array}{ccc|c} 1 & 1 & 0 & 5 \\ 1 & 0 & 1 & 8 \\ 0 & 1 & 1 & 7 \end{array}\right]
\xrightarrow{R_2 \leftarrow R_2 - R_1}
\left[\begin{array}{ccc|c} 1 & 1 & 0 & 5 \\ 0 & -1 & 1 & 3 \\ 0 & 1 & 1 & 7 \end{array}\right]
\xrightarrow{R_2 \leftarrow (-1)R_2}
\left[\begin{array}{ccc|c} 1 & 1 & 0 & 5 \\ 0 & 1 & -1 & -3 \\ 0 & 1 & 1 & 7 \end{array}\right]$$
$$\xrightarrow{R_3 \leftarrow R_3 - R_2}
\left[\begin{array}{ccc|c} 1 & 1 & 0 & 5 \\ 0 & 1 & -1 & -3 \\ 0 & 0 & 2 & 10 \end{array}\right]
\xrightarrow{R_3 \leftarrow \frac{1}{2}R_3}
\left[\begin{array}{ccc|c} 1 & 1 & 0 & 5 \\ 0 & 1 & -1 & -3 \\ 0 & 0 & 1 & 5 \end{array}\right] \text{ (REF)}$$

### Final Solution & Verification
- **Back-substitution (to RREF):** $z = 5$, $y = 2$, $x = 3$
- **Unique Intersection Point:** $(x, y, z) = (3, 2, 5)$ — Coffee = ₹3, Tea = ₹2, Sandwich = ₹5
- **Order Checks:** $3 + 2 = 5$, $3 + 5 = 8$, $2 + 5 = 7$
- *(Note: `Scripts/verify_math.py` also verifies the alternate reference system $x+y+z=6$, $2x+3y+z=11$, $x+2y+3z=14 \implies (1,2,3)$ mentioned in the initial assignment brief, while keeping the narration and visuals faithful to the actual video.)*

---

## Project Workflow
1. **Backup & Inspection:** Backed up the source MP4 untouched into `Original_Video_Backup/` and inspected streams via `ffprobe` (1920×1080, 16:9, 24 fps, H.264, 300.00s).
2. **Visual & Audio Analysis:** Extracted frames across all 300 seconds and inspected the embedded audio track (`Video_Analysis.md` / `Video_Analysis.pdf`).
3. **Silent Video Preparation:** Stripped the original ambient audio stream losslessly (`ffmpeg -c:v copy -an`) to create `Video/Silent_Animation.mp4`.
4. **Mathematical Verification:** Verified every matrix step, determinant, rank, and solution independently using Python + NumPy (`Scripts/verify_math.py`).
5. **Personal Script & Recording Guide:** Authored a frame-synchronized narration script (`Narration_Script.txt` / `.pdf`) and scene-by-scene recording guide (`Recording_Guide.txt`).
6. **Voiceover Processing & Sync:** Automated scene-level audio cleanup, loudness normalization, settled-frame holds, final H.264/AAC export, and FFprobe QC (`Scripts/synchronize_audio.py`, `Scripts/export_final_video.py`).
7. **Viva Preparation:** Compiled 15 core Linear Algebra & pipeline viva Q&As (`Documents/Viva_Prep.pdf`).

---

## Tools Used
- **FFmpeg / FFprobe** (`9.0.2`): Stream inspection, lossless audio stripping, audio filtering (`highpass`, `afftdn`, `acompressor`, `loudnorm`), video holds, and H.264/AAC MP4 muxing.
- **Python 3** (`numpy`, `opencv-python`, `json`, `subprocess`): Frame difference analysis, mathematical verification, and timeline synchronization automation.
- **Google Chrome (Headless)** + HTML/CSS: Print-ready PDF generation for scripts, analysis, and viva notes.

---

## Voice Recording & Synchronization Workflow
1. Read `Scripts/Recording_Guide.txt` and open `Video/Silent_Animation.mp4` muted as a visual reference.
2. Record the 13 scene clips (`Scene_01_Cafe_Puzzle.wav` through `Scene_12_Conclusion.wav`) into `Voiceover/`.
3. Check readiness:
   ```bash
   python3 Scripts/synchronize_audio.py --check
   ```
4. Synchronize, process audio naturally, and export `Video/Final_Video.mp4` with FFprobe verification:
   ```bash
   python3 Scripts/export_final_video.py
   ```
   - `synchronize_audio.py` never speeds up or alters your voice; if a recording runs longer than its visual slot, it inserts a clean visual hold at a pre-verified static frame (`hold_frame_sec` in `Scripts/scenes_manifest.json`).

---

## Folder Structure
```text
M3_Gaussian_Elimination_Parv/
├── Original_Video_Backup/
│   └── gaussian_elimination_cinematic_explainer (7).mp4
├── Video/
│   ├── Silent_Animation.mp4
│   ├── Preview.mp4                  (generated after voiceover sync)
│   └── Final_Video.mp4              (generated after voiceover sync)
├── Voiceover/
│   ├── Scene_01_Cafe_Puzzle.wav ... Scene_12_Conclusion.wav  (user recordings)
├── Scripts/
│   ├── scenes_manifest.json
│   ├── Narration_Script.txt
│   ├── Recording_Guide.txt
│   ├── Video_Analysis.md
│   ├── synchronize_audio.py
│   ├── export_final_video.py
│   └── verify_math.py
├── Documents/
│   ├── Narration_Script.pdf
│   ├── Video_Analysis.pdf
│   └── Viva_Prep.pdf
└── README.md
```

---

## References
- Gilbert Strang, *Introduction to Linear Algebra* (MIT / Wellesley-Cambridge Press).
- David C. Lay, Steven R. Lay, & Judi J. McDonald, *Linear Algebra and Its Applications*.
- NumPy (`numpy.linalg`) & FFmpeg Official Documentation.

---

## AI Disclosure
- The original visual animation (`gaussian_elimination_cinematic_explainer (7).mp4`) was provided as an existing completed asset; its original audio track (ambient background score) was completely removed.
- AI coding/editorial tools were used to inspect video frames, build Python/FFmpeg synchronization and verification scripts, format documentation, and draft the scene-matched narration script.
- **No AI voiceover or synthetic speech is used in the final submission:** the final video uses Parv Malani's own recorded voiceover with zero background music.
