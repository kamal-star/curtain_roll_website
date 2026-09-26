"""What the team can change on the home page without a developer.

The page was a captured static file: the logo, the slider, the category bar and
the collection cards were all baked into the markup, so every one of them was a
developer job. They are read from here now.

Saving clears the cached copy, so an edit shows on the site on the next page
load rather than whenever a cache happened to expire.
"""
import frappe
from frappe.model.document import Document

CACHE_KEY = "curtain_roll_storefront"


class CurtainStorefrontSettings(Document):
	def on_update(self):
		frappe.cache().delete_value(CACHE_KEY)
		# the pages themselves are cached HTML, so the copy on disk has to go
		# too or an edit would not show until something else cleared it
		frappe.clear_cache()
