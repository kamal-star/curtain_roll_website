"""ClickPay (PayTabs) payments for the storefront.

ClickPay is PayTabs white-labelled for Saudi Arabia, so the API is PayTabs':
a Hosted Payment Page. We ask for a payment, get a URL back, send the customer
to it, and ClickPay tells us the outcome twice - once through the browser and
once server to server.

Both of those matter, and for different reasons:

  `return`   is where the customer's browser lands afterwards. It is what they
             see, and it is NOT trustworthy on its own: a browser can be closed,
             lose signal, or be made to send anything at all.
  `callback` is ClickPay's own server telling ours, independently of the
             customer. It is the one that decides whether an order is paid.

Nothing here charges a card. The card form lives on ClickPay's page, which is
what keeps the site at PCI SAQ A - no card number ever reaches this server.

Credentials are read from site_config.json and never from the repo:

    bench --site <site> set-config clickpay_profile_id <id>
    bench --site <site> set-config clickpay_server_key <key>
    bench --site <site> set-config clickpay_live 0
"""
import hashlib
import hmac
import json
import urllib.parse

import frappe
from frappe import _

DOMAIN = "https://secure.clickpay.com.sa"
PAY_REQUEST = "/payment/request"
QUERY = "/payment/query"


# ----------------------------------------------------------------- config
def settings():
	"""Credentials, from the site config. Never from the database or the repo."""
	conf = frappe.conf
	profile = conf.get("clickpay_profile_id")
	key = conf.get("clickpay_server_key")
	if not profile or not key:
		frappe.throw(_("ClickPay is not configured on this site."))
	return {
		"profile_id": int(profile),
		"server_key": str(key),
		"domain": (conf.get("clickpay_domain") or DOMAIN).rstrip("/"),
		"live": bool(int(conf.get("clickpay_live") or 0)),
	}


def configured():
	return bool(frappe.conf.get("clickpay_profile_id")
	            and frappe.conf.get("clickpay_server_key"))


# ------------------------------------------------------------- signatures
def callback_signature(raw_body, server_key):
	"""HMAC-SHA256 of the WHOLE raw body.

	The raw bytes as received, not a re-serialised dict: re-encoding JSON
	reorders keys and changes spacing, and the hash is over the exact text
	ClickPay hashed.
	"""
	if isinstance(raw_body, str):
		raw_body = raw_body.encode("utf-8")
	return hmac.new(server_key.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def return_signature(fields, server_key):
	"""The return URL's own, longer scheme.

	Not the same as the callback's, which is a trap worth naming: the callback
	hashes the raw body, while the return POST has to be rebuilt first - drop
	`signature`, drop every empty value, sort by key, url-encode both sides,
	and only then hash. Using one scheme for the other fails every time and
	looks like a wrong key.
	"""
	parts = []
	for key in sorted(fields):
		if key == "signature":
			continue
		value = fields[key]
		if value is None or value == "":
			continue
		parts.append("%s=%s" % (urllib.parse.quote_plus(str(key)),
		                        urllib.parse.quote_plus(str(value))))
	payload = "&".join(parts)
	return hmac.new(server_key.encode("utf-8"), payload.encode("utf-8"),
	                hashlib.sha256).hexdigest()


def genuine(expected, received):
	"""Constant-time compare, so a wrong signature cannot be guessed by timing."""
	return hmac.compare_digest(str(expected or ""), str(received or ""))


# --------------------------------------------------------------- requests
def _post(path, payload):
	import requests

	cfg = settings()
	res = requests.post(
		cfg["domain"] + path,
		headers={"authorization": cfg["server_key"],
		         "content-type": "application/json"},
		data=json.dumps(payload), timeout=30)
	try:
		body = res.json()
	except ValueError:
		frappe.log_error(title="ClickPay non-JSON reply",
		                 message="%s\n%s" % (res.status_code, res.text[:2000]))
		frappe.throw(_("The payment provider returned an unreadable reply."))
	return res.status_code, body


def create_payment(cart_id, amount, description, return_url, callback_url,
                   currency="SAR", email=None, name=None, phone=None):
	"""Ask ClickPay for a payment page. Returns (tran_ref, redirect_url).

	`amount` must come from the server's own pricing, never from the browser.
	"""
	cfg = settings()
	payload = {
		"profile_id": cfg["profile_id"],
		"tran_type": "sale",
		"tran_class": "ecom",
		"cart_id": str(cart_id),
		"cart_description": (description or "Curtains")[:500],
		"cart_currency": currency,
		"cart_amount": float(amount),
		"return": return_url,
		"callback": callback_url,
	}
	if email or name or phone:
		payload["customer_details"] = {
			"name": (name or "")[:60] or "Customer",
			"email": email or "",
			"phone": phone or "",
			"street1": "-", "city": "-", "state": "-",
			"country": "SA", "zip": "-",
		}

	status, body = _post(PAY_REQUEST, payload)
	redirect = body.get("redirect_url")
	if status != 200 or not redirect:
		frappe.log_error(title="ClickPay payment request refused",
		                 message=json.dumps({"sent": _redacted(payload),
		                                     "status": status,
		                                     "got": body}, indent=1)[:4000])
		frappe.throw(_("The payment could not be started. Please try again."))
	return body.get("tran_ref"), redirect


def query(tran_ref):
	"""Ask ClickPay what actually happened to a transaction.

	The last word on an order's state. A callback can be missed - a deploy at
	the wrong moment, a network blip - and a customer who paid must not be left
	looking unpaid because one HTTP request did not arrive.
	"""
	cfg = settings()
	status, body = _post(QUERY, {"profile_id": cfg["profile_id"],
	                             "tran_ref": tran_ref})
	return body if status == 200 else {}


def _redacted(payload):
	"""A copy safe to write to the error log."""
	out = dict(payload)
	out.pop("profile_id", None)
	return out


# ----------------------------------------------------------------- result
SUCCESS = ("A",)          # Authorised
HELD = ("H",)             # held for review
PENDING = ("P",)


def outcome(fields):
	"""Read a ClickPay response into something the rest of the app can use."""
	status = (fields.get("respStatus")
	          or (fields.get("payment_result") or {}).get("response_status") or "")
	message = (fields.get("respMessage")
	           or (fields.get("payment_result") or {}).get("response_message") or "")
	return {
		"paid": status in SUCCESS,
		"pending": status in HELD or status in PENDING,
		"status": status,
		"message": message,
		"tran_ref": fields.get("tranRef") or fields.get("tran_ref"),
		"cart_id": fields.get("cartId") or fields.get("cart_id"),
		"amount": fields.get("cart_amount") or fields.get("cartAmount"),
		"currency": fields.get("cart_currency") or fields.get("cartCurrency"),
	}


# =====================================================================
#  The payment flow
# =====================================================================
STATUS_FIELD = "clickpay_status"
REF_FIELD = "clickpay_tran_ref"

PAID = "Paid"
PENDING_REVIEW = "Pending"
FAILED = "Failed"
STARTED = "Started"


def allow_gateway_post():
	"""Let ClickPay's browser redirect POST back to us.

	Frappe checks a CSRF token on every POST from a signed-in session. The
	return from ClickPay IS such a POST - the customer's browser still carries
	their session cookie - but it originates on ClickPay's page and so has no
	token. Without this the customer lands on a 403 having just paid.

	Exempting one path is safe because nothing here trusts that POST: the money
	is decided by the server-to-server callback, and both are signature-checked
	against the server key before they are believed.
	"""
	path = getattr(frappe.request, "path", "") or ""
	if path.startswith("/api/method/curtain_roll.clickpay.payment_return"):
		frappe.flags.ignore_csrf = True


def _cart_quotation():
	"""The signed-in customer's draft cart."""
	from curtain_roll import cart

	customer = cart.get_party()
	if not customer:
		frappe.throw(_("No cart to pay for."))
	name = frappe.db.get_value(
		"Quotation", {"party_name": customer, "docstatus": 0},
		"name", order_by="modified desc")
	if not name:
		frappe.throw(_("Your cart is empty."))
	return frappe.get_doc("Quotation", name)


@frappe.whitelist(methods=["POST"])
def checkout():
	"""Start a payment for the signed-in customer's cart."""
	from curtain_roll import cart

	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in to pay."), frappe.PermissionError)

	quotation = _cart_quotation()

	# Re-price before quoting an amount. The total comes from the document the
	# server has just computed and never from anything the browser sent - the
	# whole point being that the customer cannot choose what to be charged.
	cart.reprice(quotation)
	quotation.reload()

	amount = float(quotation.grand_total or 0)
	if amount <= 0:
		frappe.throw(_("There is nothing to pay for."))
	if (quotation.currency or "") != "SAR":
		frappe.throw(_("This order is in {0}; ClickPay charges in SAR.")
		             .format(quotation.currency))

	# ClickPay refuses a callback it cannot reach - "Invalid Callback URL" -
	# so a developer machine on http://localhost cannot complete the loop.
	# `clickpay_base_url` lets a dev site point its callbacks at a tunnel or at
	# the staging domain while everything else stays local.
	base = (frappe.conf.get("clickpay_base_url") or frappe.utils.get_url()).rstrip("/")
	if base.startswith("http://") and "localhost" not in base:
		frappe.throw(_("ClickPay requires an https callback address."))

	tran_ref, redirect_url = create_payment(
		cart_id=quotation.name,
		amount=amount,
		description="Kayan order %s" % quotation.name,
		return_url="%s/api/method/curtain_roll.clickpay.payment_return" % base,
		callback_url="%s/api/method/curtain_roll.clickpay.callback" % base,
		currency="SAR",
		email=frappe.session.user if "@" in frappe.session.user else None,
		name=frappe.db.get_value("User", frappe.session.user, "full_name"))

	frappe.db.set_value("Quotation", quotation.name,
	                    {REF_FIELD: tran_ref, STATUS_FIELD: STARTED},
	                    update_modified=False)
	frappe.db.commit()
	return {"ok": 1, "redirect_url": redirect_url, "tran_ref": tran_ref}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def callback():
	"""ClickPay's server telling ours what happened. The source of truth.

	Answers 200 whatever we decide, because a gateway that cannot get a 200
	retries - for days - and a retry storm caused by our own bug helps nobody.
	Anything wrong is logged instead.
	"""
	raw = frappe.request.get_data() or b""
	sent = frappe.get_request_header("Signature") or ""
	cfg = settings()

	if not genuine(callback_signature(raw, cfg["server_key"]), sent):
		frappe.log_error(title="ClickPay callback signature rejected",
		                 message=raw.decode("utf-8", "replace")[:2000])
		return {"ok": 0}

	try:
		fields = json.loads(raw.decode("utf-8"))
	except ValueError:
		frappe.log_error(title="ClickPay callback not JSON",
		                 message=raw.decode("utf-8", "replace")[:2000])
		return {"ok": 0}

	try:
		settle(outcome(fields))
	except Exception:
		frappe.log_error(title="ClickPay callback failed",
		                 message=frappe.get_traceback())
	return {"ok": 1}


@frappe.whitelist(allow_guest=True)
def payment_return(**kwargs):
	"""Where the customer's browser lands. Shows a result; decides nothing."""
	fields = dict(frappe.form_dict or {})
	fields.pop("cmd", None)
	cfg = settings()

	ok = genuine(return_signature(fields, cfg["server_key"]),
	             fields.get("signature"))
	result = outcome(fields)

	# The callback is the source of truth and usually arrives first, but not
	# always. Settling here too - idempotently - keeps a customer from being
	# shown "unpaid" for a payment that went through.
	if ok and result["paid"]:
		try:
			settle(result)
		except Exception:
			frappe.log_error(title="ClickPay return settle failed",
			                 message=frappe.get_traceback())

	state = "paid" if (ok and result["paid"]) else (
		"pending" if result["pending"] else "failed")
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/payment-result?state=%s&order=%s" % (
		state, frappe.utils.quoted(result.get("cart_id") or ""))
	_keep_the_browsers_session()


def _keep_the_browsers_session():
	"""Stop this response touching the visitor's login cookie.

	ClickPay sends the customer back with a cross-site POST. A SameSite=Lax
	cookie is not sent on one, so Frappe sees no session here, starts a Guest
	one, and would answer with Set-Cookie: sid=Guest - silently logging the
	customer out at the exact moment they finish paying, and then telling them
	the payment failed because a guest owns no orders.

	Nothing on this path needs to set a cookie, so the safest thing is to send
	none at all and leave whatever the browser already holds alone.
	"""
	manager = getattr(frappe.local, "cookie_manager", None)
	if manager:
		manager.cookies.clear()
		del manager.to_delete[:]


def settle(result):
	"""Record a successful payment. Safe to call more than once.

	Both the callback and the return can arrive, in either order and more than
	once, because gateways retry. Everything here keys on the quotation's
	stored status, read with a row lock, so a second arrival does nothing
	rather than raising a second invoice for the same money.
	"""
	name = result.get("cart_id")
	if not name or not frappe.db.exists("Quotation", name):
		return

	if not result["paid"]:
		frappe.db.set_value("Quotation", name, STATUS_FIELD,
		                    PENDING_REVIEW if result["pending"] else FAILED,
		                    update_modified=False)
		frappe.db.commit()
		return

	# lock the row, so two arrivals cannot both decide they are the first
	current = frappe.db.sql(
		"select `%s` from `tabQuotation` where name = %%s for update"
		% STATUS_FIELD, (name,))
	if current and current[0][0] == PAID:
		return

	quotation = frappe.get_doc("Quotation", name)

	# What ClickPay says was paid must match what we asked for. A mismatch is
	# not a rounding problem, it is a different amount, and it stops here.
	charged = frappe.utils.flt(result.get("amount") or 0, 2)
	expected = frappe.utils.flt(quotation.grand_total, 2)
	if charged and abs(charged - expected) > 0.01:
		frappe.log_error(
			title="ClickPay amount mismatch",
			message="%s: charged %s, expected %s (tran %s)"
			        % (name, charged, expected, result.get("tran_ref")))
		return

	invoice = _raise_invoice(quotation)
	_record_payment(invoice, result)

	frappe.db.set_value("Quotation", name,
	                    {STATUS_FIELD: PAID, REF_FIELD: result.get("tran_ref")},
	                    update_modified=False)
	frappe.db.commit()


def _raise_invoice(quotation):
	from erpnext.selling.doctype.quotation.quotation import make_sales_invoice

	if quotation.docstatus == 0:
		quotation.flags.ignore_permissions = True
		quotation.submit()

	invoice = make_sales_invoice(quotation.name)
	invoice.flags.ignore_permissions = True
	invoice.set_missing_values()
	invoice.insert(ignore_permissions=True)
	invoice.submit()
	return invoice


def _record_payment(invoice, result):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	entry = get_payment_entry("Sales Invoice", invoice.name)
	entry.reference_no = result.get("tran_ref") or invoice.name
	entry.reference_date = frappe.utils.nowdate()
	entry.mode_of_payment = _mode_of_payment()
	entry.flags.ignore_permissions = True
	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry


def _mode_of_payment():
	"""A Mode of Payment named for the gateway, created once if absent."""
	name = "ClickPay"
	if not frappe.db.exists("Mode of Payment", name):
		frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": name,
		                "type": "Bank"}).insert(ignore_permissions=True)
	return name
