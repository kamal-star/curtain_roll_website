# -*- coding: utf-8 -*-
"""The 3D room a product shows, when the team has chosen one.

Curtain Product -> 3D Room holds an uploaded 360-degree picture and the box
the team drew over its window. When both are set, the product's page gets
the picture and the box ahead of its 3D bundle (see language._add_room), and
public/js/curtain_room.js fits the blind to the box. Without them the page
keeps the room it was built with.
"""

import hashlib
import io

import frappe
from frappe import _

CACHE_KEY = "curtain_roll_room:%s"
SIZE = (4096, 2048)          # what the 3D sphere is made for

# How deep each 3D model puts its blind when its page opens. A blind nearer
# than this is mounted Outside and is shown a little bigger than the box.
# Measured off the pages; a variant uses its base model's.
ANCHOR_Z = {"blackout": -425, "wooden": -415, "vertical": -325, "zebra": -425,
            "roman": -360, "metal": -428, "sunscreen": -400, "printed": -400}


def _anchor(key):
	from curtain_roll.utils import get_product

	product = get_product(key) or {}
	return ANCHOR_Z.get(product.get("variant_of") or key)


def parse_box(text):
	"""'l,t,r,b' as fractions of the picture -> [l, t, r, b], or None."""
	try:
		box = [float(x) for x in (text or "").split(",")]
	except ValueError:
		return None
	if len(box) != 4:
		return None
	l, t, r, b = box
	if not (0 <= l < r <= 1 and 0 <= t < b <= 1):
		return None
	return box


def room_config(key):
	"""{"url", "box", "anchor"} for the product's chosen room, or {}."""
	if not key:
		return {}
	cached = frappe.cache().get_value(CACHE_KEY % key)
	if cached is not None:
		return cached
	out = {}
	try:
		row = frappe.db.get_value("Curtain Product", {"product_key": key},
		                          ["room_scene", "room_window"], as_dict=True)
	except Exception:          # before the fields exist (mid-migrate)
		row = None
	box = parse_box(row and row.room_window)
	if row and row.room_scene and box:
		out = {"url": row.room_scene, "box": box, "anchor": _anchor(key)}
	frappe.cache().set_value(CACHE_KEY % key, out, expires_in_sec=6 * 60 * 60)
	return out


def clear(key):
	frappe.cache().delete_value(CACHE_KEY % key)


def prepare_scene(doc):
	"""The uploaded picture made ready for the 3D: checked, sized, stored.

	A 360-degree room is twice as wide as it is tall; anything else is not a
	panorama and would wrap round the sphere warped, so it is refused. It is
	saved at the 4096 x 2048 the sphere is made for, as a new file whose name
	carries its content hash - browsers keep room pictures for a year, so a
	changed room must arrive under a new address.
	"""
	from PIL import Image

	if not doc.room_image:
		doc.room_scene = ""
		return
	f = frappe.get_doc("File", {"file_url": doc.room_image})
	try:
		im = Image.open(io.BytesIO(f.get_content())).convert("RGB")
	except Exception:
		frappe.throw(_("The room picture could not be read as an image."))
	w, h = im.size
	if abs(w / float(h) - 2.0) > 0.12:
		frappe.throw(_("The room picture must be a 360° panorama, twice as wide as it is tall "
		               "(for example 4096 x 2048). This one is {0} x {1}.").format(w, h))
	if w < 2000:
		frappe.msgprint(_("The room picture is only {0} pixels wide; it will look soft. "
		                  "4096 x 2048 is best.").format(w), indicator="orange")
	if (w, h) != SIZE:
		im = im.resize(SIZE, Image.LANCZOS)
	buf = io.BytesIO()
	im.save(buf, "JPEG", quality=90, optimize=True)
	data = buf.getvalue()
	name = "room-%s-%s.jpg" % (doc.product_key, hashlib.md5(data).hexdigest()[:10])
	existing = frappe.db.get_value("File", {"file_name": name, "is_private": 0}, "file_url")
	if not existing:
		existing = frappe.get_doc({"doctype": "File", "file_name": name, "content": data,
		                           "is_private": 0, "attached_to_doctype": "Curtain Product",
		                           "attached_to_name": doc.name}).insert(ignore_permissions=True).file_url
	doc.room_scene = existing
