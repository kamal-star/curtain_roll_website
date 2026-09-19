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

from curtain_roll.utils import get_product, get_products

DOCTYPE = "Curtain Product"
CACHE_KEY = "curtain_roll:spec:%s"

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

	spec = {
		"product_key": product_key,
		"title": doc.product_title or page.get("heading"),
		"item_code": doc.item_code,
		"rate_basis": doc.rate_basis,
		"base_rate": flt(doc.base_rate),
		"min_billable_sqm": flt(doc.min_billable_sqm) or 0.0,
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
			str(c.option_value): _color_entry(c)
			for c in (doc.get("colors") or [])
		},
		"options": {},
	}
	for o in doc.get("options") or []:
		spec["options"].setdefault(str(o.group_id), {})[str(o.option_value)] = {
			"label": o.option_label,
			"group_label": o.group_label,
			"enabled": cint(o.enabled),
			"charge_type": o.charge_type,
			"rate": flt(o.rate),
			"tiered": cint(o.get("tiered")),
		}

	frappe.cache().set_value(CACHE_KEY % product_key, json.dumps(spec))
	return spec


def _color_entry(row):
	entry = {
		"label": row.color_name,
		"enabled": cint(row.enabled),
		"charge_type": row.charge_type,
		"rate": flt(row.rate),
		"custom": cint(row.get("is_custom")),
	}
	if entry["custom"]:
		# This colour has no swatch in the captured HTML, so the page has to
		# build one. It needs the photo, and a path the 3D bundle will resolve
		# back to that same photo - see texture_url().
		entry["image"] = row.fabric_image or ""
		entry["texture"] = texture_url(row.fabric_image)
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


def _dimension(value):
	try:
		n = flt(str(value).strip().replace(",", "."))
	except Exception:
		return None
	return n if n > 0 else None


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
			area = (width * height) / 10000.0

	per_sqm = spec["rate_basis"] == "Per Square Meter"
	if per_sqm and spec["min_billable_sqm"]:
		area = max(area, spec["min_billable_sqm"])

	dims = {
		"area": area,
		"width_m": (width or 0) / 100.0,
		"height_m": (height or 0) / 100.0,
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

	precision = spec["rounding"]
	unit = flt(sum(amount for _label, amount in lines), precision)

	return {
		"ok": not errors,
		"errors": errors,
		"partial": partial,
		"area": flt(area, 4),
		"width": width,
		"height": height,
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
	from curtain_roll import cart as cart_api

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
	if result.get("partial"):
		# still mid-configuration, so do not present this as the final figure
		total = "%s %s" % (_("From"), total)
	return {"total": total, "total_extax": total}


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
	}


@frappe.whitelist()
def resync(product_key=None):
	"""Desk button: pull any new swatches off the pages into this record."""
	frappe.only_for(("System Manager", "Sales Manager"))
	sync_from_catalog(product_key=product_key)
	return {"ok": True}
