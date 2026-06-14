#!/usr/bin/env python3
"""
Remove unwanted interlude items from all session JSON files.
Add keywords to SKIP_KEYWORDS to remove more item types.

Run from the experiment folder:
    python clean_json.py
"""
import json, glob, os

# Add any keywords here to remove matching interludes
SKIP_KEYWORDS = ('attn', 'catch', 'hint')

def should_skip(item):
    if item.get('type') != 'interlude':
        return False
    item_id = item.get('id', '')
    cont_id = item.get('content', {}).get('id', '')
    path    = item.get('content', {}).get('path', '')
    return (any(k in item_id for k in SKIP_KEYWORDS) or
            any(k in cont_id for k in SKIP_KEYWORDS) or
            'attn_catch' in path)

files = sorted(glob.glob('session_*.json'))
if not files:
    print("No session_*.json files found. Run from the experiment folder.")
else:
    for path in files:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        removed = 0
        for ss in data.get('subSessions', []):
            for g in ss.get('questionsGroups', []):
                before = g.get('questions', [])
                after  = [q for q in before if not should_skip(q)]
                removed += len(before) - len(after)
                g['questions'] = after
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f'  {path}: removed {removed} item(s)')
    print(f'\nDone. {len(files)} files cleaned.')
