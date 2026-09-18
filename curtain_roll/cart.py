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


_PRODUCTS = None


def _products():
	"""Full product definitions (option groups, swatch codes, labels)."""
	global _PRODUCTS
	if _PRODUCTS is None:
		path = os.path.join(frappe.get_app_path("curtain_roll"), "data", "products.json")
		try:
			with open(path, encoding="utf-8") as f:
				_PRODUCTS = {p["key"]: p for p in json.load(f)}
		except Exception:
			_PRODUCTS = {}
	return _PRODUCTS


def describe_options(product_key, form):
	"""Turn the submitted option[...] fields into readable lines.

	The storefront posts option[371]=664 (a swatch), option[375][width]=120 and
	so on. Without translating them the quotation would carry meaningless ids,
	so map each back to its group label and the swatch code the customer saw
	(e.g. "Material: ss7003", "Control type: Motor").

	Returns (lines, captured_image_url).
	"""
	spec = _products().get(product_key) or {}
	lines = []
	captured = ""

	def submitted(key):
		try:
			return form.get(key)
		except Exception:
			return None

	for group in spec.get("option_groups") or []:
		gid = group.get("id")
		label = (group.get("label") or "").strip() or ("Option %s" % gid)
		kind = group.get("kind")

		if kind == "size":
			width = submitted("option[%s][width]" % gid)
			height = submitted("option[%s][height]" % gid)
			if width or height:
				lines.append("%s: %s x %s cm" % (label, width or "?", height or "?"))

		elif kind == "capture":
			captured = submitted("option[%s]" % gid) or ""

		else:  # swatch / choice
			value = submitted("option[%s]" % gid)
			if not value:
				continue
			shown = value
			for opt in (group.get("options") or []) + (group.get("choices") or []):
				if str(opt.get("value")) == str(value):
					shown = opt.get("code") or opt.get("label") or value
					break
			lines.append("%s: %s" % (label, shown))

	# a capture field can also live outside the groups
	if not captured and spec.get("capture_option_id"):
		captured = submitted("option[%s]" % spec["capture_option_id"]) or ""

	return lines, captured


def attach_render(quotation_name, file_url):
	"""Link the configurator render (saved by script.php) to the quotation."""
	if not file_url or not quotation_name:
		return None
	try:
		existing = frappe.db.get_value(
			"File",
			{"file_url": file_url, "attached_to_doctype": "Quotation",
			 "attached_to_name": quotation_name},
			"name",
		)
		if existing:
			return existing
		# script.php saved the render unattached; adopt that row rather than
		# creating a second File pointing at the same bytes.
		src = frappe.db.get_value(
			"File",
			{"file_url": file_url, "attached_to_name": ["in", ["", None]]},
			"name",
		)
		if src:
			doc = frappe.get_doc("File", src)
			doc.attached_to_doctype = "Quotation"
			doc.attached_to_name = quotation_name
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
			return doc.name

		if not frappe.db.exists("File", {"file_url": file_url}):
			return None

		doc = frappe.get_doc({
			"doctype": "File",
			"file_url": file_url,
			"file_name": file_url.split("/")[-1],
			"attached_to_doctype": "Quotation",
			"attached_to_name": quotation_name,
			"is_private": 0,
		})
		doc.flags.ignore_duplicate_entry_error = True
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(title="curtain_roll attach_render")
		return None


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

	lines, captured = describe_options(entry.get("key"), form)
	spec = "\n".join(lines)

	quotation = get_cart_quotation(create=True)
	# Merge only when the SAME item was configured the SAME way - otherwise a
	# white blind and a brown one would collapse into a single line.
	for row in quotation.get("items", []):
		if row.item_code == code and (row.get("description") or "") == spec:
			row.qty = float(row.qty or 0) + qty
			break
	else:
		quotation.append("items", {
			"item_code": code,
			"qty": qty,
			"rate": entry.get("price") or 0,
			"description": spec or entry["name"],
		})

	try:
		_save(quotation)
	except Exception:
		frappe.log_error(title="curtain_roll cart add", message=frappe.get_traceback())
		return {"error": {"warning": "Could not add to cart."}}

	if captured:
		attach_render(quotation.name, captured)

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


def set_qty(item_code, qty):
	"""Update one line on the cart quotation; qty <= 0 removes it."""
	if is_guest():
		return {"error": "login"}
	quotation = get_cart_quotation()
	if not quotation:
		return {"ok": True, "total": _total_text(None)}
	try:
		qty = float(qty)
	except (TypeError, ValueError):
		qty = 0
	kept = []
	for row in quotation.items:
		if row.item_code == item_code:
			if qty <= 0:
				continue
			row.qty = qty
		kept.append(row)
	quotation.set("items", kept)
	if not quotation.items:
		# an empty quotation cannot be saved; drop it entirely
		name = quotation.get("name")
		if name:
			frappe.delete_doc("Quotation", name, force=True, ignore_permissions=True)
			frappe.db.commit()
		return {"ok": True, "total": _total_text(None), "empty": True}
	_save(quotation)
	return {"ok": True, "total": _total_text(quotation)}


def place_order():
	"""Submit the draft cart quotation so the team can act on it."""
	if is_guest():
		return {"error": "login"}
	quotation = get_cart_quotation()
	if not quotation or not quotation.get("items"):
		return {"error": "empty"}
	try:
		quotation.flags.ignore_permissions = True
		quotation.submit()
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="curtain_roll place_order", message=frappe.get_traceback())
		return {"error": "failed"}
	return {"ok": True, "quotation": quotation.name}


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
				"spec": (row.get("description") or "").strip(),
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
