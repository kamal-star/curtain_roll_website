"""The order confirmation, reachable without an account.

A guest has just placed an order and has no login to look it up with, so the
link carries a key generated when the order was made. That key is the only thing
that opens this page: knowing an order number is not enough, which matters
because order numbers are sequential and guessable.

The two filenames here do not match, and must not. The route is the TEMPLATE's
name, so the page has to be order-placed.html to answer /order-placed; the
controller is found by swapping the route's hyphens for underscores, so it has
to be order_placed.py. Name them both the same way and one of two things
happens: order_placed.html gives a 404, or order-placed.py is never imported
and the template renders with every variable undefined and every `{% if %}`
taking its empty branch - a page that looks like it works and lies.
"""

import frappe
from frappe import _

from curtain_roll import checkout, totals


def get_context(context):
	context.no_cache = 1
	context.title = _("Order placed")

	name = (frappe.form_dict.get("order") or "").strip()
	key = (frappe.form_dict.get("key") or "").strip()

	context.order = _mine(name, key)
	context.found = bool(context.order)
	if not context.found:
		return context

	quotation = context.order
	context.method = quotation.get(checkout.METHOD_FIELD) or ""
	context.by_bank = context.method == checkout.BANK
	context.bank = checkout.bank_details()

	money = totals.summarise(quotation.get("items"), quotation.get("coupon_code"))
	context.totals = money
	context.shown = totals.as_text(money)
	context.items = quotation.get("items")

	# recorded on the quotation when the invoice was raised; ERPNext keeps no
	# link of its own from an invoice back to its quotation
	context.invoice = quotation.get("cr_invoice") or ""
	return context


def _mine(name, key):
	"""The order, but only for someone holding its key.

	Compared with a constant-time check, because a plain == on a secret leaks
	how much of it was right to anyone patient enough to measure.
	"""
	import hmac

	if not name or not key or not frappe.db.exists("Quotation", name):
		return None

	stored = frappe.db.get_value("Quotation", name, checkout.ACCESS_FIELD) or ""
	if not stored or not hmac.compare_digest(str(stored), str(key)):
		return None

	from curtain_roll.utils import as_system_user

	# The buyer may be a guest, who can read no Quotation at all. The key is
	# what authorises this, so the read runs with permission and the check
	# above is the gate.
	with as_system_user():
		return frappe.get_doc("Quotation", name)
