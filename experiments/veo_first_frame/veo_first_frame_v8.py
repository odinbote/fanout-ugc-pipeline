import base64, os, time, requests

API = "https://openrouter.ai/api/v1"
KEY = os.environ["OPENROUTER_API_KEY"]
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

with open("frame1.png", "rb") as f:
    FIRST_FRAME_URL = "data:image/png;base64," + base64.b64encode(f.read()).decode()

PROMPT = '''
The provided image is the first frame; continue from it exactly. Same woman, same
clothes, same bed and blinds, same flat daylight, matte skin, no shine. Front-facing
phone camera held at arm's length, slight handheld sway, framing stays the same, no
zoom, one continuous take, no cuts.

She talks to the camera like she's on FaceTime with a friend — eyes on the lens the
whole time, relaxed face, small natural mouth movements, no big expressions. Her
right hand slides off her jaw into her lap in the first second and her hands stay
relaxed in her lap.

She says, at a normal quick conversational pace with no long pauses: "This feels like
cheating, but it works." She says it once, starting right away, and nothing else.
After the line she just looks at the camera with a faint smile.

Audio: her natural voice, casual American, mid-20s, soft, low energy, phone mic in a
quiet room. No music, no sound effects, no subtitles, no captions, no on-screen text.

Total clip length: 4 seconds.
'''.strip()

NEGATIVE = ("eye roll, looking up, looking away, big smile, teeth, exaggerated "
            "expression, raised finger, slow speech, long pause, stutter, jump cut, zoom, "
            "pull back, reframe, subtitles, captions, music")

def make_body(use_passthrough):
    body = {
        "model": "google/veo-3.1",
        "prompt": PROMPT if use_passthrough else PROMPT + "\n\nNegative: " + NEGATIVE + ".",
        "duration": 4,
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
open("out8.mp4", "wb").write(d.content)
print("saved out8.mp4")
