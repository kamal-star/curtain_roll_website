import contextlib
import json
import os

import frappe

_CACHE = None


def _load():
	global _CACHE
	if _CACHE is None:
		path = os.path.join(frappe.get_app_path("curtain_roll"), "data", "products.json")
		with open(path, encoding="utf-8") as f:
			_CACHE = json.load(f)
	return _CACHE


def get_products():
	"""All products, in site menu order."""
	return _load()


def get_product(key):
	"""One product dict by key, or None."""
	for p in _load():
		if p.get("key") == key:
			return p
	return None


def asset(path):
	"""Map a captured site-relative path to this app's static assets.

	    image/cache/catalog/x.jpg  ->  /assets/curtain_roll/image/cache/catalog/x.jpg

	Textures under maps/ are deliberately NOT remapped: the obfuscated
	configurator bundles request them from the site root, so they are served
	from curtain_roll/www/maps/ instead.
	"""
	if not path:
		return ""
	if path.startswith(("http://", "https://", "/")):
		return path
	return "/assets/curtain_roll/" + path.lstrip("/")


@contextlib.contextmanager
def as_system_user():
	"""Run a block as a user allowed to read what ERPNext reads.

	A storefront customer is a Website User with no read permission on Item,
	Sales Invoice or Payment Entry - by design. So anything that renders one
	of those for them, or validates a document that reads them, has to run as
	someone who can, AFTER we have checked the record is actually theirs.

	Switching the session user keeps every permission check in place and gives
	it someone who passes, rather than turning checking off. Restore is in a
	finally, so an exception cannot leave the request running as Administrator.
	"""
	previous = frappe.session.user
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(previous)
