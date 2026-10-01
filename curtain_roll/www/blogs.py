"""The blog list: every published Curtain Blog Post, newest first."""

from frappe import _

from curtain_roll import blog


def get_context(context):
	context.title = _("Blog")
	context.posts = blog.posts()
	# a new article must show at once, and the language changes per visitor
	context.no_cache = 1
