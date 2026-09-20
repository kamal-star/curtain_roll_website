"""Everything the customer can change about themselves, from the storefront.

Kept apart from cart.py: that module is about a Quotation in progress, this one
is about the person. They meet only at get_party(), which maps the signed-in
user to the Customer their documents hang off.

Every entry point re-derives the user from the session. Nothing here takes a
user, a customer or a document name from the request and trusts it - a portal
where one customer can name another customer's address is the whole class of
bug worth designing out rather than checking for.
"""
import frappe
from frappe import _


def guest_redirect(target):
	"""Send a signed-out visitor to log in, and back to `target` afterwards.

	Lives here rather than in www/account.py so every page under /account can
	import it without the www package having to be importable.
	"""
	frappe.local.flags.redirect_location = "/login?redirect-to=%s" % target
	raise frappe.Redirect


def _user():
	if frappe.session.user == "Guest":
		frappe.throw(_("Please sign in."), frappe.PermissionError)
	return frappe.session.user


def _customer():
	from curtain_roll import cart
	return cart.get_party()


# ----------------------------------------------------------------- profile
@frappe.whitelist(methods=["POST"])
def update_profile(first_name=None, last_name=None, phone=None):
	"""Name and phone. Email is the login, so it is not editable here."""
	user = frappe.get_doc("User", _user())
	user.first_name = (first_name or "").strip() or user.first_name
	user.last_name = (last_name or "").strip()
	user.phone = (phone or "").strip()
	user.flags.ignore_permissions = True
	user.save(ignore_permissions=True)

	# the Customer is what appears on their documents, so keep it in step
	customer = _customer()
	if customer:
		full = " ".join(p for p in [user.first_name, user.last_name] if p).strip()
		if full and frappe.db.get_value("Customer", customer, "customer_name") != full:
			frappe.db.set_value("Customer", customer, "customer_name", full)

	frappe.db.commit()
	return {"ok": 1, "message": _("Your details have been saved.")}


@frappe.whitelist(methods=["POST"])
def change_password(old_password=None, new_password=None):
	from frappe.utils.password import check_password, update_password

	user = _user()
	if not new_password or len(new_password) < 6:
		frappe.throw(_("Please choose a password of at least 6 characters."))

	try:
		check_password(user, old_password or "")
	except frappe.AuthenticationError:
		frappe.throw(_("Your current password is not correct."))

	update_password(user, new_password)
	frappe.db.commit()
	return {"ok": 1, "message": _("Your password has been changed.")}


# ----------------------------------------------------------------- addresses
ADDRESS_FIELDS = ("address_title", "address_line1", "address_line2", "city",
                  "state", "pincode", "country", "phone")


def my_addresses():
	customer = _customer()
	if not customer:
		return []
	names = frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer",
		         "link_name": customer},
		pluck="parent")
	if not names:
		return []
	return frappe.get_all(
		"Address", filters={"name": ["in", names]},
		fields=["name", "is_primary_address"] + list(ADDRESS_FIELDS),
		order_by="is_primary_address desc, modified desc")


def _owned(name):
	"""The address, but only if it belongs to the signed-in customer."""
	if not name:
		return None
	mine = {a["name"] for a in my_addresses()}
	if name not in mine:
		frappe.throw(_("That address is not yours."), frappe.PermissionError)
	return frappe.get_doc("Address", name)


@frappe.whitelist(methods=["POST"])
def save_address(name=None, **values):
	customer = _customer()
	if not customer:
		frappe.throw(_("No customer record yet - add something to your cart first."))

	doc = _owned(name) if name else frappe.new_doc("Address")
	for field in ADDRESS_FIELDS:
		if field in values:
			doc.set(field, (values.get(field) or "").strip())

	if not doc.address_title:
		doc.address_title = frappe.db.get_value("Customer", customer, "customer_name")
	if not doc.address_line1:
		frappe.throw(_("Please give at least a street address."))
	doc.address_type = doc.address_type or "Shipping"

	if not name:
		doc.append("links", {"link_doctype": "Customer", "link_name": customer})

	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": 1, "name": doc.name, "message": _("Address saved.")}


@frappe.whitelist(methods=["POST"])
def delete_address(name):
	doc = _owned(name)
	frappe.delete_doc("Address", doc.name, ignore_permissions=True, force=True)
	frappe.db.commit()
	return {"ok": 1, "message": _("Address removed.")}


# ----------------------------------------------------------------- wishlist
@frappe.whitelist(methods=["POST"])
def wishlist_remove(product_key):
	from curtain_roll import cart

	_user()
	left = cart.wishlist_remove(product_key)
	return {"ok": 1, "total": left, "message": _("Removed from your wish list.")}


# ----------------------------------------------------------------- orders
def my_orders():
	"""Everything the customer has placed, newest first.

	A storefront order is a Quotation with order_type "Shopping Cart" - that is
	what the cart builds - and the team turns it into a Sales Order. Both are
	listed, because from the customer's side they are one history: the quote is
	the order they placed, the Sales Order is it being fulfilled.
	"""
	customer = _customer()
	if not customer:
		return []

	rows = []
	for q in frappe.get_all(
			"Quotation",
			filters={"party_name": customer, "docstatus": ["!=", 2]},
			fields=["name", "transaction_date", "grand_total", "currency",
			        "docstatus", "status"],
			order_by="transaction_date desc, creation desc"):
		rows.append({
			"name": q.name,
			"date": q.transaction_date,
			"total": q.grand_total,
			"currency": q.currency,
			"stage": _("Basket") if q.docstatus == 0 else (q.status or _("Placed")),
			"open": q.docstatus == 0,
		})

	for so in frappe.get_all(
			"Sales Order",
			filters={"customer": customer, "docstatus": ["!=", 2]},
			fields=["name", "transaction_date", "grand_total", "currency", "status"],
			order_by="transaction_date desc, creation desc"):
		rows.append({
			"name": so.name,
			"date": so.transaction_date,
			"total": so.grand_total,
			"currency": so.currency,
			"stage": so.status or _("Confirmed"),
			"open": False,
		})

	rows.sort(key=lambda r: (r["date"] or ""), reverse=True)
	return rows


def order_lines(name, doctype="Quotation"):
	"""The items on one document, if it is the customer's own."""
	customer = _customer()
	owner_field = "party_name" if doctype == "Quotation" else "customer"
	if not customer or frappe.db.get_value(doctype, name, owner_field) != customer:
		frappe.throw(_("That order is not yours."), frappe.PermissionError)
	return frappe.get_all(
		doctype + " Item", filters={"parent": name},
		fields=["item_name", "description", "qty", "rate", "amount"],
		order_by="idx")
