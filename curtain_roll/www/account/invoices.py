import frappe
from frappe import _

from curtain_roll import account
from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/invoices")
	context.title = _("Your Invoices")
	context.no_cache = 1
	context.invoices = account.my_invoices()
	return context
