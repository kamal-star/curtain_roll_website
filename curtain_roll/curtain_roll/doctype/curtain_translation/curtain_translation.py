"""One storefront phrase, in English and in Arabic.

The Arabic started life in a file in the repository, which meant only a
developer could correct it. Curtain terminology is the client's to decide -
"ستائر رول" against "ستائر دوّارة" is a judgement about how their customers
speak, not a technical question - so the phrases live here, where the people
who know the answer can change them without asking anyone.

The file is still the seed: a new site is filled from it once, and from then on
this table wins. Nothing here is ever overwritten by a deploy.
"""
import hashlib

import frappe
from frappe.model.document import Document

CACHE_KEY = "curtain_roll_phrases"


def fingerprint(text):
	"""Identify a phrase by its content, with whitespace ignored.

	The same sentence can arrive from the page with different line wrapping,
	and it is still the same sentence. Hashing the collapsed form keeps one
	row per phrase and makes the uniqueness check reliable.
	"""
	body = " ".join((text or "").split())
	return hashlib.sha1(body.encode("utf-8")).hexdigest()


class CurtainTranslation(Document):
	def before_save(self):
		self.source_key = fingerprint(self.source_text)
		if self.arabic:
			self.arabic = self.arabic.strip()

	def on_update(self):
		clear_phrase_cache()

	def on_trash(self):
		clear_phrase_cache()


def clear_phrase_cache():
	"""Let the website see an edit at once.

	Someone correcting a word expects to reload the page and see it. Without
	this they would wait for the next cache expiry and reasonably conclude the
	field does not work.
	"""
	frappe.cache().delete_value(CACHE_KEY)
