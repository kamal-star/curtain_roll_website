"""The checkout page.

Reachable by anyone with something in their cart. Whether they have an account
only changes what the form arrives pre-filled with - never whether they are
allowed to buy - unless the team has turned guest checkout off, in which case
the page says so and offers a sign-in rather than a dead end.
"""

import frappe
from frappe import _

from kayan_curtain import checkout as checkout_api


def get_context(context):
	context.no_cache = 1
	context.title = _("Checkout")

	data = checkout_api.context()
	context.update(data)

	# Nothing to check out is not an error; it is a customer who has arrived
	# too early, and the page tells them so instead of a form with no totals.
	context.empty = not data["items"]

	# A guest on a site that requires an account gets the one thing that helps:
	# a sign-in link that brings them straight back here, with the cart they
	# already built still in it.
	context.must_sign_in = data["guest"] and not data["guest_allowed"]
	context.login_url = "/login?redirect-to=/checkout"
	return context
