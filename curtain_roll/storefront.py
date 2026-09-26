"""The home page's editable content.

The page was captured as a static file, so the logo, the category bar, the
slider and the collection cards were all markup - every change a developer
job. They come from Curtain Storefront Settings now.

DEFAULTS is what the page showed before any of this existed. It serves twice:
it seeds the settings on first migrate, and it is the floor underneath them, so
a site with an empty setting renders exactly as it always did rather than
losing its header.

The captured markup pointed its images at https://erp.atozksa.com - the
production site - which meant a local or staging copy quietly loaded its
pictures from live. The paths here are relative; the files are in the app.
"""
import frappe

from curtain_roll.curtain_roll.doctype.curtain_storefront_settings.curtain_storefront_settings 	import CACHE_KEY

DOCTYPE = "Curtain Storefront Settings"

DEFAULTS = {
 "logo": "/assets/curtain_roll/image/logo-kayan.png",
 "logo_light": "/assets/curtain_roll/image/logo-kayan-light.png",
 "logo_alt": "Kayan Andalus - More Than Curtain",
 "favicon": "/assets/curtain_roll/image/favicon.png",
 "brand_title": "Kayan Andalus Curtains",
 "collections_eyebrow": "Curated Collections",
 "collections_heading": "Architectural Blinds & Shades",
 "collections_description": "Engineered to balance privacy, thermal protection, and contemporary design for upscale homes and workspaces.",
 "nav_items": [
  {
   "label": "Home",
   "route": "/",
   "icon": "fa-solid fa-house"
  },
  {
   "label": "Blackout",
   "route": "/blackout",
   "icon": ""
  },
  {
   "label": "Blackout Kayan",
   "route": "/blackout-kayan",
   "icon": ""
  },
  {
   "label": "Shutters",
   "route": "/shutters",
   "icon": ""
  },
  {
   "label": "Sunscreen",
   "route": "/sunscreen",
   "icon": ""
  },
  {
   "label": "Zebra",
   "route": "/zebra",
   "icon": ""
  },
  {
   "label": "Wooden",
   "route": "/wooden",
   "icon": ""
  },
  {
   "label": "Wooden Kayan",
   "route": "/wooden-premium",
   "icon": ""
  },
  {
   "label": "Vertical",
   "route": "/vertical",
   "icon": ""
  },
  {
   "label": "Vertical Kayan",
   "route": "/vertical-premium",
   "icon": ""
  },
  {
   "label": "Metal",
   "route": "/metal",
   "icon": ""
  },
  {
   "label": "Roman",
   "route": "/roman",
   "icon": ""
  },
  {
   "label": "Wavy",
   "route": "/wavy",
   "icon": ""
  },
  {
   "label": "Printed",
   "route": "/printed",
   "icon": ""
  }
 ],
 "slides": [
  {
   "image": "/assets/curtain_roll/image/cache/catalog/SND-curtain%20roll-04-1400x600w.jpg",
   "alt_text": "Modern roller blinds",
   "link": ""
  },
  {
   "image": "/assets/curtain_roll/image/cache/catalog/SND-curtain%20roll-05-1400x600w.jpg",
   "alt_text": "Luxury hotel wavy curtains",
   "link": ""
  },
  {
   "image": "/assets/curtain_roll/image/cache/catalog/SND-curtain%20roll-06-1400x600w.jpg",
   "alt_text": "Blackout window shades",
   "link": ""
  }
 ],
 "categories": [
  {
   "title": "Blackout Roller Blinds",
   "route": "/blackout",
   "image": "/assets/curtain_roll/image/cache/catalog/category-banners/blackout-940x550.jpg",
   "badge": "100% Blackout",
   "description": "Complete darkness and high thermal barrier. Ideal for bedrooms, home cinemas, and spaces requiring total light blockade.",
   "wide": 1
  },
  {
   "title": "Sunscreen Roller Blinds",
   "route": "/sunscreen",
   "image": "/assets/curtain_roll/image/cache/catalog/category-banners/sunscreen-940x550.jpg",
   "badge": "50% Light Filtering",
   "description": "Diffuses direct sunlight and blocks UV rays while preserving outside daytime panoramic vistas.",
   "wide": 1
  },
  {
   "title": "Wavy Hotel-Style Drapes",
   "route": "/wavy",
   "image": "/assets/curtain_roll/image/cache/catalog/wavy-images/one-layer-1400x600.png",
   "badge": "Hotel Standard",
   "description": "Uniform ripple folds on concealed tracks, delivering tailored architectural elegance to lounges and master suites.",
   "wide": 1
  },
  {
   "title": "Zebra Blinds",
   "route": "/zebra",
   "image": "/assets/curtain_roll/image/cache/catalog/category-banners/zebra-940x550.jpg",
   "badge": "Dual-Layer",
   "description": "Alternating sheer and solid fabric bands for flexible, instantaneous light control.",
   "wide": 0
  },
  {
   "title": "Wooden Blinds",
   "route": "/wooden",
   "image": "/assets/curtain_roll/image/cache/catalog/category-banners/wooden-940x550.jpg",
   "badge": "Natural Timber",
   "description": "Natural timber slats offering warmth, enduring texture, and classic elegance to offices and majlis.",
   "wide": 0
  },
  {
   "title": "Metal Blinds",
   "route": "/metal",
   "image": "/assets/curtain_roll/image/cache/catalog/category-banners/metal-940x550.jpg",
   "badge": "Moisture Proof",
   "description": "Lightweight, moisture-resistant aluminum slats engineered for kitchens, bathrooms, and studios.",
   "wide": 0
  },
  {
   "title": "Vertical Blinds",
   "route": "/vertical",
   "image": "/assets/curtain_roll/image/cache/catalog/category-banners/vertical-940x550.jpg",
   "badge": "Wide Glazing",
   "description": "Versatile 180° rotatable louvers designed for wide floor-to-ceiling office windows.",
   "wide": 0
  },
  {
   "title": "Roman Blinds",
   "route": "/roman",
   "image": "/assets/curtain_roll/image/cache/catalog/roman-category-940x550.jpg",
   "badge": "Fabric Pleats",
   "description": "Crisp geometric fabric folds uniting traditional drapery appeal with compact mechanical ease.",
   "wide": 0
  },
  {
   "title": "Printed Blinds",
   "route": "/printed",
   "image": "/assets/curtain_roll/image/cache/catalog/category-banners/printed-940x550.jpg",
   "badge": "Custom Print",
   "description": "Bespoke high-definition imagery and company logo printing on solar-protective textiles.",
   "wide": 0
  }
 ],
 "social_links": [
  {
   "platform": "WhatsApp",
   "icon": "fa-brands fa-whatsapp",
   "url": "https://wa.me/966114550783"
  }
 ]
}


def _rows(doc, field, keys):
	"""Enabled child rows, in the order the grid shows them."""
	out = []
	for row in (doc.get(field) or []):
		if not row.get("enabled"):
			continue
		out.append({k: (row.get(k) or "") for k in keys})
	return out


def storefront_settings():
	"""Everything the home page needs, cached, defaults underneath.

	Named for what it is, not just "settings": Frappe exposes a jinja hook
	under the function's own name into a Jinja environment shared with every
	other app, so a generic name is a collision waiting to happen.

	Returns plain dicts rather than the document, so a template cannot
	accidentally write to it and the whole thing can sit in the cache.
	"""
	cached = frappe.cache().get_value(CACHE_KEY)
	if cached is not None:
		return cached

	data = dict(DEFAULTS)
	try:
		doc = frappe.get_cached_doc(DOCTYPE)
	except Exception:
		# before the first migrate the table does not exist; the page still works
		frappe.cache().set_value(CACHE_KEY, data)
		return data

	for plain in ("logo", "logo_alt", "logo_light", "favicon", "brand_title",
	              "collections_eyebrow", "collections_heading",
	              "collections_description"):
		value = (doc.get(plain) or "").strip()
		if value:
			data[plain] = value

	nav = _rows(doc, "nav_items", ("label", "route", "icon"))
	if nav:
		data["nav_items"] = nav
	slides = _rows(doc, "slides", ("image", "alt_text", "link"))
	if slides:
		data["slides"] = slides
	cards = _rows(doc, "categories",
	              ("title", "route", "image", "badge", "description", "wide"))
	if cards:
		data["categories"] = cards
	social = _rows(doc, "social_links", ("platform", "icon", "url"))
	if social:
		data["social_links"] = social

	frappe.cache().set_value(CACHE_KEY, data)
	return data
