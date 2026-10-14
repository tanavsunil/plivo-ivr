"""Plivo voice IVR: OTP check -> language selection -> menu (message / associate)."""
import logging
import os
import re

from dotenv import load_dotenv
from flask import Flask, Response, render_template_string, request
from plivo import plivoxml

from trigger_call import place_call

# Set this to the 4-digit OTP callers must enter (e.g. "1410" for 14 October).
OTP = "1304"

load_dotenv()

PLIVO_NUMBER = os.getenv("PLIVO_NUMBER", "")
ASSOCIATE_NUMBER = os.getenv("ASSOCIATE_NUMBER", "")
TARGET_NUMBER = os.getenv("TARGET_NUMBER", "")
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")

# Public sample MP3 used when static/message.mp3 is not present.
SAMPLE_AUDIO_URL = "https://s3.amazonaws.com/plivocloud/music.mp3"
STATIC_AUDIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "message.mp3")

PROMPTS = {
    "en": {
        "language": "en-US",
        "menu": "Press 1 to hear a message. Press 2 to talk to an associate.",
        "invalid": "Invalid option.",
        "connecting": "Connecting you to an associate. Please wait.",
    },
    "es": {
        "language": "es-ES",
        "menu": "Presione 1 para escuchar un mensaje. Presione 2 para hablar con un asociado.",
        "invalid": "Opción no válida.",
        "connecting": "Le estamos conectando con un asociado. Por favor espere.",
    },
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ivr")

app = Flask(__name__)


def url(path):
    return f"{BASE_URL}{path}"


def xml_response(response):
    body = response.to_string()
    log.info("Responding XML: %s", body)
    return Response(body, mimetype="application/xml")


def digits():
    return request.values.get("Digits", "").strip()


def audio_url():
    return url("/static/message.mp3") if os.path.isfile(STATIC_AUDIO) else SAMPLE_AUDIO_URL


def lang_param():
    lang = request.args.get("lang", "en")
    return lang if lang in PROMPTS else "en"


@app.before_request
def log_request():
    if request.path.startswith("/static"):
        return
    log.info(
        "%s %s | CallUUID=%s From=%s To=%s Digits=%s",
        request.method,
        request.full_path.rstrip("?"),
        request.values.get("CallUUID", "-"),
        request.values.get("From", "-"),
        request.values.get("To", "-"),
        request.values.get("Digits", "-"),
    )


# ---------------------------------------------------------------- web trigger

PAGE = """<!doctype html>
<title>Plivo IVR</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 28rem; margin: 3rem auto; padding: 0 1rem; }
  input, button { font-size: 1rem; padding: .5rem; }
  input { width: 100%; box-sizing: border-box; margin: .5rem 0 1rem; }
  .ok { color: #106b21; } .err { color: #b00020; }
</style>
<h1>Plivo IVR demo</h1>
<form method="post" action="/call">
  <label for="to">Phone number (E.164, e.g. 14155550123)</label>
  <input id="to" name="to" value="{{ to }}" required>
  <button type="submit">Call me</button>
</form>
{% if message %}<p class="{{ cls }}">{{ message }}</p>{% endif %}
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(PAGE, to=TARGET_NUMBER, message=None, cls="")


@app.route("/call", methods=["POST"])
def call():
    to = re.sub(r"[\s\-()]", "", request.form.get("to", ""))
    if not re.fullmatch(r"\+?\d{8,15}", to):
        return render_template_string(PAGE, to=to, message="Enter a valid phone number.", cls="err"), 400
    try:
        result = place_call(to.lstrip("+"))
    except Exception as exc:  # surface Plivo/config errors on the page
        log.exception("Call failed")
        return render_template_string(PAGE, to=to, message=f"Call failed: {exc}", cls="err"), 502
    log.info("Call queued to %s: %s", to, result)
    return render_template_string(PAGE, to=to, message=f"Calling {to}...", cls="ok")


# ---------------------------------------------------------------- IVR flow


@app.route("/answer", methods=["GET", "POST"])
def answer():
    response = plivoxml.ResponseElement()
    get_input = plivoxml.GetInputElement(
        action=url("/verify-otp"),
        method="POST",
        input_type="dtmf",
        num_digits=4,
        digit_end_timeout=5,
        redirect=True,
    )
    get_input.add(plivoxml.SpeakElement("Welcome. Please enter your 4 digit O T P."))
    response.add(get_input)
    response.add(plivoxml.SpeakElement("We did not receive any input."))
    response.add(plivoxml.RedirectElement(url("/answer"), method="POST"))
    return xml_response(response)


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    response = plivoxml.ResponseElement()
    if digits() == OTP:
        log.info("OTP verified")
        response.add(plivoxml.SpeakElement("Thank you. Your O T P is verified."))
        response.add(plivoxml.RedirectElement(url("/language"), method="POST"))
    else:
        log.info("OTP incorrect")
        response.add(plivoxml.SpeakElement("Incorrect OTP."))
        response.add(plivoxml.RedirectElement(url("/answer"), method="POST"))
    return xml_response(response)


@app.route("/language", methods=["GET", "POST"])
def language():
    response = plivoxml.ResponseElement()
    get_input = plivoxml.GetInputElement(
        action=url("/language/select"),
        method="POST",
        input_type="dtmf",
        num_digits=1,
        digit_end_timeout=5,
        redirect=True,
    )
    get_input.add(plivoxml.SpeakElement("Press 1 for English. Press 2 for Spanish."))
    get_input.add(plivoxml.SpeakElement("Para español, presione 2.", language="es-ES"))
    response.add(get_input)
    response.add(plivoxml.SpeakElement("Invalid option."))
    response.add(plivoxml.RedirectElement(url("/language"), method="POST"))
    return xml_response(response)


@app.route("/language/select", methods=["GET", "POST"])
def language_select():
    response = plivoxml.ResponseElement()
    choice = {"1": "en", "2": "es"}.get(digits())
    if choice:
        response.add(plivoxml.RedirectElement(url(f"/menu?lang={choice}"), method="POST"))
    else:
        response.add(plivoxml.SpeakElement("Invalid option."))
        response.add(plivoxml.RedirectElement(url("/language"), method="POST"))
    return xml_response(response)


@app.route("/menu", methods=["GET", "POST"])
def menu():
    lang = lang_param()
    p = PROMPTS[lang]
    response = plivoxml.ResponseElement()
    get_input = plivoxml.GetInputElement(
        action=url(f"/menu/select?lang={lang}"),
        method="POST",
        input_type="dtmf",
        num_digits=1,
        digit_end_timeout=5,
        redirect=True,
    )
    get_input.add(plivoxml.SpeakElement(p["menu"], language=p["language"]))
    response.add(get_input)
    response.add(plivoxml.SpeakElement(p["invalid"], language=p["language"]))
    response.add(plivoxml.RedirectElement(url(f"/menu?lang={lang}"), method="POST"))
    return xml_response(response)


@app.route("/menu/select", methods=["GET", "POST"])
def menu_select():
    lang = lang_param()
    p = PROMPTS[lang]
    choice = digits()
    response = plivoxml.ResponseElement()
    if choice == "1":
        response.add(plivoxml.PlayElement(audio_url()))
        response.add(plivoxml.RedirectElement(url(f"/menu?lang={lang}"), method="POST"))
    elif choice == "2":
        response.add(plivoxml.SpeakElement(p["connecting"], language=p["language"]))
        dial = plivoxml.DialElement(caller_id=PLIVO_NUMBER)
        dial.add(plivoxml.NumberElement(ASSOCIATE_NUMBER))
        response.add(dial)
    else:
        response.add(plivoxml.SpeakElement(p["invalid"], language=p["language"]))
        response.add(plivoxml.RedirectElement(url(f"/menu?lang={lang}"), method="POST"))
    return xml_response(response)


if __name__ == "__main__":
    missing = [n for n in ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "PLIVO_NUMBER",
                           "ASSOCIATE_NUMBER", "BASE_URL") if not os.getenv(n)]
    if missing:
        log.warning("Missing environment variables: %s", ", ".join(missing))
    log.info("BASE_URL=%s", BASE_URL)
    app.run(host="0.0.0.0", port=5000, debug=False)
