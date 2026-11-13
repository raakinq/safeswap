"""PayPal seam for SafeSwap.

THE INTEGRATION POINT for money movement.

    create_and_send_invoice(buyer_email, item_title, amount, note="") -> dict

Tonight it returns MOCK data (no PayPal account exists yet). The moment
PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are set in the environment, the same
function runs the LIVE sandbox flow — no call-site changes needed:

    1. POST https://api-m.sandbox.paypal.com/v1/oauth2/token
         Basic auth Base64(client_id:secret), body grant_type=client_credentials
    2. POST https://api-m.sandbox.paypal.com/v2/invoicing/invoices
         Bearer token + JSON body (see _build_invoice_body)
    3. POST https://api-m.sandbox.paypal.com/v2/invoicing/invoices/{id}/send
         -> invoice goes DRAFT -> SENT, buyer gets a PayPal payment link by email

Full research notes: ../hidden_files/paypal-invoicing-notes.md
"""
import base64
import os

import requests

PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")  # sandbox | live
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")

BASE_URLS = {
    "sandbox": "https://api-m.sandbox.paypal.com",
    "live": "https://api-m.paypal.com",
}
BASE_URL = BASE_URLS.get(PAYPAL_MODE, BASE_URLS["sandbox"])

MOCK_MODE = not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)


def create_and_send_invoice(buyer_email, item_title, amount, note=""):
    """Create a PayPal invoice for the deal and send it to the buyer.

    Returns a dict the frontend renders. In mock mode the dict is clearly
    labeled; in live mode it carries the real invoice id + buyer link.
    """
    if MOCK_MODE:
        return _mock_invoice(buyer_email, item_title, amount, note)
    return _live_create_and_send_invoice(buyer_email, item_title, amount, note)


# --------------------------------------------------------------------------- #
# Mock — what runs tonight.
# --------------------------------------------------------------------------- #
def _mock_invoice(buyer_email, item_title, amount, note):
    return {
        "status": "stub",
        "invoice_id": "MOCK-INV-0001",
        "buyer_email": buyer_email or "(no email entered)",
        "item_title": item_title or "(no title entered)",
        "amount": amount or "(no amount entered)",
        "message": (
            "PayPal sandbox is not wired yet — this is a mock invoice. "
            "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET and the same button "
            "will create + send a real sandbox invoice via the Invoicing API."
        ),
        "integration": {
            "token_url": BASE_URL + "/v1/oauth2/token",
            "create_url": BASE_URL + "/v2/invoicing/invoices",
            "send_url_template": BASE_URL + "/v2/invoicing/invoices/{invoice_id}/send",
            "function": "paypal_invoices.create_and_send_invoice",
            "credentials_from": "env PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET (Raakin provides)",
        },
    }


# --------------------------------------------------------------------------- #
# Live — runs automatically once credentials exist. Written against the
# Invoices v2 REST reference; untested until Raakin's sandbox account lands.
# --------------------------------------------------------------------------- #
def _get_access_token():
    auth = base64.b64encode(
        f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()
    ).decode()
    resp = requests.post(
        f"{BASE_URL}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _build_invoice_body(buyer_email, item_title, amount, note):
    value = "%.2f" % float(str(amount).replace("$", "").replace(",", ""))
    return {
        "detail": {
            "currency_code": "USD",
            "note": note or f"SafeSwap deal: {item_title}",
        },
        "primary_recipients": [
            {"billing_info": {"email_address": buyer_email}}
        ],
        "items": [{
            "name": item_title,
            "quantity": "1",
            "unit_amount": {"currency_code": "USD", "value": value},
            "unit_of_measure": "QUANTITY",
        }],
    }


def _live_create_and_send_invoice(buyer_email, item_title, amount, note=""):
    token = _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    create = requests.post(
        f"{BASE_URL}/v2/invoicing/invoices",
        headers=headers,
        json=_build_invoice_body(buyer_email, item_title, amount, note),
        timeout=20,
    )
    create.raise_for_status()
    invoice_id = create.json()["id"]

    send = requests.post(
        f"{BASE_URL}/v2/invoicing/invoices/{invoice_id}/send",
        headers=headers,
        json={"send_to_recipient": True},
        timeout=20,
    )
    send.raise_for_status()

    recipient_url = (
        create.json().get("detail", {}).get("metadata", {}).get("recipient_view_url")
    )
    return {
        "status": "sent",
        "invoice_id": invoice_id,
        "buyer_email": buyer_email,
        "item_title": item_title,
        "amount": amount,
        "buyer_link": recipient_url,
        "message": f"Invoice {invoice_id} sent to {buyer_email} via PayPal sandbox.",
    }
