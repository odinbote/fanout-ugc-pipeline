#!/usr/bin/env python3
"""Assemble UGC clips in Palmier Pro the way the user cuts them.
Usage: python3 palmier_assemble.py --name "cut name" --files clip_01_final.mp4 clip_02_final.mp4 ... [--folder NAME] [--dry-run]
Rules (see memory ugc-cut-style): 720x1280 @ 24, clips back-to-back in given order, in-point on first-word onset (zero handle),
out-point ~0.08 s after the audible end of the last word, internal pauses > 0.6 s tightened to ~0.2 s, hard cuts, no fades,
grade stack copied from Timeline 1: contrast .9556 highlights -.3311 shadows 0 vibrance .1058, grain .1891/1.5, sharpen 0.
Palmier Pro must be running with the project open."""
import argparse, json, os, subprocess, array, math, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from palmier_mcp import Palmier

GRADE = {"contrast": 0.9556371979553904, "highlights": -0.3311454460966543, "shadows": 0, "vibrance": 0.1057736988847584}
FX = [{"type": "blur.sharpen", "params": {"amount": 0}}, {"type": "stylize.grain", "params": {"amount": 0.1891409154275093, "size": 1.5}}]
TAIL_AIR = 0.12      # seconds of air after the audible end of the last word
MAX_PAUSE = 0.6      # internal pauses longer than this get tightened
KEEP_PAUSE = 0.2     # ...to this

def J(r):
    s = "".join(c.get("text", "") for c in r.get("content", []))
    try: return json.loads(s)
    except Exception: return s

def envelope(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    a = array.array("h"); a.frombytes(raw); win = 320; rms = []
    for i in range(0, len(a) - win, win):
        seg = a[i:i + win]; v = math.sqrt(sum(x * x for x in seg) / win) + 1e-9; rms.append(20 * math.log10(v / 32768))
    floor = sorted(rms)[int(len(rms) * 0.1)]; thr = max(floor + 10, -45)
    on = [i * 0.02 for i, v in enumerate(rms) if v > thr]
    bursts = []
    for t in on:
        if bursts and t - bursts[-1][1] <= 0.25: bursts[-1][1] = t + 0.02
        else: bursts.append([t, t + 0.02])
    return bursts

def plan_clip(words, bursts, media_dur):
    """words: [[text,start,end],...] source seconds. Returns (in, out, internal_cuts[(a,b)])"""
    first_on = words[0][1]
    last_word_start = words[-1][1]
    cand = [b for b in bursts if b[1] > last_word_start]
    aud_end = cand[0][1] if cand else max(words[-1][2] - 0.1, last_word_start + 0.2)
    out = min(aud_end + TAIL_AIR, media_dur)
    # internal pauses from audible gaps between bursts inside [in, out]
    cuts = []
    inside = [b for b in bursts if b[1] > first_on and b[0] < out]
    for b1, b2 in zip(inside, inside[1:]):
        gap = b2[0] - b1[1]
        if gap > MAX_PAUSE:
            a = b1[1] + 0.08; b = b2[0] - (KEEP_PAUSE - 0.08)
            if b - a > 0.15: cuts.append((round(a, 3), round(b, 3)))
    return first_on, out, cuts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True); ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--folder"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--project", help="create a NEW Palmier project with this name (720p 9:16 24fps) and build the timeline in it")
    ap.add_argument("--deliver-dir", help="after building, close the project and move its .palmier package into this folder")
    a = ap.parse_args()
    p = Palmier()
    if a.project and not a.dry_run:
        lst = J(p.call("manage_project", {"action": "list"}))
        existing = [x for x in lst.get("projects", []) if x.get("name", "").lower() == a.project.lower() and x.get("isAccessible")]
        if existing:
            r = J(p.call("manage_project", {"action": "open", "path": existing[0]["path"]})); print("project opened (existing):", existing[0]["path"])
        else:
            r = J(p.call("manage_project", {"action": "create", "name": a.project, "fps": 24, "aspectRatio": "9:16", "quality": "720p"}))
            if not isinstance(r, dict) or r.get("isError"): sys.exit(f"manage_project create failed: {r}")
            print("project created:", r.get("name") or a.project, r.get("path") or "")
    media = J(p.call("get_media", {}))
    by_name = {m["name"]: m["id"] for m in media.get("assets", [])}
    refs = []
    for f in a.files:
        name = os.path.splitext(os.path.basename(f))[0]
        if name in by_name: refs.append((by_name[name], f)); continue
        if a.dry_run: print(f"[dry] would import {f}"); refs.append((None, f)); continue
        r = J(p.call("import_media", {"source": {"path": os.path.abspath(f)}, **({"folder": a.folder} if a.folder else {})}))
        rid = (r.get("id") or (r.get("assets") or [{}])[0].get("id")) if isinstance(r, dict) else None
        if not rid:
            media = J(p.call("get_media", {})); rid = {m["name"]: m["id"] for m in media.get("assets", [])}.get(name)
        if not rid: sys.exit(f"import failed for {f}: {r}")
        refs.append((rid, f)); print(f"imported {f} -> {rid}")
    plans = []
    for rid, f in refs:
        words = None
        if rid:
            info = J(p.call("inspect_media", {"mediaRef": rid, "wordTimestamps": True, "maxFrames": 0}))
            words = (info.get("transcription") or {}).get("words")
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "csv=p=0", f], capture_output=True, text=True).stdout.strip())
        bursts = envelope(f)
        if not words:
            print(f"  no transcript for {f}; falling back to audible bursts"); words = [["?", bursts[0][0], bursts[0][1]], ["?", bursts[-1][0], bursts[-1][1]]] if bursts else [["?", 0, dur]]
        i, o, cuts = plan_clip(words, bursts, dur)
        plans.append((rid, f, i, o, cuts, " ".join(w[0] for w in words)))
        print(f"{os.path.basename(f)}: in {i:.2f}s out {o:.2f}s cuts {cuts} | {plans[-1][5][:70]}")
    if a.dry_run: print("[dry] no timeline changes made"); return
    r = J(p.call("create_timeline", {"name": a.name})); tid = r.get("timelineId"); print("timeline:", tid)
    start = 0; first = True; clip_ids = []
    for rid, f, i, o, cuts, _ in plans:
        e = {"mediaRef": rid, "startFrame": start, "source": [round(i, 3), round(o, 3)]}
        if not first: e["trackIndex"] = 0
        r = J(p.call("add_clips", {"entries": [e]}))
        if isinstance(r, dict) and r.get("isError"): sys.exit(f"add_clips failed: {r}")
        tl = J(p.call("get_timeline", {"captionDetail": "none"})); vt = [t for t in tl["tracks"] if t["type"] == "video"][0]
        last = sorted(vt["clips"], key=lambda c: c["frames"][0])[-1]; start = last["frames"][1]; first = False
        if cuts:
            r = J(p.call("ripple_delete_ranges", {"clipId": last["id"], "ranges": [list(c) for c in cuts], "units": "seconds"}))
            tl = J(p.call("get_timeline", {"captionDetail": "none"})); vt = [t for t in tl["tracks"] if t["type"] == "video"][0]
            start = sorted(vt["clips"], key=lambda c: c["frames"][0])[-1]["frames"][1]
    tl = J(p.call("get_timeline", {"captionDetail": "none"})); vt = [t for t in tl["tracks"] if t["type"] == "video"][0]
    clip_ids = [c["id"] for c in vt["clips"]]
    p.call("apply_color", {"clipIds": clip_ids, **GRADE}); p.call("apply_effect", {"clipIds": clip_ids, "effects": FX})
    p.call("set_project_settings", {"width": 720, "height": 1280})
    tl = J(p.call("get_timeline", {"captionDetail": "none"}))
    print(f"\nDONE: {tl['name']} {tl['width']}x{tl['height']} @ {tl['fps']} fps, {tl['durationSeconds']:.2f}s, {len(clip_ids)} clips, grade+grain applied, hard cuts, no fades")
    if a.deliver_dir and a.project:
        import shutil, time
        lst = J(p.call("manage_project", {"action": "list"}))
        proj = next((x for x in lst.get("projects", []) if x.get("name", "").lower() == a.project.lower()), None)
        src = (proj or {}).get("path") or os.path.expanduser(f"~/Documents/Palmier Pro/{a.project}.palmier")
        r = J(p.call("manage_project", {"action": "close", "path": src})); print("project closed (saved):", str(r)[:120])
        for _ in range(20):
            if os.path.exists(src): break
            time.sleep(0.5)
        os.makedirs(a.deliver_dir, exist_ok=True)
        dst = os.path.join(a.deliver_dir, os.path.basename(src))
        if os.path.exists(dst): shutil.rmtree(dst)
        shutil.move(src, dst); print("project file moved to:", dst)
        r = J(p.call("manage_project", {"action": "open", "path": dst})); print("reopened from new location:", str(r)[:120])

if __name__ == "__main__":
    main()
