# -*- coding: utf-8 -*-
"""Take the copied Curtain Roll details out of the site.

The storefront was built from a capture of curtain-roll.com, and some of that
company's own details came along: its toll-free number and WhatsApp line, its
Facebook / Instagram / Twitter accounts, and its address in front of every
page description. All of it is replaced with Kayan's here.

The same table serves two places:

  * the files in this repository - pages, translations, defaults - which
    were rewritten once with it (and stay rewritten);
  * what a running site keeps in its database, seeded from those files when
    it was installed: the editable info pages, the storefront settings and
    the translation table. apply() rewrites those, once, on migrate.

Order matters: a whole phrase is replaced before the bare number inside it,
so "Toll-Free Support: 8001268000" does not become "Toll-Free Support:
+966 55 546 5718" - a mobile number is not toll free.
"""

import frappe

KAYAN_PHONE = "+966 55 546 5718"
KAYAN_PHONE_RAW = "+966555465718"
KAYAN_WA = "966555465718"

REPLACEMENTS = (
	# English phrases around the old toll-free number
	("Call our toll-free support 8001268000", "Call our support line " + KAYAN_PHONE),
	("Toll-Free Support: 8001268000", "Customer Support: " + KAYAN_PHONE),
	("Toll Free: 8001268000", "Phone: " + KAYAN_PHONE),
	("toll-free support line <strong>8001268000</strong>", "support line <strong>%s</strong>" % KAYAN_PHONE),
	("Toll-Free Phone:</strong> 8001268000", "Phone:</strong> " + KAYAN_PHONE),
	("Toll-Free Phone: 8001268000", "Phone: " + KAYAN_PHONE),
	# the same in Arabic ("free" goes with it)
	("الرقم المجاني: 8001268000", "الهاتف: " + KAYAN_PHONE),
	("الدعم المجاني: 8001268000", "دعم العملاء: " + KAYAN_PHONE),
	# the "toll-free" wording, which no longer describes a mobile number
	("by calling our toll-free support line", "by calling our support line"),
	("Toll-Free Phone:", "Phone:"),
	("Toll-Free Support", "Phone Support"),
	("بخط الدعم المجاني", "بخط الدعم"),
	("الهاتف المجاني:", "الهاتف:"),
	("الدعم المجاني", "الدعم الهاتفي"),
	# the bare numbers, in every form they were written
	("tel:8001268000", "tel:" + KAYAN_PHONE_RAW),
	("+9668001268000", KAYAN_PHONE_RAW),
	("+966 8001268000", KAYAN_PHONE),
	("8001268000", KAYAN_PHONE),
	("wa.me/966114550783", "wa.me/" + KAYAN_WA),
	("+966 11 455 0783", KAYAN_PHONE),
	("+966114550783", KAYAN_PHONE_RAW),
	("966114550783", KAYAN_WA),
	# curtain-roll.com's address, left in front of the copied descriptions
	("https://curtain-roll.com/", ""),
	# its promotional banners, the first home-page slides
	("/assets/kayan_curtain/image/cache/catalog/SND-curtain%20roll-04-1400x600w.jpg", "/assets/kayan_curtain/image/slides/kayan-slide-1.jpg"),
	("/assets/kayan_curtain/image/cache/catalog/SND-curtain%20roll-05-1400x600w.jpg", "/assets/kayan_curtain/image/slides/kayan-slide-2.jpg"),
	("/assets/kayan_curtain/image/cache/catalog/SND-curtain%20roll-06-1400x600w.jpg", "/assets/kayan_curtain/image/slides/kayan-slide-3.jpg"),
)

FLAG = "curtain_roll_rebranded_v2"


def replace(text):
	"""text with every Curtain Roll detail swapped for Kayan's."""
	if not text or not isinstance(text, str):
		return text
	for old, new in REPLACEMENTS:
		if old in text:
			text = text.replace(old, new)
	return text


def _rewrite_doc(doc):
	"""Every text field of a document and its child rows; True if any changed."""
	changed = False
	for d in [doc] + list(doc.get_all_children()):
		for df in d.meta.fields:
			# text, and the picture fields - a slide's image is an Attach Image
			if df.fieldtype not in ("Data", "Small Text", "Text", "Long Text", "Text Editor",
			                        "HTML Editor", "Code", "Markdown Editor",
			                        "Attach", "Attach Image"):
				continue
			old = d.get(df.fieldname)
			new = replace(old)
			if new != old:
				d.set(df.fieldname, new)
				changed = True
	return changed


def apply(force=False):
	"""Rewrite what this site's database was seeded with. Once, on migrate."""
	if frappe.db.get_default(FLAG) and not force:
		return
	done = []
	for doctype in ("Curtain Info Page", "Curtain Storefront Settings"):
		if not frappe.db.exists("DocType", doctype):
			continue
		names = [doctype] if frappe.get_meta(doctype).issingle else \
			frappe.get_all(doctype, pluck="name")
		for name in names:
			doc = frappe.get_doc(doctype, name)
			if _rewrite_doc(doc):
				doc.flags.ignore_permissions = True
				doc.save(ignore_permissions=True)
				done.append("%s %s" % (doctype, name))

	# translations: only the Arabic side. A row is found by its English text,
	# and the pages now say the new English, which arrives as a new row from
	# the dictionary - the old rows simply stop being used.
	for row in frappe.get_all("Curtain Translation", fields=["name", "arabic"]):
		new = replace(row.arabic)
		if new != row.arabic:
			frappe.db.set_value("Curtain Translation", row.name, "arabic", new, update_modified=False)
			done.append("translation %s" % row.name)

	frappe.db.set_default(FLAG, "1")
	frappe.clear_cache()
	if done:
		print("  Curtain Roll details replaced in %d record(s)" % len(done))
