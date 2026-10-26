#!/usr/bin/env python3
"""UGC clip pipeline: split script -> Veo 3.1 Fast clips (chained first frames) -> quality gate -> ElevenLabs STS -> mux.
Usage: python3 ugc_pipeline.py --script "..." [--script-file f] --first-frame frame1.png [--voice-id ID] [--room "bed and blinds"] [--outdir ugc_out] [--seed 7] [--dry-run]
Env: OPENROUTER_API_KEY, ELEVENLABS_API_KEY
"""
import argparse, base64, json, os, re, shutil, subprocess, sys, time, requests

OR = "https://openrouter.ai/api/v1"
EL = "https://api.elevenlabs.io/v1"
VIDEO_MODEL = "google/veo-3.1-fast"
VISION_MODEL = "google/gemini-2.5-flash"

TEMPLATE = """The provided image is the first frame; continue from it exactly. Same woman, same
clothes, same {room}, same flat daylight, matte skin, no shine. Front-facing phone
camera held at arm's length, slight handheld sway, framing stays the same, no zoom,
one continuous take, no cuts.

She talks straight into the camera like a friend who just found something great —
eyes on the lens the whole time. Her face reacts to every phrase like a real person:
eyebrows jump on the surprising bit, eyes widen on the key word, mouth opens wide on
the stressed vowels, a quick head tilt or nod with the rhythm, a real smile when the
line lands. Her free hand gestures continuously at chest height while she talks and
hits the stressed words — an open palm pushed toward the camera for emphasis, fingers
spread on a number, a quick point on a "not" or "no", small sweeps while listing —
never frozen, never resting in her lap for more than a second.
{beat}

She says, fast and fluent like a real influencer talking to camera, with a tiny beat
after the key phrase and strong emphasis on the key words: "{line}" She says it once,
starting right away, and nothing else. After the line she holds eye contact with a
small real smile.

Audio: her natural voice, casual American, mid-20s, lively and warm with real energy,
slightly imperfect like a real voice memo, not a presenter read, phone mic in a quiet room. No music, no sound effects, no subtitles, no captions, no on-screen text.

Total clip length: {dur} seconds."""

NEGATIVE = ("eye roll, looking up, looking away, frozen face, blank stare, deadpan, hands still in lap, "
            "robotic, presenter voice, slow speech, slow motion, drawn-out words, long pause, stutter, jump cut, zoom, pull back, reframe, "
            "subtitles, captions, music")

BEATS = [
    "On the key word her free hand pushes an open palm toward the camera, then keeps moving as she talks.",
    "A small nod on the key word while her free hand sweeps in a little circle at chest height.",
    "A slight lean in toward the phone on the key word, free hand spread open at chest height.",
    "A quick point of the finger on the key word, then the hand keeps gesturing loosely.",
    "Fingers spread wide on the number or key word, then the hand drops a little and keeps moving.",
]
BEAT1 = ("In the first second her free hand comes up to chest height and starts gesturing with the "
         "words, an open palm toward the camera on the key word.")
HOOK_MOOD = ("eyes on the lens the whole time, lit up like she just found something great: eyebrows up, "
             "eyes wide on the key word, a real smile breaking through, head tilt into the camera, free hand "
             "already gesturing at chest height — genuinely enthusiastic, human, not a presenter, not performing.")
HOOK_PACE = "fast and fluent like a real influencer talking to camera, with a tiny beat after the key phrase and strong emphasis on the key words"
HOOK_AUDIO = "casual American, mid-20s, natural and warm, lightly upbeat, slightly imperfect like a real voice memo, not a presenter read,"
HOOK_NEGATIVE = ("eye roll, looking up, looking away, frozen face, blank stare, deadpan, hands still in lap, robotic, presenter voice, salesy, slow speech, slow motion, drawn-out words, long pause, stutter, jump cut, zoom, "
                 "pull back, reframe, subtitles, captions, music")

def log(*a): print(*a, flush=True)

def sh(cmd, check=True, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{r.stderr[-800:]}")
    return r

# ---------- Step 1: split ----------
def split_script(text, max_words=12, dur_override=None):
    text = re.sub(r"\s+", " ", text.replace("…", "...")).strip()
    text = re.sub(r"\s*\.\.\.\s*", ", ", text)
    text = re.sub(r",\s*,", ",", text)
    text = re.sub(r"\b([A-Za-z]+)\.sh\b", r"\1 dot ess aitch", text)  # speak URLs: Fanout.sh -> Fanout dot ess aitch
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    clips = []
    for s in sents:
        parts = [s]
        while any(len(p.split()) > max_words for p in parts):
            new = []
            for p in parts:
                if len(p.split()) <= max_words:
                    new.append(p); continue
                words = p.split(); n = len(words)
                # candidate split points by priority: comma/dash, then "or"/"but", then "to"/"so", then "and", then midpoint
                tiers = [[], [], [], [], [n // 2]]
                for i in range(1, n):
                    if re.search(r"[,—–-]$", words[i - 1]): tiers[0].append(i)
                    w = words[i].lower()
                    if w in ("or", "but"): tiers[1].append(i)
                    elif w in ("to", "so"): tiers[2].append(i)
                    elif w == "and": tiers[3].append(i)
                cut = None
                for tier in tiers:
                    ok = [i for i in tier if 2 <= i <= n - 2]
                    if not ok: continue
                    fit = [i for i in ok if i <= max_words and n - i <= max_words]
                    pool = fit or ok
                    cut = min(pool, key=lambda i: abs(i - n / 2)); break
                new += [" ".join(words[:cut]).rstrip(","), " ".join(words[cut:])]
            parts = new
        clips += parts
    out = []
    for i, line in enumerate(clips, 1):
        if not re.search(r"[.!?]$", line): line = line.rstrip(",") + "."
        line = line[0].upper() + line[1:]
        wc = len(line.split())
        d = 4 if wc <= 9 else (6 if wc <= 14 else 8)
        if dur_override and i in dur_override: d = dur_override[i]
        out.append({"n": i, "line": line, "words": wc, "dur": d})  # tight: <=9w 4s, 10-14w 6s, 15+w 8s (user: 6/8s clips felt slow)
    return out

def beat_for(n):
    return BEAT1 if n == 1 else BEATS[(n - 2) % len(BEATS)]

def build_prompt(clip, room):
    pr = TEMPLATE.format(room=room, beat=beat_for(clip["n"]), line=clip["line"], dur=clip["dur"])
    if clip["n"] == 1:  # the hook is always excited and expressive
        pr = pr.replace("eyes on the lens the whole time. Her face reacts to every phrase like a real person:\neyebrows jump on the surprising bit, eyes widen on the key word, mouth opens wide on\nthe stressed vowels, a quick head tilt or nod with the rhythm, a real smile when the\nline lands.", HOOK_MOOD)
        pr = pr.replace("fast and fluent like a real influencer talking to camera, with a tiny beat\nafter the key phrase and strong emphasis on the key words", HOOK_PACE)
        pr = pr.replace("casual American, mid-20s, lively and warm with real energy,\nslightly imperfect like a real voice memo, not a presenter read,", HOOK_AUDIO)
    return pr

def negative_for(n):
    return HOOK_NEGATIVE if n == 1 else NEGATIVE

# ---------- vision / audio helpers ----------
def or_headers():
    return {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type": "application/json"}

def data_url(path):
    ext = path.rsplit(".", 1)[-1].lower(); mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    return f"data:{mime};base64," + base64.b64encode(open(path, "rb").read()).decode()

def ask_vision(text, image_paths, audio_path=None):
    content = [{"type": "text", "text": text}]
    for p in image_paths:
        content.append({"type": "image_url", "image_url": {"url": data_url(p)}})
    if audio_path:
        content.append({"type": "input_audio", "input_audio": {"data": base64.b64encode(open(audio_path, "rb").read()).decode(), "format": "mp3"}})
    r = requests.post(f"{OR}/chat/completions", headers=or_headers(),
                      json={"model": VISION_MODEL, "messages": [{"role": "user", "content": content}], "temperature": 0}, timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def duration_of(path):
    return float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).stdout.strip())

def silence_spans(path, noise="-30dB", mindur=0.4):
    r = sh(["ffmpeg", "-i", path, "-af", f"silencedetect=n={noise}:d={mindur}", "-vn", "-f", "null", "-"], check=False)
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", r.stderr)]
    spans = list(zip(starts, ends)) if len(ends) == len(starts) else list(zip(starts, ends + [duration_of(path)]))
    return spans

def scene_spikes(path, thr=0.08):
    r = sh(["ffmpeg", "-i", path, "-vf", f"select='gt(scene,{thr})',showinfo", "-vsync", "vfr", "-f", "null", "-"], check=False)
    ts = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    return [t for t in ts if t > 0.05]

# ---------- Step 4: generate ----------
def submit_video(prompt, first_frame, dur, seed, negative=None):
    negative = negative or NEGATIVE
    body = {"model": VIDEO_MODEL, "prompt": prompt, "duration": dur, "resolution": "1080p", "aspect_ratio": "9:16",
            "generate_audio": True, "negativePrompt": negative,
            "frame_images": [{"type": "image_url", "image_url": {"url": data_url(first_frame)}, "frame_type": "first_frame"}]}
    if seed is not None: body["seed"] = seed
    r = requests.post(f"{OR}/videos", headers=or_headers(), json=body, timeout=180)
    if r.status_code == 400 and ("negativePrompt" in r.text or "generate_audio" in r.text or "seed" in r.text):
        log("  passthrough field rejected, retrying with negatives in prompt body:", r.text[:160])
        body.pop("negativePrompt", None); body.pop("seed", None); body.pop("generate_audio", None)
        body["prompt"] = prompt + "\n\nNegative: " + negative + "."
        r = requests.post(f"{OR}/videos", headers=or_headers(), json=body, timeout=180)
    if not r.ok: raise RuntimeError(f"submit failed {r.status_code}: {r.text[:400]}")
    job = r.json(); jid = job["id"]; poll = job.get("polling_url", f"{OR}/videos/{jid}")
    status = job.get("status", "pending")
    for _ in range(120):
        if status in ("completed", "failed", "cancelled", "expired"): break
        time.sleep(8)
        try:
            s = requests.get(poll, headers=or_headers(), timeout=30); s.raise_for_status()
            status = s.json().get("status", status)
        except (requests.exceptions.RequestException, ValueError) as e:
            log(f"  poll hiccup ({type(e).__name__}), retrying"); continue
    if status != "completed": raise RuntimeError(f"job {jid} {status}")
    for attempt in range(3):
        try:
            d = requests.get(f"{OR}/videos/{jid}/content?index=0", headers=or_headers(), timeout=600); d.raise_for_status()
            return d.content
        except requests.exceptions.RequestException as e:
            log(f"  download hiccup ({type(e).__name__}), retrying"); time.sleep(5)
    raise RuntimeError(f"download failed for job {jid}")

# ---------- Step 5: gate ----------
def gate(clip_path, first_frame, workdir, n):
    report = {"speech": None, "scene": None, "vision": None, "face": None, "ok": False, "why": []}
    dur = duration_of(clip_path)
    # 1. speech continuity
    mp3 = os.path.join(workdir, f"clip_{n:02d}_gate.mp3")
    sh(["ffmpeg", "-v", "error", "-y", "-i", clip_path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", mp3])
    spans = silence_spans(clip_path)
    edge = silence_spans(clip_path, mindur=0.2)
    leading = [s for s in edge if s[0] <= 0.05]
    trailing = [s for s in edge if s[1] >= dur - 0.05]
    mid = [s for s in spans if s[0] > 0.05 and s[1] < dur - 0.05]
    speech_end = min([s[0] for s in trailing], default=dur)
    ends_early = speech_end <= dur - 1.0
    report["speech"] = {"mid_gaps": [(round(a, 2), round(b, 2)) for a, b in mid], "speech_end": round(speech_end, 2), "dur": dur}
    if len(mid) > 2: report["why"].append(f"{len(mid)} mid-line gaps >0.4s")
    if not ends_early: report["why"].append(f"speech ends at {speech_end:.2f}s, inside last 1s of {dur:.1f}s")
    # 2. scene spikes
    spikes = scene_spikes(clip_path)
    report["scene"] = spikes
    if spikes: report["why"].append(f"scene spike at {spikes}")
    # 3. frames at 4 fps -> contact sheet -> vision check
    sheet = os.path.join(workdir, f"clip_{n:02d}_sheet.png")
    nfr = int(dur * 4)
    cols = min(nfr, 8); rows = (nfr + cols - 1) // cols
    sh(["ffmpeg", "-v", "error", "-y", "-i", clip_path, "-vf", f"fps=4,scale=270:-1,tile={cols}x{rows}", "-frames:v", "1", sheet])
    q = ("This is a contact sheet of every frame (4 fps, left-to-right, top-to-bottom) from a short talking-to-camera clip, "
         "plus the clip's audio. Answer in strict JSON with keys: eyes_away (true if ANY frame has her eyes clearly looking up, "
         "down or to the side instead of at the lens), teeth_wide_smile (true if any frame shows teeth in a wide smile), "
         "raised_finger (true if any frame shows a raised/pointing finger), transcript (verbatim speech), extra_words "
         "(true if she says anything beyond one clean sentence, e.g. um, repeats), notes (short).")
    try:
        v = ask_vision(q, [sheet], mp3)
        vj = json.loads(re.search(r"\{.*\}", v, re.S).group(0))
    except Exception as e:
        vj = {"error": str(e)[:200]}
    report["vision"] = vj
    for k in ("eyes_away", "teeth_wide_smile", "raised_finger"):
        if vj.get(k) is True: report["why"].append(k)
    # 4. last-frame face vs first frame
    last = os.path.join(workdir, f"clip_{n:02d}_last.png")
    sh(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.1", "-i", clip_path, "-frames:v", "1", last])
    try:
        f = ask_vision("Image 1 is the first frame of a clip, image 2 is its last frame. Is it clearly the same person with the same "
                       "hair, clothes and room, with no identity drift? Answer strict JSON: {\"same_person\": true/false, \"notes\": \"...\"}",
                       [first_frame, last])
        fj = json.loads(re.search(r"\{.*\}", f, re.S).group(0))
    except Exception as e:
        fj = {"error": str(e)[:200]}
    report["face"] = fj
    if fj.get("same_person") is False: report["why"].append("face drift")
    report["ok"] = not report["why"]
    return report

# ---------- chain frame ----------
def pick_chain_frame(clip_path, workdir, n):
    """Candidate frames from the end of the clip (never the literal last frame); vision picks eyes-on-lens, mouth closed, hands in lap."""
    dur = duration_of(clip_path)
    offsets = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    cands = []
    for i, off in enumerate(offsets):
        p = os.path.join(workdir, f"clip_{n:02d}_cand{i}.png")
        sh(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(dur - off, 0):.3f}", "-i", clip_path, "-frames:v", "1", p])
        cands.append(p)
    sheet = os.path.join(workdir, f"clip_{n:02d}_cands.png")
    sh(["ffmpeg", "-v", "error", "-y", "-i", clip_path, "-vf",
        f"select='" + "+".join(f"between(t\\,{max(dur-o,0)-0.02:.3f}\\,{max(dur-o,0)+0.02:.3f})" for o in offsets) + "',scale=270:-1,tile=8x1",
        "-vsync", "vfr", "-frames:v", "1", sheet], check=False)
    q = ("These 8 frames are candidates numbered 1-8 left to right. Pick the single best one where: eyes are open and on the lens, "
         "mouth closed or nearly closed, hands relaxed in her lap, no motion blur. Answer strict JSON: {\"pick\": N, \"notes\": \"...\"}")
    pick = 1
    try:
        v = ask_vision(q, [sheet]); pick = int(json.loads(re.search(r"\{.*\}", v, re.S).group(0))["pick"])
        pick = max(1, min(8, pick))
    except Exception as e:
        log("  chain-frame vision pick failed, using -0.3s:", str(e)[:120])
    out = os.path.join(os.path.dirname(clip_path), f"frame_{n+1:02d}.png")
    shutil.copy(cands[pick - 1], out)
    return out, offsets[pick - 1]

# ---------- speed-up (pace) ----------
def speed_up(clip_path, factor):
    """Speed a clip up by factor (video setpts + pitch-preserving atempo), in place. 1.0 = no change."""
    if not factor or abs(factor - 1.0) < 1e-3: return clip_path
    tmp = clip_path.replace(".mp4", f"_x{factor:.2f}.mp4")
    sh(["ffmpeg", "-v", "error", "-y", "-i", clip_path, "-filter_complex",
        f"[0:v]setpts=PTS/{factor}[v];[0:a]atempo={factor}[a]", "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "24", "-c:a", "aac", "-b:a", "192k", tmp])
    os.replace(tmp, clip_path)
    return clip_path

# ---------- Step 6: STS ----------
def sts(clip_path, voice_id, outdir, n):
    src = os.path.join(outdir, f"clip_{n:02d}_src.wav"); outwav = os.path.join(outdir, f"clip_{n:02d}_voice.wav")
    sh(["ffmpeg", "-v", "error", "-y", "-i", clip_path, "-vn", "-ac", "1", "-ar", "44100", src])
    H = {"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}
    vs = json.dumps({"stability": 0.40, "similarity_boost": 0.80, "style": 0.15, "use_speaker_boost": False})
    match = False
    for attempt in range(3):
        with open(src, "rb") as f:
            r = requests.post(f"{EL}/speech-to-speech/{voice_id}", params={"output_format": "mp3_44100_192"}, headers=H,
                              files={"audio": (os.path.basename(src), f, "audio/wav")},
                              data={"model_id": "eleven_multilingual_sts_v2", "voice_settings": vs, "remove_background_noise": "false"}, timeout=300)
        if not r.ok: raise RuntimeError(f"STS failed {r.status_code}: {r.text[:300]}")
        raw = os.path.join(outdir, f"clip_{n:02d}_voice.mp3"); open(raw, "wb").write(r.content)
        sh(["ffmpeg", "-v", "error", "-y", "-i", raw, "-ar", "44100", "-ac", "1", outwav])
        d_in, d_out = duration_of(src), duration_of(outwav)
        match = abs(d_in - d_out) <= 0.05
        log(f"  STS attempt {attempt+1}: in {d_in:.3f}s out {d_out:.3f}s -> {'match' if match else 'MISMATCH'}")
        if match: break
    final = os.path.join(outdir, f"clip_{n:02d}_final.mp4")
    sh(["ffmpeg", "-v", "error", "-y", "-i", clip_path, "-i", outwav, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", final])
    return final, match

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script"); ap.add_argument("--script-file")
    ap.add_argument("--first-frame", required=True); ap.add_argument("--voice-id")
    ap.add_argument("--room", default="bed and blinds"); ap.add_argument("--outdir", default="ugc_out")
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--beat1", help="override the fixed clip-1 beat sentence")
    ap.add_argument("--beat-all", help="override the beat sentence for every clip after clip 1")
    ap.add_argument("--max-words", type=int, default=12, help="max words per clip before splitting (spec default 12)")
    ap.add_argument("--dur", help="per-clip duration overrides, e.g. \"1=6,4=8\"")
    ap.add_argument("--speed", type=float, default=1.0, help="speed-up factor applied to every generated clip before the voice swap (1.0 = off, the default; user rejected 1.15x)")
    ap.add_argument("--no-gate", action="store_true", help="generate every clip once, skip Step 5 and re-rolls")
    ap.add_argument("--no-sts", action="store_true", help="skip Step 6 voice swap")
    ap.add_argument("--same-first-frame", action="store_true", help="every clip starts from FIRST_FRAME (no chaining)")
    ap.add_argument("--only-clip", type=int, help="trial mode: generate and voice-swap just this clip number, then stop")
    ap.add_argument("--start-at", type=int, default=1, help="resume from clip N (expects earlier clips + frame_N.png in outdir)")
    a = ap.parse_args()
    text = a.script or (open(a.script_file).read() if a.script_file else None)
    if not text: sys.exit("SCRIPT missing: pass --script or --script-file")
    voice = a.voice_id or (open("voice_id.txt").read().strip() if os.path.exists("voice_id.txt") else None)
    if not voice: sys.exit("VOICE_ID missing and voice_id.txt not found")
    if not os.path.exists("voice_id.txt"): open("voice_id.txt", "w").write(voice + "\n")
    os.makedirs(a.outdir, exist_ok=True); work = os.path.join(a.outdir, "work"); os.makedirs(work, exist_ok=True)

    global BEAT1, BEATS
    if a.beat1: BEAT1 = a.beat1
    if a.beat_all: BEATS = [a.beat_all]
    dur_override = {int(k): int(v) for k, v in (x.split("=") for x in a.dur.split(","))} if a.dur else None
    clips = split_script(text, a.max_words, dur_override)
    log("\nSTEP 1 — SPLIT"); log(f"{'#':>2}  {'words':>5}  {'dur':>3}  line")
    for c in clips: log(f"{c['n']:>2}  {c['words']:>5}  {c['dur']:>3}s  {c['line']}")
    prompts = {c["n"]: build_prompt(c, a.room) for c in clips}
    for c in clips: open(os.path.join(a.outdir, f"clip_{c['n']:02d}_prompt.txt"), "w").write(prompts[c["n"]] + "\n\nNegative: " + negative_for(c["n"]) + ".\n")
    if a.dry_run:
        log("\nDRY RUN — prompts written to", a.outdir); log("\n--- clip 1 prompt ---\n" + prompts[1]); return

    results = []
    first = a.first_frame if (a.start_at == 1 or a.same_first_frame) else os.path.join(a.outdir, f"frame_{a.start_at:02d}.png")
    shutil.copy(a.first_frame, os.path.join(a.outdir, "frame_01.png"))
    for c in clips:
        n = c["n"]
        if a.only_clip and n != a.only_clip:
            continue
        if n < a.start_at:
            done = os.path.exists(os.path.join(a.outdir, f"clip_{n:02d}_final.mp4"))
            results.append({"clip": n, "line": c["line"], "dur": c["dur"], "gate": "prev", "sts": "prev" if done else None, "file": f"clip_{n:02d}_final.mp4" if done else None}); continue
        clip_path = os.path.join(a.outdir, f"clip_{n:02d}.mp4")
        passed = False; rep = None
        for attempt in range(1 if a.no_gate else 4):  # 1 + 3 re-rolls
            log(f"\nSTEP 4 — clip {n} attempt {attempt+1} ({c['dur']}s) from {os.path.basename(first)}")
            seed = a.seed + attempt * 1000  # re-rolls must not repeat the same seed
            data = submit_video(prompts[n], first, c["dur"], seed, negative_for(n))
            log(f"  seed {seed}")
            open(clip_path, "wb").write(data)
            shutil.copy(clip_path, os.path.join(work, f"clip_{n:02d}_raw.mp4"))  # untouched Veo output
            speed_up(clip_path, a.speed)
            if a.speed and abs(a.speed - 1.0) > 1e-3: log(f"  sped up x{a.speed:.2f} -> {duration_of(clip_path):.2f}s")
            if attempt: shutil.copy(clip_path, os.path.join(work, f"clip_{n:02d}_try{attempt+1}.mp4"))
            if a.no_gate:
                rep = {"ok": True, "why": [], "vision": {}, "speech": None, "scene": None, "face": None}; passed = True
                log("  gate skipped (--no-gate)"); break
            log(f"STEP 5 — gate clip {n}")
            rep = gate(clip_path, first, work, n)
            log("  transcript:", (rep["vision"] or {}).get("transcript")); log("  speech:", rep["speech"]); log("  scene spikes:", rep["scene"])
            log("  face:", rep["face"]); log("  PASS" if rep["ok"] else "  FAIL: " + "; ".join(rep["why"]))
            if rep["ok"]: passed = True; break
        if not passed:
            log(f"clip {n} failed after 3 re-rolls — stopping. Shorten this line and rerun with --start-at {n}.")
            results.append({"clip": n, "line": c["line"], "dur": c["dur"], "gate": "FAIL", "sts": "-", "file": f"clip_{n:02d}.mp4"}); break
        json.dump(rep, open(os.path.join(work, f"clip_{n:02d}_gate.json"), "w"), indent=1)
        if n < len(clips) and not a.same_first_frame:
            first, off = pick_chain_frame(clip_path, work, n); log(f"  chain frame -> {os.path.basename(first)} (from end-{off}s)")
        results.append({"clip": n, "line": c["line"], "dur": c["dur"], "gate": "pass", "sts": None, "file": None})

    if a.no_sts:
        log("\nSTEP 6 — skipped (--no-sts); originals delivered for review")
    elif results and all(r["gate"] in ("pass", "prev") for r in results):
        log("\nSTEP 6 — VOICE SWAP (voice", voice + ")")
        for r in results:
            if r["gate"] not in ("pass", "prev"): continue
            if r["gate"] == "prev" and r["sts"] == "prev": continue  # already voice-swapped in an earlier run
            final, match = sts(os.path.join(a.outdir, f"clip_{r['clip']:02d}.mp4"), voice, a.outdir, r["clip"])
            r["sts"] = "match" if match else "MISMATCH"; r["file"] = os.path.basename(final)
    log("\nSTEP 7 — OUTPUT"); log(f"{'clip':>4}  {'dur':>3}  {'gate':>5}  {'sts':>8}  file                 line")
    for r in results: log(f"{r['clip']:>4}  {r['dur']:>3}s  {r['gate']:>5}  {str(r['sts']):>8}  {str(r['file']):<20} {r['line']}")
    json.dump(results, open(os.path.join(a.outdir, "summary.json"), "w"), indent=1)

if __name__ == "__main__":
    main()
