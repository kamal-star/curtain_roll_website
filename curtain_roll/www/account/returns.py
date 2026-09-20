import frappe
from frappe import _

from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/returns")
	context.title = _("Return Requests")
	context.no_cache = 1
	return context
