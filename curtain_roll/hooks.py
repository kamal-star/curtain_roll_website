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
	]
}

# ---------------------------------------------------------------- renderers
# The ported Journal3 pages still call OpenCart's /index.php endpoints. Without
# this the theme alert()s Frappe's HTML 404 page at the visitor.
page_renderer = ["curtain_roll.renderers.OpenCartStub"]

# ---------------------------------------------------------------- install
after_install = "curtain_roll.install.after_install"
after_migrate = "curtain_roll.install.after_migrate"
before_uninstall = "curtain_roll.install.before_uninstall"

# ---------------------------------------------------------------- website
website_context = {
	"favicon": "/assets/curtain_roll/image/favicon.png",
	"splash_image": "/assets/curtain_roll/image/favicon.png",
}
