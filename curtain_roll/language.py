"""English and Arabic for the storefront.

The site is two different things wearing one skin:

  * the pages I wrote - cart, the account area, checkout - are ordinary Jinja
    and use `_()`, so Frappe translates them from a normal translation file
    once `frappe.local.lang` is "ar". Nothing in those pages changes.
  * the ported Journal3 pages keep their English inside `{% raw %}`, which is
    what stops Jinja - and therefore `_()` - from ever seeing it. Their text
    has to be swapped in the rendered HTML instead.

So the Arabic for those pages lives in `translations/strings.json`, one flat
map of English to Arabic that the client can read and correct without touching
markup, and `translate_html` applies it to the finished page.

Same URLs in both languages, chosen by a cookie, which is how the original
curtain-roll.com behaved.
"""
import io
import json
import os
import re
from html import unescape
from html.parser import HTMLParser

import frappe

COOKIE = "preferred_language"
SUPPORTED = ("en", "ar")
RTL = ("ar",)

# script and style hold code, not prose; textarea holds the visitor's own text
OPAQUE = {"script", "style", "noscript", "textarea"}
SHOWN_ATTRS = ("alt", "title", "placeholder", "value")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


# "SR 380.00" is built by the money formatter, not written anywhere, so it
# cannot be in the dictionary. In Arabic the amount leads and the currency
# follows it.
MONEY = re.compile(r"^SR\s*([\d,]+(?:\.\d+)?)$")
RIYAL = "ر.س"
PARENTHESISED = re.compile(r"^(.+?)\s*\((.+)\)$")


# --------------------------------------------------------------- the language
def current():
	"""Which language this request is in - always one of SUPPORTED."""
	lang = (getattr(frappe.local, "lang", None) or "en").lower()
	lang = lang.split("-")[0]
	return lang if lang in SUPPORTED else "en"


def is_rtl():
	return current() in RTL


def direction():
	return "rtl" if is_rtl() else "ltr"


@frappe.whitelist(allow_guest=True, methods=["POST"])
def set_language(lang=None):
	"""Remember the visitor's choice, for a year.

	Frappe reads this cookie itself (`frappe.translate.get_preferred_language_cookie`)
	and only honours a language that is actually installed, so an unknown value
	here is ignored rather than breaking the site.
	"""
	lang = (lang or "").lower()
	if lang not in SUPPORTED:
		frappe.throw(frappe._("Unknown language"))

	frappe.local.cookie_manager.set_cookie(
		COOKIE, lang, max_age=365 * 24 * 60 * 60, samesite="Lax")

	# The cookie alone is not enough for someone signed in. Frappe's
	# get_language() returns early for a logged-in user and reads their User
	# record instead, so without this the switch appears to do nothing for
	# exactly the people most likely to use it - customers with an account.
	# It also means their choice follows them to another browser.
	user = frappe.session.user
	if user and user != "Guest":
		frappe.db.set_value("User", user, "language", lang,
		                    update_modified=False)
		frappe.db.commit()

	frappe.local.lang = lang
	return {"ok": 1, "lang": lang}


def apply_language():
	"""before_request hook: let the cookie decide, whoever is asking.

	Frappe resolves language differently for a guest and for someone signed
	in - a guest gets the cookie, while a signed-in user gets their User
	record, read through a cache. So the switch worked for browsers and not
	for customers, and a stale cache could put it back to English on its own.

	A shop should not behave that way: the visitor's last click wins, right
	away. set_language still writes the User record so the desk and their
	emails agree, but nothing here depends on that having worked.

	This runs after the session is set up (Frappe calls before_request hooks
	at the end of process_request), so it has the last word on the language.
	"""
	request = getattr(frappe.local, "request", None)
	if request is None:
		return

	path = getattr(request, "path", "") or ""
	if path.startswith("/app") or path.startswith("/assets"):
		return

	try:
		chosen = (request.cookies.get(COOKIE) or "").lower().split("-")[0]
	except Exception:
		return
	if chosen in SUPPORTED:
		frappe.local.lang = chosen


# ------------------------------------------------------------- the dictionary
def phrases():
	"""English -> Arabic, from the file the client reviews. Cached per request."""
	if getattr(frappe.local, "_curtain_phrases", None) is not None:
		return frappe.local._curtain_phrases

	path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
	                    "translations", "strings.json")
	table = {}
	try:
		data = json.load(io.open(path, encoding="utf-8"))
		for english, arabic in (data.get("strings") or {}).items():
			arabic = (arabic or "").strip()
			if arabic:
				table[english] = arabic
	except Exception:
		# a broken or missing file must not take the storefront down; English
		# is a perfectly good fallback and the error is worth seeing
		frappe.log_error(title="curtain_roll: could not read strings.json",
		                 message=frappe.get_traceback())

	frappe.local._curtain_phrases = table
	return table


def say(text, table=None):
	"""Translate one visible string, keeping the whitespace around it.

	Falls back twice when the whole string is not in the dictionary, because
	a lot of what a customer reads is assembled rather than written:

	  * a cart line's description is several "Label: value" lines in one text
	    node, built when the item was added and stored on the Quotation. It
	    will never match as a whole, but every part of it is in the file.
	  * so each line, and then each side of the colon, is looked up on its own.

	Only exact matches are ever replaced, so this can add Arabic but cannot
	invent it.
	"""
	table = phrases() if table is None else table
	if not text or not text.strip():
		return text

	lead = text[:len(text) - len(text.lstrip())]
	tail = text[len(text.rstrip()):]
	body = " ".join(text.split())

	found = table.get(body)
	if found:
		return lead + found + tail

	if "\n" in text.strip():
		lines = [say(line, table) for line in text.split("\n")]
		return "\n".join(lines)

	money = MONEY.match(body)
	if money:
		return "%s%s %s%s" % (lead, money.group(1), RIYAL, tail)

	if ":" in body:
		label, _, value = body.partition(":")
		label, value = label.strip(), value.strip()
		new_label = _label(label, table)
		new_value = say(value, table) if value else ""
		if new_label or (value and new_value != value):
			shown = "%s:" % (new_label or label)
			if value:
				shown = "%s %s" % (shown, new_value)
			return lead + shown + tail
	return text


def _label(label, table):
	"""Translate a label, including the "Option (Group)" form.

	The price breakdown builds its lines as "<option> (<group>)", so the whole
	label is never in the dictionary even though both halves always are.
	"""
	found = table.get(label)
	if found:
		return found

	parts = PARENTHESISED.match(label)
	if parts:
		outer = table.get(parts.group(1).strip())
		inner = table.get(parts.group(2).strip())
		if outer or inner:
			return "%s (%s)" % (outer or parts.group(1).strip(),
			                    inner or parts.group(2).strip())
	return None


# ----------------------------------------------------------- rendered pages
class _Translator(HTMLParser):
	"""Rewrite a finished page's visible text, leaving everything else alone.

	Rebuilds the document as it goes. Tags are re-emitted from their original
	source text whenever nothing in them changed, so attribute quoting,
	spacing and odd hand-written markup survive untouched - important here,
	because this HTML was captured from someone else's site and is not ours
	to tidy.
	"""

	def __init__(self, table):
		super().__init__(convert_charrefs=False)
		self.table = table
		self.out = []
		self.depth = []
		# Text arrives in pieces: an entity reference splits a run of prose
		# into three callbacks, so "Help &amp; Orders" would be looked up as
		# "Help", "&", "Orders" and never match. Collect the pieces and
		# translate the whole run when it ends.
		self.buffer = []

	def flush(self):
		if not self.buffer:
			return
		raw = "".join(self.buffer)
		self.buffer = []
		if any(t in OPAQUE for t in self.depth):
			self.out.append(raw)
			return
		plain = unescape(raw)
		spoken = say(plain, self.table)
		# only re-escape when we actually replaced something, so untouched
		# markup keeps its original entities exactly as captured
		self.out.append(
			spoken.replace("&", "&amp;").replace("<", "&lt;")
			if spoken != plain else raw)

	# -- things we pass straight through
	def handle_comment(self, data):
		self.flush()
		self.out.append("<!--%s-->" % data)

	def handle_decl(self, decl):
		self.flush()
		self.out.append("<!%s>" % decl)

	def handle_pi(self, data):
		self.flush()
		self.out.append("<?%s>" % data)

	def unknown_decl(self, data):
		self.flush()
		self.out.append("<![%s]>" % data)

	def handle_entityref(self, name):
		self.buffer.append("&%s;" % name)

	def handle_charref(self, name):
		self.buffer.append("&#%s;" % name)

	# -- tags
	def _tag(self, tag, attrs, closing):
		self.flush()
		source = self.get_starttag_text() or ""
		changed = {}
		for key, value in attrs:
			if key.lower() in SHOWN_ATTRS and value:
				new = say(value, self.table)
				if new != value:
					changed[key] = new
		if tag == "html":
			changed["dir"] = direction()
			changed["lang"] = current()

		if not changed:
			self.out.append(source)
			return

		parts = []
		for key, value in attrs:
			value = changed.pop(key, value)
			parts.append(key if value is None
			             else '%s="%s"' % (key, _quote(value)))
		for key, value in changed.items():
			parts.append('%s="%s"' % (key, _quote(value)))
		self.out.append("<%s%s%s>" % (tag, (" " + " ".join(parts)) if parts else "",
		                              " /" if closing else ""))

	def handle_starttag(self, tag, attrs):
		self._tag(tag, attrs, closing=False)
		if tag not in VOID:
			self.depth.append(tag)

	def handle_startendtag(self, tag, attrs):
		self._tag(tag, attrs, closing=True)

	def handle_endtag(self, tag):
		self.flush()
		if tag in self.depth:
			while self.depth and self.depth.pop() != tag:
				pass
		self.out.append("</%s>" % tag)

	# -- the text itself
	def handle_data(self, data):
		self.buffer.append(data)

	def result(self):
		self.flush()
		return "".join(self.out)


def _quote(value):
	return (value.replace("&", "&amp;").replace('"', "&quot;")
	             .replace("<", "&lt;").replace(">", "&gt;"))


def translate_html(html):
	"""Swap the visible English on a rendered page for Arabic.

	Returns the page unchanged when there is nothing to swap, so a site with an
	empty dictionary costs nothing and behaves exactly as before.
	"""
	table = phrases()
	if not table or not html:
		return html
	try:
		parser = _Translator(table)
		parser.feed(html)
		parser.close()
		out = parser.result()
	except Exception:
		frappe.log_error(title="curtain_roll: could not translate a page",
		                 message=frappe.get_traceback())
		return html

	# a mangled rebuild is worse than English - sanity check the size
	if not out or not (0.5 < len(out) / float(len(html)) < 2.5):
		frappe.log_error(
			title="curtain_roll: translated page looks wrong, kept English",
			message="in %d bytes, out %d bytes" % (len(html), len(out) if out else 0))
		return html
	return out


# Frappe's desk, the API and static files are not the storefront and must not
# be rewritten - the desk in particular is a JavaScript app whose HTML shell
# carries no prose worth touching.
NOT_OURS = ("/app", "/api/", "/assets/", "/files/", "/private/", "/socket.io")


def _asset(relative):
	"""A versioned URL for one of our own files under public/.

	/assets is served with a long cache lifetime, so without a version in the
	URL a returning visitor keeps running the copy they downloaded weeks ago -
	a deployed fix silently does not reach the people who use the site most.
	The file's own timestamp is version enough: it changes exactly when the
	file does, and never otherwise.
	"""
	here = os.path.dirname(os.path.abspath(__file__))
	try:
		stamp = int(os.path.getmtime(os.path.join(here, "public", relative)))
	except OSError:
		stamp = 0
	return "/assets/curtain_roll/%s?v=%d" % (relative, stamp)


def _switcher_tag():
	return '<script src="%s" defer></script>' % _asset("js/curtain_lang.js")


def _rtl_sheet_tag():
	return '<link rel="stylesheet" href="%s">' % _asset("css/curtain_rtl.css")


# The header and the cart line are rewritten by the page's own script after
# it loads - applySession swaps in the account links, and the cart total is
# redrawn on every change. None of that exists yet when the server sees the
# HTML, so these few strings have to reach the browser.
RUNTIME_STRINGS = ("My Account", "Logout", "Login", "View Cart", "Checkout",
                   "Wishlist", "Your cart is empty.", "Continue shopping",
                   "Remove", "Your shopping cart is empty!")


def _runtime_phrases():
	"""Hand the browser only the strings its own script will write.

	A short allow-list rather than the whole dictionary: the page does not
	need 600 strings to redraw a header, and the file stays the single place
	the Arabic lives.
	"""
	table = phrases()
	wanted = {k: table[k] for k in RUNTIME_STRINGS if k in table}
	if not wanted:
		return ""
	return "<script>window.__crPhrases=%s;</script>" % json.dumps(
		wanted, ensure_ascii=False)


def _add_chrome(html):
	"""Put the language switch, and Arabic layout, on the page.

	The 18 ported pages are standalone documents - they do not extend Frappe's
	base template, so web_include_js never reaches them, and each carries its
	own frozen copy of the header. Adding one script tag here covers all of
	them and every page written since, and survives the next regeneration of
	the captures.
	"""
	if "curtain_lang.js" in html:
		return html

	tag = _switcher_tag()
	if is_rtl():
		tag = _rtl_sheet_tag() + _runtime_phrases() + tag
	end = html.rfind("</body>")
	if end == -1:
		return html + tag
	return html[:end] + tag + html[end:]


def finish_page(response=None, request=None):
	"""after_request hook: give the storefront its language switch, and Arabic.

	Two jobs in one pass because both need the finished HTML. The switch goes
	on every page - a visitor reading English still has to be able to reach
	Arabic - while the translation only runs when Arabic is the current
	language.
	"""
	if response is None or getattr(response, "status_code", 0) != 200:
		return

	path = (getattr(request, "path", "") or "")
	if any(path.startswith(p) for p in NOT_OURS):
		return
	if "text/html" not in (response.headers.get("Content-Type") or ""):
		return
	if getattr(response, "is_streamed", False):
		return

	try:
		html = response.get_data(as_text=True)
	except Exception:
		return
	if not html:
		return

	out = _add_chrome(translate_html(html) if current() == "ar" else html)
	if out != html:
		response.set_data(out)
