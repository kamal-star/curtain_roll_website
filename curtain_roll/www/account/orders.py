import frappe
from frappe import _

from curtain_roll import account
from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/orders")
	context.title = _("Order History")
	context.no_cache = 1
	context.orders = account.my_orders()
	return context
