"""Cart for the ported Journal3 storefront, backed by a draft ERPNext Quotation.

Flow:
  * a guest who clicks Add to cart / Wishlist is sent to login (the theme
    follows ``json['redirect']``)
  * a logged-in user gets a Customer (created on first use) and a draft
    Quotation with ``order_type = "Shopping Cart"``; items are appended there
  * the header counter reads that Quotation's totals

So the cart is real ERP data, not a session blob: it shows up in the Selling
workspace and can be submitted into a Sales Order by the team.

Known limit: rates come from the captured catalogue (the product's starting
price). OpenCart's per-option surcharges are server-side rules we do not have,
so a total here will not match the live site once options are priced.
"""

import json
import os
from urllib.parse import quote

import frappe
from frappe.utils import nowdate

CURRENCY = "SR"
_CATALOG = None


# ------------------------------------------------------------------ catalogue
def catalog():
	global _CATALOG
	if _CATALOG is None:
		path = os.path.join(frappe.get_app_path("curtain_roll"), "data", "catalog_ids.json")
		try:
			with open(path, encoding="utf-8") as f:
				_CATALOG = json.load(f)
		except Exception:
			_CATALOG = {}
	return _CATALOG


def product(product_id):
	return catalog().get(str(product_id))


def item_code_for(entry):
	return "CR-" + (entry.get("key") or "").upper()


# ---------------------------------------------------------------------- auth
def is_guest():
	return frappe.session.user in (None, "", "Guest")


def login_redirect(args=None):
	"""Send the visitor to Frappe's login, returning to the page they were on."""
	back = "/"
	try:
		ref = frappe.local.request.headers.get("Referer") or ""
		if ref:
			from urllib.parse import urlparse
			p = urlparse(ref)
			back = p.path or "/"
	except Exception:
		pass
	return {
		"redirect": "/login?redirect-to=%s" % quote(back, safe="/"),
		"success": "Please sign in to continue.",
	}


# -------------------------------------------------------------------- party
def get_party():
	"""Customer for the current user, created on first use."""
	user = frappe.session.user

	contact = frappe.db.get_value("Contact", {"user": user}, "name")
	if contact:
		linked = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
			"link_name",
		)
		if linked and frappe.db.exists("Customer", linked):
			return linked

	full_name = frappe.db.get_value("User", user, "full_name") or user
	existing = frappe.db.get_value("Customer", {"customer_name": full_name}, "name")
	if existing:
		return existing

	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": full_name,
		"customer_type": "Individual",
	})
	customer.flags.ignore_mandatory = True
	customer.insert(ignore_permissions=True)

	# link a Contact so the same user maps back to this Customer next time
	try:
		c = frappe.get_doc({
			"doctype": "Contact",
			"first_name": full_name,
			"user": user,
			"email_id": user if "@" in user else None,
		})
		c.append("links", {"link_doctype": "Customer", "link_name": customer.name})
		c.flags.ignore_mandatory = True
		c.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="curtain_roll contact link")

	return customer.name


def _defaults():
	company = frappe.defaults.get_global_default("company") \
		or frappe.db.get_value("Company", {}, "name")
	currency = frappe.db.get_value("Company", company, "default_currency") or "SAR"
	price_list = frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name") \
		or "Standard Selling"
	return company, currency, price_list


# ---------------------------------------------------------------- quotation
def get_cart_quotation(create=False):
	party = get_party()
	name = frappe.db.get_value("Quotation", {
		"quotation_to": "Customer",
		"party_name": party,
		"docstatus": 0,
		"order_type": "Shopping Cart",
	}, "name")
	if name:
		return frappe.get_doc("Quotation", name)
	if not create:
		return None

	company, currency, price_list = _defaults()
	quotation = frappe.get_doc({
		"doctype": "Quotation",
		"quotation_to": "Customer",
		"party_name": party,
		"order_type": "Shopping Cart",
		"transaction_date": nowdate(),
		"company": company,
		"currency": currency,
		"selling_price_list": price_list,
	})
	quotation.flags.ignore_permissions = True
	return quotation


def _total_text(quotation):
	if not quotation or not quotation.get("items"):
		return "0 item(s) - %s 0.00" % CURRENCY
	count = int(sum(float(i.qty or 0) for i in quotation.items))
	amount = float(quotation.get("total") or 0)
	return "%d item(s) - %s %s" % (count, CURRENCY, "{:,.2f}".format(amount))


def _save(quotation):
	quotation.flags.ignore_permissions = True
	quotation.flags.ignore_mandatory = True
	quotation.save(ignore_permissions=True)
	frappe.db.commit()


# ------------------------------------------------------------------ handlers
def add(args, form):
	if is_guest():
		return login_redirect(args)

	pid = str(form.get("product_id") or args.get("product_id") or "").strip()
	try:
		qty = max(1, int(float(form.get("quantity") or args.get("quantity") or 1)))
	except (TypeError, ValueError):
		qty = 1

	entry = product(pid)
	if not entry:
		return {"error": {"warning": "Product not available."}}

	code = item_code_for(entry)
	if not frappe.db.exists("Item", code):
		return {"error": {"warning": "Product not set up in ERPNext yet."}}

	quotation = get_cart_quotation(create=True)
	for row in quotation.get("items", []):
		if row.item_code == code:
			row.qty = float(row.qty or 0) + qty
			break
	else:
		quotation.append("items", {
			"item_code": code,
			"qty": qty,
			"rate": entry.get("price") or 0,
		})

	try:
		_save(quotation)
	except Exception:
		frappe.log_error(title="curtain_roll cart add", message=frappe.get_traceback())
		return {"error": {"warning": "Could not add to cart."}}

	return {
		"success": "Added <b>%s</b> to your cart." % frappe.utils.escape_html(entry["name"]),
		"total": _total_text(quotation),
	}


def edit(args, form):
	if is_guest():
		return login_redirect(args)
	quotation = get_cart_quotation()
	if not quotation:
		return {"total": _total_text(None)}
	pid = str(form.get("key") or form.get("product_id") or "")
	entry = product(pid)
	code = item_code_for(entry) if entry else pid
	try:
		qty = int(float(form.get("quantity") or 1))
	except (TypeError, ValueError):
		qty = 1
	quotation.set("items", [r for r in quotation.items
	                        if not (r.item_code == code and qty <= 0)])
	for row in quotation.items:
		if row.item_code == code:
			row.qty = qty
	_save(quotation)
	return {"success": "Cart updated.", "total": _total_text(quotation)}


def remove(args, form):
	if is_guest():
		return login_redirect(args)
	quotation = get_cart_quotation()
	if not quotation:
		return {"total": _total_text(None)}
	pid = str(form.get("key") or form.get("product_id") or "")
	entry = product(pid)
	code = item_code_for(entry) if entry else pid
	quotation.set("items", [r for r in quotation.items if r.item_code != code])
	_save(quotation)
	return {"success": "Item removed.", "total": _total_text(quotation)}


def wishlist_add(args, form):
	if is_guest():
		return login_redirect(args)
	pid = str(form.get("product_id") or args.get("product_id") or "").strip()
	entry = product(pid)
	if not entry:
		return {"error": {"warning": "Product not available."}}
	key = "curtain_roll_wishlist:%s" % frappe.session.user
	items = frappe.cache().get_value(key) or []
	if pid not in items:
		items.append(pid)
	frappe.cache().set_value(key, items)
	return {
		"success": "Added <b>%s</b> to your wish list." % frappe.utils.escape_html(entry["name"]),
		"total": "%d" % len(items),
	}


def info():
	"""Cart summary for the header / cart page."""
	if is_guest():
		return {"count": 0, "text": _total_text(None), "items": [], "guest": True}
	quotation = get_cart_quotation()
	items = []
	if quotation:
		for row in quotation.items:
			items.append({
				"item_code": row.item_code,
				"name": row.item_name,
				"qty": row.qty,
				"rate": row.rate,
				"amount": row.amount,
			})
	return {
		"count": len(items),
		"text": _total_text(quotation),
		"quotation": quotation.name if quotation and quotation.get("name") else None,
		"items": items,
		"guest": False,
	}


# ------------------------------------------------- configurator image upload
def save_render(form):
	"""script.php - the configurator POSTs canvas.toDataURL() here as imgBase64.

	The page chains the real cart call inside this request's .done(), so this
	must always answer 200 or add-to-cart silently dies.
	"""
	import base64
	import re as _re

	raw = ""
	for source in (getattr(frappe.local, "form_dict", None), form):
		if not source:
			continue
		try:
			value = source.get("imgBase64")
		except Exception:
			value = None
		if value:
			raw = value
			break

	if not raw:
		try:
			from urllib.parse import parse_qs
			body = frappe.local.request.get_data(as_text=True) or ""
			raw = (parse_qs(body, keep_blank_values=True).get("imgBase64") or [""])[0]
		except Exception:
			raw = ""

	raw = (raw or "").strip()
	m = _re.match(r"^data:image/(png|jpe?g|webp);base64,(.+)$", raw, _re.S)
	if not m:
		return ""

	ext = "jpg" if m.group(1) in ("jpeg", "jpg") else m.group(1)
	try:
		content = base64.b64decode(m.group(2))
	except Exception:
		return ""
	if not content or len(content) > 8 * 1024 * 1024:
		return ""

	doc = frappe.get_doc({
		"doctype": "File",
		"file_name": "curtain-design-%s.%s" % (frappe.generate_hash(length=10), ext),
		"is_private": 0,
		"content": content,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.file_url
