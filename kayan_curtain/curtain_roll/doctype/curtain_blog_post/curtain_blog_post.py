import frappe
from frappe.model.document import Document


def link_name(text):
	"""how-to-measure-windows: lower case, hyphens, nothing a URL would mangle."""
	return frappe.scrub((text or "").strip()).replace("_", "-").strip("-")[:120]


class CurtainBlogPost(Document):
	def before_insert(self):
		# the link name is the record's name (autoname field:route), and naming
		# happens right after this - so it is settled here, not in validate
		self.route = link_name(self.route) or link_name(self.title)
		if not self.route:
			frappe.throw(frappe._("Give the article a Link Name, e.g. how-to-measure-windows."))
