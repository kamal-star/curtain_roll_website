import frappe
from frappe import _

from kayan_curtain import cart as cart_api


def get_context(context):
	context.no_cache = 1
	context.title = _("Your Cart")

	info = cart_api.info()
	context.guest = info.get("guest")
	context.items = info.get("items") or []
	context.total_text = info.get("text")
	context.quotation = info.get("quotation")
	context.totals = info.get("totals")
	context.shown = info.get("shown")
	context.coupon = (info.get("totals") or {}).get("coupon") or ""
	context.login_url = "/login?redirect-to=/cart"

	# A cart no longer needs an account, so the page no longer asks for one.
	# What it still needs is somewhere to go next, and that is the checkout -
	# which is where the customer is asked who they are, once, at the point it
	# actually matters.
	context.can_check_out = bool(context.items)
	return context
