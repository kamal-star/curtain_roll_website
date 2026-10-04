# -*- coding: utf-8 -*-
"""The heading and description at the top of a product page, from the desk.

Curtain Product -> Page Text holds them, in English and Arabic. They were
part of each captured page; seed() copies today's words into the record once
(the Arabic from the site's dictionary), and from then on the page shows what
the record says (language._product_text puts it into the finished HTML).
An empty field leaves the page's own words in place.
"""

import html as htmllib
import io
import os
import re

import frappe

CACHE_KEY = "curtain_roll_page_text:%s"
HEADING = re.compile(r'(<h2 class="product-title">)(.*?)(</h2>)', re.S)
DESCRIPTION = re.compile(r'(<p class="product-desc-snippet">)(.*?)(</p>)', re.S)


def get(key):
	"""{"heading", "description", "heading_ar", "description_ar"} or {}."""
	if not key:
		return {}
	cached = frappe.cache().get_value(CACHE_KEY % key)
	if cached is not None:
		return cached
	out = {}
	try:
		row = frappe.db.get_value(
			"Curtain Product", {"product_key": key},
			["page_heading", "page_description", "page_heading_ar", "page_description_ar"],
			as_dict=True)
	except Exception:          # before the fields exist (mid-migrate)
		row = None
	if row:
		out = {k.replace("page_", ""): (v or "").strip() for k, v in row.items()}
	frappe.cache().set_value(CACHE_KEY % key, out, expires_in_sec=6 * 60 * 60)
	return out


def clear(key):
	frappe.cache().delete_value(CACHE_KEY % key)


def apply(page_html, key, arabic):
	"""The page with the record's heading and description in it."""
	text = get(key)
	if not text:
		return page_html

	def put(pattern, value, html_in):
		if not value:
			return html_in
		safe = htmllib.escape(value).replace("\n", "<br>")
		return pattern.sub(lambda m: m.group(1) + safe + m.group(3), html_in, count=1)

	heading = (arabic and text.get("heading_ar")) or text.get("heading")
	description = (arabic and text.get("description_ar")) or text.get("description")
	page_html = put(HEADING, heading, page_html)
	return put(DESCRIPTION, description, page_html)


def _plain(fragment):
	text = re.sub(r"<br\s*/?>", "\n", fragment or "")
	text = re.sub(r"<[^>]+>", "", text)
	return htmllib.unescape(text).strip()


def seed():
	"""Fill Page Text from each page as it is today.

	A record with no heading yet gets the page's heading and description. Any
	Arabic field still empty gets the dictionary's Arabic for the English
	beside it, matched without regard to capitals ("ZEBRA KAYAN" is the
	dictionary's "Zebra Kayan"). Nothing the team has typed is overwritten.
	"""
	from kayan_curtain.language import phrases

	try:
		table = phrases() or {}
	except Exception:
		table = {}
	folded = {k.strip().lower(): v for k, v in table.items() if k}

	def arabic(english):
		english = (english or "").strip()
		return table.get(english) or folded.get(english.lower()) or ""

	www = os.path.join(frappe.get_app_path("kayan_curtain"), "www")
	fields = ["name", "product_key", "page_heading", "page_description",
	          "page_heading_ar", "page_description_ar"]
	for row in frappe.get_all("Curtain Product", fields=fields):
		update = {}
		heading, description = row.page_heading, row.page_description
		if not heading:
			path = os.path.join(www, "%s.html" % row.product_key)
			if not os.path.exists(path):
				continue
			page = io.open(path, encoding="utf-8").read()
			h, d = HEADING.search(page), DESCRIPTION.search(page)
			heading = _plain(h.group(2)) if h else ""
			description = _plain(d.group(2)) if d else ""
			if not heading:
				continue
			update.update(page_heading=heading, page_description=description)
		if not row.page_heading_ar and arabic(heading):
			update["page_heading_ar"] = arabic(heading)
		if not row.page_description_ar and arabic(description):
			update["page_description_ar"] = arabic(description)
		if update:
			frappe.db.set_value("Curtain Product", row.name, update, update_modified=False)
			clear(row.product_key)
