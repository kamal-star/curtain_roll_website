"""The customer's own picture, for a printed blind.

The Printed page takes an image or a PDF from the customer, shows it on the blind
in the 3D room, and sends the original to the team to print from. This module is
the server half: it keeps the file, and it vouches for it.

Three decisions worth knowing:

  * **Stored private.** These are people's photos - their children, their
    family, their logo. A public file is downloadable by anyone who has the
    link, and links travel. Private files are readable only by the team.

  * **Checked by content, not by name.** A file called photo.jpg is whatever
    its bytes say it is. Only JPEG, PNG and PDF signatures are accepted, so
    nothing else can be parked on the server by renaming it.

  * **Handed back as a signed token, not a file name.** The upload happens
    before there is any cart to attach it to, and a guest has no account to tie
    it to. If the cart accepted a bare file name, anyone could attach someone
    else's upload to their own order - and get it back in their order history -
    by guessing the name. The token carries the file's id and an HMAC made with
    the site's own key, so only the browser that uploaded the file can use it.
"""

import hashlib
import hmac
import os

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from curtain_roll.language import text as say

MAX_BYTES = 20 * 1024 * 1024

# what the first bytes of an accepted file must be
SIGNATURES = (
	(b"\xff\xd8\xff", "jpg"),
	(b"\x89PNG\r\n\x1a\n", "png"),
	(b"%PDF-", "pdf"),
)


def _key():
	from frappe.utils.password import get_encryption_key

	return get_encryption_key().encode()


def sign(file_name):
	digest = hmac.new(_key(), file_name.encode(), hashlib.sha256).hexdigest()[:32]
	return "%s.%s" % (file_name, digest)


def verify(token):
	"""The File this token was issued for, or None if it was not issued by us."""
	if not token or "." not in str(token):
		return None
	file_name, digest = str(token).rsplit(".", 1)
	expected = sign(file_name).rsplit(".", 1)[1]
	if not hmac.compare_digest(expected, digest):
		return None
	if not frappe.db.exists("File", file_name):
		return None
	return file_name


def kind_of(content):
	for magic, kind in SIGNATURES:
		if content.startswith(magic):
			return kind
	return None


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60)
def upload():
	"""Take the customer's picture. Answers with a token the cart will accept.

	Rate-limited per visitor: this is open to anyone, and without a limit it is
	free storage for whoever finds it.
	"""
	files = getattr(frappe.request, "files", None) or {}
	sent = files.get("file")
	if not sent:
		frappe.throw(say("Please choose a picture to upload."))

	content = sent.stream.read(MAX_BYTES + 1)
	if len(content) > MAX_BYTES:
		frappe.throw(say("That file is too large. The limit is 20 MB."))

	kind = kind_of(content)
	if not kind:
		frappe.throw(say("Please upload a JPG, PNG or PDF file."))

	# the customer's own file name is kept for the team, but never trusted as a
	# path: only its last part, and only its stem
	original = os.path.basename(sent.filename or "picture").strip() or "picture"
	stem = os.path.splitext(original)[0][:60] or "picture"

	doc = frappe.get_doc({
		"doctype": "File",
		"file_name": "print-%s-%s.%s" % (frappe.generate_hash(length=8), stem, kind),
		"content": content,
		"is_private": 1,
	})
	doc.flags.ignore_permissions = True
	try:
		doc.insert(ignore_permissions=True)
	except Exception:
		# Frappe reads every uploaded PDF (it looks for embedded scripts), and a
		# damaged one makes it raise from deep inside - which the customer would
		# see as a bare server error with a traceback. Say what is wrong instead.
		frappe.db.rollback()
		if kind == "pdf":
			frappe.throw(say("That PDF could not be read. Please save it again, "
			                 "or send the picture as a JPG or PNG."))
		raise
	frappe.db.commit()

	return {"ok": 1, "token": sign(doc.name), "name": original, "kind": kind}


def attach(token, doctype, name):
	"""Hang a verified upload off a cart or a quotation, so the team has it."""
	file_name = verify(token)
	if not file_name:
		return None
	frappe.db.set_value("File", file_name, {
		"attached_to_doctype": doctype,
		"attached_to_name": name,
	}, update_modified=False)
	return file_name


def original_name(token):
	"""The customer's own name for the file, for the order line."""
	file_name = verify(token)
	if not file_name:
		return ""
	stored = frappe.db.get_value("File", file_name, "file_name") or ""
	# print-<hash>-<their name>.<ext> -> <their name>.<ext>
	parts = stored.split("-", 2)
	return parts[2] if len(parts) == 3 else stored
