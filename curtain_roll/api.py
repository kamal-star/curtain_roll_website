import base64
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from curtain_roll.utils import get_product

MAX_IMAGE_BYTES = 4 * 1024 * 1024
DATA_URL = re.compile(r"^data:image/(png|jpe?g|webp);base64,(.+)$", re.S)


@frappe.whitelist(allow_guest=True)
def csrf_token():
	"""Hand the current session's CSRF token to the ported storefront pages.

	Those pages are raw theme HTML with no Frappe boot script, so the theme's
	jQuery AJAX sends no token and Frappe rejects every POST with
	CSRFTokenError. Baking the token into the HTML does not work either -
	website pages are cached, so visitors get a stale or blank token.

	Fetching it live sidesteps the cache. This is a GET (exempt from CSRF) and
	same-origin only, so another site cannot read the response.
	"""
	return {"token": (frappe.session.data.get("csrf_token") or "") if frappe.session else ""}


@frappe.whitelist()
def cart_set_qty(item_code=None, qty=0):
	"""Change a cart line's quantity (0 removes it). Login required."""
	from curtain_roll import cart as cart_api

	if not item_code:
		frappe.throw(_("Missing item"))
	return cart_api.set_qty(item_code, qty)


@frappe.whitelist()
def cart_place_order():
	"""Submit the draft cart quotation. Login required."""
	from curtain_roll import cart as cart_api

	return cart_api.place_order()


@frappe.whitelist(allow_guest=True)
def session_info():
	"""Who is browsing, and what is in their cart.

	The ported pages are static theme snapshots, so their header always renders
	the logged-out state. The storefront script calls this on load and swaps the
	Login/Register links for the account links when someone is signed in.
	"""
	from curtain_roll import cart as cart_api

	guest = cart_api.is_guest()
	info = cart_api.info()
	return {
		"logged_in": not guest,
		"full_name": (frappe.db.get_value("User", frappe.session.user, "full_name")
		              if not guest else ""),
		"cart_text": info.get("text"),
		"cart_count": info.get("count") or 0,
		"cart_items": [
			{
				"name": i.get("name") or i.get("item_code"),
				"qty": i.get("qty"),
				"amount": i.get("amount"),
			}
			for i in (info.get("items") or [])
		],
		"csrf_token": (frappe.session.data.get("csrf_token") or "") if frappe.session else "",
	}


def _clean(value, limit=140):
	return (value or "").strip()[:limit]


def _num(value):
	"""Parse a user-entered dimension; returns None if it isn't a positive number."""
	try:
		n = float(str(value).strip())
	except (TypeError, ValueError):
		return None
	return n if n > 0 else None


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=10, seconds=60 * 60)
def submit_quote(product=None, name=None, phone=None, email=None, city=None,
                 notes=None, selections=None, captured_image=None,
                 width=None, height=None, quantity=None):
	"""Public endpoint behind the 'Request a quote' form on each product page.

	Creates a Lead and attaches the configurator render, if one was captured.

	The original storefront is made-to-measure: it collects width and height as
	option[<id>][width] / [height], so they are captured here too. The final
	price still comes from the team, since the live site recalculates it with a
	server-side formula we do not have.
	"""
	product_key = _clean(product, 40)
	item = get_product(product_key)
	if not item:
		frappe.throw(_("Unknown product"))

	person = _clean(name)
	if not person:
		frappe.throw(_("Please enter your name"))

	phone = _clean(phone, 40)
	email = _clean(email)
	if not phone and not email:
		frappe.throw(_("Please enter a phone number or an email address"))

	lead = frappe.new_doc("Lead")
	lead.lead_name = person
	lead.status = "Lead"
	lead.mobile_no = phone
	if email:
		lead.email_id = email
	if city:
		lead.city = _clean(city, 60)
	lead.insert(ignore_permissions=True)

	summary = [
		"%s: %s" % (_("Product"), item.get("heading") or product_key),
		"%s: SR %s" % (_("Starting price"), item.get("price")),
	]

	w, h = _num(width), _num(height)
	if w and h:
		summary.append("%s: %g x %g cm (%.2f m²)" % (_("Size"), w, h, (w * h) / 10000.0))
	elif w or h:
		summary.append("%s: %s x %s cm" % (_("Size"), width or "?", height or "?"))

	qty = _num(quantity)
	if qty and qty != 1:
		summary.append("%s: %g" % (_("Quantity"), qty))

	if selections:
		summary.append("%s: %s" % (_("Selections"), _clean(selections, 900)))
	if notes:
		summary.append("%s: %s" % (_("Notes"), _clean(notes, 900)))

	lead.add_comment(
		"Comment",
		"<br>".join(frappe.utils.escape_html(line) for line in summary),
	)

	file_url = _attach_render(lead, captured_image, product_key)
	frappe.db.commit()

	return {
		"ok": True,
		"lead": lead.name,
		"image": file_url,
		"message": _("Thank you — we will contact you shortly."),
	}


def _attach_render(lead, captured_image, product_key):
	"""Save the configurator's base64 render as a File attached to the Lead."""
	if not captured_image:
		return None
	match = DATA_URL.match(captured_image.strip())
	if not match:
		return None

	ext, payload = match.group(1), match.group(2)
	try:
		content = base64.b64decode(payload)
	except Exception:
		return None
	if not content or len(content) > MAX_IMAGE_BYTES:
		return None

	ext = "jpg" if ext in ("jpeg", "jpg") else ext
	doc = frappe.get_doc({
		"doctype": "File",
		"file_name": "curtain-%s-%s.%s" % (product_key, lead.name, ext),
		"attached_to_doctype": "Lead",
		"attached_to_name": lead.name,
		"is_private": 1,
		"content": content,
	})
	doc.insert(ignore_permissions=True)
	return doc.file_url
