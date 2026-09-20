import frappe
from frappe import _

from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/edit")
	context.title = _("Account Information")
	context.no_cache = 1
	context.account_user = frappe.get_doc("User", frappe.session.user)
	return context
