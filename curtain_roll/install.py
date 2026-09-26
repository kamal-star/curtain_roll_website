import frappe

from curtain_roll.utils import get_products

HOME_ROUTE = "home"


def after_install():
	"""Make the storefront live the moment the app is installed."""
	_ensure_billing_contact_field()
	_ensure_config_field()
	_ensure_payment_fields()
	_enable_signup()
	_point_website_at_storefront()
	_ensure_item_group()
	_ensure_items()
	_seed_pricing()
	_seed_translations()
	_seed_storefront()
	frappe.db.commit()
	print("\nCurtain Roll storefront installed.")
	print("  home            /")
	for p in get_products():
		print("  %-14s /%s" % (p["heading"][:14], p["route"]))


def _ensure_billing_contact_field():
	"""Work around an ERPNext 16.35 / Frappe 16.34 mismatch.

	ERPNext's accounts/party.py filters Contact on `is_billing_contact`, which
	Frappe 16.34 does not define, so every Quotation save that resolves a party
	fails with: Unknown column 'tabContact.is_billing_contact'.

	`bench update` does not help - both apps are already at the tip of
	version-16, so the mismatch is in the released versions themselves. Adding
	the field as a Custom Field creates the column without patching core; it
	defaults to 0, so ERPNext just falls back to its normal behaviour.

	Delete the Custom Field "Contact-is_billing_contact" once Frappe ships it.
	"""
	if frappe.db.exists("Custom Field", "Contact-is_billing_contact"):
		return
	if frappe.get_meta("Contact").has_field("is_billing_contact"):
		return  # a newer Frappe already provides it
	try:
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Contact",
			"fieldname": "is_billing_contact",
			"label": "Is Billing Contact",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "email_id",
			"description": "Added by curtain_roll for ERPNext 16.35 on Frappe 16.34.",
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="curtain_roll is_billing_contact")


def _enable_signup():
	"""The storefront's Register link points at Frappe's signup, which is
	disabled by default - without this the button leads nowhere on a fresh site."""
	try:
		ws = frappe.get_single("Website Settings")
		if ws.disable_signup:
			ws.disable_signup = 0
			ws.flags.ignore_mandatory = True
			ws.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="curtain_roll enable signup")


def _point_website_at_storefront():
	ws = frappe.get_single("Website Settings")
	ws.home_page = HOME_ROUTE
	# top navigation
	ws.set("top_bar_items", [])
	for p in get_products():
		ws.append("top_bar_items", {"label": p["heading"], "url": "/" + p["route"]})
	ws.flags.ignore_mandatory = True
	ws.save(ignore_permissions=True)


def _ensure_payment_fields():
	"""Where a cart's payment state lives.

	On the Quotation rather than in a table of its own, because the whole point
	is that the state can be read and written in the same row lock that decides
	whether a callback is the first to arrive. A separate table would need its
	own locking to answer the same question.
	"""
	fields = (
		("clickpay_status", "Payment Status", "Data",
		 "Started, Paid, Pending or Failed. Set by the gateway, not by hand."),
		("clickpay_tran_ref", "ClickPay Reference", "Data",
		 "The gateway's own reference for the transaction."),
	)
	after = "order_type"
	for fieldname, label, fieldtype, description in fields:
		name = "Quotation-%s" % fieldname
		if frappe.db.exists("Custom Field", name):
			after = fieldname
			continue
		try:
			frappe.get_doc({
				"doctype": "Custom Field",
				"dt": "Quotation",
				"fieldname": fieldname,
				"label": label,
				"fieldtype": fieldtype,
				"read_only": 1,
				"no_copy": 1,
				"print_hide": 1,
				"insert_after": after,
				"description": description,
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title="curtain_roll payment field %s" % fieldname)
		after = fieldname


def _ensure_config_field():
	"""Remember each cart line's configuration on the line itself.

	Installation is banded by the total curtains on the order, so adding a
	second curtain re-prices the first. Re-pricing needs the options the
	customer picked, and the line's description is prose that cannot be parsed
	back into them.
	"""
	name = "Quotation Item-curtain_config"
	if frappe.db.exists("Custom Field", name):
		return
	try:
		frappe.get_doc({
			"doctype": "Custom Field",
			"dt": "Quotation Item",
			"fieldname": "curtain_config",
			"label": "Curtain Configuration",
			"fieldtype": "Small Text",
			"read_only": 1,
			"no_copy": 0,
			"print_hide": 1,
			"insert_after": "description",
			"description": "Set by the storefront. JSON of the options chosen.",
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="curtain_roll curtain_config field")


def _ensure_item_group():
	if frappe.db.exists("Item Group", "Curtains"):
		return
	parent = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ""}, "name") \
		or "All Item Groups"
	frappe.get_doc({
		"doctype": "Item Group",
		"item_group_name": "Curtains",
		"parent_item_group": parent,
		"is_group": 0,
	}).insert(ignore_permissions=True)


def _ensure_items():
	"""One Item per curtain type, so quotes/orders can reference real stock items."""
	uom = "Nos" if frappe.db.exists("UOM", "Nos") else frappe.db.get_value("UOM", {}, "name")
	for p in get_products():
		code = "CR-" + p["key"].upper()
		if frappe.db.exists("Item", code):
			# Keep the NAME in step. A product can be renamed - the storefront
			# heading is what the customer sees and what belongs on their quote -
			# and simply skipping every Item that already existed left the old
			# name printing on documents long after the page had changed.
			#
			# Only the name. The rate and the description are editable in Desk
			# and rewriting them on every migrate would throw away whatever the
			# client had set there.
			want = p["heading"][:140]
			if frappe.db.get_value("Item", code, "item_name") != want:
				frappe.db.set_value("Item", code, "item_name", want)
			continue
		frappe.get_doc({
			"doctype": "Item",
			"item_code": code,
			"item_name": p["heading"][:140],
			"item_group": "Curtains",
			"stock_uom": uom,
			"is_stock_item": 0,
			"description": (p.get("description") or p["heading"])[:2000],
			"standard_rate": p.get("price") or 0,
		}).insert(ignore_permissions=True)


def after_migrate():
	"""Keep the site in step with the pages after every migrate.

	An app update can add a product - a new capture, or a variant in
	data/variants.json - and that product needs its Item before anyone can
	add it to a cart.
	"""
	_ensure_config_field()
	_ensure_payment_fields()
	_ensure_item_group()
	_ensure_items()
	_seed_pricing()
	_seed_translations()
	_seed_storefront()


def _seed_storefront():
	"""Fill Curtain Storefront Settings from what the page already showed.

	So the first migrate changes nothing on screen - the team opens the record
	and finds today's logo, links, slides and cards already in it, ready to
	edit, rather than an empty form and a blank home page.

	Each table is filled only when it is empty, so their edits are never
	overwritten by a later deploy. Deleting every row is a legitimate choice
	too, and this would refill it - but an empty category bar is not something
	anyone does on purpose, so refilling is the kinder mistake.
	"""
	from curtain_roll.storefront import DEFAULTS, DOCTYPE

	doc = frappe.get_single(DOCTYPE)
	filled = []

	for plain in ("logo", "logo_alt", "favicon", "brand_title",
	              "collections_eyebrow", "collections_heading",
	              "collections_description"):
		if not (doc.get(plain) or "").strip():
			doc.set(plain, DEFAULTS.get(plain) or "")

	tables = (("nav_items", "Curtain Nav Item", ("label", "route", "icon")),
	          ("slides", "Curtain Hero Slide", ("image", "alt_text", "link")),
	          ("categories", "Curtain Category Card",
	           ("title", "route", "image", "badge", "description", "wide")),
	          ("social_links", "Curtain Social Link",
	           ("platform", "icon", "url")))

	for field, child, keys in tables:
		if doc.get(field):
			continue
		for entry in DEFAULTS.get(field) or []:
			row = doc.append(field, {})
			for k in keys:
				row.set(k, entry.get(k) or "")
			row.enabled = 1
		if DEFAULTS.get(field):
			filled.append("%s x%d" % (field, len(DEFAULTS[field])))

	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	if filled:
		print("  storefront settings seeded: %s" % ", ".join(filled))


def _seed_translations():
	"""Fill Curtain Translation from the shipped file, without ever overwriting.

	The file is the seed and the client's table is the truth. A row that
	already exists is left exactly as it is - including one they have
	deliberately blanked - so correcting a word here survives every future
	deploy. Only genuinely new phrases are added.
	"""
	import io
	import json
	import os

	from curtain_roll.curtain_roll.doctype.curtain_translation.curtain_translation 		import fingerprint, clear_phrase_cache

	path = os.path.join(frappe.get_app_path("curtain_roll"),
	                    "translations", "strings.json")
	try:
		data = json.load(io.open(path, encoding="utf-8"))
	except Exception:
		frappe.log_error(title="curtain_roll: could not seed translations",
		                 message=frappe.get_traceback())
		return

	known = set(frappe.get_all("Curtain Translation", pluck="source_key",
	                           limit_page_length=0))
	added = 0
	for english, arabic in (data.get("strings") or {}).items():
		key = fingerprint(english)
		if key in known:
			continue
		doc = frappe.new_doc("Curtain Translation")
		doc.source_text = english
		doc.arabic = (arabic or "").strip()
		doc.source_key = key
		doc.insert(ignore_permissions=True)
		known.add(key)
		added += 1

	if added:
		clear_phrase_cache()
		print("  %d phrase(s) added to Curtain Translation" % added)


def _seed_pricing():
	"""One Curtain Product per curtain type, holding the colours and the rates.

	Seeded from the captured pages so the team opens a record that already
	lists every swatch and option - they only have to type the numbers. Reruns
	add newly captured options and never overwrite a rate already set.
	"""
	from curtain_roll.pricing import sync_from_catalog

	try:
		sync_from_catalog()
	except Exception:
		frappe.log_error(title="curtain_roll seed pricing", message=frappe.get_traceback())


SHUTTER_COLORS = [
	("White", "slat-white.jpg", 260),
	("Beige", "slat-beige.jpg", 260),
	("Grey", "slat-grey.jpg", 285),
	("Brown", "slat-brown.jpg", 300),
]


def setup_shutter_colors():
	"""Give the shutter its own colours, from the textures shipped with the app.

	Run once per site:  bench --site <site> execute
	                      curtain_roll.install.setup_shutter_colors

	Not part of after_migrate, because it writes RATES, and seeding a price
	onto a site nobody asked to be priced is not this hook's business - the
	rest of _seed_pricing deliberately leaves the numbers to the team.

	It exists because a shutter cannot inherit its colours the way the other
	variants do. It borrows the blackout model, so it arrives carrying
	blackout's 65 fabric swatches, and a shutter is not sold in fabric. Left
	alone the page renders the slat casing and surround over a curtain
	fabric, which is worse than either.

	The textures are generated from a measured slat profile - see
	make_slat_texture.py in the build directory - and ship in the app rather
	than being uploaded per site, so a deploy carries them. They are attached
	as Files because that is the path the configurator bundles can resolve;
	see pricing.texture_url.

	Safe to repeat: existing colours are left exactly as they are, so a rate
	edited in Desk survives.
	"""
	import os

	from curtain_roll import pricing

	if not frappe.db.exists("Curtain Product", "shutters"):
		print("no shutters product on this site - run migrate first")
		return

	doc = frappe.get_doc("Curtain Product", "shutters")
	have = {(c.color_name or "").strip().lower() for c in doc.colors if c.get("is_custom")}

	# the inherited fabric swatches are not something a shutter is sold in
	withdrawn = 0
	for row in doc.colors:
		if not row.get("is_custom") and row.enabled:
			row.enabled = 0
			withdrawn += 1

	src = frappe.get_app_path("curtain_roll", "public", "image", "shutters")
	added = 0
	for label, filename, rate in SHUTTER_COLORS:
		if label.lower() in have:
			continue
		path = os.path.join(src, filename)
		if not os.path.exists(path):
			print("  missing texture, skipped: %s" % filename)
			continue
		with open(path, "rb") as fh:
			content = fh.read()
		photo = frappe.get_doc({
			"doctype": "File",
			"file_name": "shutter-" + filename,
			"is_private": 0,
			"content": content,
		}).insert(ignore_permissions=True)
		doc.append("colors", {
			"color_name": label,
			"fabric_image": photo.file_url,
			"charge_type": "Per Square Meter",
			"rate": rate,
			"enabled": 1,
		})
		added += 1

	if doc.pricing_mode != "Material Rate":
		doc.pricing_mode = "Material Rate"
		doc.rate_basis = "Per Square Meter"
	if not doc.minimum_price:
		doc.minimum_price = 450
	if not doc.display_from_price:
		doc.display_from_price = 450

	doc.flags.ignore_permissions = True
	doc.save()
	frappe.db.commit()
	pricing.clear_cache("shutters")

	print("shutters: %d colour(s) added, %d inherited swatch(es) withdrawn"
	      % (added, withdrawn))
	for c in doc.colors:
		if c.get("is_custom") and c.enabled:
			print("  %-6s %-34s %s/m2" % (c.color_name, c.fabric_image, c.rate))


def before_uninstall():
	"""Hand the home page back so the site is not left pointing at a dead route."""
	try:
		ws = frappe.get_single("Website Settings")
		if ws.home_page == HOME_ROUTE:
			ws.home_page = ""
			ws.flags.ignore_mandatory = True
			ws.save(ignore_permissions=True)
			frappe.db.commit()
	except Exception:
		frappe.log_error(title="curtain_roll before_uninstall")
