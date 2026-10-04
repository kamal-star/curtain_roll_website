# -*- coding: utf-8 -*-
"""About Us, Terms, Privacy, Delivery and Contact Us, editable from ERPNext.

Each page reads one Curtain Info Page record (named by the page's address):

  * the hero - the small heading, the title and the line under it - always
    comes from the record;
  * the page content replaces the designed sections only once it is filled
    in. Empty, and the page keeps the layout it has always had.

Terms, Privacy and Delivery are text, so their records are seeded with the
text the pages carry today (seed()), Arabic included from the dictionary the
site already translates with - the team edits the real words rather than
starting from a blank box. About Us and Contact Us keep their designed
sections until the team writes something to replace them.
"""

import io
import os

import frappe

DOCTYPE = "Curtain Info Page"
PAGES = ("about-us", "terms-and-conditions", "privacy-policy",
         "delivery-and-installation", "contact-us")
# pages whose content is seeded from today's text; the others keep their design
SEED_BODY = ("terms-and-conditions", "privacy-policy", "delivery-and-installation")
SEEDED_FLAG = "curtain_roll_info_pages_seeded"


# ------------------------------------------------------------------ reading
def info_page(route):
	"""What the template needs, in the visitor's language. {} when no record."""
	from kayan_curtain.language import current

	if route not in PAGES or not frappe.db.exists(DOCTYPE, route):
		return {}
	doc = frappe.get_cached_doc(DOCTYPE, route)
	ar = current() == "ar"

	def pick(field):
		return ((doc.get(field + "_ar") if ar else "") or doc.get(field) or "").strip()

	return frappe._dict({
		"eyebrow": pick("hero_eyebrow"),
		"title": pick("hero_title"),
		"subtitle": pick("hero_subtitle"),
		"body": pick("body"),
	})


# ------------------------------------------------------------------ seeding
def seed():
	"""One record per page, from the page as it is today. Once only."""
	if frappe.db.get_default(SEEDED_FLAG):
		return
	for route in PAGES:
		if frappe.db.exists(DOCTYPE, route):
			continue
		try:
			values = _from_page(route)
			frappe.get_doc(dict(doctype=DOCTYPE, page=route, **values)).insert(ignore_permissions=True)
			print("  info page %s: seeded%s" % (route, " with its text" if values.get("body") else ""))
		except Exception:
			frappe.log_error(title="kayan_curtain: info page %s" % route)
	frappe.db.set_default(SEEDED_FLAG, "1")


def _from_page(route):
	from bs4 import BeautifulSoup, NavigableString

	from kayan_curtain.language import phrases

	import re

	path = os.path.join(frappe.get_app_path("kayan_curtain"), "www", route + ".html")
	html = io.open(path, encoding="utf-8").read()
	# the page's own Jinja - {% if pg.title %}{{ pg.title }}{% else %}... - is
	# not page text; without it what is left is the original wording
	html = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", "", html, flags=re.S)
	soup = BeautifulSoup(html, "html.parser")
	main = soup.find("main")
	hero = main.find("section", class_=lambda c: c and any(x.endswith("-hero") for x in c.split()))

	def text(cls):
		el = hero.find(class_=cls) if hero else None
		return el.get_text(" ", strip=True) if el else ""

	table = phrases()
	values = {"hero_eyebrow": text("hero-eyebrow"), "hero_title": text("hero-title"),
	          "hero_subtitle": text("hero-subtitle")}
	for key in list(values):
		values[key + "_ar"] = table.get(values[key], "")

	if route in SEED_BODY:
		html = _content_html(main, hero)
		values["body"] = html
		values["body_ar"] = _translated(html, table)
	return values


SKIP_CLASSES = ("toc", "section-num", "btn", "cta", "hero")


def _content_html(main, hero):
	"""Headings, paragraphs, lists and highlight boxes - the words, not the layout."""
	if hero:
		hero.decompose()
	for el in main.find_all(["aside", "nav", "i", "img", "svg", "button", "form", "script", "style"]):
		el.decompose()
	for el in main.find_all(class_=lambda c: c and any(s in c for s in SKIP_CLASSES)):
		el.decompose()

	out, in_list = [], False
	emitted = set()

	def close_list():
		nonlocal in_list
		if in_list:
			out.append("</ul>")
			in_list = False

	for el in main.find_all(True):
		if any(id(p) in emitted for p in el.parents):
			continue
		name = el.name
		leaf_div = name == "div" and not el.find(["div", "p", "ul", "ol", "h2", "h3", "h4", "article", "section"]) \
			and el.get_text(strip=True)
		if name in ("h1", "h2", "h3", "h4"):
			close_list()
			out.append("<h3>%s</h3>" % el.get_text(" ", strip=True))
		elif name == "p" or leaf_div:
			# a timeline's step number ("1", "02") is layout, not content
			if el.get_text(strip=True).isdigit():
				emitted.add(id(el))
				continue
			close_list()
			out.append("<p>%s</p>" % _inline(el))
		elif name == "li":
			if not in_list:
				out.append("<ul>")
				in_list = True
			out.append("<li>%s</li>" % _inline(el))
		else:
			continue
		emitted.add(id(el))
	close_list()
	return "\n".join(out)


def _inline(el):
	"""The element's text, keeping bold and links."""
	parts = []
	for node in el.children:
		if getattr(node, "name", None) in ("strong", "b"):
			parts.append("<strong>%s</strong>" % frappe.utils.escape_html(node.get_text(" ", strip=True)))
		elif getattr(node, "name", None) == "a" and node.get("href"):
			parts.append('<a href="%s">%s</a>' % (frappe.utils.escape_html(node["href"]),
			                                       frappe.utils.escape_html(node.get_text(" ", strip=True))))
		elif getattr(node, "name", None):
			parts.append(frappe.utils.escape_html(node.get_text(" ", strip=True)))
		else:
			parts.append(frappe.utils.escape_html(str(node)))
	return " ".join(" ".join(parts).split())


def _translated(html, table):
	"""The same content with every text the dictionary knows in Arabic."""
	from bs4 import BeautifulSoup, NavigableString

	soup = BeautifulSoup(html, "html.parser")
	changed = False
	for node in list(soup.find_all(string=True)):
		key = " ".join(str(node).split())
		if key and table.get(key):
			node.replace_with(NavigableString(str(node).replace(str(node).strip(), table[key])))
			changed = True
	return str(soup) if changed else ""
