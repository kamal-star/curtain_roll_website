from curtain_roll.utils import get_product


def get_context(context):
	context.p = get_product("wavy")
	context.title = context.p["title"]
	context.metatags = {
		"title": context.p["title"],
		"description": context.p["meta_description"],
		"keywords": context.p["meta_keywords"],
		"image": "/assets/curtain_roll/" + (context.p["main_image"] or ""),
	}
	return context
