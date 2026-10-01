"""Words from Curtain Info Page (curtain_roll.info_pages), in the visitor's
language - so the rendered page must not be cached and served to everyone."""


def get_context(context):
	context.no_cache = 1
