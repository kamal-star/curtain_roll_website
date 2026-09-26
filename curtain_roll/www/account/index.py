"""The customer's account hub.

Everything under /account is per-customer, so none of it may be cached: the
storefront's captured pages ARE cached, which is why their header cannot know
who is signed in and has to be corrected in the browser. These pages are
rendered per request instead, so the shell can simply ask.
"""
import frappe
from frappe import _

from curtain_roll.account import guest_redirect

no_cache = 1


def counts():
	"""What to show on the tiles, so the hub reports rather than just links."""
	from curtain_roll import account, cart

	out = {"orders": 0, "wishlist": 0, "addresses": 0, "invoices": 0}
	try:
		out["orders"] = len(account.my_orders())
		out["addresses"] = len(account.my_addresses())
		out["wishlist"] = len(cart.wishlist_keys())
		out["invoices"] = len(account.my_invoices())
	except Exception:
		# a brand new customer has no Customer record yet; an empty hub is the
		# right answer, not a stack trace
		frappe.clear_last_message()
	return out


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account")

	context.title = _("My Account")
	context.no_cache = 1
	# NOT context.user: Frappe's own website context already owns that name and
	# fills it with the session user's id as a plain string, so assigning a
	# Document here is overwritten and the template ends up doing .name on a str
	context.account_user = frappe.get_doc("User", frappe.session.user)
	context.counts = counts()
	return context
