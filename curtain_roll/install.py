import frappe

from curtain_roll.utils import get_products

HOME_ROUTE = "home"


def after_install():
	"""Make the storefront live the moment the app is installed."""
	_point_website_at_storefront()
	_ensure_item_group()
	_ensure_items()
	frappe.db.commit()
	print("\nCurtain Roll storefront installed.")
	print("  home            /")
	for p in get_products():
		print("  %-14s /%s" % (p["heading"][:14], p["route"]))


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
