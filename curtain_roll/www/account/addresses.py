import frappe
from frappe import _

from curtain_roll import account
from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account/addresses")
	context.title = _("Address Book")
	context.no_cache = 1
	context.addresses = account.my_addresses()
	context.countries = frappe.get_all("Country", pluck="name", order_by="name")
	return context
