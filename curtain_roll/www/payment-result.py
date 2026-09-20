"""Where the customer lands after paying.

Reports; it does not decide. What is shown comes from the Quotation, which
only the signature-checked callback and return handler ever write to - so a
customer cannot reach this page with ?state=paid and be told an unpaid order
is paid.

The query string is a hint and nothing more. It comes back through the
customer's browser from the gateway's page, so it can be stale, truncated or
missing, and the return's signature can fail for reasons that have nothing to
do with whether the money moved. The stored status is the answer; the order is
found from the customer's own records when the query string cannot say which
one it was.

Never report failure from uncertainty. Telling someone who has just paid that
their payment failed is the worst answer available, so anything we cannot
confirm is shown as "being confirmed" instead.
"""
import frappe
from frappe import _

no_cache = 1

FIELDS = ["clickpay_status", "grand_total", "currency", "party_name"]


def _customer():
	"""The signed-in customer, or None. Never raises."""
	from curtain_roll import cart

	try:
		if cart.is_guest():
			return None
		return cart.get_party()
	except Exception:
		frappe.log_error(title="payment-result: could not resolve the customer",
		                 message=frappe.get_traceback())
		return None


def _order_for(party, asked):
	"""The order this page is about, as a row, or None.

	`asked` is what the query string named. It is honoured only when it really
	belongs to this customer. When it names nothing usable we fall back to
	their most recent order that has been through the gateway, which is what
	they have just come back from.
	"""
	if asked and frappe.db.exists("Quotation", asked):
		row = frappe.db.get_value("Quotation", asked, FIELDS, as_dict=True)
		if row and (not party or row.get("party_name") == party):
			return asked, row

	if not party:
		return "", None

	name = frappe.db.get_value(
		"Quotation",
		{"party_name": party, "clickpay_status": ["is", "set"]},
		"name", order_by="modified desc")
	if not name:
		return "", None
	return name, frappe.db.get_value("Quotation", name, FIELDS, as_dict=True)


def get_context(context):
	context.no_cache = 1
	context.title = _("Payment")

	asked = frappe.form_dict.get("order") or ""
	claimed = (frappe.form_dict.get("state") or "").lower()

	order, row = _order_for(_customer(), asked)
	status = ((row or {}).get("clickpay_status") or "").lower()

	# The stored status decides. Only with no order at all does the query
	# string get a say, and even then it has to say "failed" explicitly.
	context.state = status or ("failed" if claimed == "failed" else "pending")
	context.order = order
	context.total = row
	return context
