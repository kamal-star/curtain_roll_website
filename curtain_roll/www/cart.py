import frappe

from curtain_roll import cart as cart_api


def get_context(context):
	context.no_cache = 1
	context.title = "Your Cart"
	info = cart_api.info()
	context.guest = info.get("guest")
	context.items = info.get("items") or []
	context.total_text = info.get("text")
	context.quotation = info.get("quotation")
	context.login_url = "/login?redirect-to=/cart"

	# Offer to pay only when the gateway is actually configured on this site.
	# A Pay button that throws "ClickPay is not configured" is worse than no
	# button, and this way a site without keys simply keeps the old flow.
	from curtain_roll import clickpay

	context.pay_online = bool(
		clickpay.configured() and not info.get("guest") and context.items)
	return context
