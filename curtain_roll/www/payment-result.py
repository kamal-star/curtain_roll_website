"""Where the customer lands after paying.

Reports; it does not decide. The state shown is read back from the Quotation,
which only the signature-checked callback and return handler write to - so a
customer cannot reach this page with ?state=paid and be told their order is
paid when it is not.
"""
import frappe
from frappe import _

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.title = _("Payment")

	order = frappe.form_dict.get("order") or ""
	claimed = (frappe.form_dict.get("state") or "").lower()

	status = ""
	total = None
	if order and frappe.db.exists("Quotation", order):
		row = frappe.db.get_value(
			"Quotation", order,
			["clickpay_status", "grand_total", "currency", "party_name"],
			as_dict=True) or {}
		status = (row.get("clickpay_status") or "").lower()
		total = row

		# only show someone their own order
		from curtain_roll import cart
		try:
			if row.get("party_name") != cart.get_party():
				status, total = "", None
		except Exception:
			status, total = "", None

	# the stored status wins; the query string is only a hint for the wording
	context.state = status or ("failed" if claimed == "failed" else "pending")
	context.order = order
	context.total = total
	return context
