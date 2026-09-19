import frappe

from curtain_roll.utils import get_products

HOME_ROUTE = "home"


def after_install():
	"""Make the storefront live the moment the app is installed."""
	_ensure_billing_contact_field()
	_enable_signup()
	_point_website_at_storefront()
	_ensure_item_group()
	_ensure_items()
	_seed_pricing()
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
	_ensure_item_group()
	_ensure_items()
	_seed_pricing()


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
