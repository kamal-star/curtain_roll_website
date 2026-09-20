import frappe
from frappe import _

from curtain_roll import cart
from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/wishlist")
	context.title = _("Wish List")
	context.no_cache = 1
	context.saved = cart.wishlist_items()
	return context
