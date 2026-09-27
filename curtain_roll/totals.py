"""What the customer is actually asked to pay, and why.

Three numbers reach the customer - subtotal, discount, VAT - and every one of
them has to mean the same thing in four places: the cart page, the checkout
summary, the amount handed to the payment gateway, and the tax invoice ERPNext
raises afterwards. So they are computed here, once, and every one of those four
reads this rather than doing its own arithmetic.

On VAT being included in the price: Saudi retail quotes prices with VAT in them,
and every price on this site was written that way. So the default is inclusive -
the total stays exactly the number the customer already saw on the product page,
and the VAT line shows how much of it the tax authority gets. A site that wants
to quote net prices instead flips one tick in the settings, and then VAT is
added on top. Getting this backwards silently makes everything 15% dearer, which
is why it is a setting and not a constant.
"""

import frappe
from frappe.utils import flt

from curtain_roll.language import text as say
from curtain_roll.storefront import storefront_settings

# ERPNext rounds money to the currency's precision; doing the same here keeps
# our displayed total and the invoice's grand total from differing by a halala.
PRECISION = 2


def vat_rate():
	"""The VAT percentage this site charges. 0 turns the tax line off."""
	return flt(storefront_settings().get("vat_rate") or 0)


def prices_include_vat():
	settings = storefront_settings()
	# absent means inclusive: that is how the captured prices were written, so
	# a site that has never opened the setting must not suddenly charge more
	value = settings.get("prices_include_vat")
	return True if value in (None, "") else bool(int(value))


# ------------------------------------------------------------------ coupons
def coupon_discount(code, subtotal):
	"""What a coupon takes off, in money. 0 if it takes nothing.

	The coupon itself is an ERPNext Coupon Code, and what it is worth comes from
	the Pricing Rule it points at - so the team sets up a discount the way they
	would for any other channel, and the storefront does not invent a second
	kind of discount that only exists here.
	"""
	if not code or not subtotal:
		return 0.0

	rule = frappe.db.get_value("Coupon Code", code, "pricing_rule")
	if not rule:
		return 0.0

	kind, percent, amount = frappe.db.get_value(
		"Pricing Rule", rule,
		["rate_or_discount", "discount_percentage", "discount_amount"]) \
		or (None, 0, 0)

	if kind == "Discount Percentage":
		return flt(subtotal * flt(percent) / 100.0, PRECISION)
	if kind == "Discount Amount":
		# never more than the basket is worth - a fixed-amount coupon on a small
		# order must not turn into money owed to the customer
		return flt(min(flt(amount), subtotal), PRECISION)
	return 0.0


def coupon_problem(code):
	"""Why this coupon cannot be used, in words, or None if it can.

	Every reason is returned as its own sentence rather than one "invalid
	coupon", because "that code ran out" and "that code is not ours" send the
	customer to two different places.
	"""
	from frappe.utils import getdate, nowdate

	if not code:
		return None

	name = frappe.db.get_value("Coupon Code", {"coupon_code": code}, "name") \
		or (code if frappe.db.exists("Coupon Code", code) else None)
	if not name:
		return say("That coupon code was not recognised.")

	doc = frappe.db.get_value(
		"Coupon Code", name,
		["valid_from", "valid_upto", "maximum_use", "used", "pricing_rule"],
		as_dict=True)

	today = getdate(nowdate())
	if doc.valid_from and getdate(doc.valid_from) > today:
		return say("That coupon is not active yet.")
	if doc.valid_upto and getdate(doc.valid_upto) < today:
		return say("That coupon has expired.")
	if doc.maximum_use and flt(doc.used) >= flt(doc.maximum_use):
		return say("That coupon has been fully used.")
	if not doc.pricing_rule:
		return say("That coupon is not set up with a discount yet.")
	return None


def resolve_coupon(code):
	"""The Coupon Code record's name for what the customer typed, or None."""
	if not code:
		return None
	return frappe.db.get_value("Coupon Code", {"coupon_code": code}, "name") \
		or (code if frappe.db.exists("Coupon Code", code) else None)


# ------------------------------------------------------------------- totals
def summarise(lines, coupon=None):
	"""Subtotal, discount, VAT and total for a set of cart lines.

	``lines`` is anything with .qty and .rate - a Quotation's items or a guest
	cart's - so one calculation serves a basket that has an account behind it
	and one that does not.
	"""
	subtotal = flt(sum(flt(row.qty or 0) * flt(row.rate or 0) for row in lines),
	               PRECISION)
	discount = coupon_discount(coupon, subtotal) if coupon else 0.0
	after_discount = flt(subtotal - discount, PRECISION)

	rate = vat_rate()
	if not rate:
		vat = 0.0
		total = after_discount
	elif prices_include_vat():
		# the line prices already contain the tax, so pull it back out
		net = flt(after_discount / (1 + rate / 100.0), PRECISION)
		vat = flt(after_discount - net, PRECISION)
		total = after_discount
		after_discount = net
	else:
		vat = flt(after_discount * rate / 100.0, PRECISION)
		total = flt(after_discount + vat, PRECISION)

	return {
		"subtotal": subtotal,
		"discount": discount,
		"net": after_discount,
		"vat_rate": rate,
		"vat": vat,
		"vat_included": prices_include_vat(),
		"total": total,
		"coupon": coupon or "",
	}


def as_text(summary):
	"""The same numbers formatted for display, so no template formats money."""
	from curtain_roll import pricing

	symbol = pricing.currency_symbol()

	def money(value):
		return "%s %s" % (symbol, "{:,.2f}".format(flt(value)))

	shown = {k: money(summary[k])
	         for k in ("subtotal", "discount", "net", "vat", "total")}
	shown["vat_label"] = "%s %s%%" % (say("VAT"),
	                                  ("{:g}".format(summary["vat_rate"])))
	return shown
