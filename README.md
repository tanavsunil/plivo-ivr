# Plivo Voice IVR (Flask)

An outbound IVR built with Flask and the Plivo Python SDK (`plivoxml`):
OTP verification, then a language choice (English/Spanish), then a menu to hear a message or talk to an associate.

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask app: web trigger page and all IVR XML endpoints. The `OTP` constant is at the top. |
| `trigger_call.py` | CLI that places the outbound call (`place_call()` is also used by the web page). |
| `.env.example` | Template for the required environment variables. |
| `requirements.txt` | Python dependencies. |

## Required credentials

From the [Plivo console](https://console.plivo.com/) overview page:

- **Auth ID** → `PLIVO_AUTH_ID`
- **Auth Token** → `PLIVO_AUTH_TOKEN`

You also need a voice-enabled Plivo number (`PLIVO_NUMBER`). On a trial account, the destination numbers
(`TARGET_NUMBER`, `ASSOCIATE_NUMBER`) must be verified in the console (Phone Numbers → Sandbox Numbers).

Credentials are read from `.env` via `python-dotenv` and are never hardcoded. `.env` is git-ignored; don't commit it.

## Setup (Windows PowerShell)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # only if you don't already have a .env; then fill in real values
```

Then set the OTP in `app.py`:

```python
OTP = "DDMM"   # replace with 4 digits, e.g. "1410"
```

## Expose Flask with ngrok

Plivo has to reach your answer and action URLs over the public internet.

```powershell
ngrok http 5000
```

Copy the `https://...ngrok-free.app` forwarding URL into `BASE_URL` in `.env` (no trailing slash).
Every action and redirect URL in the XML is built as an absolute URL from `BASE_URL`.
Free ngrok URLs change each time ngrok restarts, so update `BASE_URL` and restart Flask when that happens.

## Run

Terminal 1, the Flask app (port 5000):

```powershell
.\venv\Scripts\Activate.ps1
python app.py
```

Terminal 2, ngrok:

```powershell
ngrok http 5000
```

## Trigger a call

- **Web:** open `http://localhost:5000/` (or your ngrok URL), enter a number, click **Call me**.
- **CLI:**

  ```powershell
  python trigger_call.py               # calls TARGET_NUMBER
  python trigger_call.py 14155550123   # calls a specific number
  ```

Both call `plivo.RestClient().calls.create(from_=PLIVO_NUMBER, to_=..., answer_url=BASE_URL + "/answer", answer_method="POST")`.

## Call flow

```
calls.create ──► /answer
                  "Please enter your 4 digit OTP"  (GetInput, dtmf, 4 digits)
                  no input ──► redirect /answer
                    │
                    ▼
                /verify-otp
                  wrong ──► "Incorrect OTP" ──► /answer
                  correct ──► /language
                    │
                    ▼
                /language
                  "Press 1 for English, press 2 for Spanish"
                  no input ──► "Invalid option" ──► /language
                    │
                    ▼
                /language/select
                  1 ──► /menu?lang=en
                  2 ──► /menu?lang=es
                  other ──► "Invalid option" ──► /language
                    │
                    ▼
                /menu?lang=en|es   (Spanish uses <Speak language="es-ES">)
                  "Press 1 to hear a message, press 2 to talk to an associate"
                  no input ──► invalid message ──► /menu
                    │
                    ▼
                /menu/select?lang=en|es
                  1 ──► <Play> MP3 ──► back to /menu
                  2 ──► <Dial callerId=PLIVO_NUMBER><Number>ASSOCIATE_NUMBER</Number></Dial>
                  other ──► invalid message ──► /menu
```

**Audio for option 1:** if `static/message.mp3` exists, it's played from `BASE_URL/static/message.mp3`.
Otherwise the app plays Plivo's public sample MP3 (`https://s3.amazonaws.com/plivocloud/music.mp3`).

## Testing

1. Start Flask and ngrok, and confirm `BASE_URL` matches the ngrok URL.
2. Check the XML locally before placing a call:

   ```powershell
   Invoke-WebRequest -Method Post http://localhost:5000/answer | Select-Object -ExpandProperty Content
   Invoke-WebRequest -Method Post http://localhost:5000/verify-otp -Body @{Digits="0000"} | Select-Object -ExpandProperty Content
   Invoke-WebRequest -Method Post "http://localhost:5000/menu/select?lang=es" -Body @{Digits="2"} | Select-Object -ExpandProperty Content
   ```

3. Place a real call and walk through the menus. Try a wrong OTP, no input, invalid keys, both languages, and both menu options.
4. Watch the Flask console. Every request is logged with method, path, CallUUID, From, To and Digits, plus the XML returned.
   The ngrok inspector at `http://127.0.0.1:4040` also shows the raw Plivo requests.

**Troubleshooting:** if the call connects and then drops, Plivo usually couldn't fetch `/answer`.
Check that ngrok is running, `BASE_URL` is current, and look at the call's debug log in the Plivo console.
