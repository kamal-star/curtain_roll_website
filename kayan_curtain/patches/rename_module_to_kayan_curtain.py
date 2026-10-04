"""Rename the desk module "Curtain Roll" to "Kayan Curtain".

Runs before the model sync (see patches.txt), so by the time the DocType JSON -
which now says "Kayan Curtain" - is imported, the Module Def it points at
already exists and every record that named the old module names the new one.
"""

import frappe

OLD = "Curtain Roll"
NEW = "Kayan Curtain"


def execute():
	_module_def()
	_module_links()
	_sidebars_and_icons()
	frappe.clear_cache()


def _module_def():
	if not frappe.db.exists("Module Def", OLD):
		return
	if frappe.db.exists("Module Def", NEW):
		frappe.db.delete("Module Def", {"name": OLD})
		return
	frappe.db.sql(
		"update `tabModule Def` set name=%s, module_name=%s where name=%s", (NEW, NEW, OLD)
	)


def _module_links():
	"""Every field that holds a module name: DocType, Report, Page, Workspace..."""
	fields = set()
	for df in frappe.get_all(
		"DocField", filters={"fieldtype": "Link", "options": "Module Def"}, fields=["parent", "fieldname"]
	):
		fields.add((df.parent, df.fieldname))
	for df in frappe.get_all(
		"Custom Field", filters={"fieldtype": "Link", "options": "Module Def"}, fields=["dt", "fieldname"]
	):
		fields.add((df.dt, df.fieldname))
	# plain-text module fields, e.g. Workspace Sidebar.module
	for table, column in frappe.db.sql(
		"""select table_name, column_name from information_schema.columns
		where table_schema = database() and column_name in ('module', 'module_name')
		and table_name like 'tab%%'"""
	):
		fields.add((table[3:], column))

	singles = set(frappe.get_all("DocType", filters={"issingle": 1}, pluck="name"))
	for doctype, fieldname in fields:
		if doctype in singles:
			frappe.db.sql(
				"update `tabSingles` set value=%s where doctype=%s and field=%s and value=%s",
				(NEW, doctype, fieldname, OLD),
			)
		elif frappe.db.table_exists(doctype) and frappe.db.has_column(doctype, fieldname):
			frappe.db.sql(
				"update `tab{0}` set `{1}`=%s where `{1}`=%s".format(doctype, fieldname), (NEW, OLD)
			)


def _sidebars_and_icons():
	# The app now ships its sidebar as "Kayan Curtain"; the old standard one goes.
	if frappe.db.table_exists("Workspace Sidebar"):
		frappe.db.delete("Workspace Sidebar Item", {"parent": OLD, "parenttype": "Workspace Sidebar"})
		frappe.db.delete("Workspace Sidebar", {"name": OLD})

	if frappe.db.table_exists("Desktop Icon"):
		for column in ("label", "link_to", "sidebar", "parent_icon"):
			if frappe.db.has_column("Desktop Icon", column):
				frappe.db.sql(
					"update `tabDesktop Icon` set `{0}`=%s where `{0}`=%s".format(column), (NEW, OLD)
				)
		if frappe.db.exists("Desktop Icon", NEW):
			frappe.db.delete("Desktop Icon", {"name": OLD})
		else:
			frappe.db.sql("update `tabDesktop Icon` set name=%s where name=%s", (NEW, OLD))
		frappe.db.sql(
			"update `tabHas Role` set parent=%s where parenttype='Desktop Icon' and parent=%s", (NEW, OLD)
		)
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")
