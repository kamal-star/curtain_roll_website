"""Storefront search: one box, the whole catalogue, in either language.

The site is thirteen product pages and a handful of information pages. That is
small enough to rank in Python on every keystroke, so there is no index to
build and nothing that can drift out of step with the catalogue. What this shop
needs is not scale but forgiveness:

  * someone who types "zibra" or "blakout" still wants the blind, so a query
    that matches nothing exactly is tried a second time against the closest
    words rather than answering "no results".
  * someone reading the site in Arabic types Arabic. The Arabic already exists -
    it is the same dictionary the pages are translated from - so every name is
    indexed in both languages and either query finds the page.
  * Arabic writes one sound several ways. To a reader the four alifs are one
    letter; to a computer they are four characters. Both the query and the
    index are folded to one spelling before they meet, or an Arabic search is a
    coin toss.
  * the fabric swatches are searchable. A customer holding a sample knows
    "7317" and nothing else about it, and that is enough to reach the blind
    that offers it.

Ranking is deliberately blunt. A hit on a product's name outranks a hit on one
of its four hundred swatch codes, and every word of the query has to land
somewhere, or "wooden blind" would return the whole shop.
"""

import difflib
import re

import frappe
from frappe.utils import cint

from curtain_roll import language
from curtain_roll.storefront import storefront_settings
from curtain_roll.utils import get_products

SUGGESTIONS = 6
MAX_RESULTS = 40

# How close a misspelling has to be before we offer the word we think was meant.
# Measured against the words actually in this catalogue: "blakout" against
# "blackout" scores .93 and "zibra" against "zebra" .80, while "curtain"
# against "printed" manages only .43 - so the gap either side of this is wide.
FUZZY = 0.74

# Tashkeel and the decorative tatweel are produced by some keyboards and carry
# no meaning in a search box.
_MARKS = re.compile("[ً-ْٰـ]")

# Letters a shopper uses interchangeably: the four alifs, ya for alif maqsura,
# ha for ta marbuta, and the two hamza carriers.
_SAME_LETTER = str.maketrans({
	"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
	"ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
})

_WORDS = re.compile(r"[0-9a-z؀-ۿ]+")

# A few captured descriptions begin with the old site's own URL, which was
# never meant to be read.
_LEADING_URL = re.compile(r"^https?://\S+")


def fold(text):
	"""One spelling for a word that can be typed several ways."""
	return _MARKS.sub("", (text or "").lower()).translate(_SAME_LETTER)


def words(text):
	"""The searchable words in a string, folded. Punctuation is dropped."""
	return _WORDS.findall(fold(text))


# ------------------------------------------------------------------ the index
def _tidy(name):
	"""A name in title case, whatever case it happens to be stored in.

	The captured headings are a mix - "Printed", "blackout", "WOODEN KAYAN" -
	because they were typed into the old site over several years. A results list
	that shouts one product and whispers the next looks broken.
	"""
	name = " ".join((name or "").split())
	return name.title() if (name.isupper() or name.islower()) else name


def _arabic(term, table):
	"""The Arabic for one English term, trying the casings the file may hold.

	The dictionary was built from the pages, so it holds whichever case the page
	used: "Blackout" from the menu but "BLACKOUT KAYAN" from a heading. Asking
	only for the spelling we happen to have in hand is how a name ends up
	searchable in English alone.
	"""
	for form in (term, _tidy(term), term.title(), term.upper(), term.capitalize()):
		if form and table.get(form):
			return table[form]
	return None


def _swatches():
	"""Colour names and option labels per product, from the team's own records.

	These are the words a customer arrives with: a code off a fabric sample, or
	"motorized" because that is the thing they want. They are read from the
	Curtain Product record rather than from the capture, so a colour added this
	morning is searchable this morning.
	"""
	found = {}
	for doctype, field in (("Curtain Product Color", "color_name"),
	                       ("Curtain Product Option", "option_label")):
		try:
			rows = frappe.get_all(doctype, filters={"enabled": 1},
			                      fields=["parent", field],
			                      parent_doctype="Curtain Product")
		except Exception:
			# before the first migrate there is no table to read, and a search
			# box that 500s is worse than one that misses the swatches
			continue
		for row in rows:
			value = (row.get(field) or "").strip()
			if value:
				found.setdefault(row.get("parent"), set()).add(value)
	return found


def _variant_image(route, cards):
	"""A variant page borrows the photograph of the product it is a variant of.

	/blackout-kayan is the blackout blind shown in a different room, and
	/wooden-premium the wooden one in a better timber. The home page carries a
	photograph for the base product and none for the variant, so without this a
	results list has a picture on one row and a grey square on the next, which
	reads as broken rather than as deliberate.
	"""
	bases = [r for r in cards if r != route and route.startswith(r + "-")]
	if not bases:
		return ""
	# the longest match, so /vertical-premium prefers /vertical over /
	return (cards.get(max(bases, key=len)) or {}).get("image") or ""


def _bag(terms, table):
	"""Fold a set of phrases into searchable words, English and Arabic."""
	out = set()
	for term in terms:
		if not term:
			continue
		out.update(words(term))
		found = _arabic(term, table)
		if found:
			out.update(words(found))
	return out


def _pages():
	"""The information pages, which are as searchable as the products.

	Written out here rather than discovered from www/: the list is short, it
	changes about once a year, and a page needs a name a shopper would recognise
	anyway, which a filename does not carry.
	"""
	return (
		("About Us", "/about-us",
		 "Who we are, and how the curtains are made.",
		 "fa-regular fa-circle-question"),
		("Contact Us", "/contact-us",
		 "Phone, WhatsApp and where to find the showroom.",
		 "fa-regular fa-envelope"),
		("Delivery and Installation", "/delivery-and-installation",
		 "How measuring, delivery and fitting work.",
		 "fa-solid fa-truck-fast"),
		("My Account", "/account",
		 "Your orders, invoices and addresses.", "fa-regular fa-user"),
		("Wishlist", "/account/wishlist",
		 "The blinds you saved for later.", "fa-regular fa-heart"),
		("Your Invoices", "/account/invoices",
		 "Print an invoice or download it as a PDF.",
		 "fa-regular fa-file-lines"),
		("Cart", "/cart", "What you are about to order.",
		 "fa-solid fa-bag-shopping"),
		("Terms and Conditions", "/terms-and-conditions", "",
		 "fa-regular fa-file-lines"),
		("Privacy Policy", "/privacy-policy", "",
		 "fa-solid fa-shield-halved"),
	)


def _build():
	"""Everything a shopper can search, each with the words that should find it.

	Three bags per entry, in the order that a hit on them means something: the
	product's own names, then the swatches and options it offers, then the
	sentence describing it.
	"""
	table = language.phrases()
	settings = storefront_settings()
	cards = {c.get("route"): c for c in settings.get("categories") or []}
	menu = {n.get("route"): n.get("label") for n in settings.get("nav_items") or []}
	swatches = _swatches()

	withdrawn = set(settings.get("withdrawn") or ())
	entries = []
	for page in get_products():
		key = page.get("key")
		route = "/" + (page.get("route") or key).lstrip("/")
		if route in withdrawn:
			continue
		card = cards.get(route) or {}

		# the menu label is the client's own wording and the tidiest of the
		# three; the captured heading is the fallback
		name = _tidy(menu.get(route) or page.get("heading") or key)
		blurb = card.get("description") or page.get("meta_description") or ""
		blurb = _LEADING_URL.sub("", blurb).strip()

		entries.append({
			"kind": "product",
			"label": name,
			"route": route,
			"image": card.get("image") or _variant_image(route, cards),
			"price": page.get("price_text") or "",
			"blurb": blurb,
			"icon": "fa-solid fa-scroll",
			"names": _bag({name, page.get("heading"), card.get("title"),
			               key.replace("-", " ")}, table),
			"terms": _bag(swatches.get(key) or (), table)
			| _bag({card.get("badge")}, table),
			"text": _bag({blurb}, table),
		})

	for name, route, blurb, icon in _pages():
		entries.append({
			"kind": "page",
			"label": name,
			"route": route,
			"image": "",
			"price": "",
			"blurb": blurb,
			"icon": icon,
			"names": _bag({name}, table),
			"terms": set(),
			"text": _bag({blurb}, table),
		})

	# products before information pages, catalogue order within each, so an
	# equal score falls back to the order the menu itself shows
	for position, entry in enumerate(entries):
		entry["order"] = position
	return entries


def index():
	"""The built index, held for the rest of the request.

	Not put in Redis: the bags are sets, the whole thing is built from two
	values that are themselves cached - the phrase table and the storefront
	settings - and the only uncached part is one query over two small child
	tables. Caching it as well would buy a millisecond and add a third thing
	that can be stale.
	"""
	if getattr(frappe.local, "_curtain_search_index", None) is None:
		frappe.local._curtain_search_index = _build()
	return frappe.local._curtain_search_index


# ------------------------------------------------------------------- matching
# A hit on the name is what the shopper meant; the rest is how we catch the
# ones who describe the thing instead of naming it.
WHOLE_NAME = 200
NAME_EXACT = 80
NAME_START = 60
NAME_IN = 40
TERM_EXACT = 24
TERM_START = 18
TERM_IN = 12
TEXT_IN = 5


def _best(word, bag, exact, starts, inside):
	"""The strongest way one query word touches one bag of indexed words."""
	score = 0
	for indexed in bag:
		if indexed == word:
			return exact
		if indexed.startswith(word):
			score = max(score, starts)
		elif word in indexed:
			score = max(score, inside)
	return score


def _score(entry, query):
	"""How well one entry answers the query. Zero means it does not.

	Every word has to land somewhere, so "wooden blind" cannot match a blind
	that is merely a blind, and a second word narrows the list instead of
	widening it.
	"""
	total = 0
	for word in query:
		hit = _best(word, entry["names"], NAME_EXACT, NAME_START, NAME_IN) \
			or _best(word, entry["terms"], TERM_EXACT, TERM_START, TERM_IN) \
			or _best(word, entry["text"], TEXT_IN, TEXT_IN, 0)
		if not hit:
			return 0
		total += hit

	# typing a product's name exactly should put it first even when another
	# product happens to list that word among its four hundred swatches
	if " ".join(query) == " ".join(words(entry["label"])):
		total += WHOLE_NAME
	return total


def _closest(entry, query):
	"""Score an entry against a query that matched nothing, for a misspelling.

	Only the names are tried, and only words long enough to be a typo rather
	than a different word: guessing at three letters turns every short query
	into a wrong answer delivered confidently.
	"""
	total = 0
	for word in query:
		if len(word) < 4:
			return 0
		ratio = max((difflib.SequenceMatcher(None, word, indexed).ratio()
		             for indexed in entry["names"]), default=0)
		if ratio < FUZZY:
			return 0
		total += int(ratio * NAME_IN)
	return total


def _public(entry):
	"""What the browser and the results page are handed.

	Translated here rather than left to the site-wide Arabic pass, because
	suggestions are fetched from /api/method - a path that pass deliberately
	does not touch - and would otherwise be the one English thing on an Arabic
	page.
	"""
	shown = {k: entry[k] for k in
	         ("label", "route", "image", "price", "blurb", "kind", "icon")}
	if language.current() == "ar":
		for field in ("label", "price", "blurb"):
			shown[field] = language.say(shown[field])
	return shown


def find(query, limit=MAX_RESULTS):
	"""Rank the catalogue against a shopper's words.

	Returns the hits and whether they came from guessing at a misspelling, so
	the page can say so rather than quietly pretending the shopper typed what
	we went looking for.
	"""
	asked = words(query)
	if not asked:
		return [], False

	entries = index()
	hits = [(s, e) for s, e in ((_score(e, asked), e) for e in entries) if s]
	guessed = False
	if not hits:
		hits = [(s, e) for s, e in ((_closest(e, asked), e) for e in entries) if s]
		guessed = bool(hits)

	hits.sort(key=lambda pair: (-pair[0], pair[1]["order"]))
	return [_public(e) for _, e in hits[:limit]], guessed


@frappe.whitelist(allow_guest=True)
def suggest(q=None, limit=SUGGESTIONS):
	"""What the box offers under itself while someone is still typing."""
	results, guessed = find(q, cint(limit) or SUGGESTIONS)
	return {"query": q or "", "guessed": guessed, "results": results}
