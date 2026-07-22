#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
City Tour Task — PsychoPy Version 1

Hardcoded paths (edit once per lab setup, bottom of main()):
    BASE_PATH        = experiment root folder
    FULL_VIDEOS_DIR  = _full_videos folder
    TRANSLATION_FILE = translation.json path

World guide names: edit GUIDE_NAMES below.
"""

from psychopy import visual, core, event, gui, prefs
from psychopy.hardware import keyboard
import os, json, csv, datetime, re, numpy as _np

# sounddevice is always bundled with PsychoPy and has instant stop()
try:
    import sounddevice as _sd
    import soundfile as _sf
    _SD_OK = True
    print('[AUDIO] Using sounddevice — skip stops audio instantly')
except Exception as _sde:
    _SD_OK = False
    print(f'[AUDIO] sounddevice not available ({_sde}), using psychopy.sound')
    from psychopy import sound

# ─────────────────────────────────────────────
# WORLD / GUIDE CONFIG  ← edit for each world
# ─────────────────────────────────────────────
# Guide name changes per SESSION within a world (from useInterpolatedTranslation.ts)
GUIDE_NAMES = {
    'underwater': {1: 'Zoxni', 2: 'Pema', 3: 'Maru'},
    'desert':     {1: 'Sandy', 2: 'Sandy', 3: 'Sandy'},  # placeholder — update for T2
}

# city_names.c1–c6 come from translation.json at runtime
# cohort_a uses c1/c2/c3 for sessions 1/2/3
# cohort_b uses c4/c5/c6 for sessions 1/2/3
CITY_KEY_MAP = {('a',1):'c1', ('a',2):'c2', ('a',3):'c3',
                ('b',1):'c4', ('b',2):'c5', ('b',3):'c6'}

# ─────────────────────────────────────────────
# COUNTERBALANCING
# ─────────────────────────────────────────────
ASSIGNMENT_SEQUENCE = [(c,v) for v in [1,2,3,4] for c in ['a','b']]
COUNTS_FILE      = 'participant_counts.json'
ASSIGNMENTS_FILE = 'participant_assignments.json'

def load_json_file(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save_json_file(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def get_participant_record(pid):
    """Return the stored assignment record for pid, or None if never seen."""
    assignments = load_json_file(ASSIGNMENTS_FILE)
    return assignments.get(pid)

def assign_cohort_version(pid, age_group, lang=None, advance_counter=True):
    """Return (cohort, version). Reuses existing assignment for returning participants.

    If advance_counter=False (pilot runs), a participant record is still saved —
    so the same pilot ID keeps reusing the same cohort/version on a resume, and
    autofill/mismatch-checking still works for them — but participant_counts.json
    (which drives real counterbalancing) is left untouched.
    """
    assignments = load_json_file(ASSIGNMENTS_FILE)
    if pid in assignments:
        rec = assignments[pid]
        # Backfill lang on older records that predate this field — not a mismatch,
        # just filling in data we didn't used to track.
        if lang and not rec.get('lang'):
            rec['lang'] = lang
            save_json_file(ASSIGNMENTS_FILE, assignments)
        return rec['cohort'], rec['version']

    counts = load_json_file(COUNTS_FILE)
    if advance_counter:
        if age_group not in counts:
            counts[age_group] = 0
        idx = counts[age_group] % len(ASSIGNMENT_SEQUENCE)
        cohort, version = ASSIGNMENT_SEQUENCE[idx]
        counts[age_group] += 1
        save_json_file(COUNTS_FILE, counts)
    else:
        # Pilot: peek at the current counter (read-only) to still spread pilots
        # across conditions, but never bump the counter real participants rely on.
        idx = counts.get(age_group, 0) % len(ASSIGNMENT_SEQUENCE)
        cohort, version = ASSIGNMENT_SEQUENCE[idx]

    assignments[pid] = {'cohort': cohort, 'version': version,
                        'age_group': age_group, 'lang': lang,
                        'pilot': (not advance_counter),
                        'completed_sessions': []}
    save_json_file(ASSIGNMENTS_FILE, assignments)
    return cohort, version

def session_already_run(pid, session):
    """Return True if this participant has already completed this session."""
    assignments = load_json_file(ASSIGNMENTS_FILE)
    if pid not in assignments:
        return False
    return session in assignments[pid].get('completed_sessions', [])

def save_progress(pid, session, subsession, group, trial):
    """Record exactly where this participant is, live, as they move through a
    session — so a crash-resume can find this without anyone reading logs."""
    assignments = load_json_file(ASSIGNMENTS_FILE)
    rec = assignments.setdefault(pid, {})
    rec.setdefault('progress', {})[str(session)] = {
        'subsession': subsession, 'group': group, 'trial': trial}
    save_json_file(ASSIGNMENTS_FILE, assignments)

def get_progress(pid, session):
    """Return {'subsession','group','trial'} for the last known position in
    this session, or None if there's nothing saved (never started / finished)."""
    rec = get_participant_record(pid)
    if not rec:
        return None
    return (rec.get('progress') or {}).get(str(session))

def clear_progress(pid, session):
    """Drop the saved position once a session finishes normally, so a future
    override-rerun doesn't get offered a stale mid-session resume point."""
    assignments = load_json_file(ASSIGNMENTS_FILE)
    rec = assignments.get(pid)
    if rec and 'progress' in rec and str(session) in rec['progress']:
        del rec['progress'][str(session)]
        save_json_file(ASSIGNMENTS_FILE, assignments)

def mark_session_complete(pid, session):
    """Record that this participant has finished this session."""
    assignments = load_json_file(ASSIGNMENTS_FILE)
    if pid in assignments:
        completed = assignments[pid].setdefault('completed_sessions', [])
        if session not in completed:
            completed.append(session)
        save_json_file(ASSIGNMENTS_FILE, assignments)

# ─────────────────────────────────────────────
# TRANSLATION
# ─────────────────────────────────────────────
_translations = {}

def load_translations(path):
    global _translations
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            _translations = json.load(f)
    else:
        print(f'[WARN] translation file not found: {path}')

def get_text(key, **kwargs):
    """Lookup a dot-path key and fill {{placeholders}}."""
    parts = key.split('.')
    def _try(obj, parts):
        if not parts:
            return obj
        for i in range(1, len(parts)+1):
            k = '.'.join(parts[:i])
            if isinstance(obj, dict) and k in obj:
                result = _try(obj[k], parts[i:])
                if result is not None:
                    return result
        return None
    result = _try(_translations, parts)
    if not isinstance(result, str):
        return key  # fallback: show the key itself
    for placeholder, value in kwargs.items():
        result = result.replace('{{' + placeholder + '}}', str(value))
    return result

def city_name(cohort, session, city_slot=None):
    """
    city_slot overrides session when looking up retention questions
    (citySlot 1 = session 1 city, citySlot 2 = session 2 city).
    cohort_a: slot maps directly; cohort_b: slot + 3.
    """
    slot = city_slot if city_slot is not None else session
    if cohort == 'b':
        slot = slot + 3
    key   = f'c{slot}'
    names = _translations.get('city_names', {})
    return names.get(key, f'City{slot}')

def gen_city_name(cohort, session):
    """Gen city is the equivalent city from the OTHER cohort (similar city).
    cohort_a session1 -> c4 (Perlantis), cohort_b session1 -> c1 (Flossenland).
    """
    other_cohort = 'b' if cohort == 'a' else 'a'
    return city_name(other_cohort, session)

def guide_name(world, session):
    """Guide name changes per session within a world."""
    world_guides = GUIDE_NAMES.get(world, {})
    if isinstance(world_guides, dict):
        return world_guides.get(session, 'Guide')
    return str(world_guides)

# ─────────────────────────────────────────────
# ENCODING VIDEO LOOKUP
# ─────────────────────────────────────────────
SESSION_CITY  = {1:'1', 2:'2', 3:'3'}
CITY_FILE_MAP = {('a',1):'city1', ('a',2):'city2', ('a',3):'city3',
                 ('b',1):'city4', ('b',2):'city5', ('b',3):'city6'}

def get_encoding_video_path(full_videos_dir, cohort, session, version, lang):
    city = CITY_FILE_MAP[(cohort, session)]
    tag  = 'v1_v4' if (session == 1 and version in (1,4)) else \
           'v2_v3' if (session == 1 and version in (2,3)) else f'v{version}'
    return os.path.join(full_videos_dir, lang, f'{city}_{tag}_{lang}.mp4')

# ─────────────────────────────────────────────
# PATH RESOLVER
# ─────────────────────────────────────────────
def resolve(template, base, world, lang, num='', gen_num='', slot=''):
    p = template
    # Normalise base to use forward slashes for consistent replacement
    base_fwd = base.replace(os.sep, '/').rstrip('/')
    p = p.replace('src/assets/', base_fwd + '/')
    p = p.replace('{world}',    world)
    p = p.replace('{lang}',     lang)
    p = p.replace('{num}',      num)
    p = p.replace('{gen_num}',  gen_num)
    p = p.replace('{slot}',     slot)
    # Convert to OS-native separators so file operations work on Windows
    return os.path.normpath(p)

# ─────────────────────────────────────────────
# DATA RECORDER
# ─────────────────────────────────────────────
class DataRecorder:
    FIELDS = [
        'user_id','age','gender','ageGroup',
        'cohort','language','version',
        'session','city','citySlot',
        'trial','event_id','task_id',
        'choice','choiceContent','correct',
        'rt_seconds',
    ]

    def __init__(self, pid, age_str, session, cohort, version, lang):
        v_group = 'v1_v2' if version in (1,2) else 'v3_v4'
        folder  = f'cohort{cohort.upper()}_{v_group}'
        os.makedirs(folder, exist_ok=True)
        self.path = os.path.join(folder, f'{pid}_s{session}.csv')
        # cohort_a / cohort_b format to match online data
        self.meta = dict(
            user_id=pid,
            age=age_str,
            gender='',         # not collected in lab
            ageGroup='',       # filled per row
            cohort=f'cohort_{cohort}',
            language=lang,
            version=f'v{version}',
            session=session,
        )
        if not os.path.exists(self.path):
            with open(self.path, 'w', newline='', encoding='utf-8') as f:
                csv.DictWriter(f, fieldnames=self.FIELDS).writeheader()

    def record(self, **kwargs):
        row = {**self.meta, **kwargs}
        ic = row.get('correct')
        row['correct'] = 1 if ic is True else (0 if ic is False else ic if ic in (0,1) else '')
        with open(self.path, 'a', newline='', encoding='utf-8') as f:
            csv.DictWriter(f, fieldnames=self.FIELDS,
                           extrasaction='ignore').writerow(row)

    def save(self):
        print(f'\u2713 Data saved \u2192 {self.path}')

    def save_progress(self, subsession, group, trial):
        save_progress(self.meta['user_id'], self.meta['session'], subsession, group, trial)


def _choice_number(rc, chosen_idx):
    """Return the 1-based display position of the chosen option."""
    return chosen_idx + 1

def _city_for_session(cohort, session_num):
    """City number as shown in online data: cohort_a=1/2/3, cohort_b=4/5/6."""
    return session_num + (3 if cohort == 'b' else 0)

# ─────────────────────────────────────────────
# WINDOW  (1080×1080)
# ─────────────────────────────────────────────
WIN_AR = 1.0  # set after window opens

def _get_movie_stim(win, path, pos, size, loop=False):
    """Get a working MovieStim, trying multiple backends."""
    kwargs = dict(pos=pos, size=size, units='norm', loop=loop)
    for cls_name in ['MovieStim', 'MovieStim3', 'VlcMovieStim']:
        cls = getattr(visual, cls_name, None)
        if cls is None:
            continue
        try:
            m = cls(win, path, **kwargs)
            print(f'[VIDEO] Using {cls_name}')
            return m
        except Exception as e:
            print(f'[VIDEO] {cls_name} failed: {e}')
    raise RuntimeError(f'No working MovieStim backend for: {path}')

def make_window(fullscr=False):
    win = visual.Window(size=[1080, 1080], fullscr=fullscr,
                        color='white', units='norm', allowGUI=True,
                        winType='pyglet', useFBO=True)
    # Prevent window resizing which would distort norm-unit coordinates
    if hasattr(win, '_backend') and hasattr(win._backend, 'winHandle'):
        try:
            win._backend.winHandle.set_minimum_size(1080, 1080)
            win._backend.winHandle.set_maximum_size(1080, 1080)
        except Exception:
            pass
    global WIN_AR
    WIN_AR = win.size[0] / win.size[1]
    return win

# Set to True when dev mode is active (override fields filled in GUI)
_DEV_MODE    = False
_START_SS    = ''     # subsession name to resume from
_START_GROUP = ''     # subtask/group type to resume from within that subsession (e.g. 'gen','ps','pc')
_START_TRIAL = 0      # trial number to resume from within that subtask (0 = beginning of subtask)

# Hardware-level keyboard listener — captures keys even during movie playback
_kb = None

def _init_kb():
    global _kb
    try:
        from psychopy.hardware import keyboard as _kbmod
        _kb = _kbmod.Keyboard()
        _kb.clock.reset()
    except Exception as e:
        print(f'[WARN] keyboard listener init failed: {e}')
        _kb = None

class _SkipSection(Exception):
    """Raised by 's' key in dev mode to skip the current section."""
    pass

def check_escape(win):
    # Use hardware keyboard if available (works during MovieStim playback)
    if _kb is not None:
        pressed = _kb.getKeys(keyList=['escape', 's'], waitRelease=False, clear=True)
        key_names = [k.name for k in pressed]
    else:
        key_names = event.getKeys(keyList=['escape', 's'])
    if 'escape' in key_names:
        stop_audio()
        win.close(); core.quit()
    if 's' in key_names and _DEV_MODE:
        stop_audio()
        raise _SkipSection()

# ─────────────────────────────────────────────
# ASPECT-RATIO HELPERS
# ─────────────────────────────────────────────
def image_aspect(path):
    try:
        from PIL import Image as PILImage
        w, h = PILImage.open(path).size
        return w / h
    except Exception:
        return 1.0

def fit_size(aspect, max_w, max_h):
    """Return (w, h) fitting within max_w×max_h preserving aspect."""
    if aspect >= max_w / max_h:
        return max_w, max_w / aspect
    else:
        return max_h * aspect, max_h

def img_size(aspect, max_w, max_h):
    """Like fit_size but corrects width for non-square norm pixels."""
    w, h = fit_size(aspect, max_w, max_h)
    return w / WIN_AR, h

# ─────────────────────────────────────────────
# AUDIO / VIDEO / IMAGE
# ─────────────────────────────────────────────
def stop_audio():
    """Immediately stop all audio playback."""
    if _SD_OK:
        try: _sd.stop()
        except Exception: pass

def play_audio(path, win=None):
    """Play an audio file; polls every 50ms so 's' stops it instantly."""
    if not path or not os.path.exists(path):
        if path: print(f'  [AUDIO MISSING] {path}')
        return

    def _get_keys():
        if _kb is not None:
            return [k.name for k in _kb.getKeys(
                keyList=['escape','s'], waitRelease=False, clear=True)]
        return event.getKeys(keyList=['escape', 's'])

    if _SD_OK:
        try:
            data, sr = _sf.read(path, dtype='float32')
            _sd.play(data, sr)
            # Poll until done, checking for skip every 50ms
            while _sd.get_stream().active:
                core.wait(0.05, hogCPUperiod=0)
                keys = _get_keys()
                if 'escape' in keys:
                    _sd.stop()
                    if win: win.close()
                    core.quit()
                if 's' in keys and _DEV_MODE:
                    _sd.stop()   # instant — no buffer drain
                    raise _SkipSection()
        except _SkipSection:
            _sd.stop()
            raise
        except Exception as e:
            print(f'  [AUDIO ERR] {path}: {e}')
            _sd.stop()
    else:
        # psychopy.sound fallback — best effort, may bleed on skip
        try:
            s = sound.Sound(path)
            s.play()
            dur = s.getDuration()
            clk = core.Clock()
            while clk.getTime() < dur:
                core.wait(0.05, hogCPUperiod=0)
                keys = _get_keys()
                if 'escape' in keys:
                    s.stop()
                    if win: win.close()
                    core.quit()
                if 's' in keys and _DEV_MODE:
                    s.stop()
                    raise _SkipSection()
        except _SkipSection:
            raise
        except Exception as e:
            print(f'  [AUDIO ERR] {path}: {e}')

def _next_button(win, label=None):
    if label is None:
        label = get_text('instructions.continue') or 'Weiter'
    # Rounded pill button — try cornerRadius (PsychoPy 2022+), fallback to ShapeStim
    POS  = (0, -0.82)
    W, H = 0.50, 0.12
    try:
        # PsychoPy 2022+ supports cornerRadius on Rect
        btn = visual.Rect(win, width=W, height=H, pos=POS,
                          fillColor='#006C66', lineColor='#006C66',
                          cornerRadius=0.06, units='norm')
    except (TypeError, AttributeError):
        try:
            btn = visual.RoundRect(win, width=W, height=H, pos=POS,
                                   radius=0.06, fillColor='#006C66',
                                   lineColor='#006C66', units='norm')
        except AttributeError:
            btn = visual.Rect(win, width=W, height=H, pos=POS,
                              fillColor='#006C66', lineColor='#006C66', units='norm')
    lbl = visual.TextStim(win, text=label, color='white',
                          pos=POS, height=0.065, units='norm', bold=True)
    return btn, lbl

def _draw_next(btn, lbl):
    btn.draw(); lbl.draw()

def _clicked_next(mouse, btn):
    if mouse.getPressed()[0]:
        mp = mouse.getPos()
        bx, by = btn.pos
        return abs(mp[0]-bx) < 0.25 and abs(mp[1]-by) < 0.07
    return False

def show_text(win, text, subtitle=None, wait=True, duration=None):
    visual.TextStim(win, text=text, color='black', wrapWidth=1.60,
                    height=0.08, pos=(0, 0.20), units='norm').draw()
    if subtitle:
        visual.TextStim(win, text=subtitle, color='#666666', wrapWidth=1.60,
                        height=0.055, pos=(0, -0.10), units='norm').draw()
    if wait:
        btn, lbl = _next_button(win)
        _draw_next(btn, lbl)
    win.flip()
    if duration:
        core.wait(duration)
        return
    if wait:
        mouse = event.Mouse(win=win); mouse.clickReset()
        while True:
            check_escape(win)
            visual.TextStim(win, text=text, color='black', wrapWidth=1.60,
                            height=0.08, pos=(0, 0.20), units='norm').draw()
            if subtitle:
                visual.TextStim(win, text=subtitle, color='#666666', wrapWidth=1.60,
                                height=0.055, pos=(0, -0.10), units='norm').draw()
            _draw_next(btn, lbl)
            win.flip()
            if _clicked_next(mouse, btn):
                break
            core.wait(0.01)

def show_image_screen(win, path, text=None, wait=True, audio_path=None):
    if not os.path.exists(path):
        show_text(win, f'[Image not found]\n{os.path.basename(path)}')
        return
    # 1024x1024 images — square, leave room for text above and button below
    asp = image_aspect(path)
    max_sz = 1.10  # smaller to leave clear room for text and button
    w, h = img_size(asp, max_sz, max_sz)
    y = -0.05  # image slightly below centre

    def _draw():
        visual.ImageStim(win, image=path, pos=(0, y), size=(w, h), units='norm').draw()
        if text:
            visual.TextStim(win, text=text, color='black', wrapWidth=1.60,
                            height=0.065, pos=(0, 0.72), units='norm').draw()

    if wait:
        btn, lbl = _next_button(win)
        _draw(); _draw_next(btn, lbl); win.flip()
        if audio_path:
            play_audio(audio_path)
        mouse = event.Mouse(win=win); mouse.clickReset()
        while True:
            check_escape(win)
            _draw(); _draw_next(btn, lbl); win.flip()
            if _clicked_next(mouse, btn):
                break
            core.wait(0.01)
    else:
        _draw(); win.flip()

def _extract_first_frame(video_path):
    """Extract first frame of video as a temp PNG. Returns path or None."""
    try:
        import cv2, tempfile
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ret, frame = cap.read()
        cap.release()
        if ret:
            tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
            cv2.imwrite(tmp.name, frame)
            return tmp.name
    except Exception as e:
        print(f'  [FIRST FRAME ERR] {e}')
    return None

def play_video(win, path, auto_advance=True):
    """Play video. After it ends, hold the last frame with Next button below."""
    if not os.path.exists(path):
        show_text(win, f'[Video not found]\n{os.path.basename(path)}')
        return
    # Max video size: 1.60 norm height, width corrected for screen aspect
    VIDEO_MAX_H = 1.60
    VIDEO_MAX_W = VIDEO_MAX_H / WIN_AR  # visually square pixels
    VIDEO_Y     = 0.10
    btn, lbl    = _next_button(win)
    mouse       = event.Mouse(win=win); mouse.clickReset()
    movie_w = VIDEO_MAX_W; movie_h = VIDEO_MAX_H
    finished    = False
    try:
        movie = _get_movie_stim(win, path, pos=(0, VIDEO_Y),
                                 size=(VIDEO_MAX_W, VIDEO_MAX_H))
        try:
            vw, vh = movie.size
            movie_w, movie_h = fit_size(vw/vh, VIDEO_MAX_W, VIDEO_MAX_H)
            movie.size = (movie_w, movie_h)
        except Exception:
            movie.size = (VIDEO_MAX_W, VIDEO_MAX_H)
        while not movie.isFinished:
            movie.draw()
            if not auto_advance:
                visual.Rect(win, width=2.0, height=0.30, pos=(0, -0.88),
                            fillColor='white', lineColor=None, units='norm').draw()
                _draw_next(btn, lbl)
            win.flip(); check_escape(win)
        finished = True
    except _SkipSection:
        try: movie.stop()
        except Exception: pass
        raise   # let skip propagate — don't swallow it
    except Exception as e:
        print(f'  [VIDEO ERR] {path}: {e}')
        show_text(win, f'[Video: {os.path.basename(path)}]', duration=1.5)
        return
    if not auto_advance and finished:
        # Extract last frame to hold on screen instead of blank
        last_frame = _extract_first_frame(path)
        mouse.clickReset()
        while True:
            check_escape(win)  # 's' raises _SkipSection here too
            if last_frame and os.path.exists(last_frame):
                visual.ImageStim(win, image=last_frame,
                                 pos=(0, VIDEO_Y), size=(movie_w, movie_h),
                                 units='norm').draw()
            visual.Rect(win, width=2.0, height=0.30, pos=(0, -0.88),
                        fillColor='white', lineColor=None, units='norm').draw()
            _draw_next(btn, lbl)
            win.flip()
            if _clicked_next(mouse, btn):
                break
        if last_frame:
            try: os.remove(last_frame)
            except Exception: pass

def play_session_video(win, ss, base, world, lang, local_path, cohort, auto_advance=False):
    if os.path.exists(local_path):
        play_video(win, local_path, auto_advance=auto_advance)
        # _SkipSection propagates naturally from check_escape inside play_video
    else:
        content  = ss.get('content', {})
        path_map = content.get('localizedPath', {})
        vid_id   = (path_map.get(lang,{}) or {}).get(f'cohort_{cohort}', '')
        # Video not found — show placeholder; 's' dismisses like a click
        _old_dev = _DEV_MODE; _DEV_MODE = False
        show_text(win, f'[Video not found locally]\nVimeo ID: {vid_id}\n\n{local_path}')
        _DEV_MODE = _old_dev

# ─────────────────────────────────────────────
# TIMELINE  (gen and pc)
# ─────────────────────────────────────────────
def draw_trial_number(win, q_num, total_q):
    visual.TextStim(win, text=f'{q_num}/{total_q}', color='#aaaaaa',
                    pos=(0.92, 0.90), height=0.04, units='norm').draw()

def draw_timeline(win, current_q, total_q):
    if total_q == 0:
        return
    draw_trial_number(win, current_q, total_q)
    # Square dots — visually square by setting w=h/WIN_AR
    dot_h   = 0.100          # height in norm units
    dot_w   = dot_h / WIN_AR # width corrected for screen aspect → visually square
    spacing = min(0.10, 1.55 / max(total_q-1, 1))
    total_w = spacing * (total_q - 1)
    sx      = -total_w / 2

    for i in range(total_q):
        x = sx + i * spacing
        y = 0.64

        # Connecting line
        if i < total_q - 1:
            x2 = sx + (i+1) * spacing
            visual.Line(win, start=(x+dot_w/2, y), end=(x2-dot_w/2, y),
                        lineColor='#aaaaaa', lineWidth=3.5, units='norm').draw()

        if i < current_q - 1:        # completed — filled square
            visual.Rect(win, width=dot_w, height=dot_h, pos=(x, y),
                        fillColor='#5a3010', lineColor='#5a3010',
                        lineWidth=3.0, units='norm').draw()
        elif i == current_q - 1:     # current — open thick
            visual.Rect(win, width=dot_w, height=dot_h, pos=(x, y),
                        fillColor='white', lineColor='#5a3010',
                        lineWidth=5.0, units='norm').draw()
        else:                         # future — open thin
            visual.Rect(win, width=dot_w, height=dot_h, pos=(x, y),
                        fillColor='white', lineColor='#cccccc',
                        lineWidth=3.0, units='norm').draw()

# ─────────────────────────────────────────────
# INSTRUCTION SCREEN
# ─────────────────────────────────────────────
def show_instruction(win, instr, base, world, lang, num, gen_num, slot='',
                     cohort='a', session=1):
    text_key   = instr.get('text', '')
    audio_tmpl = instr.get('audio','') or ''
    if isinstance(audio_tmpl, list):
        audio_tmpl = audio_tmpl[0] if audio_tmpl else ''
    audio_path = resolve(audio_tmpl, base, world, lang, num, gen_num, slot) if audio_tmpl else ''

    guide = guide_name(world, session)
    cname = city_name(cohort, session)
    gname = gen_city_name(cohort, session)
    text  = get_text(text_key, guideName=guide, cityName=cname, genCityName=gname) \
            if text_key else ''
    print(f'  [INSTR] key={text_key}')
    print(f'          guide={guide} cityName={cname} genCityName={gname}')
    print(f'          text preview: {str(text)[:80]}')

    image_tmpls = instr.get('images', [])
    stims = []
    n = len(image_tmpls)
    xs = {1:[0.0], 2:[-0.50, 0.50], 3:[-0.62, 0.0, 0.62]}.get(n, [0.0]*n)
    for i, tmpl in enumerate(image_tmpls):
        p = resolve(tmpl, base, world, lang, num, gen_num, slot)
        if os.path.exists(p):
            asp = image_aspect(p)
            h = 0.90; _w, _ = img_size(asp, 1.10/max(n,1)*1.8, 0.90); w = _w
            stims.append(visual.ImageStim(win, image=p, pos=(xs[i], -0.10),
                                          size=(w, h), units='norm'))
        else:
            print(f'  [INSTR IMG MISSING] {p}')

    btn, lbl = _next_button(win)

    def draw():
        if text:
            visual.TextStim(win, text=text, color='black', wrapWidth=1.60,
                            height=0.065, pos=(0, 0.58), units='norm').draw()
        for s in stims: s.draw()
        _draw_next(btn, lbl)
        win.flip()

    draw()
    play_audio(audio_path)
    draw()

    mouse = event.Mouse(win=win); mouse.clickReset()
    while True:
        check_escape(win); draw()
        if _clicked_next(mouse, btn):
            break
        core.wait(0.01)

# ─────────────────────────────────────────────
# INTERLUDE  (gamification, skip attn/catch)
# ─────────────────────────────────────────────
SKIP_IDS = {
    'attn','catch','gen_attn','gen_catch','ps_attn','ps_catch','pc_attn','pc_catch',
    'retention_ps_attn','cs_attn','retention_first_pc_flag_content',
    'interlude_re_first_pc_content','retention_second_pc_attn_14',
    're_first_pc_catch','cs_catch','retention_second_pc_catch',
}

def handle_interlude(win, item, base, world, lang, num, gen_num, slot):
    content = item.get('content', {})
    cid   = content.get('id','')
    ctype = content.get('type','')
    tmpl  = content.get('path','')
    path  = resolve(tmpl, base, world, lang, num, gen_num, slot) if tmpl else ''
    # Audio lives on the item itself (not inside content)
    audio_tmpl = item.get('audio', '')
    if isinstance(audio_tmpl, list):
        audio_tmpl = audio_tmpl[0] if audio_tmpl else ''
    audio_path = resolve(audio_tmpl, base, world, lang, num, gen_num, slot) if audio_tmpl else ''

    # Skip attn/catch by content id, resolved path, OR template path
    item_id = item.get('id', '')  # item-level id (e.g. 'prac_attn')
    _skip_keywords = ('attn', 'catch')
    if (cid in SKIP_IDS
            or 'attn_catch' in path
            or 'attn_catch' in tmpl
            or any(k in cid for k in _skip_keywords)
            or any(k in item_id for k in _skip_keywords)):
        return

    # Get overlay text for known interlude ids
    text_map = {
        'continue':            get_text('experiments.common.interludes.continue'),
        'next_session':        get_text('experiments.common.interludes.next_session'),
        'next_session_content':get_text('experiments.common.interludes.next_session'),
        'finished_content':    get_text('experiments.common.interludes.end'),
    }
    overlay = text_map.get(cid, '')

    # Detect gamify by path (coin/unlock/pinpad folders) — IDs are inconsistent across versions
    _is_gamify = any(x in path.lower() for x in ['/gamify/', 'coin_', 'unlock', 'pinpad'])
    print(f'  [INTERLUDE] {cid} gamify={_is_gamify}')
    if ctype == 'video':
        if _is_gamify:
            play_video(win, path, auto_advance=True)   # gamify: auto-advance, no button
        else:
            play_video(win, path, auto_advance=False)  # narrative: Next button after
    elif ctype == 'image':
        # Play audio first, then show image with Next button
        show_image_screen(win, path, text=overlay if overlay else None,
                          wait=True, audio_path=audio_path if audio_path else None)

# ─────────────────────────────────────────────
# GEN QUESTION  (3 videos, sequential, then click)
# ─────────────────────────────────────────────
def run_gen_question(win, q, base, world, lang, num, gen_num, slot,
                     subsession_name, q_num, total_q, recorder,
                     cohort='a', session=1):
    event_id = str(q.get('eventId',''))
    q_id     = q.get('id', event_id)  # e.g. 'first_city_gen_1'
    q_text   = q.get('text','')
    choices  = q.get('choices',[])
    q_slot   = str(q.get('citySlot', slot)) if q.get('citySlot') else slot

    audio_tmpl = q.get('audio','')
    if isinstance(audio_tmpl, list): audio_tmpl = audio_tmpl[0] if audio_tmpl else ''
    audio_path = resolve(audio_tmpl, base, world, lang, num, gen_num, q_slot) if audio_tmpl else ''

    guide  = guide_name(world, session)
    cname  = city_name(cohort, session)
    gname  = gen_city_name(cohort, session)
    prompt = get_text(q_text, guideName=guide, cityName=cname, genCityName=gname) \
             if q_text else ''

    rc = []
    for ch in choices:
        cc = ch.get('content',{})
        p  = resolve(cc.get('path',''), base, world, lang, num, gen_num, q_slot)
        rc.append({'id': ch.get('id',''), 'content_id': cc.get('id',''),
                   'isCorrect': ch.get('isCorrect',None), 'path': p})

    n = len(rc)
    if n == 0: return

    # Layout in height units (window is 1080×1080, units='norm' → 1.0 = full height)
    # box_h = visual height in norm; box_w = norm width for a visually square box
    box_h  = 0.80
    box_w  = box_h / WIN_AR  # visually square on any monitor
    gap    = 0.08
    total  = n * box_w + (n-1) * gap
    sx     = -total/2 + box_w/2
    positions = [(sx + i*(box_w+gap), -0.05) for i in range(n)]

    # ── Step 0: show screen with all 3 boxes GRAY, then play audio ────────
    # Capture first frame of each video using PIL / cv2 for "first frame" display
    first_frames = []
    for ch in rc:
        frame_img = None
        if os.path.exists(ch['path']):
            try:
                import cv2
                cap = cv2.VideoCapture(ch['path'])
                ret, frame = cap.read()
                cap.release()
                if ret:
                    import tempfile, cv2 as _cv2
                    frame_rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
                    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                    _cv2.imwrite(tmp.name, _cv2.cvtColor(frame_rgb, _cv2.COLOR_RGB2BGR))
                    frame_img = tmp.name
            except Exception as e:
                print(f'  [FIRST FRAME ERR] {e}')
        first_frames.append(frame_img)

    def draw_all_boxes(played_up_to, playing_now=-1, first_frames=first_frames):
        """Draw all n boxes. played_up_to = how many are done (show first frame).
        playing_now = index currently playing (-1 = none)."""
        draw_timeline(win, q_num, total_q)
        if prompt:
            visual.TextStim(win, text=prompt, color='black', wrapWidth=1.60,
                            height=0.065, pos=(0, 0.50), units='norm').draw()
        for i, pos in enumerate(positions):
            ff = first_frames[i]
            if ff and os.path.exists(ff):
                asp = image_aspect(ff)
                if i < played_up_to:
                    # Played — full colour first frame, no border
                    visual.ImageStim(win, image=ff, pos=pos,
                                     size=(box_w, box_h), units='norm').draw()
                elif i == playing_now:
                    pass  # nothing drawn — movie fills this slot on top
                else:
                    # Not yet — first frame at low opacity (grayed out), no border
                    visual.ImageStim(win, image=ff, pos=pos,
                                     size=(box_w, box_h), opacity=0.30,
                                     units='norm').draw()
            else:
                # Fallback if no first frame
                col = '#e0e0e0' if i < played_up_to else '#cccccc'
                visual.Rect(win, width=box_w, height=box_h, pos=pos,
                            fillColor=col, lineColor=None,
                            lineWidth=0, units='norm').draw()

    # Pre-create ImageStim objects once (not on every frame)
    ff_stims = {}
    for i, ff in enumerate(first_frames):
        if ff and os.path.exists(ff):
            ff_stims[i] = visual.ImageStim(win, image=ff, pos=positions[i],
                                            size=(box_w, box_h), units='norm')

    def draw_boxes_fast(played_up_to, playing_now=-1):
        draw_timeline(win, q_num, total_q)
        if prompt:
            visual.TextStim(win, text=prompt, color='black', wrapWidth=1.60,
                            height=0.065, pos=(0, 0.50), units='norm').draw()
        for i, pos in enumerate(positions):
            stim = ff_stims.get(i)
            if i < played_up_to:
                if stim: stim.setOpacity(1.0); stim.draw()
            elif i == playing_now:
                pass  # movie draws on top
            else:
                if stim: stim.setOpacity(0.30); stim.draw()
                else:
                    visual.Rect(win, width=box_w, height=box_h, pos=pos,
                                fillColor='#cccccc', lineColor=None,
                                units='norm').draw()

    # Show all gray boxes and play question audio
    draw_boxes_fast(0)
    win.flip()
    play_audio(audio_path)

    # ── Phase 1: play each animation sequentially ───────────────────────
    for play_idx in range(n):
        if not os.path.exists(rc[play_idx]['path']):
            print(f'  [VIDEO MISSING] {rc[play_idx]["path"]}')
            core.wait(0.5)
            continue
        try:
            movie = _get_movie_stim(win, rc[play_idx]['path'],
                                     pos=positions[play_idx],
                                     size=(box_w, box_h))
            while not movie.isFinished:
                draw_boxes_fast(play_idx, playing_now=play_idx)
                movie.draw()
                win.flip()
                check_escape(win)
        except _SkipSection:
            try: movie.stop()
            except Exception: pass
            raise
        except Exception as e:
            print(f'  [VIDEO ERR] {rc[play_idx]["path"]}: {e}')
            core.wait(0.5)

        # After this video ends: show its first frame, rest still gray
        draw_boxes_fast(play_idx + 1)
        win.flip()
        core.wait(0.3)

    # ── Phase 2: all played — participant clicks to choose ───────────────
    mouse = event.Mouse(win=win); mouse.clickReset()
    selected_idx = None
    confirmed    = False
    clock        = core.Clock()
    btn, next_lbl = _next_button(win)

    while not confirmed:
        check_escape(win)
        draw_timeline(win, q_num, total_q)

        if prompt:
            visual.TextStim(win, text=prompt, color='black', wrapWidth=1.60,
                            height=0.065, pos=(0, 0.50), units='norm').draw()
        for i, pos in enumerate(positions):
            ff = first_frames[i]
            if ff and os.path.exists(ff):
                asp = image_aspect(ff)
                if i == selected_idx:
                    # Light green border to indicate selection
                    visual.Rect(win, width=box_w+0.03, height=box_h+0.03, pos=pos,
                                fillColor='#ccecea', lineColor='#006C66',
                                lineWidth=2, units='norm').draw()
                visual.ImageStim(win, image=ff, pos=pos,
                                 size=(box_w, box_h), units='norm').draw()
            else:
                if i == selected_idx:
                    visual.Rect(win, width=box_w, height=box_h, pos=pos,
                                fillColor='#ccecea', lineColor='#006C66',
                                lineWidth=2, units='norm').draw()
                visual.TextStim(win, text=str(i+1), color='#444444',
                                pos=pos, height=0.10, units='norm').draw()
        _draw_next(btn, next_lbl)
        win.flip()

        if mouse.getPressed()[0]:
            mp = mouse.getPos()
            for i, pos in enumerate(positions):
                if abs(mp[0]-pos[0]) < box_w/2 and abs(mp[1]-pos[1]) < box_h/2:
                    selected_idx = i
                    mouse.clickReset()
                    break
            if _clicked_next(mouse, btn) and selected_idx is not None:
                confirmed = True; rt = clock.getTime()
        core.wait(0.01)

    # Cleanup temp first-frame files
    import os as _os
    for ff in first_frames:
        if ff:
            try: _os.remove(ff)
            except Exception: pass

    chosen = rc[selected_idx]
    recorder.record(
        city=_city_for_session(cohort, session),
        citySlot='',
        trial=q_id,
        event_id=event_id,
        task_id='gen',
        choice=_choice_number(rc, selected_idx),
        choiceContent=chosen.get('content_id',''),
        correct=chosen['isCorrect'],
        rt_seconds=round(rt,4))

# ─────────────────────────────────────────────
# MC QUESTION  (ps / pc / retention — images)
# ─────────────────────────────────────────────
def run_mc_question(win, q, base, world, lang, num, gen_num, slot,
                    group_type, subsession_name, q_num, total_q, recorder,
                    cohort='a', session=1):
    event_id = str(q.get('eventId',''))
    q_id     = q.get('id', event_id)  # e.g. 'first_city_gen_1'
    q_text   = q.get('text','')
    choices  = q.get('choices',[])
    q_slot   = str(q.get('citySlot', slot)) if q.get('citySlot') else slot

    audio_tmpl = q.get('audio','')
    if isinstance(audio_tmpl, list): audio_tmpl = audio_tmpl[0] if audio_tmpl else ''
    audio_path = resolve(audio_tmpl, base, world, lang, num, gen_num, q_slot) if audio_tmpl else ''

    guide  = guide_name(world, session)
    cname  = city_name(cohort, session)
    gname  = gen_city_name(cohort, session)
    prompt = get_text(q_text, guideName=guide, cityName=cname, genCityName=gname) \
             if q_text else ''

    rc = []
    for ch in choices:
        cc = ch.get('content',{})
        p  = resolve(cc.get('path',''), base, world, lang, num, gen_num, q_slot)
        rc.append({'id': ch.get('id',''), 'content_id': cc.get('id',''),
                   'isCorrect': ch.get('isCorrect',None),
                   'path': p, 'type': cc.get('type','')})

    n = len(rc)
    if n == 0: return

    show_timeline = group_type in ('pc','prac_pc','pc_retention_s1','pc_retention_s2')

    box_h = 0.80
    box_w = box_h / WIN_AR  # visually square
    gap   = 0.08
    total = n*box_w + (n-1)*gap
    sx    = -total/2 + box_w/2
    positions = [(sx + i*(box_w+gap), -0.05) for i in range(n)]

    img_stims = []
    for i, ch in enumerate(rc):
        if ch['type'] == 'image' and os.path.exists(ch['path']):
            img_stims.append(visual.ImageStim(win, image=ch['path'],
                                              pos=positions[i],
                                              size=(box_w, box_h),
                                              units='norm'))
        else:
            img_stims.append(None)

    mouse = event.Mouse(win=win); mouse.clickReset()
    selected_idx = None; confirmed = False
    clock = core.Clock()
    btn, next_lbl = _next_button(win)
    audio_played  = False   # play audio on first draw

    while not confirmed:
        check_escape(win)
        if show_timeline:
            draw_timeline(win, q_num, total_q)

        for i, pos in enumerate(positions):
            if i == selected_idx:
                visual.Rect(win, width=box_w+0.025, height=box_h+0.025, pos=pos,
                            fillColor='#ccecea', lineColor='#4CAF9A',
                            lineWidth=2, units='norm').draw()
            if img_stims[i]:
                img_stims[i].draw()
            else:
                visual.TextStim(win, text=os.path.basename(rc[i]['path']),
                                color='#666666', pos=pos,
                                height=0.05, wrapWidth=box_w*0.9,
                                units='norm').draw()

        if prompt:
            visual.TextStim(win, text=prompt, color='black', wrapWidth=1.60,
                            height=0.065, pos=(0, 0.50), units='norm').draw()
        _draw_next(btn, next_lbl)
        win.flip()

        if not audio_played:
            audio_played = True
            play_audio(audio_path)

        if mouse.getPressed()[0]:
            mp = mouse.getPos()
            for i, pos in enumerate(positions):
                if abs(mp[0]-pos[0]) < box_w/2 and abs(mp[1]-pos[1]) < box_h/2:
                    selected_idx = i; mouse.clickReset(); break
            if _clicked_next(mouse, btn) and selected_idx is not None:
                confirmed = True; rt = clock.getTime()

    chosen = rc[selected_idx]
    q_slot_val = q.get('citySlot', '') or ''
    recorder.record(
        city=_city_for_session(cohort, session),
        citySlot=q_slot_val,
        trial=str(q.get('id', event_id)),
        event_id=event_id,
        task_id=group_type,
        choice=_choice_number(rc, selected_idx),
        choiceContent=chosen.get('content_id',''),
        correct=chosen['isCorrect'],
        rt_seconds=round(rt,4))

# ─────────────────────────────────────────────
# CITY SORTING
# ─────────────────────────────────────────────
def run_citysorting_question(win, q, base, world, lang, num, gen_num, slot,
                              subsession_name, q_num, recorder,
                              cohort='a', session=1):
    event_id = str(q.get('eventId',''))
    q_slot   = str(q.get('citySlot', slot)) if q.get('citySlot') else slot
    choices  = q.get('choices',[])

    audio_tmpl = q.get('audio','')
    if isinstance(audio_tmpl, list): audio_tmpl = audio_tmpl[0] if audio_tmpl else ''
    audio_path = resolve(audio_tmpl, base, world, lang, num, gen_num, q_slot) if audio_tmpl else ''

    if event_id == 'guide':
        run_mc_question(win, q, base, world, lang, num, gen_num, slot,
                        'citysorting', subsession_name, q_num, 0, recorder,
                        cohort=cohort, session=session)
        return

    img_tmpl = q.get('image','')
    img_path = resolve(img_tmpl, base, world, lang, num, gen_num, q_slot) if img_tmpl else ''
    prompt   = get_text('experiments.common.questions.citysorting')

    play_audio(audio_path)

    btn1 = visual.Rect(win, width=0.65, height=0.18, pos=(-0.38,-0.72),
                       fillColor='#006C66', lineColor='#006C66', units='norm')
    btn2 = visual.Rect(win, width=0.65, height=0.18, pos=(0.38,-0.72),
                       fillColor='#006C66', lineColor='#006C66', units='norm')
    lbl1 = visual.TextStim(win, text='Stadt 1', color='white',
                           pos=(-0.38,-0.72), height=0.07, units='norm')
    lbl2 = visual.TextStim(win, text='Stadt 2', color='white',
                           pos=(0.38,-0.72), height=0.07, units='norm')

    img_stim = None
    if img_path and os.path.exists(img_path):
        asp  = image_aspect(img_path)
        w, h = img_size(asp, 1.30, 1.00)
        img_stim = visual.ImageStim(win, image=img_path, pos=(0, 0.15),
                                    size=(w, h), units='norm')

    mouse = event.Mouse(win=win); mouse.clickReset()
    clock = core.Clock(); selected = None; confirmed = False
    correct_city = choices[0].get('content',{}).get('id','') if choices else ''

    while not confirmed:
        check_escape(win)
        if img_stim: img_stim.draw()
        if prompt:
            visual.TextStim(win, text=prompt, color='black', wrapWidth=1.60,
                            height=0.065, pos=(0,-0.48), units='norm').draw()
        btn1.draw(); btn2.draw(); lbl1.draw(); lbl2.draw()
        win.flip()
        if mouse.getPressed()[0]:
            mp = mouse.getPos()
            if abs(mp[0]+0.38) < 0.325 and abs(mp[1]+0.72) < 0.09:
                selected='1'; confirmed=True; rt=clock.getTime()
            elif abs(mp[0]-0.38) < 0.325 and abs(mp[1]+0.72) < 0.09:
                selected='2'; confirmed=True; rt=clock.getTime()
        core.wait(0.01)

    recorder.record(
        city=_city_for_session(cohort, session),
        citySlot=q_slot,
        trial=str(q.get('id', event_id)),
        event_id=event_id,
        task_id='citysorting',
        choice=int(selected),
        choiceContent=correct_city,
        correct='',
        rt_seconds=round(rt,4))

# ─────────────────────────────────────────────
# GROUP RUNNER
# ─────────────────────────────────────────────
def run_group(win, group, base, world, lang, num, gen_num, slot,
              subsession_name, recorder, cohort='a', session=1, start_trial=0):
    gtype   = group.get('type','unknown')
    items   = group.get('questions',[])
    total_q = sum(1 for it in items if it.get('type')=='question')
    print(f'\n  [GROUP] {gtype} ({total_q} questions)')

    # Entered this group — nothing completed in it yet (unless we're resuming
    # straight into the middle of it, in which case the loop below will
    # overwrite this with the real trial number as soon as it processes one).
    recorder.save_progress(subsession_name, gtype, 0)

    # start_trial only applies to the specific group we're resuming into —
    # skipping its instructions too, since those were already seen before the crash.
    if not (start_trial > 0):
        for instr in group.get('instructions',[]):
            try:
                show_instruction(win, instr, base, world, lang, num, gen_num, slot,
                                 cohort=cohort, session=session)
            except _SkipSection:
                print(f'[DEV] Skipped group instruction')

    q_num = 0
    for item in items:
        itype = item.get('type','question')
        if itype == 'question':
            q_num += 1
            if start_trial > 0 and q_num < start_trial:
                print(f'[RESUME] Skipping trial {q_num} in {gtype}')
                continue
        try:
            if itype == 'interlude':
                handle_interlude(win, item,
                                 base, world, lang, num, gen_num, slot)
            elif itype == 'question':
                if gtype == 'gen':
                    run_gen_question(win, item, base, world, lang, num, gen_num, slot,
                                     subsession_name, q_num, total_q, recorder,
                                     cohort=cohort, session=session)
                elif gtype == 'citysorting':
                    run_citysorting_question(win, item, base, world, lang, num, gen_num, slot,
                                             subsession_name, q_num, recorder,
                                             cohort=cohort, session=session)
                else:
                    run_mc_question(win, item, base, world, lang, num, gen_num, slot,
                                    gtype, subsession_name, q_num, total_q, recorder,
                                    cohort=cohort, session=session)
        except _SkipSection:
            print(f'[DEV] Skipped item {q_num} in {gtype}')
        if itype == 'question':
            # Completed (or deliberately skipped) — either way we've moved past
            # it, so a resume should pick up at the next trial.
            recorder.save_progress(subsession_name, gtype, q_num)
    try:
        check_escape(win)
    except _SkipSection:
        print(f'[DEV] Skip between items in {gtype} — continuing to next group')

# ─────────────────────────────────────────────
# SUBSESSION RUNNER
# ─────────────────────────────────────────────
def run_subsession(win, ss, base, world, lang, cohort, session_num, version,
                   full_videos_dir, recorder):
    name   = ss.get('name','')
    ss_id  = ss.get('id','')
    content= ss.get('content',{})
    print(f'\n[SUBSESSION] {name or ss_id}')

    # Entered this subsession — group/trial unknown until run_group updates it.
    recorder.save_progress(name or ss_id, '', 0)

    # num = actual city folder for this cohort/session
    # cohort_a: City1/2/3, cohort_b: City4/5/6
    _sess_base = SESSION_CITY.get(session_num, 1)  # 1, 2, or 3
    num     = str(int(_sess_base) + (3 if cohort == 'b' else 0))
    gen_num = str(int(_sess_base) + (0 if cohort == 'b' else 3))
    slot    = num

    # Are we resuming INTO this subsession specifically (vs. just running it
    # normally because we already passed the resume point)?
    resuming_this_ss = bool(_START_SS) and (name == _START_SS or ss_id == _START_SS)
    # If a subtask was also given, skip this subsession's intro video/instructions
    # entirely and jump straight to that subtask's group.
    skip_intro = resuming_this_ss and bool(_START_GROUP)

    if content and not skip_intro:
        cid = content.get('id','')
        if ss_id == 'cover_story':
            local_path = os.path.join(base, world, 'cover', lang, 'cover.mp4')
        elif ss_id == 'continue_cover':
            local_path = os.path.join(base, world, 'cover', lang, 'continue.mp4')
        elif cid == 'prac_video':
            local_path = os.path.join(base, 'City0', 'common', lang, 'prac_video.mp4')
        else:
            local_path = get_encoding_video_path(full_videos_dir, cohort,
                                                  session_num, version, lang)
        print(f'  [VIDEO PATH] {local_path}  exists={os.path.exists(local_path)}')
        try:
            play_session_video(win, ss, base, world, lang, local_path, cohort,
                               auto_advance=False)
        except _SkipSection:
            print(f'[DEV] Skipped video: {os.path.basename(local_path)}')
    elif skip_intro:
        print(f'[RESUME] Skipping intro video for {name or ss_id} (resuming at subtask "{_START_GROUP}")')

    if not skip_intro:
        for instr in ss.get('instructions',[]):
            try:
                show_instruction(win, instr, base, world, lang, num, gen_num, slot,
                                 cohort=cohort, session=session_num)
            except _SkipSection:
                print(f'[DEV] Skipped instruction')

    # If resuming with a target subtask, skip groups until we reach it.
    _group_target_found = not (resuming_this_ss and _START_GROUP)
    for group in ss.get('questionsGroups',[]):
        gtype = group.get('type','unknown')
        if not _group_target_found:
            if gtype == _START_GROUP:
                _group_target_found = True
            else:
                print(f'[RESUME] Skipping subtask: {gtype} (waiting for "{_START_GROUP}")')
                continue
        # Only the exact group we resumed into gets the trial-skip; any group
        # after it in the same subsession starts from its own beginning.
        this_group_start_trial = _START_TRIAL if (resuming_this_ss and gtype == _START_GROUP) else 0
        try:
            run_group(win, group, base, world, lang, num, gen_num, slot,
                      name or ss_id, recorder, cohort=cohort, session=session_num,
                      start_trial=this_group_start_trial)
        except _SkipSection:
            print(f'[DEV] Skipped group: {gtype}')

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    # ── Hardcoded paths — edit once ──────────
    # Use script location so paths work on both Mac and Windows
    BASE_PATH        = os.path.dirname(os.path.abspath(__file__))
    ASSET_BASE       = os.path.join(BASE_PATH, 'assets')
    JSON_FOLDER      = BASE_PATH
    FULL_VIDEOS_DIR  = os.path.join(ASSET_BASE, 'underwater', '_full_videos')
    LOCALES_PATH = os.path.join(BASE_PATH, 'assets', 'underwater', 'locales')
    # ─────────────────────────────────────────
    # translations loaded after language confirmed in GUI

    # Default values — updated on each loop so dialog re-opens pre-filled
    _vals = dict(pid='', age='', session='', lang='de',
                 cohort='', version='', world='underwater',
                 start_ss='', start_group='', start_trial='', pilot=False)

    # Subsession choices exposed to the resume dropdown, and — per subsession —
    # which subtask/group types actually exist in that subsession's JSON.
    # NB: the practice tour's third group is typed 'prac_pc' in the JSON
    # (not 'pc') — that's the value actually matched against, even though
    # it plays the same role as 'pc' in the real sessions.
    SS_CHOICES = ['', 'Practice Tour', 'first city tour',
                  'second city tour', 'third city tour']
    SUBTASK_CHOICES_BY_SS = {
        'Practice Tour':     ['', 'gen', 'ps', 'prac_pc'],
        'first city tour':   ['', 'gen', 'ps', 'pc'],
        'second city tour':  ['', 'gen', 'ps', 'pc'],
        'third city tour':   ['', 'gen', 'ps', 'pc',
                               'citysorting', 'pc_retention_s1', 'pc_retention_s2'],
    }

    # ── Stage 0: participant ID + session lookup ─────────────────────
    # Ask for these two first, on their own, so returning participants (e.g.
    # after a crash) don't have to retype age/language, risk a cohort/version
    # typo, or hunt through logs to find where they left off.
    _id_error = ''
    while True:
        iddlg = gui.Dlg(title='City Tour Experiment — Participant')
        if _id_error:
            iddlg.addText(_id_error, color='red')
        iddlg.addText('Enter the participant ID and session. If this participant has\n'
                      'run before, their info — and where they left off, if a session\n'
                      'was interrupted — will be filled in automatically.',
                      color='gray')
        iddlg.addField('Participant ID (required, 6 chars):', _vals['pid'])
        iddlg.addField('Session (required):', _vals['session'], choices=['','1','2','3'])
        iok = iddlg.show()
        if not iddlg.OK: core.quit()
        _pid_lookup     = iok[0].strip()
        _session_lookup = iok[1].strip()
        if not _pid_lookup:
            _id_error = '⚠  Participant ID is required.'; continue
        if not re.match(r'^[A-Za-z0-9]{6}$', _pid_lookup):
            _id_error = '⚠  Participant ID must be exactly 6 letters/numbers (e.g. P00001).'; continue
        if not _session_lookup:
            _id_error = '⚠  Session is required.'; continue
        break

    _vals['pid']     = _pid_lookup
    _vals['session'] = _session_lookup
    _returning_note = ''
    _prior_rec = get_participant_record(_pid_lookup)
    if _prior_rec:
        if _prior_rec.get('age_group'):
            _vals['age'] = str(_prior_rec['age_group'])
        if _prior_rec.get('lang'):
            _vals['lang'] = _prior_rec['lang']
        _returning_note = (
            f"✓ Returning participant — prior record found: "
            f"Age {_prior_rec.get('age_group','?')}, "
            f"Lang {_prior_rec.get('lang') or '?'}, "
            f"Cohort {_prior_rec.get('cohort','?').upper()}, "
            f"Version v{_prior_rec.get('version','?')}.\n"
            f"Age/Language pre-filled below — leave Cohort/Version overrides blank "
            f"to reuse the same assignment automatically.\n")

        # Was Session {_session_lookup} left mid-way? Auto-fill the resume fields.
        if not session_already_run(_pid_lookup, int(_session_lookup)):
            _progress = get_progress(_pid_lookup, int(_session_lookup))
            if _progress and _progress.get('subsession') in SS_CHOICES:
                _vals['start_ss'] = _progress['subsession']
                if _progress.get('group'):
                    _vals['start_group'] = _progress['group']
                    # trial=0 in the saved progress means nothing in that group
                    # was completed yet (instructions may not have been seen) —
                    # leave start_trial at 0 so they replay from the group's own
                    # beginning, instead of skipping straight past its intro.
                    if _progress.get('trial', 0) > 0:
                        _vals['start_trial'] = str(_progress['trial'] + 1)
                _resume_bits = _progress['subsession']
                if _progress.get('group'):
                    _resume_bits += f" → {_progress['group']}"
                    if _vals['start_trial']:
                        _resume_bits += f" → trial {_vals['start_trial']}"
                _returning_note += (
                    f"⏸ Session {_session_lookup} looks unfinished — last seen at: "
                    f"{_resume_bits}.\n"
                    f"Resume fields pre-filled below — clear them if you'd rather "
                    f"restart this session from the top.\n")

    def _build_main_dlg(v, error_msg=''):
        d = gui.Dlg(title='City Tour Experiment')
        if error_msg:
            d.addText(error_msg, color='red')
        if _returning_note:
            d.addText(_returning_note, color='#006C66')
        d.addText('─── Participant ───', color='navy')
        d.addField('Participant ID (required, 6 chars):', v['pid'])
        d.addField('Age in years (required):',            v['age'])
        d.addField('Session (required):',   v['session'], choices=['','1','2','3'])
        d.addField('Language:',             v['lang'],    choices=['de','en'])
        d.addText('─── Override (optional — leave blank for auto-assign) ───', color='gray')
        d.addField('Cohort (a / b):',  v['cohort'])
        d.addField('Version (1-4):',   v['version'])
        d.addText('─── World ───', color='navy')
        d.addField('World folder:',    v['world'])   # ← update default for each timepoint
        d.addText('─── Resume (blank = start from beginning) ───', color='gray')
        d.addField('Start from subsession:', v.get('start_ss',''), choices=SS_CHOICES)
        d.addField('Pilot mode (skip enabled, no counter):', v['pilot'])
        return d

    def _build_subtask_dlg(v, subtask_choices, error_msg=''):
        d = gui.Dlg(title='Resume — pick subtask')
        if error_msg:
            d.addText(error_msg, color='red')
        d.addText(f"Subsession: {v['start_ss']}", color='navy')
        d.addField('Start from subtask (blank = beginning of subsession):',
                   v.get('start_group','') if v.get('start_group','') in subtask_choices else '',
                   choices=subtask_choices)
        d.addField('Start from trial # within that subtask (0 = its beginning):',
                   v.get('start_trial',''))
        return d

    while True:  # outer — loops back if user clicks Back/Cancel further down
        _error_msg = ''
        while True:
            dlg = _build_main_dlg(_vals, _error_msg)
            ok  = dlg.show()
            if not dlg.OK: core.quit()

            # Save values so dialog re-opens pre-filled if validation fails
            _vals['pid']     = ok[0].strip()
            _vals['age']     = ok[1].strip()
            _vals['session'] = ok[2].strip()
            _vals['lang']    = ok[3]
            _vals['cohort']  = ok[4].strip().lower()
            _vals['version'] = ok[5].strip()
            _vals['world']       = ok[6].strip()
            _vals['start_ss']    = ok[7].strip()
            _vals['pilot']       = bool(ok[8])

            pid              = _vals['pid']
            age_str          = _vals['age']
            session_str      = _vals['session']
            lang             = _vals['lang']
            override_cohort  = _vals['cohort']
            override_version = _vals['version']
            world            = _vals['world']
            start_ss         = _vals.get('start_ss', '')
            pilot_mode       = _vals['pilot']
            fullscr          = True  # always fullscreen, pilot or not

            errors = []
            # Participant ID: required, max 6 alphanumeric chars
            if not pid:
                errors.append('Participant ID is required.')
            elif not re.match(r'^[A-Za-z0-9]{6}$', pid):
                errors.append('Participant ID must be exactly 6 letters/numbers (e.g. P00001).')
            # Age: required, digits only
            if not age_str:
                errors.append('Age is required.')
            elif not age_str.isdigit():
                errors.append('Age must be a number.')
            # Session: required
            if not session_str:
                errors.append('Session is required.')
            # Override cohort/version: if one is filled both must be filled and valid
            cohort_filled  = override_cohort in ('a','b')
            version_filled = override_version in ('1','2','3','4')
            if override_cohort and not cohort_filled:
                errors.append("Cohort override must be 'a' or 'b'.")
            if override_version and not version_filled:
                errors.append('Version override must be 1, 2, 3, or 4.')
            if bool(override_cohort) != bool(override_version):
                errors.append('Fill in BOTH cohort and version, or leave both blank.')

            if errors:
                # Re-open main dialog with errors shown at top (values pre-filled)
                _error_msg = '⚠  ' + '   •  '.join(errors)
                continue

            # Duplicate session check — skip if override supplied
            has_override = cohort_filled and version_filled
            if not has_override and session_str and session_already_run(pid, int(session_str)):
                _error_msg = (f'⚠  {pid} already completed Session {session_str}. '
                              f'Check the ID and session, or supply overrides to run anyway.')
                continue

            # Consistency check for returning participants — catches a typo'd
            # age/language/cohort/version that would otherwise silently diverge
            # from what this participant actually ran before.
            _rec = get_participant_record(pid)
            if _rec:
                mismatches = []
                if age_str and _rec.get('age_group') and age_str != str(_rec['age_group']):
                    mismatches.append(f"Age — entered {age_str}, prior record has {_rec['age_group']}")
                if _rec.get('lang') and lang != _rec['lang']:
                    mismatches.append(f"Language — entered {lang}, prior record has {_rec['lang']}")
                if override_cohort and override_cohort != _rec.get('cohort'):
                    mismatches.append(f"Cohort override — entered {override_cohort.upper()}, "
                                      f"prior record has {str(_rec.get('cohort','?')).upper()}")
                if override_version and override_version != str(_rec.get('version','')):
                    mismatches.append(f"Version override — entered v{override_version}, "
                                      f"prior record has v{_rec.get('version','?')}")
                if mismatches:
                    warn = gui.Dlg(title='⚠ Mismatch for returning participant')
                    warn.addText(
                        f'{pid} has a prior record, but this does not match it:\n\n' +
                        '\n'.join(f'  •  {m}' for m in mismatches) +
                        '\n\nOK = proceed with the values just entered '
                        '(only if that mismatch is really intended)\n'
                        'Cancel = go back and fix')
                    warn.show()
                    if not warn.OK:
                        _error_msg = ''
                        continue  # back to main dialog, values still pre-filled

            _error_msg = ''  # clear errors on success
            break

        # ── Stage 2: subtask, ONLY shown (and only offering choices that
        # actually exist) once a subsession has been picked ─────────────
        if start_ss:
            subtask_choices = SUBTASK_CHOICES_BY_SS.get(start_ss, [''])
            _sub_error = ''
            while True:
                sdlg = _build_subtask_dlg(_vals, subtask_choices, _sub_error)
                sok  = sdlg.show()
                if not sdlg.OK:
                    # Back — return to the main dialog (subsession, etc. stay pre-filled)
                    break
                _vals['start_group'] = sok[0].strip()
                _vals['start_trial'] = sok[1].strip()
                start_group = _vals['start_group']
                start_trial = int(start_trial_s) if (start_trial_s := _vals['start_trial'].strip()).isdigit() else 0
                if start_trial > 0 and not start_group:
                    _sub_error = '⚠  Pick a subtask (gen/ps/pc/…) to go with that trial #.'
                    continue
                _sub_error = ''
                break
            if not sdlg.OK:
                continue  # back to outer loop → main dialog again
        else:
            _vals['start_group'] = ''
            _vals['start_trial'] = ''
            start_group = ''
            start_trial = 0

        session = int(session_str)

        # Load translations in the confirmed language
        load_translations(os.path.join(LOCALES_PATH, lang, 'translation.json'))

        # dev_mode  = pilot checkbox ticked
        # has_override = cohort+version manually specified
        # Skip ('s') enabled only in pilot mode
        # Counter only incremented for real runs (not pilot, not override)
        dev_mode     = pilot_mode
        has_override = cohort_filled and version_filled

        if has_override:
            # Manual override — use supplied values, do NOT touch counter
            cohort  = override_cohort
            version = int(override_version)
        elif dev_mode:
            # Pilot mode without override — still auto-assign and PERSIST the
            # record (so a crash-resume or the mismatch-check keeps working for
            # pilot IDs too), but never advance the real counterbalancing counter.
            cohort, version = assign_cohort_version(pid, age_str, lang=lang, advance_counter=False)
        else:
            # Real participant — auto-assign and increment counter
            cohort, version = assign_cohort_version(pid, age_str, lang=lang)

        global _DEV_MODE, _START_SS, _START_GROUP, _START_TRIAL
        _DEV_MODE    = dev_mode
        _START_SS    = start_ss
        _START_GROUP = start_group
        _START_TRIAL = start_trial

        if start_ss:
            resume_line = f'Resume at  : {start_ss}'
            if start_group:
                resume_line += f' → {start_group}'
                if start_trial:
                    resume_line += f' → trial {start_trial}'
            resume_line += '\n'
        else:
            resume_line = ''

        confirm = gui.Dlg(title='Please confirm')
        confirm.addText(
            f'Participant : {pid}\n'
            f'Age         : {age_str}\n'
            f'Cohort      : {cohort.upper()}  '
            f'({"manual" if has_override else "auto-assigned"})\n'
            f'Version     : v{version}\n'
            f'Session     : {session}\n'
            f'Language    : {lang}\n'
            f'World       : {world}\n'
            f'{resume_line}'
            f'Pilot mode  : {"YES — skip enabled, counter unchanged" if dev_mode else "NO"}\n\n'
            f'OK = start session     Cancel = back to edit')
        confirm.show()
        if not confirm.OK:
            # User wants to go back — loop returns to main dialog, values pre-filled
            _error_msg = ''
            continue  # back to outer while True
        break  # confirm accepted — exit outer loop

    json_file = os.path.join(JSON_FOLDER, f'session_{session}_v{version}.json')
    if not os.path.exists(json_file):
        print(f'ERROR: JSON not found: {json_file}'); core.quit()
    with open(json_file, encoding='utf-8') as f:
        session_data = json.load(f)

    recorder = DataRecorder(pid, age_str, session, cohort, version, lang)
    win      = make_window(fullscr=fullscr)
    _init_kb()  # start hardware keyboard listener after window is open

    # Welcome screen — 's' does nothing here, only escape works
    _old_dev = _DEV_MODE
    _DEV_MODE = False
    show_text(win, f'Session {session}')
    _DEV_MODE = _old_dev

    _completed_normally = False
    try:
        _reached_ss = not bool(_START_SS)
        for ss in session_data.get('subSessions',[]):
            ss_name = ss.get('name', ss.get('id',''))
            if not _reached_ss:
                if ss_name == _START_SS:
                    _reached_ss = True
                else:
                    print(f'[RESUME] Skipping subsession: {ss_name}')
                    continue
            try:
                run_subsession(win, ss, ASSET_BASE, world, lang,
                               cohort, session, version, FULL_VIDEOS_DIR, recorder)
            except _SkipSection:
                print(f'[DEV] Skipped to next subsession')
        _completed_normally = True
    except Exception as e:
        import traceback; traceback.print_exc()
    finally:
        recorder.save()
        # Escape calls core.quit() directly, which raises SystemExit — that
        # skips 'except Exception' above but still runs this 'finally', so
        # _completed_normally correctly stays False for an Escape-quit too.
        # Only a session that actually reached the end should ever be marked
        # complete or have its resume point cleared.
        if _completed_normally:
            if not dev_mode and not has_override:
                mark_session_complete(pid, session)
            # Finished for real — a future rerun (e.g. via override) shouldn't
            # be offered this stale mid-session resume point.
            clear_progress(pid, session)

    _end_title = get_text('sessionEnd.session3.title') if session == 3 \
              else get_text('sessionEnd.session12.title')
    _end_msg   = get_text('sessionEnd.session3.message') if session == 3 \
              else get_text('end_session.next')
    show_text(win, _end_title, subtitle=_end_msg)
    win.close(); core.quit()


if __name__ == '__main__':
    main()
