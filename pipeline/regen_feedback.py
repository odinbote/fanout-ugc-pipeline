import os, sys, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ugc_pipeline as P

OUT = "ugc_out"; FIRST = "first_frame.png"; ROOM = "bed and blinds"; SEED = 7
voice = open("voice_id.txt").read().strip()

def prompt(line, beat, dur, mood_line, pace, audio_extra):
    return P.TEMPLATE.format(room=ROOM, beat=beat, line=line, dur=dur) \
        .replace("eyes on the lens the\nwhole time, relaxed face, small natural mouth movements, no big expressions.", mood_line) \
        .replace("at a normal quick conversational pace with no long pauses", pace) \
        .replace("casual American, mid-20s, soft, low energy,", audio_extra)

JOBS = {
 3: dict(line="System design breakdowns, AI research, and structured learning paths—all in one place.", dur=8,
         beat=P.BEATS[1], mood_line=None,
         pace="at a calm, slow, clear conversational pace, taking her time, a brief natural pause at each comma",
         audio_extra=None, negative=P.NEGATIVE),
 5: dict(line="Check out Fanout dot ess aitch.", dur=4,
         beat=P.BEATS[3], mood_line=None, pace=None, audio_extra=None, negative=P.NEGATIVE),
}

for n, j in JOBS.items():
    pr = P.TEMPLATE.format(room=ROOM, beat=j["beat"], line=j["line"], dur=j["dur"])
    if j["mood_line"]: pr = pr.replace("eyes on the lens the\nwhole time, relaxed face, small natural mouth movements, no big expressions.", j["mood_line"])
    if j["pace"]: pr = pr.replace("at a normal quick conversational pace with no long pauses", j["pace"])
    if j["audio_extra"]: pr = pr.replace("casual American, mid-20s, soft, low energy,", j["audio_extra"])
    if n == 5: pr = pr.replace('"Check out Fanout dot ess aitch."', '"Check out Fanout dot ess aitch." (the website is fanout.sh; she says the two letters S and H by name, "ess" then "aitch", not as a word)')
    P.NEGATIVE = j["negative"]
    open(f"{OUT}/clip_{n:02d}_prompt.txt", "w").write(pr + "\n\nNegative: " + j["negative"] + ".\n")
    print(f"\nSTEP 4 — clip {n} ({j['dur']}s) from {FIRST}", flush=True)
    data = P.submit_video(pr, FIRST, j["dur"], SEED)
    open(f"{OUT}/clip_{n:02d}.mp4", "wb").write(data); print(f"  saved clip_{n:02d}.mp4", flush=True)

print("\nSTEP 6 — VOICE SWAP", flush=True)
for n in JOBS:
    final, match = P.sts(f"{OUT}/clip_{n:02d}.mp4", voice, OUT, n)
    print(f"  clip {n}: {'match' if match else 'MISMATCH'} -> {os.path.basename(final)}", flush=True)
    shutil.copy(final, f"final/clip_{n:02d}_final.mp4"); shutil.copy(f"{OUT}/clip_{n:02d}_prompt.txt", f"final/clip_{n:02d}_prompt.txt")
print("final folder updated", flush=True)
