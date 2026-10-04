"""The search results page.

Named search.py for search.html deliberately: Frappe turns a page's route into
a module name by swapping hyphens for underscores, so a controller whose
filename does not already match that form is never imported and its context
never reaches the template - silently, because Jinja treats the missing
variables as undefined rather than as an error.
"""

import frappe
from frappe import _

from kayan_curtain import search


def get_context(context):
	query = (frappe.form_dict.get("q") or "").strip()

	context.query = query
	context.results, context.guessed = \
		search.find(query) if query else ([], False)

	# the query alone, not "Search results for X": the Arabic pass matches whole
	# text nodes, so a sentence with the query interpolated into it is a string
	# that can never be in the dictionary and would stay English on an Arabic
	# page. What the shopper typed needs no translating.
	context.title = query or _("Search")

	# the results depend on the query string and on the visitor's language, so
	# there is nothing here worth keeping in the page cache
	context.no_cache = 1
