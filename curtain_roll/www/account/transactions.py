import frappe
from frappe import _

from curtain_roll import account
from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/transactions")
	context.title = _("Your Transactions")
	context.no_cache = 1
	context.payments = account.my_payments()
	return context
