"""A product a customer has saved.

Previously the wish list lived in the Redis cache. That looked fine in testing
and quietly lost every customer's list on each `bench clear-cache`, every
migrate and every deploy - the cache is not storage, and a wish list that
disappears when the site is updated is worse than none.
"""
import frappe
from frappe.model.document import Document


class CurtainWishlistItem(Document):
	pass
