"""
Scans every .mp4 under the assets/ folder and reports any that fail to open
or yield a readable frame via OpenCV — the same check the main experiment
now runs before handing a file to the video player. A file that fails here
is one that would otherwise risk crashing the experiment mid-session.

Usage:
    python validate_videos.py
    python validate_videos.py path\to\assets

If a file is flagged, re-encode it to a broadly-compatible format, e.g.:
    ffmpeg -i bad_file.mp4 -c:v libx264 -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 128k fixed.mp4
Then replace the original file with the re-encoded one (keep the same filename).
"""
import os
import sys

try:
    import cv2
except ImportError:
    print("ERROR: opencv-python is not installed in this environment.")
    print("Install it with:  pip install opencv-python")
    sys.exit(1)

BASE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'assets')

if not os.path.isdir(BASE):
    print(f"ERROR: folder not found: {BASE}")
    sys.exit(1)

print(f"Scanning for .mp4 files under: {BASE}\n")

checked = 0
bad = []

for root, _dirs, files in os.walk(BASE):
    for fname in files:
        if not fname.lower().endswith('.mp4'):
            continue
        path = os.path.join(root, fname)
        checked += 1
        ok = False
        try:
            cap = cv2.VideoCapture(path)
            ok = cap.isOpened()
            if ok:
                ok, _ = cap.read()
            cap.release()
        except Exception as e:
            ok = False
            print(f"  [ERROR while checking] {path}: {e}")
        if not ok:
            bad.append(path)
            print(f"  ✗ FAILS pre-check: {path}")

print(f"\nChecked {checked} video(s). {len(bad)} failed.\n")

if bad:
    print("Files that need re-encoding before running with a real participant:")
    for p in bad:
        print(f"  - {p}")
    print(
        "\nSuggested re-encode command (run per file, then replace the original):\n"
        '  ffmpeg -i "INPUT.mp4" -c:v libx264 -pix_fmt yuv420p -movflags +faststart '
        '-c:a aac -b:a 128k "FIXED.mp4"'
    )
else:
    print("All videos passed the pre-check.")
