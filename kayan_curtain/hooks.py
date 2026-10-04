app_name = "kayan_curtain"
app_title = "Kayan Andalus"
app_publisher = "Kayan Andalus"
app_description = "Kayan Andalus storefront with the 3D curtain configurator"
app_email = ""
app_license = "mit"

# ---------------------------------------------------------------- assets
# Loaded on every website page. The configurator libraries are NOT included
# here on purpose — they are pulled in per product page, in a fixed order,
# by templates/includes/product_scripts.html
web_include_css = "/assets/kayan_curtain/css/curtain.css"

# ---------------------------------------------------------------- jinja
jinja = {
	"methods": [
		"kayan_curtain.utils.get_product",
		"kayan_curtain.utils.get_products",
		"kayan_curtain.utils.asset",
		# the home page's editable content - logo, category bar, slider, cards
		"kayan_curtain.storefront.storefront_settings",
		# which language a request is in, for text the client edits in two
		# languages rather than leaving to the dictionary
		"kayan_curtain.storefront.storefront_lang",
		# About Us, Terms, Privacy, Delivery, Contact Us - Curtain Info Page
		"kayan_curtain.info_pages.info_page",
	]
}

# ---------------------------------------------------------------- renderers
# The ported Journal3 pages still call OpenCart's /index.php endpoints. Without
# this the theme alert()s Frappe's HTML 404 page at the visitor.
page_renderer = [
	"kayan_curtain.renderers.OpenCartStub",
	# /logout signs out and lands on the home page; /login passes a signed-in
	# visitor on with a redirect browsers do not cache. See renderers.py.
	"kayan_curtain.renderers.SignOut",
	"kayan_curtain.renderers.SignedInLogin",
]

# ClickPay redirects the customer's browser back to us with a POST. That POST
# carries their session cookie but no CSRF token, because it originates on
# ClickPay's page - so Frappe would answer 403 to someone who has just paid.
# The hook exempts that one path; nothing trusts the POST anyway, since both
# it and the callback are signature-checked against the server key.
before_request = [
	"kayan_curtain.clickpay.allow_gateway_post",
	# the storefront's language comes from the visitor's own choice, not
	# from a cached User record - see language.apply_language
	"kayan_curtain.language.apply_language",
	# a page the team switched off is not served by its link either
	"kayan_curtain.storefront.block_withdrawn",
]

# The ported pages keep their English inside {% raw %}, so Jinja - and with it
# _() - never sees it. Arabic is swapped into the finished HTML instead, in one
# place, so a page added later is covered without anyone wiring it up.
after_request = ["kayan_curtain.language.finish_page"]

# The storefront templates' `_()` asks the client's dictionary before ERPNext's.
# Without it ERPNext's accounting vocabulary wins - "Total" read as "total
# excluding tax" above a VAT-inclusive total - and the client's own corrections
# in Curtain Translation lose to it. See language.storefront_translate.
update_website_context = ["kayan_curtain.language.website_context"]

# one blog article per address: /blogs/<link name> is served by blog-post.html
website_route_rules = [
	{"from_route": "/blogs/<post>", "to_route": "blog-post"},
]

# A basket filled before signing in belongs to the person who filled it. Without
# this, signing in at the checkout - to use a saved address, say - empties the
# cart they were about to pay for.
on_session_creation = ["kayan_curtain.cart.claim_guest_cart"]

# Anonymous carts nobody came back to. Keeping them for ever would be collecting
# data about visitors for no purpose at all.
scheduler_events = {
	"daily": [
		"kayan_curtain.kayan_curtain.doctype.curtain_guest_cart.curtain_guest_cart.clear_stale",
	],
}

# ------------------------------------------------------------ documents
# A card payment is made as a draft Payment Entry before its invoice is
# submitted; submitting the invoice is when the two can be tied together
doc_events = {
	"Sales Invoice": {
		"on_submit": "kayan_curtain.orders.link_payment",
	},
}

# ---------------------------------------------------------------- install
after_install = "kayan_curtain.install.after_install"
after_migrate = "kayan_curtain.install.after_migrate"
before_uninstall = "kayan_curtain.install.before_uninstall"

# ---------------------------------------------------------------- website
website_context = {
	"favicon": "/assets/kayan_curtain/image/favicon.png",
	"splash_image": "/assets/kayan_curtain/image/favicon.png",
}
