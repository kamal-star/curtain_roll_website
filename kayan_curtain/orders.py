"""The ERP paperwork a website order leaves behind - all of it as drafts.

The team asked for nothing to be submitted by the website: the Quotation, the
Sales Invoice and the Payment Entry are generated, and a person looks at them
and submits them. So:

  * the Quotation stays a draft. It stops being the customer's basket through
    its payment status (cart.PLACED_STATUSES), not through being submitted.
  * the Sales Invoice is made as a draft straight from the draft Quotation.
    ERPNext's own "make invoice from quotation" refuses a draft source, so the
    same mapping is done here without that one check.
  * a card payment becomes a draft Payment Entry. ERPNext will not let a
    Payment Entry point at an invoice that is not submitted, so the entry is
    made unallocated, and it is tied to the invoice the moment the team submits
    the invoice (link_payment, a Sales Invoice on_submit hook). The team then
    submits the payment.

Every one of the three names the "Website" Sales Person, and the invoice and the
payment name the quotation they came from - ERPNext 16 keeps no link of its own.
"""

import frappe
from frappe.utils import flt, nowdate

SALES_PERSON = "Website"
QUOTATION_FIELD = "cr_quotation"
PERSON_FIELD = "cr_sales_person"
INVOICE_FIELD = "cr_sales_invoice"


# ---------------------------------------------------------------- set-up
def ensure_sales_person():
	"""The "Website" Sales Person, made once under the root of the tree."""
	if frappe.db.exists("Sales Person", SALES_PERSON):
		return SALES_PERSON
	root = frappe.db.get_value("Sales Person", {"is_group": 1, "parent_sales_person": ""},
	                           "name") or frappe.db.get_value(
		"Sales Person", {"is_group": 1}, "name")
	try:
		frappe.get_doc({
			"doctype": "Sales Person",
			"sales_person_name": SALES_PERSON,
			"parent_sales_person": root,
			"is_group": 0,
			"enabled": 1,
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="kayan_curtain: Website sales person")
		return None
	return SALES_PERSON


def ensure_fields():
	from kayan_curtain.install import _custom_field

	for doctype, after in (("Quotation", "order_type"),
	                       ("Payment Entry", "mode_of_payment")):
		_custom_field(doctype, PERSON_FIELD, label="Sales Person",
		              fieldtype="Link", options="Sales Person",
		              insert_after=after, no_copy=0,
		              description="Website for orders placed on the storefront.")

	for doctype, after in (("Sales Invoice", "customer"),
	                       ("Payment Entry", "party")):
		_custom_field(doctype, QUOTATION_FIELD, label="Website Order",
		              fieldtype="Link", options="Quotation", read_only=1,
		              no_copy=1, insert_after=after,
		              description="The storefront order this came from.")

	_custom_field("Payment Entry", INVOICE_FIELD, label="For Invoice",
	              fieldtype="Link", options="Sales Invoice", read_only=1,
	              no_copy=1, insert_after=QUOTATION_FIELD,
	              description="Allocated to this invoice when the invoice is "
	                          "submitted.")


def stamp_quotation(quotation):
	"""Name the Website Sales Person on the order itself."""
	if frappe.get_meta("Quotation").has_field(PERSON_FIELD) \
			and not quotation.get(PERSON_FIELD) and ensure_sales_person():
		quotation.set(PERSON_FIELD, SALES_PERSON)


# --------------------------------------------------------------- invoice
def draft_invoice(quotation):
	"""A draft Sales Invoice for this order. Made once; asked again, the same one.

	The mapping is ERPNext's own (selling/doctype/quotation/quotation.py,
	_make_sales_invoice) less its "source must be submitted" check - the whole
	of the difference.
	"""
	from frappe.model.mapper import get_mapped_doc

	existing = frappe.db.get_value("Quotation", quotation.name, "cr_invoice")
	if existing and frappe.db.exists("Sales Invoice", existing):
		return frappe.get_doc("Sales Invoice", existing)

	def update_item(source, target, source_parent):
		target.cost_center = None
		target.stock_qty = flt(source.qty) * flt(source.conversion_factor)

	def finish(source, target):
		target.customer = source.party_name
		target.flags.ignore_permissions = True
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	invoice = get_mapped_doc(
		"Quotation", quotation.name,
		{
			"Quotation": {"doctype": "Sales Invoice"},
			"Quotation Item": {
				"doctype": "Sales Invoice Item",
				"postprocess": update_item,
				"condition": lambda row: not row.is_alternative,
			},
			"Sales Taxes and Charges": {"doctype": "Sales Taxes and Charges",
			                            "reset_value": True},
		},
		None, finish, ignore_permissions=True)

	if invoice.meta.has_field(QUOTATION_FIELD):
		invoice.set(QUOTATION_FIELD, quotation.name)
	if ensure_sales_person():
		invoice.set("sales_team", [])
		invoice.append("sales_team", {"sales_person": SALES_PERSON,
		                              "allocated_percentage": 100})
	invoice.flags.ignore_permissions = True
	invoice.insert(ignore_permissions=True)

	# ERPNext 16 leaves nothing on the invoice pointing back at the quotation,
	# so the connection is written down both ways the moment it is known
	frappe.db.set_value("Quotation", quotation.name, "cr_invoice", invoice.name,
	                    update_modified=False)
	return invoice


# --------------------------------------------------------------- payment
def draft_payment(quotation, invoice, amount, reference, mode_of_payment):
	"""A draft Payment Entry for money the gateway has taken. Made once."""
	existing = frappe.db.get_value(
		"Payment Entry", {QUOTATION_FIELD: quotation.name, "docstatus": ["<", 2]},
		"name")
	if existing:
		return frappe.get_doc("Payment Entry", existing)

	from erpnext.accounts.party import get_party_account

	company = quotation.company
	entry = frappe.new_doc("Payment Entry")
	entry.update({
		"payment_type": "Receive",
		"company": company,
		"posting_date": nowdate(),
		"mode_of_payment": mode_of_payment,
		"party_type": "Customer",
		"party": quotation.party_name,
		"paid_amount": flt(amount),
		"received_amount": flt(amount),
		"reference_no": reference or quotation.name,
		"reference_date": nowdate(),
		"paid_from": get_party_account("Customer", quotation.party_name, company),
		"paid_to": _receiving_account(mode_of_payment, company),
		"remarks": "Website order %s%s, paid online (ClickPay %s)." % (
			quotation.name,
			" / invoice %s" % invoice.name if invoice else "",
			reference or "-"),
	})
	entry.set(QUOTATION_FIELD, quotation.name)
	if invoice:
		entry.set(INVOICE_FIELD, invoice.name)
	if ensure_sales_person():
		entry.set(PERSON_FIELD, SALES_PERSON)
	entry.flags.ignore_permissions = True
	# the receiving account may not be set up for the gateway yet; a draft
	# with that one field to fill is still the record that the money came in
	entry.flags.ignore_mandatory = True
	entry.insert(ignore_permissions=True)
	return entry


def _receiving_account(mode_of_payment, company):
	try:
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import \
			get_bank_cash_account

		account = (get_bank_cash_account(mode_of_payment, company) or {}).get("account")
		if account:
			return account
	except Exception:
		pass
	return frappe.get_cached_value("Company", company, "default_bank_account") \
		or frappe.get_cached_value("Company", company, "default_cash_account")


def link_payment(invoice, method=None):
	"""Sales Invoice on_submit: tie the waiting card payment to this invoice.

	The Payment Entry was made while the invoice was a draft, when ERPNext would
	not accept the reference. Now it will. The entry stays a draft - it is only
	made ready for the team to submit.
	"""
	name = frappe.db.get_value(
		"Payment Entry", {INVOICE_FIELD: invoice.name, "docstatus": 0}, "name")
	if not name:
		return
	entry = frappe.get_doc("Payment Entry", name)
	if any(r.reference_name == invoice.name for r in entry.get("references") or []):
		return
	entry.append("references", {
		"reference_doctype": "Sales Invoice",
		"reference_name": invoice.name,
		"total_amount": invoice.grand_total,
		"outstanding_amount": invoice.outstanding_amount,
		"allocated_amount": min(flt(entry.paid_amount), flt(invoice.outstanding_amount)),
	})
	entry.flags.ignore_permissions = True
	entry.flags.ignore_mandatory = True
	entry.save(ignore_permissions=True)
