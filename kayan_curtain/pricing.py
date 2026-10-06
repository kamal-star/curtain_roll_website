"""Back-office pricing for the storefront configurator.

Everything the customer picks on a product page - the colour, the size, the
control type, the mounting, the valance box, the installation service - is
priced from a **Curtain Product** record, one per storefront route. The team
edits those records in the desk; the storefront reads them.

Two rules make this safe:

  * the catalogue captured from the original site is only ever a *seed*. Once
    a Curtain Product exists, ``sync_from_catalog`` keeps the option lists in
    step with the pages but never overwrites a rate the team has set.
  * the browser is never trusted. ``calculate`` prices the live total on the
    page AND the quotation line, so a tampered form cannot buy a disabled
    colour or invent a rate.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from kayan_curtain.utils import get_product, get_products

DOCTYPE = "Curtain Product"
CACHE_KEY = "kayan_curtain:spec:%s"

# The group holding the fabric swatches is named differently per product:
# "Material" on most of them, "slice width and color" on the metal blind.
_COLOR_LABEL = re.compile(r"materi|colou?r", re.I)
_MONEY = re.compile(r"-?\d+(?:[.,]\d+)?")


def is_color_group(group):
	return bool(_COLOR_LABEL.search(group.get("label") or ""))


def money(text):
	"""Parse a captured price label such as "SR 1.60" into a number."""
	m = _MONEY.search(str(text or ""))
	return flt(m.group(0).replace(",", "")) if m else 0.0


def currency_symbol():
	"""What the storefront prints in front of a price."""
	company = frappe.defaults.get_global_default("company") \
		or frappe.db.get_value("Company", {}, "name")
	code = (frappe.db.get_value("Company", company, "default_currency") or "SAR") \
		if company else "SAR"
	return "SR" if code in ("SAR", "SR") else code


def fmt(amount, symbol=None):
	return "%s %s" % (symbol or currency_symbol(), "{:,.2f}".format(flt(amount)))


# --------------------------------------------------------------- seeding
def sync_from_catalog(product_key=None, prune=True):
	"""Create or refresh Curtain Product records from the captured pages.

	Adds option rows that are on the page but missing from the record and,
	when ``prune``, drops rows whose swatch no longer exists. Rates, charge
	types and the Show-on-site ticks the team has already set are carried
	over - this is deliberately not a reset.
	"""
	touched = []
	for page in get_products():
		key = page.get("key")
		if product_key and key != product_key:
			continue

		fresh = not frappe.db.exists(DOCTYPE, key)
		if fresh:
			doc = frappe.new_doc(DOCTYPE)
			doc.product_key = key
			# the captured "starts from" price is a per-piece figure, so seed
			# it that way rather than leaving a new site priced at zero
			doc.rate_basis = "Per Piece"
			doc.base_rate = flt(page.get("price"))
			doc.min_billable_sqm = 1
			doc.rounding = 2
		else:
			doc = frappe.get_doc(DOCTYPE, key)

		doc.product_title = page.get("heading") or key
		item = "CR-" + key.upper()
		if frappe.db.exists("Item", item):
			doc.item_code = item

		_sync_colors(doc, page, prune)
		_sync_options(doc, page, prune)

		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		if fresh:
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)
		touched.append((key, fresh))

	frappe.db.commit()
	clear_cache()
	return touched


def _sync_colors(doc, page, prune):
	existing = {str(r.option_value): r for r in (doc.get("colors") or [])}
	seen, rows = set(), []

	# colours the team added in the desk are not on the captured page, so they
	# would be pruned as "no longer exists". Carry them through untouched.
	for row in doc.get("colors") or []:
		if cint(row.get("is_custom")):
			rows.append(row.as_dict())
			seen.add(str(row.option_value))

	for group in page.get("option_groups") or []:
		if group.get("kind") != "swatch" or not is_color_group(group):
			continue
		for opt in group.get("options") or []:
			value = str(opt.get("value"))
			if value in seen:
				continue
			seen.add(value)
			old = existing.get(value)
			rows.append({
				"enabled": cint(old.enabled) if old else 1,
				"color_name": (old.color_name if old else None) or opt.get("code") or value,
				"charge_type": (old.charge_type if old else None) or "Fixed Amount",
				"rate": flt(old.rate) if old else money(opt.get("price")),
				"option_value": value,
				"texture_code": opt.get("code") or "",
				"image": opt.get("image") or "",
			})

	if not prune:
		for value, old in existing.items():
			if value not in seen:
				rows.append(old.as_dict())

	doc.set("colors", rows)


def _sync_options(doc, page, prune):
	existing = {"%s:%s" % (r.group_id, r.option_value): r for r in (doc.get("options") or [])}
	seen, rows = set(), []

	for group in page.get("option_groups") or []:
		if group.get("kind") != "swatch" or is_color_group(group):
			continue
		gid = str(group.get("id"))
		label = (group.get("label") or "").strip() or ("Option %s" % gid)
		for opt in (group.get("options") or []) + (group.get("choices") or []):
			value = str(opt.get("value"))
			ident = "%s:%s" % (gid, value)
			seen.add(ident)
			old = existing.get(ident)
			rows.append({
				"enabled": cint(old.enabled) if old else 1,
				"group_id": gid,
				"group_label": label,
				"option_label": (old.option_label if old else None)
					or opt.get("code") or opt.get("label") or value,
				"option_value": value,
				"charge_type": (old.charge_type if old else None) or "Fixed Amount",
				"rate": flt(old.rate) if old else money(opt.get("price")),
				# Carried over like every other setting on the row. Leaving it
				# out silently dropped it on every sync, which took the
				# installation banding with it: the tiers stayed on the product
				# but nothing was flagged to use them, so 1-4 and 5+ both
				# charged the flat captured rate and no one could see why.
				"tiered": cint(old.tiered) if old else 0,
				"image": opt.get("image") or "",
			})

	if not prune:
		for ident, old in existing.items():
			if ident not in seen:
				rows.append(old.as_dict())

	doc.set("options", rows)


# ------------------------------------------------------------------ spec
def clear_cache(product_key=None):
	keys = [product_key] if product_key else [p["key"] for p in get_products()]
	for key in keys:
		frappe.cache().delete_value(CACHE_KEY % key)


def get_spec(product_key):
	"""Page definition merged with the priced record. None if not priced yet."""
	cached = frappe.cache().get_value(CACHE_KEY % product_key)
	if cached:
		return json.loads(cached)

	page = get_product(product_key)
	if not page or not frappe.db.exists(DOCTYPE, product_key):
		return None

	doc = frappe.get_cached_doc(DOCTYPE, product_key)
	if not cint(doc.enabled):
		return None

	flat = bool(page.get("flat"))
	size_group = color_group = capture_group = None
	color_label = "Material"
	required = {}
	for group in page.get("option_groups") or []:
		gid = str(group.get("id"))
		kind = group.get("kind")
		if kind == "size":
			size_group = gid
		elif kind == "capture":
			capture_group = gid
		elif kind == "swatch" and is_color_group(group):
			color_group = gid
			color_label = (group.get("label") or "").strip() or "Material"
		if "required" in ((group.get("wrap") or {}).get("class") or ""):
			required[gid] = (group.get("label") or "").strip() or gid

	# What this product can be made in. Zero means "no limit", so a record
	# nobody has opened behaves exactly as it did before these existed.
	limits = {
		"min_width": flt(doc.get("min_width")),
		"max_width": flt(doc.get("max_width")),
		"min_height": flt(doc.get("min_height")),
		"max_height": flt(doc.get("max_height")),
	}

	# Both default to 1, and Frappe writes a Check's default into the existing
	# rows when it adds the column - measured on all thirteen products, which
	# is worth knowing, because the alternative would have hidden every fabric
	# swatch on the site the day this shipped. The `is None` arm is only for a
	# record read before its column exists.
	show_material = doc.get("show_material")
	show_material = True if show_material is None else bool(cint(show_material))
	show_motor = doc.get("show_motor")
	show_motor = True if show_motor is None else bool(cint(show_motor))

	spec = {
		"product_key": product_key,
		"title": doc.product_title or page.get("heading"),
		"item_code": doc.item_code,
		"rate_basis": doc.rate_basis,
		"base_rate": flt(doc.base_rate),
		"limits": limits,
		"show_material": show_material,
		"show_motor": show_motor,
		"allow_upload": bool(cint(doc.get("allow_upload"))),
		"min_billable_sqm": flt(doc.min_billable_sqm) or 0.0,
		# a blind smaller than these is charged as this size (cm); 0 = off
		"min_billed_width": flt(doc.get("min_billed_width")) or 0.0,
		"min_billed_height": flt(doc.get("min_billed_height")) or 0.0,
		"rounding": cint(doc.rounding) or 2,
		"pricing_mode": doc.pricing_mode or "Base Rate",
		"minimum_price": flt(doc.minimum_price),
		"display_from_price": flt(doc.display_from_price),
		"install_tiers": [
			{"from_qty": cint(t.from_qty), "to_qty": cint(t.to_qty),
			 "rate": flt(t.rate), "description": t.description or ""}
			for t in (doc.get("install_tiers") or [])
		],
		"currency": currency_symbol(),
		"flat": flat,
		"size_group": size_group,
		"color_group": color_group,
		"color_label": color_label,
		"capture_group": capture_group or page.get("capture_option_id"),
		"required": required,
		"slabs": [
			{"from_sqm": flt(s.from_sqm), "to_sqm": flt(s.to_sqm),
			 "rate_basis": s.rate_basis, "rate": flt(s.rate)}
			for s in (doc.get("size_slabs") or [])
		],
		"colors": {
			str(c.option_value): _color_entry(c, flat)
			for c in (doc.get("colors") or [])
		},
		"options": {},
	}
	for o in doc.get("options") or []:
		spec["options"].setdefault(str(o.group_id), {})[str(o.option_value)] = {
			"label": o.option_label,
			"group_label": o.group_label,
			"enabled": cint(o.enabled) and not _is_motor(o, show_motor),
			"charge_type": o.charge_type,
			"rate": flt(o.rate),
			"tiered": cint(o.get("tiered")),
		}

	# Nothing is chosen for the customer on the page any more (see
	# language._no_preselected_options), so every choice they can make has to
	# be made: a group with at least one choice on offer is required, whatever
	# the captured page marked. Installation service, for one, was not marked -
	# it arrived pre-ticked instead. A group with nothing on offer stays
	# optional, or no order could ever be placed.
	for gid, choices in spec["options"].items():
		if gid not in spec["required"] and any(c["enabled"] for c in choices.values()):
			spec["required"][gid] = (next(iter(choices.values()))["group_label"] or gid)

	# The control-type group - the one holding Manual and Motorized - is found
	# by its choices rather than by an id, because every product numbers its
	# groups differently.
	spec["control_group"] = None
	for gid, choices in spec["options"].items():
		labels = [c["label"] or "" for c in choices.values()]
		if any(_MOTOR.search(l) for l in labels) or "Manual" in labels:
			spec["control_group"] = gid
			break

	# Which choice each dependent row sits under. "Shown Under" is typed by the
	# team - Manual, Motorized, 5 cm - so it is matched to the product's real
	# choices by their names, in any group, the colour group included.
	choices = {}
	for gid, group in spec["options"].items():
		for value, entry in group.items():
			choices.setdefault((entry["label"] or "").strip().lower(), (gid, value))
	for value, entry in spec["colors"].items():
		if color_group:
			choices.setdefault((entry["label"] or "").strip().lower(), (color_group, value))

	spec["sub_options"] = []
	for row in (doc.get("sub_options") or []):
		if not (cint(row.enabled) and (row.group_label or "").strip()
		        and (row.option_label or "").strip()):
			continue
		parent = (row.parent_choice or "").strip()
		# no motor on offer means nothing to choose under Motorized either
		if _MOTOR.search(parent) and not show_motor:
			continue
		where = _parent_of(parent, choices, spec)
		if not where:
			continue            # names a choice this product does not have
		spec["sub_options"].append({
			"id": row.name,
			"parent": parent,
			"parent_gid": where[0],
			"parent_value": where[1],
			"group": (row.group_label or "").strip(),
			"key": _group_key(row.group_label),
			"group_ar": (row.group_label_ar or "").strip(),
			"label": (row.option_label or "").strip(),
			"label_ar": (row.option_label_ar or "").strip(),
			"image": row.get("image") or "",
			"charge_type": row.charge_type or "Fixed Amount",
			"rate": flt(row.rate),
			"min_width": flt(row.min_width), "max_width": flt(row.max_width),
			"min_height": flt(row.min_height), "max_height": flt(row.max_height),
		})

	# kept even when hidden: the page needs to know WHICH card to take away
	spec["material_group"] = color_group
	if not show_material:
		# The group stops being asked for rather than being emptied. calculate
		# skips it entirely, so nothing is required, nothing is priced, and a
		# colour posted by an old page or a curious customer changes no total.
		spec["color_group"] = None

	frappe.cache().set_value(CACHE_KEY % product_key, json.dumps(spec))
	return spec


# Which row in the control-type group is "the motor". There is no field saying
# so - the captured catalogue only has labels - and every product that offers
# one calls it Motorized, or كهربائي once the page is in Arabic. Matching the
# label is therefore the only way to know, and it is why the per-row Show on
# site tick still exists: a product whose motor is named something else can be
# withdrawn by hand.
_MOTOR = re.compile(r"motor|كهربائي", re.I)


def _is_motor(row, show_motor):
	"""True when this option is a motor and the product is not offering one."""
	if show_motor:
		return False
	return bool(_MOTOR.search(row.option_label or ""))


# ------------------------------------------ choices under Manual / Motorized
def _group_key(label):
	"""A group's name as a key: "Motor Type" -> "motor-type".

	Hyphens, not underscores, on purpose. The theme shows an option's error
	under the element with id "input-option" + key.replace('_', '-') - a replace
	that swaps only the FIRST underscore - so a key with two of them would point
	at an element that does not exist and the message would never be shown.
	"""
	return re.sub(r"[^a-z0-9]+", "-", (label or "").strip().lower()).strip("-") or "choice"


def _fits(entry, width, height):
	"""Whether a choice is offered at this size. No size yet means yes."""
	if not width or not height:
		return True
	for value, low, high in ((width, entry["min_width"], entry["max_width"]),
	                         (height, entry["min_height"], entry["max_height"])):
		if low and value < low:
			return False
		if high and value > high:
			return False
	return True


# "Shown Under: Always" - a group of its own, offered whatever else is picked
# (the Sheer Curtain's blackout colours). It has no parent choice, so it is
# filed under this made-up group, which every request counts as chosen.
ALWAYS = ("always", "دائما", "دائماً")
ALWAYS_GID = "always"


def _parent_of(parent, choices, spec):
	"""(group id, value) of the choice a dependent row sits under, or None.

	By name first. Manual and Motorized also match a control choice that is
	spelled differently - Motorised, Motor - because that is how most rows are
	typed and a product's own label is whatever the old site called it.
	"""
	if parent.lower() in ALWAYS:
		return ALWAYS_GID, "1"
	found = choices.get(parent.lower())
	if found:
		return found
	gid = spec.get("control_group")
	if gid and parent.lower() in ("manual", "motorized", "motorised"):
		want_motor = parent.lower() != "manual"
		for value, entry in (spec["options"].get(gid) or {}).items():
			if bool(_MOTOR.search(entry["label"] or "")) == want_motor:
				return gid, value
	return None


def active_sub_groups(spec, submitted):
	"""The dependent choices whose parent the customer has picked, {key: [rows]}.

	In the grid's order. A row belongs only while its parent choice is the one
	selected in its group - pick 2.5 cm and the 5 cm colours stop existing.
	"""
	groups = {}
	for row in spec.get("sub_options") or []:
		if row["parent_gid"] == ALWAYS_GID or 				str(submitted("option[%s]" % row["parent_gid"]) or "") == row["parent_value"]:
			groups.setdefault(row["key"], []).append(row)
	return groups


def _color_entry(row, flat=False):
	entry = {
		"label": row.color_name,
		"enabled": cint(row.enabled),
		"charge_type": row.charge_type,
		"rate": flt(row.rate),
		"custom": cint(row.get("is_custom")),
		# the name the captured page prints on this swatch; the page swaps in
		# "label" when the team has renamed the colour in the desk
		"page_label": row.texture_code or "",
	}
	if entry["custom"]:
		# This colour has no swatch in the captured HTML, so the page has to
		# build one. It needs the photo, and the path to hand the viewer.
		entry["image"] = row.fabric_image or ""
		# A flat product loads exactly the URL it is given. The "-x" in
		# texture_url() exists only to survive the obfuscated bundles, which
		# mangle the path before loading it - there is no bundle here.
		entry["texture"] = ((row.fabric_image or "") if flat
						else texture_url(row.fabric_image))
		entry["code"] = row.texture_code or row.color_name
	return entry


def texture_url(file_url):
	"""Turn an uploaded photo into what the configurator must be handed.

	The obfuscated bundles do not load the URL they are given. They derive the
	fabric from it: drop "/cache", cut at the LAST hyphen, put the extension
	back. Measured against the real bundle:

	    .../cache/blackout-materials/7200-150x150.jpg -> .../blackout-materials/7200.jpg
	    /files/probe-x.png                            -> /files/probe.png

	So appending "-x" before the extension makes that derivation land exactly
	on the uploaded file, whatever it is called and whatever format it is.
	"""
	if not file_url:
		return ""
	head, dot, ext = file_url.rpartition(".")
	if not dot:
		return file_url + "-x"
	return "%s-x.%s" % (head, ext)


# ----------------------------------------------------------- calculation
def _charge(charge_type, rate, dims, base):
	"""One option's contribution. ``dims`` carries area, width_m and height_m."""
	rate = flt(rate)
	if charge_type == "Per Square Meter":
		return rate * dims["area"]
	if charge_type == "Per Metre of Width":
		return rate * dims["width_m"]
	if charge_type == "Per Metre of Height":
		return rate * dims["height_m"]
	if charge_type == "Percent of Base":
		return base * rate / 100.0
	return rate  # Fixed Amount, and the fallback


def tier_rate(spec, order_qty):
	"""Installation rate per curtain, banded by the WHOLE order's count."""
	for tier in spec.get("install_tiers") or []:
		low, high = cint(tier["from_qty"]), cint(tier["to_qty"])
		if order_qty >= (low or 1) and (not high or order_qty <= high):
			return flt(tier["rate"]), tier
	return None, None


def _outside_limits(spec, width, height):
	"""Why this size cannot be made, in words, or None if it can.

	The numbers go into the sentence AFTER it has been translated, not before:
	the dictionary is keyed on the English template, so "Width must be between
	{0} and {1} cm." is a phrase that exists and can be looked up, while
	"Width must be between 40 and 300 cm." never will be. Formatting first is
	how a message ends up permanently English.

	Told as a range rather than as "too wide", because a customer who has just
	been refused needs to know what to type instead.
	"""
	from kayan_curtain.language import text as say

	limits = spec.get("limits") or {}

	def clean(value):
		return ("%g" % flt(value))

	for edge, value, low, high in (
			("width", width, limits.get("min_width"), limits.get("max_width")),
			("height", height, limits.get("min_height"), limits.get("max_height"))):
		low, high = flt(low), flt(high)
		if not low and not high:
			continue
		if low and high and (value < low or value > high):
			template = "Width must be between {0} and {1} cm." if edge == "width" \
				else "Height must be between {0} and {1} cm."
			return say(template).format(clean(low), clean(high))
		if low and value < low:
			template = "Width must be at least {0} cm." if edge == "width" \
				else "Height must be at least {0} cm."
			return say(template).format(clean(low))
		if high and value > high:
			template = "Width can be at most {0} cm." if edge == "width" \
				else "Height can be at most {0} cm."
			return say(template).format(clean(high))
	return None


def _dimension(value):
	try:
		n = flt(str(value).strip().replace(",", "."))
	except Exception:
		return None
	return n if n > 0 else None


def install_cities():
	"""The enabled Curtain Install City records, in the team's order.

	Read straight from the table, not cached: it is a handful of rows, and a
	city enabled or re-priced in the desk must show on the next price refresh.
	"""
	if not frappe.db.table_exists("Curtain Install City"):
		return []
	return frappe.get_all(
		"Curtain Install City", filters={"enabled": 1},
		fields=["city", "city_ar", "price"],
		order_by="sort_order asc, city asc")


def _install_city(submitted, strict, lines):
	"""Add the chosen city's installation price to `lines`.

	Returns None when all is well, "partial" when the live price is still
	waiting for a city, or the sentence to show the customer.
	"""
	cities = install_cities()
	if not cities:
		return None                      # no list set up: nothing to ask
	from kayan_curtain.language import text as say

	chosen = str(submitted("cr_city") or "").strip()
	if not chosen:
		return say("Please choose your city.") if strict else "partial"
	city = next((c for c in cities if c["city"] == chosen), None)
	if not city:
		return say("We do not install in that city yet. Please contact us.")
	price = flt(city.get("price"))
	if price:
		lines.append(("%s: %s" % (say("Installation city"), city["city"]), price))
	return None


def _aramex_delivery(submitted, strict, lines, area):
	"""Add Aramex's price to the customer's city to `lines` (see aramex.py).

	Returns None when all is well or delivery is not offered, "partial" while
	the live price waits for a city, or the sentence to show the customer.
	"""
	from kayan_curtain import aramex
	from kayan_curtain.language import text as say

	if not aramex.enabled():
		return None
	city = str(submitted("cr_ship_city") or "").strip()
	if not city:
		return say("Please choose your city for delivery.") if strict else "partial"
	try:
		if city not in aramex.cities():
			return say("Aramex does not deliver to that city. Please contact us.")
		amount = aramex.rate(city, aramex.parcel_weight(area))
	except Exception:
		frappe.log_error(title="kayan_curtain: Aramex rate for %s" % city)
		if not strict:
			return "partial"
		return say("The delivery price could not be calculated right now. "
		           "Please try again in a moment, or contact us.")
	lines.append(("%s: %s" % (say("Delivery by Aramex to"), city), amount))
	return None


def calculate(product_key, form, qty=1, strict=True, order_qty=None):
	"""Price one configured blind.

	``form`` is anything exposing ``.get("option[371]")``. Errors come back
	keyed by option group id, which is exactly the shape the Journal3 theme
	already knows how to render next to the offending field.

	``strict`` separates "not allowed" from "not finished yet":

	  * strict (the cart) - a required option left unchosen is an error, so a
	    half-configured blind cannot be ordered.
	  * lenient (the live price on the page) - it is not an error, it just
	    makes the result ``partial``. The theme repaints the price only when
	    the response carries no ``error``, so being strict here would freeze
	    the total until the very last option was picked.

	``order_qty`` is how many curtains are on the whole order, which is what
	picks the installation tier. It defaults to this line's own quantity, so a
	product page shows the price for what the visitor is adding; the cart
	passes the real total and re-prices every line.
	"""
	spec = get_spec(product_key)
	if not spec:
		return {"ok": False, "errors": {}, "message": _("This product is not priced yet.")}

	def submitted(key):
		try:
			return form.get(key)
		except Exception:
			return None

	errors, lines = {}, []
	qty = max(1, cint(qty) or 1)
	order_qty = max(qty, cint(order_qty) or 0) if order_qty else qty

	# ---- size -> area, and the two edge lengths things are charged by
	area = 1.0
	partial = False
	width = height = None
	billed_w = billed_h = None
	if spec["size_group"]:
		gid = spec["size_group"]
		raw_w = submitted("option[%s][width]" % gid)
		raw_h = submitted("option[%s][height]" % gid)
		width = _dimension(raw_w)
		height = _dimension(raw_h)
		if not width or not height:
			started = bool(str(raw_w or "").strip() or str(raw_h or "").strip())
			if strict or started:
				errors[gid] = _("Enter the width and the height in cm.")
			else:
				partial = True
			width = height = None
		else:
			outside = _outside_limits(spec, width, height)
			if outside:
				errors[gid] = outside
				width = height = None
			else:
				# Charged by the billed size: a blind smaller than the minimum
				# billed width / height is priced as that size. The size the
				# customer entered is what the quotation and invoice show.
				billed_w = max(width, spec.get("min_billed_width") or 0)
				billed_h = max(height, spec.get("min_billed_height") or 0)
				area = (billed_w * billed_h) / 10000.0

	per_sqm = spec["rate_basis"] == "Per Square Meter"
	if per_sqm and spec["min_billable_sqm"]:
		area = max(area, spec["min_billable_sqm"])

	dims = {
		"area": area,
		"width_m": (billed_w or 0) / 100.0,
		"height_m": (billed_h or 0) / 100.0,
	}

	# ---- the fabric: either the chosen material's own m2 rate, or the base
	rate, basis = spec["base_rate"], spec["rate_basis"]
	for slab in spec["slabs"]:
		if slab["rate"] <= 0:
			continue
		low, high = slab["from_sqm"], slab["to_sqm"]
		if area >= low and (not high or area <= high):
			rate, basis = slab["rate"], slab["rate_basis"]
			break

	by_material = spec.get("pricing_mode") == "Material Rate"
	base = rate * area if basis == "Per Square Meter" else rate
	fabric_label = _("Base")

	if spec["color_group"]:
		gid = spec["color_group"]
		value = str(submitted("option[%s]" % gid) or "")
		entry = spec["colors"].get(value)
		if not value:
			if gid in spec["required"]:
				if strict:
					errors[gid] = _("Please choose a colour.")
				else:
					partial = True
		elif not entry or not entry["enabled"]:
			errors[gid] = _("That colour is not available.")
		elif by_material:
			# the material IS the price: its rate is per square metre
			base = flt(entry["rate"]) * area
			fabric_label = "%s (%s)" % (entry["label"], spec["color_label"])
		elif entry["charge_type"] == "Override Base Rate":
			base = flt(entry["rate"]) * area if basis == "Per Square Meter" else flt(entry["rate"])
			fabric_label = "%s (%s)" % (entry["label"], spec["color_label"])
		else:
			extra = _charge(entry["charge_type"], entry["rate"], dims, base)
			if extra:
				lines.append(("%s (%s)" % (entry["label"], spec["color_label"]), extra))

	# ---- the floor applies to the fabric, not to the motor or the fitting
	minimum = flt(spec.get("minimum_price"))
	if minimum and base < minimum:
		lines.insert(0, (_("Minimum order price"), minimum))
		base = minimum
	else:
		lines.insert(0, (fabric_label, base))

	# ---- every other option group
	for gid, choices in spec["options"].items():
		value = str(submitted("option[%s]" % gid) or "")
		if not value:
			if gid in spec["required"]:
				if strict:
					errors[gid] = _("Please choose an option.")
				else:
					partial = True
			continue
		entry = choices.get(value)
		if not entry or not entry["enabled"]:
			errors[gid] = _("That choice is not available.")
			continue

		label = "%s (%s)" % (entry["label"], entry["group_label"])
		install = _install_choice(spec)
		if install and gid == install[0]:
			if value == install[1]:
				# With Installation: the customer's city, and its price
				problem, key = _install_city(submitted, strict, lines), "crcity"
			else:
				# Without installation: delivered by Aramex, by city and weight
				problem, key = _aramex_delivery(submitted, strict, lines, area), "crship"
			if problem == "partial":
				partial = True
			elif problem:
				errors[key] = problem
		if entry.get("tiered"):
			banded, tier = tier_rate(spec, order_qty)
			if banded is None:
				continue                      # no band set up; charge nothing
			if banded:
				note = (tier or {}).get("description") or ""
				lines.append(("%s%s" % (label, (" - %s" % note) if note else ""), banded))
			continue

		extra = _charge(entry["charge_type"], entry["rate"], dims, base)
		if extra:
			lines.append((label, extra))

	# ---- the choices under Manual / Motorized: handle, side, motor, position
	active = active_sub_groups(spec, submitted)
	if active:
		from kayan_curtain.language import text as say

		from kayan_curtain.language import current, phrases

		arabic = current() == "ar"
		for key, rows in active.items():
			group = rows[0]["group"]
			# the name used in a message the customer will read
			shown = group
			if arabic:
				shown = next((r["group_ar"] for r in rows if r["group_ar"]), "") \
					or phrases().get(group, group)
			err_key = "crsub-" + key
			offered = [r for r in rows if _fits(r, width, height)]
			if not offered:
				# every choice is rated for other sizes - only motors are, in
				# practice - so this blind cannot be made motorised as measured
				errors[err_key] = say(
					"No {0} is available for this size. Please contact us.").format(shown)
				continue
			chosen = str(submitted("cr_sub[%s]" % key) or "")
			if not chosen:
				if strict:
					errors[err_key] = say("Please choose the {0}.").format(shown)
				else:
					partial = True
				continue
			entry = next((r for r in offered if r["id"] == chosen), None)
			if not entry:
				# a choice from the other control, a withdrawn one, or a motor
				# that does not fit - never priced, whatever the page sent
				errors[err_key] = _("That choice is not available.")
				continue
			extra = _charge(entry["charge_type"], entry["rate"], dims, base)
			if extra:
				lines.append(("%s (%s)" % (entry["label"], group), extra))

	# ---- the customer's own picture, for a printed blind
	if spec.get("allow_upload"):
		from kayan_curtain import print_upload
		from kayan_curtain.language import text as say

		token = submitted("cr_print")
		if not token:
			if strict:
				errors["crprint"] = say("Please upload the picture to print.")
			else:
				partial = True
		elif not print_upload.verify(token):
			# a token we did not issue - someone else's file, or a made-up one
			errors["crprint"] = say("Please upload the picture again.")

	precision = spec["rounding"]
	unit = flt(sum(amount for _label, amount in lines), precision)

	return {
		"ok": not errors,
		"errors": errors,
		"partial": partial,
		"area": flt(area, 4),
		"width": width,
		"height": height,
		"billed_width": billed_w,
		"billed_height": billed_h,
		"qty": qty,
		"order_qty": order_qty,
		"unit_rate": unit,
		"total": flt(unit * qty, precision),
		"lines": [(label, flt(amount, precision)) for label, amount in lines],
		"currency": spec["currency"],
		"item_code": spec["item_code"],
	}


def label_map(product_key):
	"""{group id: {value: label}} - what the customer actually saw.

	data/products.json only knows the captured swatches, so without this a
	colour added in the desk would land on the quotation as a raw id.
	"""
	spec = get_spec(product_key)
	if not spec:
		return {}
	out = {}
	if spec["color_group"]:
		out[spec["color_group"]] = {
			value: entry["label"] for value, entry in spec["colors"].items()
		}
	for gid, choices in spec["options"].items():
		out[gid] = {value: entry["label"] for value, entry in choices.items()}
	return out


def breakdown_lines(result):
	"""Human-readable price rows for the quotation line description."""
	sym = result.get("currency") or currency_symbol()
	out = []
	bw, bh = result.get("billed_width"), result.get("billed_height")
	if bw and bh and (bw != result.get("width") or bh != result.get("height")):
		out.append("%s: %g x %g cm" % (_("Billed size"), bw, bh))
	if result.get("area"):
		out.append("%s: %.2f m2" % (_("Billed area"), result["area"]))
	for label, amount in result.get("lines") or []:
		out.append("%s: %s" % (label, fmt(amount, sym)))
	out.append("%s: %s" % (_("Unit price"), fmt(result.get("unit_rate"), sym)))
	return out


# -------------------------------------------------------------- handlers
def price_preview(args, form):
	"""index.php?route=product/product/add - the theme's live price refresh.

	Journal3 already POSTs the whole option form here on every change and
	writes ``json.total`` into #total_price, so implementing this endpoint is
	all it takes for the page total to follow the back-office rates.
	"""
	from kayan_curtain import cart as cart_api

	pid = str(form.get("product_id") or args.get("product_id") or "").strip()
	entry = cart_api.product(pid)
	if not entry:
		return {"error": {"warning": _("Product not available.")}}

	qty = cint(form.get("quantity") or 1) or 1
	# the installation band depends on the whole order, so count what is
	# already in the cart as well as what is being configured now
	try:
		order_qty = qty + cart_api.curtain_qty_in_cart()
	except Exception:
		order_qty = qty
	result = calculate(entry.get("key"), form, qty, strict=False, order_qty=order_qty)
	if result.get("errors"):
		return {"error": {"option": result["errors"]}}
	if not result.get("ok"):
		return {"error": {"warning": result.get("message") or _("Not priced yet.")}}

	total = fmt(result["total"], result["currency"])
	# No "From" in front of a partial figure any more: the page's own label
	# already says "Starts from:", and the two together read "Starts from:
	# From 150.00". `partial` lets the page switch that label to "Total:"
	# once the blind is fully configured (curtain_options.js).
	return {"total": total, "total_extax": total,
	        "partial": 1 if result.get("partial") else 0}


@frappe.whitelist(allow_guest=True)
def get_pricing(product_key=None):
	"""What a product page needs to hide withdrawn colours and show surcharges."""
	spec = get_spec(product_key or "")
	if not spec:
		return {}
	return {
		"product_key": spec["product_key"],
		"currency": spec["currency"],
		"color_group": spec["color_group"],
		"color_label": spec["color_label"],
		"colors": spec["colors"],
		"options": spec["options"],
		# the snapshot's "Starts from" figure is whatever the original site
		# charged. Replace it with the team's own display price, which is
		# deliberately NOT part of any calculation.
		"starting_text": fmt(spec.get("display_from_price") or spec["base_rate"],
		                     spec["currency"]),
		"rate_basis": spec["rate_basis"],
		# so the page can refuse an impossible size before the customer has
		# configured a whole blind and pressed Add to cart
		"size_group": spec["size_group"],
		"limits": spec.get("limits") or {},
		"show_material": spec.get("show_material", True),
		"material_group": spec.get("material_group"),
		# the choices under Manual / Motorized, drawn by curtain_options.js
		"allow_upload": spec.get("allow_upload", False),
		"sub_options": _sub_options_for_page(spec),
		# the city list shown under the installation choice, and that choice
		"install_cities": _cities_for_page(spec),
		"install_choice": _install_choice(spec),
		# Without installation: Aramex's city list is fetched by the page only
		# when that choice is picked (kayan_curtain.aramex.city_list)
		"aramex_delivery": _aramex_on(),
	}


def _aramex_on():
	try:
		from kayan_curtain import aramex

		return aramex.enabled()
	except Exception:
		return False


_WITH_INSTALL = re.compile(r"^\s*with\s+install", re.I)


def _install_choice(spec):
	"""[group id, value] of the With Installation choice, or None.

	The one priced by the installation bands when there is one (Blackout).
	Every other product sells installation as a plain priced choice, so it is
	found by its name - "With Installation", never "Without installation" -
	and its group is the one whose other choice means delivery instead.
	"""
	options = spec.get("options") or {}
	for gid, choices in options.items():
		for value, entry in choices.items():
			if entry.get("tiered") and entry.get("enabled"):
				return [gid, value]
	for gid, choices in options.items():
		for value, entry in choices.items():
			if entry.get("enabled") and _WITH_INSTALL.match(entry.get("label") or ""):
				return [gid, value]
	return None


def _cities_for_page(spec):
	from kayan_curtain.language import current

	ar = current() == "ar"
	symbol = currency_symbol()
	out = []
	for c in install_cities():
		price = flt(c.get("price"))
		out.append({
			"city": c["city"],
			"label": (c.get("city_ar") if ar and c.get("city_ar") else c["city"]),
			# both names, so the search finds "جدة" on the English site too
			"city_ar": c.get("city_ar") or "",
			"price_text": ("+%s" % fmt(price, symbol)) if price else "",
		})
	return out


def _sub_options_for_page(spec):
	"""The choices, with their Arabic filled in wherever it can be found.

	A group's Arabic name is typed on the row, and the client should not have
	to retype "نوع المحرك" on every motor they add - so a row without it borrows
	it from another row in the same group, and failing that from the phrase
	dictionary. Done here, per request, rather than in the cached spec, so a
	correction in Curtain Translation shows without re-saving the product.
	"""
	from kayan_curtain.language import phrases

	table = phrases()
	rows = [dict(r) for r in spec.get("sub_options") or []]
	group_ar = {}
	for r in rows:
		if r["group_ar"]:
			group_ar.setdefault(r["key"], r["group_ar"])
	for r in rows:
		r["group_ar"] = r["group_ar"] or group_ar.get(r["key"]) or table.get(r["group"], "")
		r["label_ar"] = r["label_ar"] or table.get(r["label"], "")
		r["price_text"] = _sub_price_text(r, spec["currency"])
	return rows


def _sub_price_text(row, symbol):
	"""What a choice adds, as the page shows it next to the name, or ""."""
	rate = flt(row["rate"])
	if not rate:
		return ""
	unit = {"Per Square Meter": " / m²", "Per Metre of Width": " / m",
	        "Per Metre of Height": " / m", "Percent of Base": "%"}.get(row["charge_type"], "")
	if row["charge_type"] == "Percent of Base":
		return "+%g%%" % rate
	return "+%s %s%s" % (symbol, "{:,.2f}".format(rate), unit)


@frappe.whitelist()
def resync(product_key=None):
	"""Desk button: pull any new swatches off the pages into this record."""
	frappe.only_for(("System Manager", "Sales Manager"))
	sync_from_catalog(product_key=product_key)
	return {"ok": True}
