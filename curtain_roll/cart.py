"""Cart for the ported Journal3 storefront, backed by a draft ERPNext Quotation.

Flow:
  * a guest who clicks Add to cart / Wishlist is sent to login (the theme
    follows ``json['redirect']``)
  * a logged-in user gets a Customer (created on first use) and a draft
    Quotation with ``order_type = "Shopping Cart"``; items are appended there
  * the header counter reads that Quotation's totals

So the cart is real ERP data, not a session blob: it shows up in the Selling
workspace and can be submitted into a Sales Order by the team.

Rates come from the **Curtain Product** record for the type (see pricing.py),
so the colour, the measured size and every option the customer picked are
priced by the team's own figures rather than by a flat starting price.
"""

import json
import os
from urllib.parse import quote

import frappe
from frappe.utils import nowdate

from curtain_roll import pricing

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


def describe_options(product_key, form, labels=None):
	"""Turn the submitted option[...] fields into readable lines.

	The storefront posts option[371]=664 (a swatch), option[375][width]=120 and
	so on. Without translating them the quotation would carry meaningless ids,
	so map each back to its group label and the swatch code the customer saw
	(e.g. "Material: ss7003", "Control type: Motor").

	``labels`` is {group id: {value: label}} from pricing.label_map, which also
	covers colours added in the desk - those are not in products.json, so
	without it they would land on the quotation as a raw id.

	Returns (lines, captured_image_url).
	"""
	labels = labels or {}
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
			shown = (labels.get(str(gid)) or {}).get(str(value))
			if not shown:
				for opt in (group.get("options") or []) + (group.get("choices") or []):
					if str(opt.get("value")) == str(value):
						shown = opt.get("code") or opt.get("label") or value
						break
			shown = shown or value
			lines.append("%s: %s" % (label, shown))

	# a capture field can also live outside the groups
	if not captured and spec.get("capture_option_id"):
		captured = submitted("option[%s]" % spec["capture_option_id"]) or ""

	# the choices under Manual / Motorized - "Handle Type: Metal" - which live
	# in the Curtain Product record rather than in the captured page
	priced = pricing.get_spec(product_key)
	if priced:
		for key, rows in pricing.active_sub_groups(priced, submitted).items():
			chosen = str(submitted("cr_sub[%s]" % key) or "")
			entry = next((r for r in rows if r["id"] == chosen), None)
			if entry:
				lines.append("%s: %s" % (entry["group"], entry["label"]))

	# where the fitters are going, when installation was chosen
	city = str(submitted("cr_city") or "").strip()
	ship_city = str(submitted("cr_ship_city") or "").strip()
	if priced and pricing._install_choice(priced):
		gid, value = pricing._install_choice(priced)
		installing = str(submitted("option[%s]" % gid) or "") == value
		if city and installing:
			lines.append("Installation city: %s" % city)
		elif ship_city and not installing:
			lines.append("Delivery by Aramex to: %s" % ship_city)

	# the customer's own picture, for a printed blind - named so the team can
	# match the line to the file attached to the order
	token = submitted("cr_print")
	if token:
		from curtain_roll import print_upload

		shown = print_upload.original_name(token)
		if shown:
			lines.append("Picture to print: %s" % shown)

	return lines, captured


def attach_render(quotation_name, file_url, doctype="Quotation"):
	"""Link the configurator render (saved by script.php) to the cart.

	``doctype`` because a cart is not always a Quotation: someone shopping
	without an account has a Curtain Guest Cart, and their render has to hang
	off that until they check out and it moves across with the lines.
	"""
	if not file_url or not quotation_name:
		return None
	try:
		existing = frappe.db.get_value(
			"File",
			{"file_url": file_url, "attached_to_doctype": doctype,
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
			doc.attached_to_doctype = doctype
			doc.attached_to_name = quotation_name
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
			# MUST commit: this runs after _save()'s commit, and the page
			# renderer path does not auto-commit, so without this the link is
			# rolled back and the render is orphaned again.
			frappe.db.commit()
			return doc.name

		if not frappe.db.exists("File", {"file_url": file_url}):
			return None

		doc = frappe.get_doc({
			"doctype": "File",
			"file_url": file_url,
			"file_name": file_url.split("/")[-1],
			"attached_to_doctype": doctype,
			"attached_to_name": quotation_name,
			"is_private": 0,
		})
		doc.flags.ignore_duplicate_entry_error = True
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name
	except Exception:
		frappe.log_error(title="curtain_roll attach_render")
		return None


def move_attachments(from_doctype, from_name, quotation_name):
	"""Re-hang every file from a guest cart on the quotation it became.

	In place, on the same File row. attach_render - which this used to go
	through - makes a NEW File row for a file that is already attached
	elsewhere, and makes it public: harmless for a render of the configurator,
	not for a customer's own photo sent in to be printed, which is private and
	must stay so.
	"""
	for name in frappe.get_all("File", filters={"attached_to_doctype": from_doctype,
	                                            "attached_to_name": from_name},
	                           pluck="name"):
		frappe.db.set_value("File", name, {"attached_to_doctype": "Quotation",
		                                   "attached_to_name": quotation_name},
		                    update_modified=False)


# ------------------------------------------------- configuration on the line
CONFIG_FIELD = "curtain_config"


def capture_config(entry, form):
	"""Keep what the customer chose, so the line can be priced again later.

	Installation is banded by the total curtains on the ORDER, so adding a
	second curtain changes the price of the first. That is only possible if
	each line remembers its own configuration - the description is prose and
	cannot be parsed back.
	"""
	options = {}
	try:
		for key, value in form.items():
			# cr_sub[...] too: the handle, side and motor are priced like any
			# option, and a line re-priced later without them would silently
			# drop the motor from the bill
			if str(key).startswith(("option[", "cr_sub[", "cr_print", "cr_city",
			                        "cr_ship_city")):
				options[str(key)] = value
	except Exception:
		pass
	return json.dumps({"product_key": entry.get("key"), "options": options})


def read_config(row):
	raw = row.get(CONFIG_FIELD)
	if not raw:
		return None
	try:
		cfg = json.loads(raw)
	except Exception:
		return None
	return cfg if cfg.get("product_key") else None


def line_description(product_key, options, priced):
	lines, _captured = describe_options(product_key, options,
	                                    pricing.label_map(product_key))
	if priced and priced.get("ok"):
		lines = lines + ["", "Price:"] + pricing.breakdown_lines(priced)
	return "\n".join(lines)


def curtain_qty_in_cart():
	"""How many curtains are already on this visitor's draft order."""
	basket = get_basket()
	if not basket:
		return 0
	return sum(int(float(row.qty or 0)) for row in basket.get("items", [])
	           if read_config(row))


def reprice(quotation):
	"""Re-price every curtain line against the whole order's curtain count.

	Takes a Quotation or a Curtain Guest Cart without caring which. The guest
	cart's child table carries the same fieldnames on purpose, so the pricing
	rules written for one apply unchanged to the other - a customer's total must
	not depend on whether they had signed in when they built the basket.
	"""
	configs = [read_config(row) for row in quotation.get("items", [])]
	total = sum(int(float(row.qty or 0))
	            for row, cfg in zip(quotation.get("items", []), configs) if cfg)
	if not total:
		return

	for row, cfg in zip(quotation.get("items", []), configs):
		if not cfg:
			continue
		priced = pricing.calculate(cfg["product_key"], cfg["options"],
		                           qty=row.qty, order_qty=total)
		if not priced.get("ok"):
			continue
		row.rate = priced["unit_rate"]
		row.description = line_description(cfg["product_key"], cfg["options"], priced)


# ---------------------------------------------------------------------- auth
def is_guest():
	return frappe.session.user in (None, "", "Guest")


def login_redirect(args=None):
	"""Send the visitor to Frappe's login, returning to the page they were on.

	Still used by the wishlist, which genuinely needs an account - a list saved
	for later has to belong to someone. The cart does not, and no longer asks.
	"""
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


# ------------------------------------------------------------- guest basket
GUEST_DOCTYPE = "Curtain Guest Cart"

# A Quotation in one of these is an order, not a basket, though it is still a
# draft: the website submits nothing (orders.py). Mirrors clickpay.PAID and
# PENDING_REVIEW and checkout.AWAITING_TRANSFER, spelt out here because both
# of those modules import this one.
PLACED_STATUSES = ("Paid", "Pending", "Awaiting Transfer")
CART_COOKIE = "cr_cart"
COOKIE_AGE = 30 * 24 * 60 * 60


def _cart_token():
	"""The cart token this browser is carrying, if any."""
	try:
		return (frappe.request.cookies.get(CART_COOKIE) or "").strip()
	except Exception:
		return ""


def _remember_cart(token):
	"""Hand the browser its cart token.

	httponly because no script on the page has any use for it, and it is the
	only thing standing between a stranger and someone else's basket. SameSite
	Lax so the cookie survives the return trip from the payment gateway, which
	arrives as a cross-site POST.
	"""
	manager = getattr(frappe.local, "cookie_manager", None)
	if not manager:
		return
	manager.set_cookie(CART_COOKIE, token, max_age=COOKIE_AGE,
	                   httponly=True, samesite="Lax")


def _forget_cart():
	manager = getattr(frappe.local, "cookie_manager", None)
	if manager:
		manager.set_cookie(CART_COOKIE, "", expires="Thu, 01 Jan 1970 00:00:00 GMT")


def guest_cart(create=False):
	"""This browser's cart, made on first use.

	A row is only created when something is actually added, so merely reading
	the site leaves nothing behind.
	"""
	token = _cart_token()
	if token and frappe.db.exists(GUEST_DOCTYPE, token):
		return frappe.get_doc(GUEST_DOCTYPE, token)
	if not create:
		return None

	doc = frappe.new_doc(GUEST_DOCTYPE)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	_remember_cart(doc.name)
	return doc


def get_basket(create=False):
	"""The visitor's cart, whoever they are.

	A Quotation when there is an account behind it, a Curtain Guest Cart when
	there is not. Everything downstream - pricing, totals, the cart page - works
	on whichever it is handed, because the two carry the same fieldnames.

	This is the whole of what "shop without signing in" means in this codebase:
	one function that stops asking who you are before letting you buy something.
	"""
	if is_guest():
		return guest_cart(create=create)
	return get_cart_quotation(create=create)


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
def open_basket_name(filters):
	"""The newest draft Quotation matching `filters` that is still a basket.

	Placed orders stay drafts for the team to submit (orders.py), so "draft"
	alone no longer means "still being filled"; the payment status says it.

	Decided here in Python, not with a "not in" filter: a basket that was never
	paid for has no status at all, and SQL's NOT IN is never true for NULL -
	frappe.db.get_value passes it straight through, so every basket vanished
	and each Add to Cart started a new one.
	"""
	rows = frappe.get_all(
		"Quotation", filters=dict(filters, docstatus=0),
		fields=["name", "clickpay_status"], order_by="modified desc")
	for row in rows:
		if (row.clickpay_status or "") not in PLACED_STATUSES:
			return row.name
	return None


def get_cart_quotation(create=False):
	party = get_party()
	name = open_basket_name({
		"quotation_to": "Customer",
		"party_name": party,
		"order_type": "Shopping Cart",
	})
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


def summary(basket):
	"""Subtotal, discount, VAT and total for a basket of either kind."""
	from curtain_roll import totals

	if not basket or not basket.get("items"):
		return totals.summarise([], None)
	return totals.summarise(basket.get("items"), basket.get("coupon_code"))


def _total_text(quotation):
	"""The header counter's line.

	Shows what the customer would pay, tax and discount included, rather than
	the sum of the lines - a header that says one number and a checkout that
	says another is how people decide a shop is not to be trusted.
	"""
	symbol = pricing.currency_symbol()
	if not quotation or not quotation.get("items"):
		return "0 item(s) - %s 0.00" % symbol
	count = int(sum(float(i.qty or 0) for i in quotation.get("items")))
	amount = summary(quotation)["total"]
	return "%d item(s) - %s %s" % (count, symbol, "{:,.2f}".format(amount))


def _save(quotation):
	"""Write the cart, as someone allowed to read a catalogue.

	Saving a Quotation makes ERPNext fetch details for every line, and that
	fetch calls Item.check_permission() - which ignores our ignore_permissions
	flag, because it is a check on the Item, not on the document being saved. A
	storefront customer is a Website User with no read permission on Item, by
	design, so the save fails with a bare PermissionError and the page says
	"Could not add to cart" with nothing to explain it.

	Nothing is trusted to the customer by doing this. Every rate on every line
	was computed by pricing.calculate from the team's own records before we got
	here; the elevated user is only so that ERPNext is allowed to look up the
	item it is being told about.
	"""
	from curtain_roll.utils import as_system_user

	quotation.flags.ignore_permissions = True
	quotation.flags.ignore_mandatory = True
	with as_system_user():
		quotation.save(ignore_permissions=True)
	frappe.db.commit()


# ------------------------------------------------------------------ handlers
def add(args, form):
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

	lines, captured = describe_options(entry.get("key"), form,
									  pricing.label_map(entry.get("key")))

	# Price it here, from the back-office record - never from anything the
	# browser posted. This also rejects a colour the team has withdrawn.
	priced = pricing.calculate(entry.get("key"), form, qty)
	if priced.get("errors"):
		return {"error": {"option": priced["errors"]}}
	if priced.get("ok"):
		rate = priced["unit_rate"]
		lines = lines + ["", "Price:"] + pricing.breakdown_lines(priced)
	else:
		# not priced in the desk yet - fall back to the catalogue price
		rate = entry.get("price") or 0

	spec = "\n".join(lines)

	quotation = get_basket(create=True)
	# Merge only when the SAME item was configured the SAME way - otherwise a
	# white blind and a brown one would collapse into a single line.
	for row in quotation.get("items", []):
		if row.item_code == code and (row.get("description") or "") == spec:
			row.qty = float(row.qty or 0) + qty
			break
	else:
		row = quotation.append("items", {
			"item_code": code,
			"qty": qty,
			"rate": rate,
			"description": spec or entry["name"],
		})
		# A Quotation Item fetches its name from the linked Item; a guest cart
		# row has no link to fetch through, so it is given one. Setting it on
		# both would quietly override whatever the team named the Item.
		if quotation.doctype == GUEST_DOCTYPE:
			row.set("item_name", entry.get("name") or code)
		row.set(CONFIG_FIELD, capture_config(entry, form))

	# installation is banded by the order total, so adding this curtain can
	# change what the ones already in the cart cost
	reprice(quotation)

	try:
		_save(quotation)
	except Exception:
		frappe.log_error(title="curtain_roll cart add", message=frappe.get_traceback())
		return {"error": {"warning": "Could not add to cart."}}

	if captured:
		attach_render(quotation.name, captured, quotation.doctype)

	print_token = form.get("cr_print") or args.get("cr_print")
	if print_token:
		from curtain_roll import print_upload

		if print_upload.attach(print_token, quotation.doctype, quotation.name):
			frappe.db.commit()

	return {
		"success": "Added <b>%s</b> to your cart." % frappe.utils.escape_html(entry["name"]),
		"total": _total_text(quotation),
	}


def edit(args, form):
	quotation = get_basket()
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
	quotation = get_basket()
	if not quotation:
		return {"total": _total_text(None)}
	pid = str(form.get("key") or form.get("product_id") or "")
	entry = product(pid)
	code = item_code_for(entry) if entry else pid
	quotation.set("items", [r for r in quotation.items if r.item_code != code])
	reprice(quotation)
	_save(quotation)
	return {"success": "Item removed.", "total": _total_text(quotation)}


WISHLIST = "Curtain Wishlist Item"


def wishlist_keys(user=None):
	"""Product keys this user has saved, newest first."""
	return frappe.get_all(
		WISHLIST, filters={"user": user or frappe.session.user},
		pluck="product_key", order_by="creation desc")


def wishlist_items(user=None):
	"""The saved products themselves, skipping any that have since gone."""
	# catalog(), not _products(): _products() is keyed BY product key and holds
	# the option definitions, so iterating it yields the keys as bare strings.
	# catalog() is keyed by catalogue id, and its values carry the name, price
	# and route that a listing actually needs.
	by_key = {e["key"]: e for e in catalog().values() if e.get("key")}
	out = []
	for key in wishlist_keys(user):
		entry = by_key.get(key)
		if entry:
			out.append(entry)
	return out


def wishlist_add(args, form):
	if is_guest():
		return login_redirect(args)
	pid = str(form.get("product_id") or args.get("product_id") or "").strip()
	entry = product(pid)
	if not entry:
		return {"error": {"warning": "Product not available."}}

	# Stored, not cached. This used to live in frappe.cache(), which tested
	# fine and silently emptied every customer's list on each clear-cache,
	# migrate and deploy.
	if not frappe.db.exists(WISHLIST, {"user": frappe.session.user,
	                                   "product_key": entry["key"]}):
		frappe.get_doc({
			"doctype": WISHLIST,
			"user": frappe.session.user,
			"product_key": entry["key"],
		}).insert(ignore_permissions=True)
		frappe.db.commit()

	return {
		"success": "Added <b>%s</b> to your wish list." % frappe.utils.escape_html(entry["name"]),
		"total": "%d" % len(wishlist_keys()),
	}


def wishlist_remove(product_key):
	"""Drop one saved product. Safe to call for something already gone."""
	name = frappe.db.get_value(WISHLIST, {"user": frappe.session.user,
	                                      "product_key": product_key})
	if name:
		frappe.delete_doc(WISHLIST, name, ignore_permissions=True, force=True)
		frappe.db.commit()
	return len(wishlist_keys())


def set_qty(item_code, qty, row_name=None):
	"""Change one cart line; qty <= 0 removes it.

	Keyed on the LINE, not the item: the same blind configured two ways is two
	lines sharing one item code, and matching on the code changed both at once.
	``item_code`` is still accepted so an older page keeps working.
	"""
	quotation = get_basket()
	if not quotation:
		return {"ok": True, "total": _total_text(None)}
	try:
		qty = float(qty)
	except (TypeError, ValueError):
		qty = 0

	kept = []
	for row in quotation.items:
		hit = (row.name == row_name) if row_name else (row.item_code == item_code)
		if hit:
			if qty <= 0:
				continue
			row.qty = qty
		kept.append(row)
	quotation.set("items", kept)
	reprice(quotation)

	if not quotation.items:
		# an empty quotation cannot be saved; drop it entirely. A guest cart
		# can hold no lines quite happily, but keeping an empty one only leaves
		# a row nobody will ever look at.
		name = quotation.get("name")
		if name:
			frappe.delete_doc(quotation.doctype, name, force=True,
			                  ignore_permissions=True)
			frappe.db.commit()
		if quotation.doctype == GUEST_DOCTYPE:
			_forget_cart()
		return {"ok": True, "total": _total_text(None), "empty": True}
	_save(quotation)
	return {"ok": True, "total": _total_text(quotation)}


def claim_guest_cart():
	"""on_session_creation: adopt a basket that was filled before signing in.

	Someone fills a basket, reaches the checkout, signs in to use a saved
	address - and without this, arrives at an empty cart and has to build it
	again. The lines are appended to whatever the account already had rather
	than replacing it: both baskets were put together deliberately, and quietly
	discarding one of them is the same bug in the other direction.

	Anything that goes wrong here is logged and swallowed. This runs inside
	login, and a cart that failed to move is a bad afternoon; a login that
	failed because of a cart is a bad week.
	"""
	try:
		if is_guest():
			return
		token = _cart_token()
		if not token or not frappe.db.exists(GUEST_DOCTYPE, token):
			return

		guest = frappe.get_doc(GUEST_DOCTYPE, token)
		lines = guest.get("items") or []
		if not lines:
			frappe.delete_doc(GUEST_DOCTYPE, token, force=True,
			                  ignore_permissions=True)
			frappe.db.commit()
			_forget_cart()
			return

		# resolved while we are still the customer, because it is their Contact
		# that says which Customer this is
		quotation = get_cart_quotation(create=True)
		for row in lines:
			for mine in quotation.get("items", []):
				same = (mine.item_code == row.item_code
				        and (mine.get("description") or "")
				            == (row.get("description") or ""))
				if same:
					mine.qty = float(mine.qty or 0) + float(row.qty or 0)
					break
			else:
				added = quotation.append("items", {
					"item_code": row.item_code,
					"qty": row.qty,
					"rate": row.rate,
					"description": row.get("description"),
				})
				added.set(CONFIG_FIELD, row.get(CONFIG_FIELD))

		reprice(quotation)
		_save(quotation)

		# the renders and any picture to print were hanging off the guest cart;
		# they belong to the quotation now, or they vanish with the row below
		move_attachments(GUEST_DOCTYPE, token, quotation.name)

		if guest.get("coupon_code") and not quotation.get("coupon_code"):
			frappe.db.set_value("Quotation", quotation.name, "coupon_code",
			                    guest.coupon_code, update_modified=False)

		frappe.delete_doc(GUEST_DOCTYPE, token, force=True, ignore_permissions=True)
		frappe.db.commit()
		_forget_cart()
	except Exception:
		frappe.log_error(title="curtain_roll: could not adopt guest cart",
		                 message=frappe.get_traceback())


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
	"""Cart summary for the header, the cart page and the checkout summary.

	`guest` still says whether there is an account behind this basket, because
	the checkout page asks for a name and an email when there is not. It no
	longer means "you cannot see your cart" - a guest has a cart like anyone
	else, and it is returned here in full.
	"""
	from curtain_roll import totals

	basket = get_basket()
	items = []
	if basket:
		for row in basket.get("items"):
			items.append({
				"row": row.name,
				"item_code": row.item_code,
				"name": row.item_name or row.item_code,
				"qty": row.qty,
				"rate": row.rate,
				"amount": frappe.utils.flt(row.qty) * frappe.utils.flt(row.rate),
				"spec": (row.get("description") or "").strip(),
			})

	money = summary(basket)
	return {
		"count": len(items),
		"text": _total_text(basket),
		"quotation": basket.name if basket and basket.get("name")
		             and basket.doctype == "Quotation" else None,
		"cart": basket.name if basket and basket.get("name") else None,
		"items": items,
		"guest": is_guest(),
		"totals": money,
		"shown": totals.as_text(money),
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
