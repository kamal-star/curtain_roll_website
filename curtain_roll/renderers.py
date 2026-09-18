import json

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

from curtain_roll import cart


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
				frappe.log_error(title="curtain_roll script.php", message=frappe.get_traceback())
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
				frappe.log_error(title="curtain_roll cart", message=frappe.get_traceback())
				payload = {"error": {"warning": "Could not update the cart."}}

		return Response(
			json.dumps(payload).encode("utf-8"),
			status=200,
			mimetype="application/json",
		)
