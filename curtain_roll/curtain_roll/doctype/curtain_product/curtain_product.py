import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

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

		self._check_limits()
		self._check_material_switch()
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

	def _check_limits(self):
		"""A range has to be a range, or nothing can be ordered at all.

		Caught here rather than on the storefront, because a minimum above the
		maximum refuses every size a customer types while looking exactly like
		the site is broken.
		"""
		for low, high, what in (("min_width", "max_width", _("Width")),
		                        ("min_height", "max_height", _("Height"))):
			bottom, top = flt(self.get(low)), flt(self.get(high))
			if bottom and top and bottom > top:
				frappe.throw(
					_("{0}: the minimum ({1} cm) is above the maximum ({2} cm), "
					  "so no size could be ordered.")
					.format(what, bottom, top))
			if bottom < 0 or top < 0:
				frappe.throw(_("{0}: a size limit cannot be negative.").format(what))

	def _check_material_switch(self):
		"""Refuse to hide the material on a product whose price IS the material.

		With Price Driven By set to Material Rate, the chosen swatch carries the
		rate per square metre. Hide the swatches and there is no rate to find,
		so every order falls back to the minimum price - quietly, and in the
		customer's favour. Better to say so here than to sell blinds at the
		floor price for a fortnight.
		"""
		if cint(self.get("show_material")):
			return
		switch = frappe.bold(_("Show Fabric / Material Choices"))
		if self.pricing_mode == "Material Rate":
			frappe.throw(
				_("This product is priced by its material, so the material "
				  "choices cannot be hidden. Either set Price Driven By to Base "
				  "Rate and give it a rate of its own, or leave {0} ticked.")
				.format(switch))
		# The same trap by another route: a base-rate product whose base rate
		# is 0 and has no minimum would sell for nothing without a swatch.
		if not flt(self.base_rate) and not flt(self.minimum_price):
			frappe.throw(
				_("Without the material choices this product has no price - its "
				  "Base Rate is 0 and it has no Minimum Order Price. Set one of "
				  "them, or leave {0} ticked.").format(switch))

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
