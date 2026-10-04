"""The storefront blog: published Curtain Blog Posts, in the visitor's language."""

import frappe

from kayan_curtain.language import current


def posts(limit=None):
	"""Published articles, newest first, with the fields the list needs."""
	ar = current() == "ar"
	rows = frappe.get_all(
		"Curtain Blog Post", filters={"published": 1},
		fields=["name", "route", "title", "title_ar", "summary", "summary_ar",
		        "cover_image", "published_on"],
		order_by="published_on desc, creation desc", limit_page_length=limit or 0)
	for r in rows:
		r.shown_title = r.title_ar if ar and r.title_ar else r.title
		r.shown_summary = (r.summary_ar if ar and r.summary_ar else r.summary) or ""
		r.url = "/blogs/%s" % r.route
	return rows
