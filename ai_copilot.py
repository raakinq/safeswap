"""AI seam for SafeSwap.

THE INTEGRATION POINT. Three functions, one job each:
    draft_reply(listing, messages)   -> str
    suggest_price(listing, messages) -> {"price": str, "target": str, "floor": str, "reasoning": [str]}
    scan_for_scams(messages)         -> [{"severity": "high|medium|info", "flag": str, "detail": str, "quote": str}]

Tonight every function runs on MOCK logic (no API keys exist yet). The mocks are
real heuristics, not lorem ipsum, so the demo is honest about what it does.

TO GO LIVE (Raakin provides the key later — no code rewrite needed):
    1. Set env AI_MOCK=false
    2. Set env AI_API_KEY=<key> (provider auto-detected: sk-ant-... = Anthropic,
       anything else = OpenAI; override with AI_PROVIDER=anthropic|openai)
    3. _call_llm() below is implemented (OpenAI gpt-4o-mini / Anthropic
       claude-haiku-4-5, plain `requests`, temperature 0.2). No new dependency.
"""
import json
import os
import re

import requests

AI_MOCK = os.environ.get("AI_MOCK", "true").lower() == "true"
AI_PROVIDER = os.environ.get("AI_PROVIDER", "anthropic")


# --------------------------------------------------------------------------- #
# Public API — the rest of the app only calls these three functions.
# --------------------------------------------------------------------------- #
def draft_reply(listing, messages):
    """Draft a reply to the buyer in the seller's voice."""
    if not AI_MOCK:
        return _call_llm(_build_reply_prompt(listing, messages))
    return _mock_draft_reply(listing, messages)


def suggest_price(listing, messages):
    """Suggest ask / target / floor prices with reasoning."""
    if not AI_MOCK:
        return _call_llm(_build_price_prompt(listing, messages))
    return _mock_suggest_price(listing, messages)


def scan_for_scams(messages):
    """Scan buyer messages for scam red flags."""
    if not AI_MOCK:
        return _call_llm(_build_scam_prompt(messages))
    return _mock_scan_for_scams(messages)


# --------------------------------------------------------------------------- #
# Live path — implemented Nov 11, 2026 (was a NotImplementedError stub).
# Provider auto-detected from the key prefix; AI_PROVIDER overrides it.
# --------------------------------------------------------------------------- #
def _detect_provider():
    provider = (os.environ.get("AI_PROVIDER") or "").strip().lower()
    if provider in ("openai", "anthropic"):
        return provider
    if os.environ.get("AI_API_KEY", "").startswith("sk-ant-"):
        return "anthropic"
    return "openai"


def _extract_json(text):
    """Pull the first JSON object/array out of model output (tolerates prose
    around it, e.g. ```json fences). Returns the parsed value or None."""
    if not text:
        return None
    start = None
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start is None:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
        return value
    except (json.JSONDecodeError, ValueError):
        return None


def _normalize(parsed, prompt):
    """Shape parsed LLM output into what the frontend expects, so a model
    that answers with slightly different keys doesn't break the demo."""
    if "pricing coach" in prompt.lower():
        if not isinstance(parsed, dict):
            raise RuntimeError("Price coach reply was not a JSON object.")
        price = parsed.get("price") or parsed.get("ask") or "—"
        reasoning = parsed.get("reasoning") or parsed.get("bullets") or []
        if isinstance(reasoning, str):
            reasoning = [reasoning]
        return {
            "price": str(price),
            "target": str(parsed.get("target", "—")),
            "floor": str(parsed.get("floor", "—")),
            "reasoning": [str(r) for r in reasoning],
        }
    if "fraud analyst" in prompt.lower():
        if isinstance(parsed, dict):
            parsed = parsed.get("flags") or parsed.get("red_flags") or []
        if not isinstance(parsed, list):
            raise RuntimeError("Scam scan reply was not a JSON list.")
        out = []
        for f in parsed:
            if not isinstance(f, dict):
                continue
            out.append({
                "severity": str(f.get("severity", "info")).lower(),
                "flag": str(f.get("flag", "Flag")),
                "detail": str(f.get("detail", "")),
                "quote": str(f.get("quote", "")),
            })
        return out
    return parsed


def _call_llm(prompt):
    """Send `prompt` to the configured provider and return the model's reply.

    - Reply prompt -> plain text (the draft reply).
    - Price/scam prompts (ask for JSON) -> parsed + normalized dict/list.
    Raises RuntimeError with a plain-English message when the key is missing
    or the provider call fails, so the app surfaces the failure instead of
    silently falling back to mock data.
    Keep temperature low (0.2) — this is analysis, not creative writing.
    """
    api_key = os.environ.get("AI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "AI_API_KEY is not set. Set it and AI_MOCK=false to use live AI."
        )
    provider = _detect_provider()
    try:
        if provider == "anthropic":
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5",
                    "max_tokens": 1024,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            text = "".join(
                block.get("text", "")
                for block in resp.json().get("content", [])
                if block.get("type") == "text"
            )
        else:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": "Bearer " + api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
    except requests.RequestException as exc:
        raise RuntimeError("AI provider request failed: %s" % exc) from exc
    if "Return JSON" in prompt:
        parsed = _extract_json(text)
        if parsed is None:
            raise RuntimeError(
                "AI reply was not JSON; got: %s" % (text[:200] or "(empty)")
            )
        return _normalize(parsed, prompt)
    return text


def _build_reply_prompt(listing, messages):
    return (
        "You are helping a Facebook Marketplace seller reply to a buyer. "
        "Write a short, friendly reply in a casual seller voice (no corporate speak, "
        "no emojis overload). Listing: %(title)s at $%(price)s — %(desc)s. "
        "Buyer messages: %(msgs)s. Reply to their latest message; if they lowballed, "
        "counter politely without caving; if they ask logistics, answer directly."
        % {"title": listing.get("title"), "price": listing.get("price"),
           "desc": listing.get("description"), "msgs": messages}
    )


def _build_price_prompt(listing, messages):
    return (
        "Marketplace pricing coach. Listing: %(title)s at $%(price)s. Buyer messages: %(msgs)s. "
        "Return JSON with ask, target, floor prices and 2-3 short reasoning bullets. "
        "Typical Marketplace negotiation room is 5-15%%; flag lowball anchors under 80%% of ask."
        % {"title": listing.get("title"), "price": listing.get("price"), "msgs": messages}
    )


def _build_scam_prompt(messages):
    return (
        "Fraud analyst for peer-to-peer sales. Buyer messages: %s. "
        "Return JSON list of red flags, each with severity (high/medium/info), "
        "a short flag name, detail, and the exact quote. Cover: overpayment/cashier-check "
        "scams, gift-card requests, wire-then-ship pressure, fake mover/pickup-agent stories, "
        "phishing links, and Zelle-before-meeting pressure. 'Is this available' alone is info-level."
        % messages
    )


# --------------------------------------------------------------------------- #
# Mock implementations — honest heuristics, clearly labeled in the UI.
# --------------------------------------------------------------------------- #
def _parse_price(raw):
    m = re.search(r"[\d,]+(?:\.\d{1,2})?", str(raw or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _mock_draft_reply(listing, messages):
    title = listing.get("title") or "the item"
    price = listing.get("price") or "the listed price"
    low = messages.lower()
    offer = re.findall(r"\$\s?([\d,]+)", messages)
    if any(k in low for k in ("still available", "is this available", "available?")):
        return (
            "Hey! Yep, %s is still available. I'm around most evenings — "
            "want to come take a look? I can do $%s if you pick up this week."
            % (title, price)
        )
    if offer:
        return (
            "Hey, appreciate the offer! I can't do $%s, but I could meet you at "
            "$%s for %s — it's in great shape and I can show you it working "
            "when you pick up. Let me know!"
            % (offer[-1], price, title)
        )
    if any(k in low for k in ("where", "pickup", "pick up", "location", "meet")):
        return (
            "Hey! I'm in Plano near Park & Preston. Happy to meet somewhere public "
            "— there's a safe trade spot at the police station parking lot. "
            "Evenings work best for me. Does that work for %s?"
            % title
        )
    return (
        "Hey, thanks for reaching out about %s! It's still available at $%s. "
        "Let me know if you want to come see it — I can do evenings this week."
        % (title, price)
    )


def _mock_suggest_price(listing, messages):
    ask = _parse_price(listing.get("price"))
    if ask is None:
        return {
            "price": "—", "target": "—", "floor": "—",
            "reasoning": ["Couldn't read a listing price — enter one like 250 or $250."],
        }
    target = round(ask * 0.93)
    floor = round(ask * 0.85)
    reasoning = [
        "Listings near $%d typically close 5-15%% under ask on Marketplace." % ask,
        "Target $%d keeps you credible while leaving haggle room." % target,
        "Floor $%d — below this, relist or wait for the next buyer." % floor,
    ]
    offers = [float(o.replace(",", "")) for o in re.findall(r"\$\s?([\d,]+)", messages)]
    lowballs = [o for o in offers if o < ask * 0.8]
    if lowballs:
        reasoning.append(
            "Buyer anchored at $%d (under 80%% of ask) — that's a lowball anchor, "
            "counter near target instead of splitting the difference." % lowballs[-1]
        )
    return {
        "price": "$%d" % ask,
        "target": "$%d" % target,
        "floor": "$%d" % floor,
        "reasoning": reasoning,
    }


_SCAM_RULES = [
    (("cashier", "check"), ("certified check",), "high", "Overpayment / fake-check scam",
     "Classic: buyer 'accidentally' overpays with a fake cashier's check and asks you to refund the difference. The check bounces days later."),
    (("gift card",), ("steam card", "apple card"), "high", "Gift-card payment request",
     "No legit buyer pays with gift cards. This is a straight-up scam setup."),
    (("wire",), ("western union", "moneygram"), "high", "Wire transfer pressure",
     "Wires are irreversible. Combined with any ship-first or remote-buyer story, walk away."),
    (("mover", "pick up"), ("shipping agent", "courier will"), "high", "Fake mover / pickup-agent story",
     "'My mover will collect it' plus remote payment = the item leaves and the money never clears."),
    (("deployed",), ("military", "out of the country"), "medium", "Sympathy + remote deal combo",
     "Not always a scam, but deployed-out-of-country plus remote payment is a textbook setup. Insist on in-person."),
    (("kindly",), (), "medium", "'Kindly' phrasing + urgency",
     "Overly formal urgency ('kindly send', 'do the needful') is a common template in advance-fee fraud."),
    (("zelle",), ("venmo", "cashapp"), "medium", "Instant-payment-before-meeting pressure",
     "Fine in person, risky remotely. Never accept then ship — only release the item after YOU verify funds."),
    (("link", "click"), ("verify", "confirm"), "medium", "Suspicious link / phishing",
     "Buyers don't need you to click links. Real payment happens in your PayPal/bank app, not their URL."),
    (("lowest", "price"), (), "info", "Price haggle",
     "'What's your lowest' is normal Marketplace behavior, not a scam — just don't negotiate against yourself."),
    (("is this available",), (), "info", "Generic opener",
     "One-word 'available?' messages are normal. No flag on their own."),
]


def _mock_scan_for_scams(messages):
    low = (messages or "").lower()
    if not low.strip():
        return []
    flags = []
    for must_any, also_any, severity, flag, detail in _SCAM_RULES:
        hit = any(k in low for k in must_any) or any(k in low for k in also_any)
        if not hit:
            continue
        # find a representative quote (first matching sentence-ish chunk)
        quote = ""
        for chunk in re.split(r"[.\n]", messages):
            c = chunk.strip()
            if c and any(k in c.lower() for k in must_any + also_any):
                quote = c[:140]
                break
        flags.append({"severity": severity, "flag": flag, "detail": detail,
                      "quote": quote})
    # de-dup by flag name, keep order
    seen, out = set(), []
    for f in flags:
        if f["flag"] not in seen:
            seen.add(f["flag"])
            out.append(f)
    return out
