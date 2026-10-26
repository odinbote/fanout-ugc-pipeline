import base64, os, time, requests

API = "https://openrouter.ai/api/v1"
KEY = os.environ["OPENROUTER_API_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

with open("frame1.png", "rb") as f:
    FIRST_FRAME_URL = "data:image/png;base64," + base64.b64encode(f.read()).decode()

PROMPT = '''
The provided image is the first frame; continue from it exactly. Same woman, hair
tied back with the ponytail over her left shoulder, small gold hoops, sage-grey
cap-sleeve tee, grey sweatpants, sitting cross-legged on the bed, white blinds behind
her, lamp off, same flat overcast daylight on her face, no shine. Front-facing phone
camera held at arm's length, slight handheld sway, framing drifts a little, no zoom,
no push-in. One unbroken continuous take from first frame to last — the camera never
cuts, the framing never jumps, every movement is animated through.

Keep her exact face, skin texture, freckles, under-eye shadow and matte finish
throughout — the skin never gets smoother, brighter or warmer. Head stays nearly
square to the camera, slight tilts only, no three-quarter turns.

Subtle, relaxed delivery — small mouth movements, jaw relaxed, eyebrows mostly still.
Not performing. Like talking to a friend on FaceTime. Natural blinks. Her eyes stay
on the lens except for one brief glance.

In the first second her right hand slides off her jaw and comes to rest in her lap,
where it stays; left hand rests on her knee. A quick half-second glance up and to the
side with a guilty half-smile — not a full eye-roll — then straight back to the lens.
She says only this, once, and nothing else: "This feels like cheating... but it
works." A small shoulder shrug on "cheating", hands staying where they are.
As she finishes "works" she keeps the same pose and keeps moving gently — breathes,
the half-smile holds and softens, a slow blink, a tiny weight shift — the same shot
continuing, nothing changes position.
No other words, no ad-libs, no filler sounds, no repeated phrases.

Audio: her natural speaking voice, casual American, mid-20s, soft, slightly breathy,
low energy, recorded on the phone's mic in a quiet bedroom. She speaks once; the rest
of the clip is faint room tone. No music, no sound effects. No subtitles, no
captions, no on-screen text.

Total clip length: exactly 6 seconds. Speech begins around 1 second and ends by
4.5 seconds; the remaining 1.5 seconds is the same continuous shot with her holding
the pose.
'''.strip()

NEGATIVE = ("jump cut, scene change, hard cut, edit, camera cut, new shot, reframe, "
            "teleport, pose snap, sudden movement, eye roll, exaggerated expression, "
            "subtitles, captions, on-screen text, music")

def make_body(use_passthrough):
    body = {
        "model": "google/veo-3.1",
        "prompt": PROMPT if use_passthrough else PROMPT + "\n\nNegative: " + NEGATIVE + ".",
        "duration": 6,
        "resolution": "1080p",
        "aspect_ratio": "9:16",
        "frame_images": [{
            "type": "image_url",
            "image_url": {"url": FIRST_FRAME_URL},
            "frame_type": "first_frame",
        }],
    }
    if use_passthrough:
        body["negativePrompt"] = NEGATIVE
    return body

r = requests.post(f"{API}/videos", headers=HEADERS, json=make_body(True), timeout=120)
if not r.ok:
    print("SUBMIT (negativePrompt passthrough) ERROR", r.status_code, r.text[:500])
    print("retrying with negative list inside the prompt")
    r = requests.post(f"{API}/videos", headers=HEADERS, json=make_body(False), timeout=120)
    if not r.ok:
        print("SUBMIT ERROR", r.status_code, r.text); raise SystemExit(1)
else:
    print("submitted with negativePrompt passthrough")
job = r.json()
job_id = job["id"]
polling_url = job.get("polling_url", f"{API}/videos/{job_id}")
print("submitted job:", job_id)

status = job.get("status", "pending")
for _ in range(90):
    if status in ("completed", "failed", "cancelled", "expired"):
        break
    time.sleep(10)
    s = requests.get(polling_url, headers=HEADERS, timeout=30)
    s.raise_for_status()
    js = s.json()
    status = js.get("status", status)
    print("status:", status)
    if status == "failed":
        print(js)

if status != "completed":
    raise SystemExit(f"video generation {status}")

d = requests.get(f"{API}/videos/{job_id}/content?index=0", headers=HEADERS, timeout=600)
d.raise_for_status()
open("out7.mp4", "wb").write(d.content)
print("saved out7.mp4")
