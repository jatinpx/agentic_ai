import os, urllib.request, json

GEMINI_API_KEY="AIzaSyAUyJc7r5nNrV36Lm9NV4TlUFdVsCZYz0g"

def test(model):
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents":[
            {"role":"user","parts":[{"text":"hello"}]}
        ]
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json"}
    )

    try:
        print(f"\nTesting: {model}")
        r = urllib.request.urlopen(req)
        print("✅ WORKING")
        print(r.read().decode()[:200])
    except Exception as e:
        print("❌ FAILED:", e)

# test("gemini-2.5-pro")
# test("gemini-1.5-flash")
test("gemini-2.5-flash")