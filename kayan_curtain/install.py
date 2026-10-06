import frappe

from kayan_curtain.utils import get_products

HOME_ROUTE = "home"

# Set once, the first time the checkout settings are filled in. After that the
# team owns those values and no deploy touches them again - see _seed_storefront.
SEEDED_FLAG = "curtain_roll_checkout_seeded"

# Pages added after a site's menu was first seeded: (label, route, after route).
NEW_NAV_ITEMS = (
	("Zebra Kayan", "/zebra-kayan", "/zebra"),
	("Roman Kayan", "/roman-kayan", "/roman"),
	("Metal Kayan", "/metal-kayan", "/metal"),
	("Sunscreen Kayan", "/sunscreen-kayan", "/sunscreen"),
	("Sheer Curtain", "/sheer-curtain", "/vertical-premium"),
	("Accordion Door", "/accordion-door", "/sheer-curtain"),
	("Smart Film", "/smart-film", "/accordion-door"),
)


def after_install():
	"""Make the storefront live the moment the app is installed."""
	_ensure_billing_contact_field()
	_ensure_config_field()
	_ensure_payment_fields()
	_ensure_checkout_fields()
	_ensure_vat_account()
	_ensure_order_paperwork()
	_enable_signup()
	_point_website_at_storefront()
	_ensure_item_group()
	_ensure_items()
	_seed_pricing()
	_seed_translations()
	_seed_storefront()
	frappe.db.commit()
	print("\nKayan Andalus storefront installed.")
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
			"description": "Added by kayan_curtain for ERPNext 16.35 on Frappe 16.34.",
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="kayan_curtain is_billing_contact")


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
		frappe.log_error(title="kayan_curtain enable signup")


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
			frappe.log_error(title="kayan_curtain payment field %s" % fieldname)
		after = fieldname


def _custom_field(doctype, fieldname, **spec):
	"""One Custom Field, created once. Existing ones are left exactly as they are.

	Never updated on a later migrate: a field the team has relabelled or moved
	is theirs, and a deploy that silently puts it back is a deploy nobody can
	work around.
	"""
	name = "%s-%s" % (doctype, fieldname)
	if frappe.db.exists("Custom Field", name):
		return name
	if frappe.get_meta(doctype).has_field(fieldname):
		return None  # a newer ERPNext already provides it
	try:
		doc = frappe.get_doc(dict(doctype="Custom Field", dt=doctype,
		                          fieldname=fieldname, **spec))
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(title="kayan_curtain: custom field %s" % name)
		return None


def _ensure_checkout_fields():
	"""What the checkout needs to record that ERPNext has no field for.

	A Saudi invoice carries the buyer's National Address and, for a business,
	its Commercial Registration number. ERPNext has the VAT number already
	(Customer.tax_id) but neither of the other two, so they are added here
	rather than crammed into a field meant for something else.
	"""
	_custom_field(
		"Address", "national_address",
		label="National Address", fieldtype="Data", length=16,
		insert_after="pincode",
		description="The Saudi short address, four letters and four digits, "
		            "e.g. RRRD2929.")

	# The second half of the ERPNext 16.35 / Frappe 16.34 mismatch that
	# _ensure_billing_contact_field works around for Contact. ERPNext's
	# accounts/party.py selects tax_category from the Address when it resolves
	# a party's taxes, and Frappe 16.34's Address does not define it - so every
	# checkout that sets a billing address dies on
	# "Unknown column 'tax_category' in 'SELECT'", after the customer has typed
	# everything in. Same fix, same reason: create the column without patching
	# core, and delete the Custom Field once Frappe ships the field.
	_custom_field(
		"Address", "tax_category",
		label="Tax Category", fieldtype="Link", options="Tax Category",
		insert_after="country",
		description="Added by kayan_curtain for ERPNext 16.35 on Frappe 16.34.")

	# The Saudi National Address in parts. Street name stays address_line1 and
	# the postal code stays pincode, so ERPNext's own reports and printouts
	# keep working; the two parts it has no field for are added
	_custom_field(
		"Address", "building_no",
		label="Building No.", fieldtype="Data", length=10,
		insert_after="address_title",
		description="Four digits, from the Saudi National Address.")
	_custom_field(
		"Address", "district",
		label="District", fieldtype="Data", length=80,
		insert_after="address_line2")
	_saudi_address_template()

	_custom_field(
		"Customer", "cr_number",
		label="CR Number", fieldtype="Data", length=40,
		insert_after="tax_id",
		description="Commercial Registration number, printed on the invoice for "
		            "business customers.")

	_custom_field(
		"Quotation", "cr_payment_method",
		label="Paid By", fieldtype="Data", read_only=1, no_copy=1, print_hide=1,
		insert_after="clickpay_tran_ref",
		description="card or bank, as chosen at the checkout.")

	# ERPNext 16 makes a Sales Invoice from a Quotation and keeps no reference
	# back: there is no prevdoc_docname on Sales Invoice Item any more, and no
	# link field to a Quotation at all. So the only moment the connection is
	# known is the moment the invoice is made, and if it is not written down
	# then it cannot be recovered - not by the confirmation page, not by the
	# team looking at an order and asking what it was billed as.
	_custom_field(
		"Quotation", "cr_invoice",
		label="Invoice", fieldtype="Link", options="Sales Invoice",
		read_only=1, no_copy=1, insert_after="cr_payment_method",
		description="The tax invoice raised for this order.")

	_custom_field(
		"Quotation", "cr_access_key",
		label="Order Access Key", fieldtype="Data", read_only=1, no_copy=1,
		print_hide=1, hidden=1, insert_after="cr_payment_method",
		description="Lets the person who placed this order reopen its "
		            "confirmation page without an account.")


SAUDI_ADDRESS_TEMPLATE = """{% if building_no %}{{ building_no }} {% endif %}{{ address_line1 }}<br>
{% if address_line2 %}{{ address_line2 }}<br>{% endif -%}
{% if district %}{{ district }}, {% endif %}{{ city }}{% if pincode %} {{ pincode }}{% endif %}<br>
{{ country }}<br>
{% if national_address %}National Address: {{ national_address }}<br>{% endif -%}
{% if phone %}Phone: {{ phone }}<br>{% endif -%}
{% if email_id %}Email: {{ email_id }}<br>{% endif -%}
"""


def _saudi_address_template():
	"""Print building number and district, which the default template has not heard of.

	Only for Saudi addresses, and only created when there is none: a template
	the team has already written for Saudi Arabia is theirs.
	"""
	if frappe.db.exists("Address Template", "Saudi Arabia") \
			or not frappe.db.exists("Country", "Saudi Arabia"):
		return
	try:
		frappe.get_doc({"doctype": "Address Template", "country": "Saudi Arabia",
		                "is_default": 0, "template": SAUDI_ADDRESS_TEMPLATE}
		               ).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="kayan_curtain: Saudi address template")


def _ensure_order_paperwork():
	"""The Website Sales Person, and the fields that tie an order's drafts together."""
	from kayan_curtain import orders

	try:
		orders.ensure_fields()
		orders.ensure_sales_person()
		from kayan_curtain import notify

		notify.ensure_setup()
		from kayan_curtain import info_pages

		info_pages.seed()
	except Exception:
		frappe.log_error(title="kayan_curtain: order paperwork set-up")


def vat_account_for(company):
	"""The account VAT is posted to for this company, created once if absent.

	Returns None rather than throwing when the chart of accounts has nowhere
	sensible to put it: a site with no tax set up should sell curtains without
	a tax line, not fail at the checkout.
	"""
	if not company:
		return None

	existing = frappe.db.get_value("Account", {
		"company": company, "account_type": "Tax", "is_group": 0,
		"account_name": ["like", "%VAT%"]}, "name")
	if existing:
		return existing

	parent = frappe.db.get_value("Account", {
		"company": company, "is_group": 1,
		"account_name": ["in", ("Duties and Taxes", "Tax Assets",
		                        "Current Liabilities")]}, "name")
	if not parent:
		return None

	try:
		account = frappe.get_doc({
			"doctype": "Account",
			"account_name": "VAT",
			"parent_account": parent,
			"company": company,
			"account_type": "Tax",
			"root_type": "Liability",
			"is_group": 0,
		})
		account.flags.ignore_permissions = True
		account.insert(ignore_permissions=True)
		return account.name
	except Exception:
		frappe.log_error(title="kayan_curtain: VAT account for %s" % company)
		return None


def _ensure_vat_account():
	"""Make the VAT account on install, so the first order does not have to."""
	company = frappe.defaults.get_global_default("company") \
		or frappe.db.get_value("Company", {}, "name")
	if company:
		vat_account_for(company)


SUB_OPTIONS_FLAG = "curtain_roll_sub_options_seeded"

# The client's list for Blackout, Sunscreen and Printed. Motor Type is left
# empty on purpose: the motors are theirs to add, each with the sizes it is
# rated for, and a group with no rows is simply not shown.
SUB_OPTION_SEED = (
	("Manual", "Handle Type", "نوع المقبض", "Plastic", "بلاستيك"),
	("Manual", "Handle Type", "نوع المقبض", "Metal", "معدن"),
	("Manual", "Manual Operating Side", "جهة التشغيل اليدوي", "Left", "يسار"),
	("Manual", "Manual Operating Side", "جهة التشغيل اليدوي", "Right", "يمين"),
	("Motorized", "Motor Position", "موضع المحرك", "Left", "يسار"),
	("Motorized", "Motor Position", "موضع المحرك", "Right", "يمين"),
)


# Each batch of products gets its own flag, so adding Zebra later still seeds
# Zebra - one flag for all of them would have been set already and skipped it.
SUB_OPTION_BATCHES = (
	(SUB_OPTIONS_FLAG, ("blackout", "sunscreen", "printed")),
	# "Zebra: same options as the roller blinds"
	("curtain_roll_sub_options_seeded_zebra", ("zebra",)),
	# "chain type and position not changing in any curtain": the rest of the
	# blinds that are sold Manual / Motorized
	("curtain_roll_sub_options_seeded_more", ("blackout-kayan", "shutters", "roman")),
)


def _seed_sub_options():
	"""Put the client's handle, side and motor-position choices on products.

	Once per product, never again: a row the team deletes is a decision, and a
	migrate that quietly puts it back is a migrate nobody can work with.
	"""
	for flag, keys in SUB_OPTION_BATCHES:
		if not frappe.db.get_default(flag):
			_seed_sub_option_rows(keys)
			frappe.db.set_default(flag, "1")


def _seed_sub_option_rows(keys):
	for key in keys:
		if not frappe.db.exists("Curtain Product", key):
			continue
		doc = frappe.get_doc("Curtain Product", key)
		if doc.get("sub_options"):
			continue
		# only where Manual / Motorized are real choices on this product: the
		# product refuses a row whose "Shown Under" it does not have, and that
		# refusal must not stop a migrate
		labels = {(o.option_label or "").strip().lower() for o in doc.get("options") or []}
		if not {"manual", "motorized"} & labels:
			print("  %s has no Manual / Motorized choice; no chain choices added" % key)
			continue
		for parent, group, group_ar, label, label_ar in SUB_OPTION_SEED:
			doc.append("sub_options", {
				"parent_choice": parent, "group_label": group,
				"group_label_ar": group_ar, "option_label": label,
				"option_label_ar": label_ar, "charge_type": "Fixed Amount",
				"rate": 0, "enabled": 1,
			})
		doc.flags.ignore_permissions = True
		try:
			doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(title="kayan_curtain: chain choices on %s" % key)
			continue
		print("  choices under Manual / Motorized seeded on %s" % key)


SHEER_FLAG = "kayan_curtain_sheer_blackout_seeded"

# The Sheer Curtain's blackout colours: Choices shown "Always", in a step of
# their own. Starter swatches (make_sheer_swatches.py) the team replaces with
# photos of the real fabrics, and renames, prices or adds to, in the desk.
SHEER_BLACKOUT = (
	("ivory", "Ivory", "عاجي"),
	("beige", "Beige", "بيج"),
	("taupe", "Taupe", "رمادي بني"),
	("latte", "Latte", "لاتيه"),
	("light-grey", "Light Grey", "رمادي فاتح"),
	("charcoal", "Charcoal", "فحمي"),
	("navy", "Navy", "كحلي"),
	("olive", "Olive", "زيتي"),
	("chocolate", "Chocolate", "شوكولاتة"),
)


def _seed_sheer_curtain():
	"""Put the blackout colours on the Sheer Curtain, once."""
	if frappe.db.get_default(SHEER_FLAG) or not frappe.db.exists("Curtain Product", "sheer-curtain"):
		return
	doc = frappe.get_doc("Curtain Product", "sheer-curtain")
	if not any((r.group_label or "").strip().lower() == "blackout colour"
	           for r in doc.get("sub_options") or []):
		for name, label, label_ar in SHEER_BLACKOUT:
			doc.append("sub_options", {
				"parent_choice": "Always", "group_label": "Blackout Colour",
				"group_label_ar": "لون البلاك آوت", "option_label": label,
				"option_label_ar": label_ar, "charge_type": "Fixed Amount",
				"rate": 0, "enabled": 1,
				"image": "/assets/kayan_curtain/image/catalog/blackout-materials/%s.jpg" % name,
			})
	# priced by the square metre, like the other made-to-measure curtains
	if not doc.get("rate_basis") or doc.rate_basis == "Per Piece":
		doc.rate_basis = "Per Square Meter"
	doc.flags.ignore_permissions = True
	try:
		doc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="kayan_curtain: sheer curtain blackout colours")
		return
	frappe.db.set_default(SHEER_FLAG, "1")
	print("  blackout colours seeded on sheer-curtain")


# Products added by hand (not captured) whose price is by area. The catalogue
# seed makes every new product Per Piece; these are switched once, on the day
# they arrive, and are the team's to change after that.
PER_SQM_PRODUCTS = ("accordion-door", "smart-film")


def _seed_per_square_metre():
	for key in PER_SQM_PRODUCTS:
		flag = "kayan_curtain_per_sqm_seeded:%s" % key
		if frappe.db.get_default(flag) or not frappe.db.exists("Curtain Product", key):
			continue
		frappe.db.set_value("Curtain Product", key, "rate_basis", "Per Square Meter")
		frappe.db.set_default(flag, "1")
		print("  %s priced per square metre" % key)


ACCORDION_FLAG = "kayan_curtain_accordion_colours_seeded"


def _seed_accordion_door():
	"""Each door type's colours, as Choices shown under Plastic or Leather. Once.

	The list and the starter swatches are in make_accordion_swatches.py (repo
	root); the team replaces the swatches with photos of the real finishes.
	"""
	if frappe.db.get_default(ACCORDION_FLAG) or not frappe.db.exists("Curtain Product", "accordion-door"):
		return
	doc = frappe.get_doc("Curtain Product", "accordion-door")
	types = {(o.option_label or "").strip() for o in doc.get("options") or []}
	if not {"Plastic", "Leather"} <= types:
		return              # the page's Door Type step has not been synced yet
	if not any((r.parent_choice or "").strip() in ("Plastic", "Leather") for r in doc.get("sub_options") or []):
		for parent, rows in (("Plastic", ACCORDION_PLASTIC), ("Leather", ACCORDION_LEATHER)):
			for name, label, label_ar in rows:
				doc.append("sub_options", {
					"parent_choice": parent, "group_label": "Door Colour",
					"group_label_ar": "لون الباب", "option_label": label,
					"option_label_ar": label_ar, "charge_type": "Fixed Amount",
					"rate": 0, "enabled": 1,
					"image": "/assets/kayan_curtain/image/catalog/accordion-materials/%s.jpg" % name,
				})
	doc.flags.ignore_permissions = True
	try:
		doc.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="kayan_curtain: accordion door colours")
		return
	frappe.db.set_default(ACCORDION_FLAG, "1")
	print("  plastic and leather colours seeded on accordion-door")


ACCORDION_PLASTIC = (
	("plastic-white", "White", "أبيض"),
	("plastic-off-white", "Off White", "أوف وايت"),
	("plastic-ivory", "Ivory", "عاجي"),
	("plastic-beige", "Beige", "بيج"),
	("plastic-light-grey", "Light Grey", "رمادي فاتح"),
	("plastic-grey", "Grey", "رمادي"),
	("plastic-oak", "Oak", "بلوط"),
	("plastic-walnut", "Walnut", "جوزي"),
	("plastic-dark-brown", "Dark Brown", "بني غامق"),
)
ACCORDION_LEATHER = (
	("leather-cream", "Cream", "كريمي"),
	("leather-beige", "Beige", "بيج"),
	("leather-caramel", "Caramel", "كراميل"),
	("leather-brown", "Brown", "بني"),
	("leather-dark-brown", "Dark Brown", "بني غامق"),
	("leather-grey", "Grey", "رمادي"),
	("leather-black", "Black", "أسود"),
	("leather-burgundy", "Burgundy", "عنابي"),
)


PRINT_UPLOAD_FLAG = "curtain_roll_print_upload_seeded"


def _seed_print_upload():
	"""Turn the picture upload on for the Printed blind, once."""
	if frappe.db.get_default(PRINT_UPLOAD_FLAG):
		return
	if frappe.db.exists("Curtain Product", "printed"):
		frappe.db.set_value("Curtain Product", "printed", "allow_upload", 1)
		print("  picture upload turned on for printed")
	frappe.db.set_default(PRINT_UPLOAD_FLAG, "1")


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
		frappe.log_error(title="kayan_curtain curtain_config field")


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
	_ensure_checkout_fields()
	_ensure_vat_account()
	_ensure_order_paperwork()
	_ensure_item_group()
	_ensure_items()
	_seed_pricing()
	_seed_sub_options()
	_seed_sheer_curtain()
	_seed_per_square_metre()
	_seed_accordion_door()
	_seed_print_upload()
	_seed_translations()
	_seed_storefront()
	_rebrand()
	_seed_page_text()


def _seed_page_text():
	"""Copy each product page's heading and description into its record, once."""
	try:
		from kayan_curtain import page_text
		page_text.seed()
	except Exception:
		frappe.log_error(title="kayan_curtain: page text", message=frappe.get_traceback())


def _rebrand():
	"""Swap the copied Curtain Roll details for Kayan's in what this site keeps
	in its database (info pages, storefront settings, translations). Once."""
	try:
		from kayan_curtain import rebrand
		rebrand.apply()
	except Exception:
		frappe.log_error(title="kayan_curtain: rebrand", message=frappe.get_traceback())


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
	from kayan_curtain.storefront import DEFAULTS, DOCTYPE

	doc = frappe.get_single(DOCTYPE)
	filled = []

	for plain in ("logo", "logo_alt", "logo_light", "favicon", "brand_title",
	              "collections_eyebrow", "collections_heading",
	              "collections_description",
	              "bank_name", "bank_account_name", "bank_account_number",
	              "bank_iban",
	              "bank_instructions"):
		if not (doc.get(plain) or "").strip():
			doc.set(plain, DEFAULTS.get(plain) or "")

	# Ticks and numbers cannot be seeded the way the text fields above are.
	# An unticked box is 0 and a rate of 0% is 0, so "off" and "never chosen"
	# read identically - and the DocType's own default does not help either: it
	# applies when a document is created, and this Single was created long
	# before these fields existed, so its first save after an update writes 0
	# into every one of them.
	#
	# Which means there is no way to ask the record whether anyone has answered.
	# So the answer is recorded outside it, once, and after that the settings
	# belong entirely to the team - including a VAT rate they have deliberately
	# set to 0. A flag is clumsier than reading the data, and it is the only
	# version of this that cannot silently reset a client's tax rate.
	if not frappe.db.get_default(SEEDED_FLAG):
		for switch in ("vat_rate", "prices_include_vat", "card_enabled",
		               "bank_transfer_enabled", "guest_checkout",
		               "require_national_address"):
			doc.set(switch, DEFAULTS.get(switch))
			filled.append(switch)
		frappe.db.set_default(SEEDED_FLAG, "1")

	tables = (("nav_items", "Curtain Nav Item", ("label", "route", "icon")),
	          ("slides", "Curtain Hero Slide", ("image", "alt_text", "link")),
	          ("features", "Curtain Feature Box",
	           ("icon", "title", "text", "title_ar", "text_ar")),
	          ("categories", "Curtain Category Card",
	           ("title", "route", "image", "badge", "description", "wide")),
	          ("social_links", "Curtain Social Link",
	           ("platform", "icon", "url")),
	          ("footer_links", "Curtain Footer Link",
	           ("column", "label", "label_ar", "link")))

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

	# A product added after the menu was first seeded. The table above is only
	# filled while empty, so on a running site a new page would never reach the
	# menu. Each is added once - after the entry it belongs beside - and then
	# the menu is the team's again: deleting it is not undone by a later deploy.
	for label, route, after in NEW_NAV_ITEMS:
		flag = "curtain_roll_nav_added:%s" % route
		if frappe.db.get_default(flag):
			continue
		rows = doc.get("nav_items") or []
		if not any((r.route or "").rstrip("/") == route for r in rows):
			at = next((i + 1 for i, r in enumerate(rows)
			           if (r.route or "").rstrip("/") == after), len(rows))
			row = doc.append("nav_items", {"label": label, "route": route,
			                               "icon": "", "enabled": 1})
			rows = doc.get("nav_items")
			rows.remove(row)
			rows.insert(at, row)
			for i, r in enumerate(rows, 1):
				r.idx = i
			filled.append("menu: %s" % label)
		frappe.db.set_default(flag, "1")

	# The footer, once: its text, contact details and Maroof link as the pages
	# showed them, so the team edits today's footer rather than a blank one.
	from kayan_curtain.storefront import FOOTER_SEEDED
	if not frappe.db.get_default(FOOTER_SEEDED):
		for plain in ("footer_about", "footer_about_ar", "copyright_text", "contact_phone",
		              "contact_whatsapp", "contact_email", "contact_address",
		              "contact_address_ar", "maroof_url"):
			if not (doc.get(plain) or "").strip():
				doc.set(plain, DEFAULTS.get(plain) or "")
		frappe.db.set_default(FOOTER_SEEDED, "1")
		filled.append("footer")

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

	from kayan_curtain.kayan_curtain.doctype.curtain_translation.curtain_translation 		import fingerprint, clear_phrase_cache

	path = os.path.join(frappe.get_app_path("kayan_curtain"),
	                    "translations", "strings.json")
	try:
		data = json.load(io.open(path, encoding="utf-8"))
	except Exception:
		frappe.log_error(title="kayan_curtain: could not seed translations",
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
	from kayan_curtain.pricing import sync_from_catalog

	try:
		sync_from_catalog()
	except Exception:
		frappe.log_error(title="kayan_curtain seed pricing", message=frappe.get_traceback())


SHUTTER_COLORS = [
	("White", "slat-white.jpg", 260),
	("Beige", "slat-beige.jpg", 260),
	("Grey", "slat-grey.jpg", 285),
	("Brown", "slat-brown.jpg", 300),
]


def setup_shutter_colors():
	"""Give the shutter its own colours, from the textures shipped with the app.

	Run once per site:  bench --site <site> execute
	                      kayan_curtain.install.setup_shutter_colors

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

	from kayan_curtain import pricing

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

	src = frappe.get_app_path("kayan_curtain", "public", "image", "shutters")
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
		frappe.log_error(title="kayan_curtain before_uninstall")
