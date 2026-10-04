import json

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

from kayan_curtain import cart, pricing


class OpenCartStub(BaseRenderer):
	"""Answer the OpenCart endpoints the ported Journal3 pages still call.

	The theme posts to /index.php?route=... for cart and wishlist actions and
	reads back ``success`` / ``total`` / ``redirect``. With no OpenCart backend
	Frappe replied with its HTML 404 page, which the theme alert()ed at the
	visitor; returning ``{}`` silenced that but left the buttons dead.

	Cart and wishlist are handled for real (see cart.py). Everything else gets
	a quiet empty object.
	"""

	HTML_ROUTES = ("product/product/review",)

	HANDLERS = {
		"checkout/cart/add": cart.add,
		"checkout/cart/edit": cart.edit,
		"checkout/cart/remove": cart.remove,
		"account/wishlist/add": cart.wishlist_add,
		# the theme re-posts the whole option form here on every change and
		# writes json.total into #total_price, which is how the live price on
		# the page follows the rates set in Curtain Product
		"product/product/add": pricing.price_preview,
	}

	def can_render(self):
		# script.php is the configurator's image upload; ADD TO CART chains
		# through it before the cart call, so it must answer too.
		return self.path in ("index.php", "script.php")

	def _route(self):
		req = getattr(frappe.local, "request", None)
		if req is None:
			return ""
		# form_dict is not reliably populated this early, so read the query
		# string (and the POST body, which is where cart.add sends things)
		return (req.args.get("route") or req.form.get("route") or "").strip()

	def render(self):
		# the configurator's image upload returns a bare URL as plain text
		if self.path == "script.php":
			req = frappe.local.request
			try:
				url = cart.save_render(req.form)
			except Exception:
				frappe.log_error(title="kayan_curtain script.php", message=frappe.get_traceback())
				url = ""
			# Always answer 200: the page chains the real cart call inside this
			# request's .done(), so a failure here would silently kill add-to-cart.
			return Response((url or "").encode("utf-8"), status=200, mimetype="text/plain")

		route = self._route()

		if any(route.endswith(r) for r in self.HTML_ROUTES):
			return Response(b"", status=200, mimetype="text/html")

		payload = {}
		handler = self.HANDLERS.get(route)
		if handler:
			req = frappe.local.request
			try:
				payload = handler(req.args, req.form)
			except Exception:
				frappe.log_error(title="kayan_curtain cart", message=frappe.get_traceback())
				payload = {"error": {"warning": "Could not update the cart."}}

		return Response(
			json.dumps(payload).encode("utf-8"),
			status=200,
			mimetype="application/json",
		)


# --------------------------------------------------------- signing in and out
def _safe_target(raw, fallback="/"):
	"""Where to send the browser next, if it is somewhere on this site.

	Only a path on this site is accepted: `/blackout` yes, `//evil.example`
	and `https://evil.example` no. Otherwise a link to our own login page could
	be used to bounce a customer, freshly signed in, to anybody's site.
	"""
	target = (raw or "").strip()
	if not target.startswith("/") or target.startswith("//") or "\\" in target:
		return fallback
	# never back to the pages that caused the loop in the first place
	if target.split("?")[0].rstrip("/") in ("/login", "/logout"):
		return fallback
	return target


def _see_other(target):
	"""A temporary redirect that no browser keeps.

	302, never 301: a 301 is "moved permanently", and browsers remember it. Frappe
	answered a signed-in visitor at /login with a 301 to the home page, so after
	one visit the browser went on skipping the login form by itself - signed out
	or not - and the customer clicked Login and found themselves where they were.
	"""
	response = Response(status=302)
	response.headers["Location"] = target
	response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
	return response


class SignOut(BaseRenderer):
	"""/logout: sign out and land on the home page, in one request.

	Frappe's /logout is a page whose script signs out and then sends the browser
	to /login. So a customer who logged out was left on a login form - and
	pressing Back from there went to /logout again, which signed them out again
	and sent them straight back to /login. Back did nothing, however many times
	it was pressed.

	Here the sign-out happens on the server and the answer is a redirect to the
	home page. /logout never becomes a page, so it never enters the history,
	and Back goes to wherever the customer really was.
	"""

	def can_render(self):
		return self.path == "logout"

	def render(self):
		if frappe.session.user != "Guest":
			try:
				frappe.local.login_manager.logout()
				frappe.db.commit()
			except Exception:
				frappe.log_error(title="kayan_curtain: sign out",
				                 message=frappe.get_traceback())
		return _see_other("/")


class SignedInLogin(BaseRenderer):
	"""/login for someone already signed in: send them on, temporarily.

	Frappe does the same, but with a 301 - see _see_other for what that did.
	This is also what makes Back after logging in behave: it arrives here, and
	is passed on to the page they came from rather than to the home page.
	"""

	def can_render(self):
		return self.path == "login" and frappe.session.user != "Guest"

	def render(self):
		asked = frappe.form_dict.get("redirect-to")
		if not asked:
			req = getattr(frappe.local, "request", None)
			asked = req.args.get("redirect-to") if req is not None else None
		return _see_other(_safe_target(asked))
