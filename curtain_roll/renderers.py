import json

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response


class OpenCartStub(BaseRenderer):
	"""Answer the OpenCart endpoints the ported Journal3 pages still call.

	The theme's JS posts to /index.php?route=product/product/add (and friends)
	when a swatch or option changes. There is no OpenCart backend here, so
	Frappe replied with its HTML 404 page and the theme alert()ed that entire
	document at the visitor ("NOT FOUND <!DOCTYPE html> ...").

	Returning quiet, well-formed responses keeps the page silent. These are
	deliberately inert: nothing is added to a cart and no price is calculated,
	because that logic lives in OpenCart and we do not have it.
	"""

	ROUTES_HTML = ("product/product/review",)

	def can_render(self):
		return self.path == "index.php"

	def render(self):
		route = (frappe.form_dict.get("route") or "").strip()

		# the review block is injected as HTML; hand back an empty fragment
		if any(route.endswith(r) for r in self.ROUTES_HTML):
			return Response(b"", status=200, mimetype="text/html")

		# everything else is consumed as JSON by the theme
		payload = {}
		if route.endswith("product/product/add"):
			# shape the theme expects: no error, nothing added
			payload = {"success": "", "total": ""}

		return Response(
			json.dumps(payload).encode("utf-8"),
			status=200,
			mimetype="application/json",
		)
