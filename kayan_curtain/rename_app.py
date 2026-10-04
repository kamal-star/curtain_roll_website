"""One-time move of a live site from the old app name `curtain_roll` to
`kayan_curtain`.

Run it ONCE per site, while both apps are still in the bench - see
"Renaming from curtain_roll" in README.md for the full order:

	cd sites && ../env/bin/python -c "import frappe; frappe.init(site='<site>', sites_path='.'); frappe.connect(); from kayan_curtain.rename_app import run; run(); frappe.destroy()"

Not `bench execute`: newer Frappe refuses to run code from an app the site
does not list as installed yet, and listing it is what this does.

It only rewrites the old name where the database stores it, so it is safe to
run again. Nothing here is a patch: a migrate cannot run it, because until the
site says `kayan_curtain` is installed Frappe never looks at its patches.
"""

import json

import frappe

OLD = "curtain_roll"
NEW = "kayan_curtain"

# Stored inside field values - image paths in Curtain Storefront Settings,
# slides, info pages, Item images... - and as dotted paths to our code.
URL_PREFIXES = (
	("/assets/%s/" % OLD, "/assets/%s/" % NEW),
	("/api/method/%s." % OLD, "/api/method/%s." % NEW),
)

TEXT_TYPES = ("char", "varchar", "text", "tinytext", "mediumtext", "longtext")


def run():
	_installed_apps()
	_module_def()
	_dotted_paths()
	_stored_urls()
	frappe.db.commit()
	frappe.clear_cache()
	print("Site now runs %s. Remove %s from the bench, then migrate." % (NEW, OLD))


def _installed_apps():
	apps = json.loads(frappe.db.get_global("installed_apps") or "[]")
	apps = [NEW if a == OLD else a for a in apps]
	# keep one entry, where the old one was
	seen = []
	for a in apps:
		if a not in seen:
			seen.append(a)
	frappe.db.set_global("installed_apps", json.dumps(seen))

	if frappe.db.table_exists("Installed Application"):
		frappe.db.sql(
			"update `tabInstalled Application` set app_name=%s where app_name=%s", (NEW, OLD)
		)


def _module_def():
	frappe.db.sql("update `tabModule Def` set app_name=%s where app_name=%s", (NEW, OLD))


def _dotted_paths():
	"""Scheduled jobs and patch log rows name our code by its module path."""
	old, new = OLD + ".", NEW + "."
	for doctype, field in (("Scheduled Job Type", "method"), ("Patch Log", "patch")):
		if not frappe.db.table_exists(doctype):
			continue
		frappe.db.sql(
			"update `tab{0}` set `{1}` = concat(%s, substring(`{1}`, %s)) "
			"where `{1}` like %s".format(doctype, field),
			(new, len(old) + 1, old + "%"),
		)


def _stored_urls():
	"""Rewrite /assets/curtain_roll/... wherever a text column holds it."""
	columns = frappe.db.sql(
		"""select table_name, column_name from information_schema.columns
		where table_schema = database() and data_type in %s
		and table_name like 'tab%%'""",
		(TEXT_TYPES,),
	)
	# Logs record history; leave them as they were.
	skip = {"tabError Log", "tabVersion", "tabActivity Log", "tabAccess Log",
		"tabRoute History", "tabScheduled Job Log", "tabEmail Queue"}
	for table, column in columns:
		if table in skip:
			continue
		for old, new in URL_PREFIXES:
			frappe.db.sql(
				"update `{0}` set `{1}` = replace(`{1}`, %s, %s) where `{1}` like %s".format(
					table, column),
				(old, new, "%" + old + "%"),
			)
