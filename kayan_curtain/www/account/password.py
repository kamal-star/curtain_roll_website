import frappe
from frappe import _

from kayan_curtain.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/password")
	context.title = _("Change Password")
	context.no_cache = 1
	return context
