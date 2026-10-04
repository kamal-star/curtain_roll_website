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

from kayan_curtain.kayan_curtain.doctype.curtain_storefront_settings.curtain_storefront_settings 	import CACHE_KEY

DOCTYPE = "Curtain Storefront Settings"

DEFAULTS = {
 "logo": "/assets/kayan_curtain/image/logo-kayan.png",
 "logo_light": "/assets/kayan_curtain/image/logo-kayan-light.png",
 "logo_alt": "Kayan Andalus - More Than Curtain",
 "favicon": "/assets/kayan_curtain/image/favicon.png",
 "brand_title": "Kayan Andalus Curtains",
 "collections_eyebrow": "Curated Collections",
 "collections_heading": "Architectural Blinds & Shades",
 "collections_description": "Engineered to balance privacy, thermal protection, and contemporary design for upscale homes and workspaces.",
 # Checkout. The tax default matters: every price on this site was written with
 # VAT already in it, so inclusive is the only default that leaves the totals
 # where the customer last saw them.
 "vat_rate": 15,
 "prices_include_vat": 1,
 "card_enabled": 1,
 "bank_transfer_enabled": 0,
 "bank_name": "",
 "bank_account_name": "",
 "bank_account_number": "",
 "bank_iban": "",
 "bank_instructions": "",
 "guest_checkout": 1,
 "aramex_enabled": 0,
 "aramex_origin_city": "Riyadh",
 "aramex_product_type": "ONP",
 "aramex_weight_per_sqm": 1.5,
 "aramex_min_weight": 1,
 "alert_role": "Sales Manager",
 "alert_emails": "",
 "no_customer_emails": 0,
 "require_national_address": 0,
 # footer & contact - what the footer said before it was editable
 "footer_about": "The leading digital platform for bespoke architectural curtains and automated shading systems across the Kingdom of Saudi Arabia.",
 "footer_about_ar": "",
 "copyright_text": "Copyright © {year} Kayan Andalus Curtain. All Rights Reserved.",
 "contact_phone": "+966 55 546 5718",
 "contact_whatsapp": "966555465718",
 "contact_email": "",
 "contact_address": "",
 "contact_address_ar": "",
 "maroof_url": "https://maroof.sa/40866",
 "footer_links": [
  {"column": "Categories", "label": "Blackout Blinds", "label_ar": "", "link": "/blackout-kayan"},
  {"column": "Categories", "label": "Sunscreen Blinds", "label_ar": "", "link": "/sunscreen-kayan"},
  {"column": "Categories", "label": "Zebra Blinds", "label_ar": "", "link": "/zebra-kayan"},
  {"column": "Categories", "label": "Wooden Blinds", "label_ar": "", "link": "/wooden-premium"},
  {"column": "Categories", "label": "Roman Blinds", "label_ar": "", "link": "/roman-kayan"},
  {"column": "Customer Service", "label": "About Factory", "label_ar": "", "link": "/about-us"},
  {"column": "Customer Service", "label": "Shipping & Delivery", "label_ar": "", "link": "/delivery-and-installation"},
  {"column": "Customer Service", "label": "Terms & Return Policy", "label_ar": "", "link": "/terms-and-conditions"},
  {"column": "Customer Service", "label": "Privacy Policy", "label_ar": "", "link": "/privacy-policy"},
  {"column": "Contact", "label": "Support Tickets", "label_ar": "", "link": "/contact-us"},
  {"column": "Contact", "label": "Order Tracking", "label_ar": "", "link": "/me"}
 ],
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
   "label": "Sunscreen Kayan",
   "route": "/sunscreen-kayan",
   "icon": ""
  },
  {
   "label": "Zebra",
   "route": "/zebra",
   "icon": ""
  },
  {
   "label": "Zebra Kayan",
   "route": "/zebra-kayan",
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
   "label": "Metal Kayan",
   "route": "/metal-kayan",
   "icon": ""
  },
  {
   "label": "Roman",
   "route": "/roman",
   "icon": ""
  },
  {
   "label": "Roman Kayan",
   "route": "/roman-kayan",
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
   "image": "/assets/kayan_curtain/image/slides/kayan-slide-1.jpg",
   "alt_text": "Installation, free delivery and speed - Kayan Andalus",
   "link": ""
  },
  {
   "image": "/assets/kayan_curtain/image/slides/kayan-slide-2.jpg",
   "alt_text": "Kayan Andalus curtains overlooking Riyadh",
   "link": ""
  },
  {
   "image": "/assets/kayan_curtain/image/slides/kayan-slide-3.jpg",
   "alt_text": "Kayan Andalus roller blinds in a living room",
   "link": ""
  }
 ],
 # The highlight boxes under the slider, as the page showed them. The Arabic is
 # carried on the row itself rather than left to the dictionary: the dictionary
 # matches the English exactly, so the moment the client rewords a title the
 # Arabic would silently stop following it. One row, both languages.
 "features": [
  {"icon": "fa-solid fa-ruler-combined",
   "title": "Millimeter Precision",
   "text": "Automated cutting tailored to your windows",
   "title_ar": "دقة بالملّيمتر",
   "text_ar": "قص آلي مضبوط على مقاس نوافذك"},
  {"icon": "fa-solid fa-shield-halved",
   "title": "5-Year Quality Warranty",
   "text": "Premium motors, fabrics & hardware",
   "title_ar": "ضمان جودة لمدة خمس سنوات",
   "text_ar": "محركات وأقمشة وقطع فاخرة"},
  {"icon": "fa-solid fa-truck-fast",
   "title": "Secure Saudi Shipping",
   "text": "Reinforced protective transit packaging",
   "title_ar": "شحن آمن داخل المملكة",
   "text_ar": "تغليف واقٍ ومدعّم للنقل"},
  {"icon": "fa-solid fa-credit-card",
   "title": "Interest-Free Installments",
   "text": "Split payments via Tamara & Tabby",
   "title_ar": "تقسيط بدون فوائد",
   "text_ar": "تقسيط عبر تمارا وتابي"},
 ],
 "hide_features": 0,
 "categories": [
  {
   "title": "Blackout Roller Blinds",
   "route": "/blackout",
   "image": "/assets/kayan_curtain/image/cache/catalog/category-banners/blackout-940x550.jpg",
   "badge": "100% Blackout",
   "description": "Complete darkness and high thermal barrier. Ideal for bedrooms, home cinemas, and spaces requiring total light blockade.",
   "wide": 1
  },
  {
   "title": "Sunscreen Roller Blinds",
   "route": "/sunscreen",
   "image": "/assets/kayan_curtain/image/cache/catalog/category-banners/sunscreen-940x550.jpg",
   "badge": "50% Light Filtering",
   "description": "Diffuses direct sunlight and blocks UV rays while preserving outside daytime panoramic vistas.",
   "wide": 1
  },
  {
   "title": "Wavy Hotel-Style Drapes",
   "route": "/wavy",
   "image": "/assets/kayan_curtain/image/cache/catalog/wavy-images/one-layer-1400x600.png",
   "badge": "Hotel Standard",
   "description": "Uniform ripple folds on concealed tracks, delivering tailored architectural elegance to lounges and master suites.",
   "wide": 1
  },
  {
   "title": "Zebra Blinds",
   "route": "/zebra",
   "image": "/assets/kayan_curtain/image/cache/catalog/category-banners/zebra-940x550.jpg",
   "badge": "Dual-Layer",
   "description": "Alternating sheer and solid fabric bands for flexible, instantaneous light control.",
   "wide": 0
  },
  {
   "title": "Wooden Blinds",
   "route": "/wooden",
   "image": "/assets/kayan_curtain/image/cache/catalog/category-banners/wooden-940x550.jpg",
   "badge": "Natural Timber",
   "description": "Natural timber slats offering warmth, enduring texture, and classic elegance to offices and majlis.",
   "wide": 0
  },
  {
   "title": "Metal Blinds",
   "route": "/metal",
   "image": "/assets/kayan_curtain/image/cache/catalog/category-banners/metal-940x550.jpg",
   "badge": "Moisture Proof",
   "description": "Lightweight, moisture-resistant aluminum slats engineered for kitchens, bathrooms, and studios.",
   "wide": 0
  },
  {
   "title": "Vertical Blinds",
   "route": "/vertical",
   "image": "/assets/kayan_curtain/image/cache/catalog/category-banners/vertical-940x550.jpg",
   "badge": "Wide Glazing",
   "description": "Versatile 180° rotatable louvers designed for wide floor-to-ceiling office windows.",
   "wide": 0
  },
  {
   "title": "Roman Blinds",
   "route": "/roman",
   "image": "/assets/kayan_curtain/image/cache/catalog/roman-category-940x550.jpg",
   "badge": "Fabric Pleats",
   "description": "Crisp geometric fabric folds uniting traditional drapery appeal with compact mechanical ease.",
   "wide": 0
  },
  {
   "title": "Printed Blinds",
   "route": "/printed",
   "image": "/assets/kayan_curtain/image/cache/catalog/category-banners/printed-940x550.jpg",
   "badge": "Custom Print",
   "description": "Bespoke high-definition imagery and company logo printing on solar-protective textiles.",
   "wide": 0
  }
 ],
 "social_links": [
  {
   "platform": "WhatsApp",
   "icon": "fa-brands fa-whatsapp",
   "url": "https://wa.me/966555465718"
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


# set once the footer fields have been filled from today's footer; until then
# an empty Maroof link means "never set", not "hide the badge"
FOOTER_SEEDED = "curtain_roll_footer_seeded"


def _route(value):
	return "/" + (value or "").strip().strip("/")


def _withdrawn(doc):
	"""Pages the team has switched off - not to be served even by their link.

	A page is withdrawn when its menu item is switched off (and no other menu
	item still points at it), or when its product's Enabled tick is off. The
	home page never is: switching off the Home button only hides the button.
	"""
	on, off = set(), set()
	for row in doc.get("nav_items") or []:
		(on if row.get("enabled") else off).add(_route(row.get("route")))
	out = off - on
	try:
		out |= {_route(k) for k in frappe.get_all("Curtain Product", filters={"enabled": 0},
		                                          pluck="product_key")}
	except Exception:
		pass
	out.discard("/")
	return sorted(out)


# Paths that are never a storefront page, so are never checked.
NOT_PAGES = ("/api/", "/assets/", "/files/", "/private/", "/app", "/desk", "/maps/",
             "/three/", "/login", "/logout", "/socket.io")


def block_withdrawn():
	"""before_request: a switched-off page sends the shopper to the home page.

	Hiding a page from the menu left it one typed address away. Raising "not
	found" here gives Frappe's bare error screen, with a Show Error button -
	nothing a shopper should land on - so an old link or a typed address goes
	to the home page instead. Search no longer offers the page either.
	"""
	try:
		path = (frappe.request.path or "/").rstrip("/") or "/"
	except Exception:
		return
	if path == "/" or path.startswith(NOT_PAGES):
		return
	if path in (storefront_settings().get("withdrawn") or ()):
		frappe.local.flags.redirect_location = "/"
		raise frappe.Redirect(302)   # temporary: switched back on, it works again


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
	              "collections_description",
	              "bank_name", "bank_account_name", "bank_account_number",
	              "bank_iban",
	              "bank_instructions", "alert_role", "alert_emails",
	              "aramex_origin_city", "aramex_product_type",
	              "footer_about", "footer_about_ar", "copyright_text", "contact_phone",
	              "contact_whatsapp", "contact_email", "contact_address",
	              "contact_address_ar"):
		value = (doc.get(plain) or "").strip()
		if value:
			data[plain] = value

	# Ticks and numbers, which cannot go through the loop above: an unticked box
	# is 0, and `0 or ""` is falsy, so "off" would read as "never set" and fall
	# back to the default - leaving a setting the client has deliberately turned
	# off still on. They are read as-is, and only a genuinely absent field keeps
	# its default.
	for switch in ("vat_rate", "prices_include_vat", "card_enabled",
	               "bank_transfer_enabled", "guest_checkout",
	               "require_national_address", "hide_features",
	               "no_customer_emails", "aramex_enabled",
	               "aramex_weight_per_sqm", "aramex_min_weight"):
		if doc.get(switch) is not None:
			data[switch] = doc.get(switch)

	nav = _rows(doc, "nav_items", ("label", "route", "icon"))
	if nav:
		data["nav_items"] = nav
	data["withdrawn"] = _withdrawn(doc)
	slides = _rows(doc, "slides", ("image", "alt_text", "link"))
	if slides:
		data["slides"] = slides
	features = _rows(doc, "features",
	                 ("icon", "title", "text", "title_ar", "text_ar"))
	if features:
		data["features"] = features
	cards = _rows(doc, "categories",
	              ("title", "route", "image", "badge", "description", "wide"))
	if cards:
		data["categories"] = cards
	social = _rows(doc, "social_links", ("platform", "icon", "url"))
	if social:
		data["social_links"] = social
	links = _rows(doc, "footer_links", ("column", "label", "label_ar", "link"))
	if links or doc.get("footer_links"):
		data["footer_links"] = links
	if doc.get("maroof_url") is not None and frappe.db.get_default(FOOTER_SEEDED):
		data["maroof_url"] = (doc.get("maroof_url") or "").strip()
	data["contact_whatsapp"] = "".join(c for c in str(data.get("contact_whatsapp") or "") if c.isdigit())

	frappe.cache().set_value(CACHE_KEY, data)
	return data


def storefront_lang():
	"""The language this request is being rendered in, for the templates.

	Not folded into storefront_settings: that is cached once for every visitor,
	and the language is per request - baking it in would serve whichever
	language happened to fill the cache to everybody after them.

	Named for the storefront, like storefront_settings, because Jinja hooks from
	every app share one namespace and a bare `current` or `lang` would collide.
	"""
	from kayan_curtain.language import current

	return current()
