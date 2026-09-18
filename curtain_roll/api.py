import base64
import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from curtain_roll.utils import get_product

MAX_IMAGE_BYTES = 4 * 1024 * 1024
DATA_URL = re.compile(r"^data:image/(png|jpe?g|webp);base64,(.+)$", re.S)


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
