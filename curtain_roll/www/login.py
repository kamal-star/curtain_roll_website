"""The storefront's own login page, in place of Frappe's.

Frappe's /login controller still does the work - it sends someone already
signed in on to where they were going, and finds the Social Login Keys
(Google, Facebook) that are set up and enabled - and this page only draws the
result in the site's own design. Logging in, the password reset and the
sign-up all go to Frappe's own endpoints, unchanged.
"""

import frappe
from frappe.utils import cint


def get_context(context):
	from frappe.www.login import get_context as frappe_login, sanitize_redirect

	frappe_login(context)          # raises a redirect for someone signed in

	req = getattr(frappe.local, "request", None)
	asked = req.args.get("redirect-to") if req is not None else None
	context.redirect_to = sanitize_redirect(asked) or "/"

	# Facebook first, then Google, as the client's design has them; anything
	# else that is set up follows
	order = {"facebook": 0, "google": 1}
	context.providers = sorted(
		context.get("provider_logins") or [],
		key=lambda p: order.get((p.get("provider_name") or p.get("name") or "").lower(), 9))

	context.allow_mobile = cint(frappe.get_system_settings("allow_login_using_mobile_number"))
	context.allow_signup = not cint(context.get("disable_signup"))
	context.title = "Login"
	context.no_cache = 1
	return context
