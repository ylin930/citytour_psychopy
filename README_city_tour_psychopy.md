# City Tour Task — PsychoPy Version
## Quick Start

### 1. Requirements
```
pip install psychopy
```
PsychoPy 2023.x+ recommended.

---

### 2. File layout
Place this file and the session JSONs in the same folder:
```
experiment/
├── city_tour_experiment.py     ← main script
├── participant_counts.json     ← auto-created; tracks counterbalancing counts
├── session_1_v1.json           ← copy from your online experiment
├── session_1_v2.json           ← (one file per version, or symlink to v1 while others are pending)
├── session_2_v1.json
├── session_3_v1.json
├── data/                       ← auto-created; CSV responses saved here
└── assets/                     ← root asset folder (set in GUI)
    ├── City0/                  ← practice city
    │   ├── audio/en/instructions/
    │   │   ├── intro.mp3
    │   │   ├── gen_intro.mp3
    │   │   ├── gen_first.mp3
    │   │   ├── gen_next.mp3
    │   │   ├── ps.mp3
    │   │   ├── pc_first.mp3
    │   │   └── pc_next.mp3
    │   ├── images/
    │   │   ├── bus_intro.png
    │   │   ├── guide.png
    │   │   └── bus.png
    │   ├── gamify/
    │   │   ├── coin_1.mp4
    │   │   ├── coin_2.mp4
    │   │   ├── coin_3.mp4
    │   │   ├── unlock.mp4
    │   │   └── audio/en/pinpad.mp4
    │   └── prac_video.mp4
    ├── WorldA/
    │   ├── City1/
    │   │   ├── audio/en/
    │   │   ├── images/
    │   │   │   ├── guide.png
    │   │   │   ├── submarine.png
    │   │   │   └── flag.png
    │   │   ├── locations/       ← PS question images: e.g. 7_2.png
    │   │   ├── gamify/
    │   │   │   ├── coin_1.mp4 … coin_6.mp4
    │   │   │   ├── unlock.mp4
    │   │   │   └── audio/en/pinpad.mp4
    │   │   └── city_video.mp4
    │   ├── City2/   (same structure)
    │   ├── City3/   (same structure)
    │   └── common/en/
    │       ├── cityExplore.mp4
    │       └── finish.mp4
    ├── WorldB/      (same structure as WorldA)
    ├── attn_catch/
    │   ├── attn/   ← attn_1.png … attn_15.png
    │   └── catch/  ← catch_1.png … catch_14.png
    └── cover_story/
        ├── cover_en_a.mp4   ← Session 1 cover, English, Cohort A
        ├── cover_en_b.mp4
        ├── cover_de_a.mp4
        ├── cover_de_b.mp4
        ├── session2_cover_en.mp4
        ├── session2_cover_de.mp4
        ├── session3_cover_en.mp4
        └── session3_cover_de.mp4
```

> **Vimeo videos**: The online experiment streams from Vimeo. For in-lab use,
> download each video and place it at the path shown above.
> The Vimeo IDs are logged in the terminal if the local file is missing.

---

### 3. Running the experiment

```bash
python city_tour_experiment.py
```

A GUI dialog opens:

| Field | Description |
|---|---|
| Participant ID | e.g. `P042` |
| Age (years) | Integer age; used for stratified counterbalancing |
| Session (1/2/3) | Which session to run today |
| Language | `en` or `de` |
| Asset base path | Path to the `assets/` folder on this machine |
| JSON data path | Folder containing `session_N_vM.json` files |

A second confirmation dialog shows the **automatically assigned** Cohort and Version before the task begins.

---

### 4. Counterbalancing logic

Counts are stored in `participant_counts.json` (one counter per age group):

```json
{
  "4": 3,
  "5": 1,
  "6": 7
}
```

Assignment sequence (repeating cycle of 8):

| Count mod 8 | Cohort | Version |
|---|---|---|
| 0 | A | v1 |
| 1 | B | v1 |
| 2 | A | v2 |
| 3 | B | v2 |
| 4 | A | v3 |
| 5 | B | v3 |
| 6 | A | v4 |
| 7 | B | v4 |

Age groups are **independent** — a 4-year-old at count 0 and a 6-year-old at count 0 both get Cohort A v1.

To **reset** counts for an age group, edit `participant_counts.json` directly.

---

### 5. Session structure summary

#### Session 1
1. **Cover Story** — cover video + intro instruction screen
2. **Practice Tour** — practice city video → gen questions (4 trials + coin interlude) → ps questions (3 trials + coin) → pc questions (3 trials + coin + unlock + pinpad + attn/catch + continue)
3. **First City Tour** — city video → gen (15 trials + flag + attn/catch + coin) → ps (14 trials + attn/catch + coin) → pc (18 trials + flag + attn/catch + coin + unlock + pinpad + next_session image)

#### Session 2
1. **Session 2 Cover** — cover/recap video
2. **Second City Tour** — same structure as Session 1 city tour but City 2

#### Session 3
1. **Session 3 Cover** — cover/recap video
2. **Third City Tour** — same structure, City 3
3. **Retention Questions**
   - *ps_retention*: 27 PS-style trials across City 1 & 2 (citySlot 1 or 2) + attn/catch + coin_4
   - *citysorting*: 3 guide questions + 39 sort trials (assign location to City 1 or 2) + attn/catch + coin_5
   - *pc_retention_s1*: 12 PC trials for City 1 (citySlot 1) + flag + attn/catch
   - *pc_retention_s2*: 16 PC trials for City 2 (citySlot 2) + flag + attn/catch + coin_6 + unlock + pinpad + finish video

---

### 6. Question types

| Code | Name | Stimulus | Choices | Correct answer |
|---|---|---|---|---|
| `gen` | Generalisation | Video clips | 4-AFC | `isCorrect: true` in JSON |
| `ps` | Perspective Shift | Image | n-AFC | `isCorrect: true` |
| `pc` | Path Completion | Image | n-AFC | `isCorrect: true` |
| `citysorting` | City Sorting | Single image | key 1 or 2 | City assignment |
| `ps_retention` | PS Retention | Image | n-AFC | `isCorrect: true` |

---

### 7. Interludes

Interludes are embedded within question groups:

| ID pattern | Type | Behaviour |
|---|---|---|
| `coin_N` | video | Play gamification coin animation |
| `unlock` | video | Play unlock animation |
| `pinpad` | video | Play pin-pad animation |
| `attn_N` | image | Show attention image, wait for SPACE |
| `catch_N` | image | Show catch image, wait for SPACE |
| `flag` | image | Show city flag, wait for SPACE |
| `next_session` / `cover` | image | Show end-of-session screen |
| `continue` / `cityExplore` | video | Play transition video |
| `finish` | video | Play end-of-experiment video |

---

### 8. Output data

Each run saves `data/{participant_id}_session{N}_{timestamp}.csv` with columns:

```
participant_id, session, cohort, version, language,
task_type, question_num, event_id, question_text,
choice_made, is_correct, rt_seconds,
[city_slot, correct_city]   ← citysorting only
```

---

### 9. Notes for adaptation

- **Fullscreen**: Change `fullscr=False` to `fullscr=True` in `make_window()`.
- **Screen size**: Adjust `size=[1024, 768]` in `make_window()`.
- **Version-specific JSONs**: Duplicate and edit `session_N_v1.json` → `session_N_v2.json` etc. for each counterbalancing version.
- **Age brackets**: If you prefer brackets (e.g. "4-5") instead of individual ages, pass a bracket string to the GUI age field — the counterbalancing logic uses it as an opaque string key.
- **Response keys**: Currently 1/2/3/4 for choice questions. Change `CHOICE_KEYS` / `CHOICE_LABELS` at the top of the script.
