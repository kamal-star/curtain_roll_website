"""A customer's own document, ready to print.

Its own page rather than a whitelisted method because this returns a whole
HTML document, and a method returns JSON. Ownership is checked inside
printable_html before anything is rendered.
"""
import frappe
from frappe import _

from curtain_roll import account
from curtain_roll.account import guest_redirect

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		guest_redirect("/account")

	doctype = frappe.form_dict.get("doctype") or ""
	name = frappe.form_dict.get("name") or ""

	context.no_cache = 1
	context.title = name or _("Print")
	context.doc_name = name
	context.doctype_name = doctype
	try:
		context.body = account.printable_html(doctype, name)
	except frappe.PermissionError:
		# say the same thing whether it does not exist or is not theirs, so the
		# page cannot be used to find out which invoice numbers are real
		context.body = None
	return context
