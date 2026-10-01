"""One blog article, at /blogs/<link name> (website_route_rules in hooks.py).

Named blog_post.py for blog-post.html: Frappe imports a page's controller by
its route with hyphens turned into underscores.
"""

import frappe
from frappe import _

from curtain_roll.language import current


def get_context(context):
	route = (frappe.form_dict.get("post") or "").strip()
	name = frappe.db.get_value("Curtain Blog Post", {"route": route, "published": 1}, "name")
	if not name:
		raise frappe.PageDoesNotExistError

	post = frappe.get_doc("Curtain Blog Post", name)
	ar = current() == "ar"
	context.post = post
	context.post_title = post.title_ar if ar and post.title_ar else post.title
	context.post_content = (post.content_ar if ar and post.content_ar else post.content) or ""
	context.title = context.post_title
	context.metatags = {
		"title": context.post_title,
		"description": (post.summary_ar if ar and post.summary_ar else post.summary) or "",
		"image": post.cover_image or "",
	}

	from curtain_roll import blog

	context.more = [p for p in blog.posts(limit=4) if p.name != post.name][:3]
	context.no_cache = 1
