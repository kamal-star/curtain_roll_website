import frappe
from frappe.model.document import Document


class CurtainInstallCity(Document):
	def validate(self):
		self.city = (self.city or "").strip()
		if self.price and self.price < 0:
			frappe.throw(frappe._("The installation price cannot be negative."))
