"""A cart that belongs to a browser rather than to a person.

Shopping does not require an account, so this holds the lines until the visitor
either signs in - when they move into their Quotation - or checks out, when the
customer record is finally made. Nothing here identifies anyone: the name is a
random token, and the only thing linking it to a browser is that browser's own
cookie.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime, nowdate

# How long an abandoned cart is kept. Long enough that someone measuring their
# windows over a weekend comes back to their configuration; short enough that
# the table does not become a record of everyone who ever visited.
KEEP_DAYS = 30


class CurtainGuestCart(Document):
	def before_save(self):
		self.last_seen = now_datetime()
		for row in self.get("items") or []:
			row.amount = frappe.utils.flt(row.qty) * frappe.utils.flt(row.rate)


def clear_stale():
	"""Daily: delete carts nobody has touched in a month.

	Called from the scheduler. These are anonymous rows with no owner to ask,
	so keeping them forever would be collecting data for no purpose.
	"""
	cutoff = add_days(nowdate(), -KEEP_DAYS)
	stale = frappe.get_all("Curtain Guest Cart",
	                       filters={"modified": ["<", cutoff]}, pluck="name")
	for name in stale:
		try:
			frappe.delete_doc("Curtain Guest Cart", name, force=True,
			                  ignore_permissions=True, delete_permanently=True)
		except Exception:
			frappe.log_error(title="kayan_curtain: stale guest cart %s" % name)
	if stale:
		frappe.db.commit()
	return len(stale)
