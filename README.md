# SafeSwap — AI deal copilot for Marketplace sellers

Paste a Facebook Marketplace listing + the buyer thread. SafeSwap drafts your reply,
coaches your price, scans for scam red flags, invoices the buyer through PayPal,
and hands you a meetup safety checklist.

## What it does

One page, one flow:

1. **Paste listing** (title, price, description) + **paste buyer messages**
2. **Suggested reply** — drafted in a casual seller voice, adapts to what the buyer asked
3. **Price coach** — ask / target / floor with reasoning (flags lowball anchors)
4. **Scam scan** — red flags for overpayment, gift cards, fake movers, and more
5. **PayPal invoice** — creates and sends a real PayPal invoice to the buyer
6. **Meetup safety checklist** — always shown

## Quickstart

```bash
cd safeswap
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py
# open http://localhost:5000 — hit "Load sample deal" then "Analyze deal"
```

Without API keys, the app runs on mock data so the full UX is demoable.
Set the env vars below to go live — no code changes needed.

## Configuration

Env vars (`.env` locally, never committed — see `.gitignore`):

```
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
AI_MOCK=true
AI_PROVIDER=anthropic
AI_API_KEY=...
PORT=5000
```

| Var | What it unlocks |
|-----|-----------------|
| `PAYPAL_CLIENT_ID` + `PAYPAL_CLIENT_SECRET` | Real PayPal invoices (sandbox by default, `PAYPAL_MODE=live` for production) via `paypal_invoices.create_and_send_invoice` |
| `AI_API_KEY` + `AI_MOCK=false` | Real LLM replies, pricing, and scam analysis via `ai_copilot` (OpenAI or Anthropic, auto-detected from the key) |

The `/api/status` endpoint reports honestly whether PayPal and AI are live or on mock,
so the UI badge never mislabels the state.

## How the seams work

- **AI:** `ai_copilot.py` — `draft_reply()`, `suggest_price()`, `scan_for_scams()`.
  Each builds its prompt already (`_build_*_prompt`); `_call_llm(prompt)` is
  implemented (OpenAI gpt-4o-mini / Anthropic claude-haiku-4-5, plain
  `requests`, provider auto-detected from the key). Flip `AI_MOCK=false`
  and set `AI_API_KEY` to go live.
- **PayPal:** `paypal_invoices.py` — `create_and_send_invoice()`.
  Live 3-step flow (token → create draft → send) is fully written in
  `_live_create_and_send_invoice()`; it runs automatically when credentials exist.

## Deploy

Any host that runs Python works. With gunicorn:

```bash
pip install -r requirements.txt
gunicorn app:app
```

Set the env vars above in the host's environment (no `.env` file on the server).
On Render: New → Web Service → connect this repo, build command
`pip install -r requirements.txt`, start command `gunicorn app:app`.

## Project layout

```
safeswap/
├── app.py              # Flask routes: / , /api/sample, /api/analyze, /api/invoice, /api/status
├── ai_copilot.py       # AI seam — reply drafting, price coaching, scam scan
├── paypal_invoices.py  # PayPal seam — Invoicing API v2 (create + send)
├── mock_data.py        # checklist + one-click sample deal
├── templates/index.html# the whole UI (vanilla JS, no build step)
├── static/style.css
├── requirements.txt    # Flask, gunicorn, requests
├── LICENSE             # MIT
└── .gitignore
```
