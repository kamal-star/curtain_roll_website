import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from kayan_curtain.utils import get_product, get_products


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
		self._check_sub_option_parents()
		self._adopt_new_colors()
		self._prepare_room()

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

	def _check_sub_option_parents(self):
		"""Every dependent choice must sit under a choice this product has.

		"Shown Under" is typed, and a typo - "5cm" for "5 cm" - would not fail
		anywhere: the row would simply never appear on the site, and nobody
		would know why the colours had gone. So it fails here, with the names
		it could have meant.
		"""
		names = {(o.option_label or "").strip().lower()
		         for o in self.get("options") or []}
		names |= {(c.color_name or "").strip().lower()
		          for c in self.get("colors") or []}
		# Manual / Motorized also match a control spelled differently
		names |= {"manual", "motorized", "motorised"}
		# a group shown on its own, under no choice
		from kayan_curtain.pricing import ALWAYS
		names |= set(ALWAYS)
		names.discard("")
		for row in self.get("sub_options") or []:
			parent = (row.parent_choice or "").strip()
			if not parent:
				frappe.throw(_("Row {0} of Choices: fill in Shown Under.").format(row.idx))
			if parent.lower() not in names:
				known = sorted({(o.option_label or "").strip() for o in self.get("options") or []}
				               | {(c.color_name or "").strip() for c in self.get("colors") or []})
				frappe.throw(_("Row {0} of Choices: {1} is not a choice on this product. "
				               "Use one of: {2}, or Always").format(
					row.idx, frappe.bold(parent), ", ".join(k for k in known if k)))

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

	def _prepare_room(self):
		"""3D Room: size a newly uploaded picture for the sphere, and check the box."""
		from kayan_curtain import room

		before = self.get_doc_before_save()
		if self.room_image != (before.room_image if before else None) or \
				(self.room_image and not self.room_scene):
			room.prepare_scene(self)
		if not self.room_image:
			self.room_window = ""
			return
		if not room.parse_box(self.room_window):
			# the page keeps its own room until the box is placed on the window
			self.room_window = ""
			frappe.msgprint(_("Room picture saved. Now drag the box over the window where the "
			                  "blind should hang, then save again. Until then the page keeps "
			                  "its own room."), indicator="blue")

	def on_update(self):
		# the storefront reads a cached, flattened copy of this record
		from kayan_curtain.pricing import clear_cache
		from kayan_curtain.room import clear as clear_room
		from kayan_curtain.kayan_curtain.doctype.curtain_translation.curtain_translation \
			import clear_phrase_cache

		clear_cache(self.product_key)
		clear_room(self.product_key)
		from kayan_curtain.page_text import clear as clear_text
		clear_text(self.product_key)
		# switching a product off withdraws its page; the list sits with the
		# storefront settings
		from kayan_curtain.storefront import CACHE_KEY as STOREFRONT_KEY
		frappe.cache().delete_value(STOREFRONT_KEY)
		# the Arabic typed on the Manual / Motorized choices is part of the
		# phrase dictionary, so a correction there must show without a restart
		clear_phrase_cache()

	def on_trash(self):
		from kayan_curtain.pricing import clear_cache

		clear_cache(self.product_key)
