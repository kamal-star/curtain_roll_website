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
	return context
