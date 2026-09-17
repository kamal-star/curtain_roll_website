from curtain_roll.utils import get_products


def get_context(context):
	context.products = get_products()
	context.title = "Curtain Roll"
	context.hero = next((p["main_image"] for p in context.products if p.get("main_image")), "")
	return context
