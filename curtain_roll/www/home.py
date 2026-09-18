import json
import os

import frappe

_CACHE = None


def _home():
	global _CACHE
	if _CACHE is None:
		path = os.path.join(frappe.get_app_path("curtain_roll"), "data", "home.json")
		with open(path, encoding="utf-8") as f:
			_CACHE = json.load(f)
	return _CACHE


def get_context(context):
	data = _home()
	context.hero = data.get("hero") or []
	context.cards = data.get("cards") or []
	context.title = "Curtain Roll"
	context.metatags = {
		"title": "Curtain Roll",
		"description": "Roller, blackout, sunscreen, zebra, wooden, vertical, metal and "
		               "roman curtains — customise your fabric and see it in 3D.",
		"image": "/assets/curtain_roll/" + (context.hero[0] if context.hero else ""),
	}
	return context
