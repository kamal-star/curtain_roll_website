import frappe
from frappe import _
from frappe.model.document import Document

from curtain_roll.utils import get_product, get_products


class CurtainProduct(Document):
	def validate(self):
		if not get_product(self.product_key):
			frappe.throw(
				_("{0} is not a storefront page. Use one of: {1}").format(
					frappe.bold(self.product_key),
					", ".join(p["key"] for p in get_products()),
				)
			)

		self._adopt_new_colors()

		seen = set()
		for row in self.get("colors") or []:
			if row.option_value in seen:
				frappe.throw(_("Row {0}: colour {1} is listed twice.")
				             .format(row.idx, frappe.bold(row.color_name)))
			seen.add(row.option_value)

		seen = set()
		for row in self.get("options") or []:
			ident = (row.group_id, row.option_value)
			if ident in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.")
				             .format(row.idx, frappe.bold(row.option_label)))
			seen.add(ident)

		# A row added and then left blank would price every size at nothing,
		# so drop it rather than saving a trap.
		self.set("size_slabs", [
			s for s in (self.get("size_slabs") or [])
			if s.rate or s.from_sqm or s.to_sqm
		])

		for slab in self.get("size_slabs") or []:
			if slab.to_sqm and slab.to_sqm < slab.from_sqm:
				frappe.throw(_("Size slab row {0}: To must be greater than From.")
				             .format(slab.idx))
			if not slab.rate:
				frappe.throw(_("Size slab row {0}: enter a rate, or remove the row.")
				             .format(slab.idx))

	def _adopt_new_colors(self):
		"""Give a colour typed into the grid what it needs to reach the site.

		A captured swatch already has a storefront id and an image baked into
		the page HTML. A colour added here has neither, so it gets an id of its
		own - prefixed so it can never collide with a catalogue one - and is
		marked custom, which is what keeps a later resync from pruning it.
		"""
		for row in self.get("colors") or []:
			if row.option_value and not row.is_custom:
				continue

			row.is_custom = 1
			if not row.option_value:
				row.option_value = "c" + frappe.generate_hash(length=10)
			if not row.fabric_image:
				frappe.throw(
					_("Row {0}: upload a Fabric Photo for {1}. Without it the colour "
					  "has no swatch on the site and nothing for the 3D preview to show.")
					.format(row.idx, frappe.bold(row.color_name or _("this colour")))
				)
			if not row.texture_code:
				row.texture_code = row.color_name
			row.image = row.fabric_image

	def on_update(self):
		# the storefront reads a cached, flattened copy of this record
		from curtain_roll.pricing import clear_cache

		clear_cache(self.product_key)

	def on_trash(self):
		from curtain_roll.pricing import clear_cache

		clear_cache(self.product_key)
