import frappe
from frappe import _

from kayan_curtain import cart
from kayan_curtain.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/wishlist")
	context.title = _("Wish List")
	context.no_cache = 1
	context.saved = cart.wishlist_items()
	return context
