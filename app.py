"""SafeSwap backend — Flask app serving the one-page UI and JSON APIs.

Run locally:
    pip install -r requirements.txt
    python app.py            # http://localhost:5000

On Render the start command is: gunicorn app:app
"""
import os

from flask import Flask, jsonify, request, render_template

import ai_copilot
import paypal_invoices
from ai_copilot import draft_reply, suggest_price, scan_for_scams
from paypal_invoices import create_and_send_invoice
from mock_data import MEETUP_CHECKLIST, SAMPLE_LISTING, SAMPLE_MESSAGES

app = Flask(__name__)


@app.get("/api/status")
def status():
    """Honest mode flags for the UI badge: live PayPal (sandbox keys set)
    and live AI (AI_MOCK=false + key set). The badge starts as MOCK and
    this endpoint corrects it, so the demo never mislabels the state."""
    return jsonify({
        "paypal_live": bool(
            paypal_invoices.PAYPAL_CLIENT_ID
            and paypal_invoices.PAYPAL_CLIENT_SECRET
        ),
        "paypal_mode": paypal_invoices.PAYPAL_MODE,
        "ai_live": (not ai_copilot.AI_MOCK)
        and bool(os.environ.get("AI_API_KEY")),
    })


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/sample")
def sample():
    """Prefill data so the demo works in one click."""
    return jsonify({"listing": SAMPLE_LISTING, "messages": SAMPLE_MESSAGES})


@app.post("/api/analyze")
def analyze():
    data = request.get_json(force=True) or {}
    listing = data.get("listing", {}) or {}
    messages = data.get("messages", "") or ""
    return jsonify({
        "reply_draft": draft_reply(listing, messages),
        "price_suggestion": suggest_price(listing, messages),
        "red_flags": scan_for_scams(messages),
        "checklist": MEETUP_CHECKLIST,
    })


@app.post("/api/invoice")
def invoice():
    data = request.get_json(force=True) or {}
    result = create_and_send_invoice(
        buyer_email=data.get("buyer_email", ""),
        item_title=data.get("item_title", ""),
        amount=data.get("amount", ""),
        note=data.get("note", ""),
    )
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
