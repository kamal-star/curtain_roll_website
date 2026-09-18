"""A small session cart for the ported Journal3 storefront.

The theme's buttons post to OpenCart's endpoints:

    checkout/cart/add | edit | remove      account/wishlist/add

and read three keys back: ``success``, ``total`` and ``redirect``. Returning
``{}`` (the first stub) silenced the error alert but left the buttons inert,
which is what "add to cart not working" was.

This keeps a cart in Frappe's cache, keyed by session, and answers in the shape
the theme expects so the buttons behave. It is deliberately small: there is no
checkout, no payment and no stock reservation. Prices come from the captured
catalogue, NOT from OpenCart's pricing rules, so a cart total here is the
starting price x quantity and ignores per-option surcharges.
"""

import json
import os

import frappe

TTL = 7 * 24 * 60 * 60
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


# ---------------------------------------------------------------- session bag
def _key():
	sid = getattr(frappe.session, "sid", None) or "guest"
	return "curtain_roll_cart:%s" % sid


def _load():
	data = frappe.cache().get_value(_key())
	if not isinstance(data, dict):
		data = {}
	data.setdefault("items", [])
	data.setdefault("wishlist", [])
	return data


def _save(bag):
	frappe.cache().set_value(_key(), bag, expires_in_sec=TTL)


# -------------------------------------------------------------------- totals
def _totals(bag):
	count = sum(int(i.get("qty") or 0) for i in bag["items"])
	amount = sum(float(i.get("price") or 0) * int(i.get("qty") or 0) for i in bag["items"])
	return count, amount


def _total_text(bag):
	count, amount = _totals(bag)
	return "%d item(s) - %s %s" % (count, CURRENCY, "{:,.2f}".format(amount))


# ------------------------------------------------------------------ handlers
def add(args, form):
	pid = str(form.get("product_id") or args.get("product_id") or "").strip()
	try:
		qty = max(1, int(float(form.get("quantity") or args.get("quantity") or 1)))
	except (TypeError, ValueError):
		qty = 1

	item = product(pid)
	if not item:
		return {"error": {"warning": "Product not available."}}

	# keep whatever option[...] fields the theme submitted, for the record
	options = {k: v for k, v in form.items() if k.startswith("option")}

	bag = _load()
	for line in bag["items"]:
		if line["product_id"] == pid and line.get("options") == options:
			line["qty"] += qty
			break
	else:
		bag["items"].append({
			"product_id": pid,
			"name": item["name"],
			"price": item["price"],
			"qty": qty,
			"options": options,
		})
	_save(bag)

	return {
		"success": "Added <b>%s</b> to your cart." % frappe.utils.escape_html(item["name"]),
		"total": _total_text(bag),
	}


def edit(args, form):
	pid = str(form.get("key") or form.get("product_id") or args.get("key") or "")
	try:
		qty = int(float(form.get("quantity") or 1))
	except (TypeError, ValueError):
		qty = 1
	bag = _load()
	for line in bag["items"]:
		if line["product_id"] == pid:
			line["qty"] = max(0, qty)
			break
	bag["items"] = [l for l in bag["items"] if l["qty"] > 0]
	_save(bag)
	return {"success": "Cart updated.", "total": _total_text(bag)}


def remove(args, form):
	pid = str(form.get("key") or form.get("product_id") or args.get("key") or "")
	bag = _load()
	bag["items"] = [l for l in bag["items"] if l["product_id"] != pid]
	_save(bag)
	return {"success": "Item removed.", "total": _total_text(bag)}


def wishlist_add(args, form):
	pid = str(form.get("product_id") or args.get("product_id") or "").strip()
	item = product(pid)
	if not item:
		return {"error": {"warning": "Product not available."}}
	bag = _load()
	if pid not in bag["wishlist"]:
		bag["wishlist"].append(pid)
	_save(bag)
	return {
		"success": "Added <b>%s</b> to your wish list." % frappe.utils.escape_html(item["name"]),
		"total": "%d" % len(bag["wishlist"]),
	}


def save_render(form):
	"""Handle script.php - the configurator's image upload.

	Clicking ADD TO CART does canvas.toDataURL() and POSTs it here as
	``imgBase64``. The original saves it and returns a filename, which the page
	drops into the "Captured image" option before the real cart call. Because
	this 404'd, the .done() callback never ran and the whole add-to-cart chain
	stopped - that was the actual "button not working".

	Returns the saved file's URL as plain text.
	"""
	import base64
	import re as _re

	# Frappe parses the request body into frappe.form_dict before page
	# renderers run, which leaves werkzeug's request.form with the KEY but an
	# empty value. So read form_dict first and only fall back to the request.
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

	# Last resort: parse the raw body ourselves. Frappe's request handling can
	# leave both form_dict and request.form with the key but no value for a
	# large urlencoded field, so go back to the bytes.
	if not raw:
		try:
			from urllib.parse import parse_qs
			body = frappe.local.request.get_data(as_text=True) or ""
			parsed = parse_qs(body, keep_blank_values=True)
			raw = (parsed.get("imgBase64") or [""])[0]
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


def info():
	"""Current cart, for rendering the header counter on page load."""
	bag = _load()
	count, amount = _totals(bag)
	return {"count": count, "amount": amount, "text": _total_text(bag),
	        "wishlist": len(bag["wishlist"]), "items": bag["items"]}
