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

		for slab in self.get("size_slabs") or []:
			if slab.to_sqm and slab.to_sqm < slab.from_sqm:
				frappe.throw(_("Size slab row {0}: To must be greater than From.")
				             .format(slab.idx))

	def on_update(self):
		# the storefront reads a cached, flattened copy of this record
		from curtain_roll.pricing import clear_cache

		clear_cache(self.product_key)

	def on_trash(self):
		from curtain_roll.pricing import clear_cache

		clear_cache(self.product_key)
