app_name = "curtain_roll"
app_title = "Curtain Roll"
app_publisher = "Curtain Roll"
app_description = "Curtain Roll storefront — 10 pages with the 3D curtain configurator"
app_email = "info@curtain-roll.com"
app_license = "mit"

# ---------------------------------------------------------------- assets
# Loaded on every website page. The configurator libraries are NOT included
# here on purpose — they are pulled in per product page, in a fixed order,
# by templates/includes/product_scripts.html
web_include_css = "/assets/curtain_roll/css/curtain.css"

# ---------------------------------------------------------------- jinja
jinja = {
	"methods": [
		"curtain_roll.utils.get_product",
		"curtain_roll.utils.get_products",
		"curtain_roll.utils.asset",
		# the home page's editable content - logo, category bar, slider, cards
		"curtain_roll.storefront.storefront_settings",
	]
}

# ---------------------------------------------------------------- renderers
# The ported Journal3 pages still call OpenCart's /index.php endpoints. Without
# this the theme alert()s Frappe's HTML 404 page at the visitor.
page_renderer = ["curtain_roll.renderers.OpenCartStub"]

# ClickPay redirects the customer's browser back to us with a POST. That POST
# carries their session cookie but no CSRF token, because it originates on
# ClickPay's page - so Frappe would answer 403 to someone who has just paid.
# The hook exempts that one path; nothing trusts the POST anyway, since both
# it and the callback are signature-checked against the server key.
before_request = [
	"curtain_roll.clickpay.allow_gateway_post",
	# the storefront's language comes from the visitor's own choice, not
	# from a cached User record - see language.apply_language
	"curtain_roll.language.apply_language",
]

# The ported pages keep their English inside {% raw %}, so Jinja - and with it
# _() - never sees it. Arabic is swapped into the finished HTML instead, in one
# place, so a page added later is covered without anyone wiring it up.
after_request = ["curtain_roll.language.finish_page"]

# ---------------------------------------------------------------- install
after_install = "curtain_roll.install.after_install"
after_migrate = "curtain_roll.install.after_migrate"
before_uninstall = "curtain_roll.install.before_uninstall"

# ---------------------------------------------------------------- website
website_context = {
	"favicon": "/assets/curtain_roll/image/favicon.png",
	"splash_image": "/assets/curtain_roll/image/favicon.png",
}
