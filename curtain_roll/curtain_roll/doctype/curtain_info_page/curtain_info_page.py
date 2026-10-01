import frappe
from frappe.model.document import Document


class CurtainInfoPage(Document):
	def on_update(self):
		# the page reads a cached copy of this record, and Frappe may hold the
		# rendered page too - both go, so a save shows on the next page load
		frappe.clear_document_cache(self.doctype, self.name)
		try:
			from frappe.website.utils import clear_cache

			clear_cache(self.name)
		except Exception:
			pass
