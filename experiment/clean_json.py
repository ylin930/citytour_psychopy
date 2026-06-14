#!/usr/bin/env python3
"""
Remove all attn/catch interlude items from all session JSON files.
Run from the experiment folder:
    python clean_json.py
"""
import json, os, glob

SKIP_KEYWORDS = ('attn', 'catch')

def is_attn_catch(item):
    if item.get('type') != 'interlude':
        return False
    item_id  = item.get('id', '')
    cont_id  = item.get('content', {}).get('id', '')
    path     = item.get('content', {}).get('path', '')
    return (
        any(k in item_id  for k in SKIP_KEYWORDS) or
        any(k in cont_id  for k in SKIP_KEYWORDS) or
        'attn_catch' in path
    )

def clean_subsessions(subsessions):
    removed = 0
    for ss in subsessions:
        for g in ss.get('questionsGroups', []):
            before = g.get('questions', [])
            after  = [q for q in before if not is_attn_catch(q)]
            removed += len(before) - len(after)
            g['questions'] = after
    return removed

# Find all session JSON files in current directory
files = sorted(glob.glob('session_*.json'))
if not files:
    print("No session_*.json files found in current directory.")
    print("Run this script from the folder containing the JSON files.")
else:
    for path in files:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        removed = clean_subsessions(data.get('subSessions', []))
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  {path}: removed {removed} attn/catch interlude(s)")
    print(f"\nDone. {len(files)} files cleaned.")
