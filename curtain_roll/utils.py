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
