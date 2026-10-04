"""Turning a basket into an order.

This is where a cart stops being a cart. Everything before it is anonymous and
reversible; everything after it is a Quotation in the Selling workspace with a
customer's name and address on it.

Four things happen here that the cart deliberately never did:

  * **the customer is named.** Someone who never signed in has typed their name,
    email and phone into the form; someone who did has it already. Either way a
    Customer, a Contact and one or two Addresses exist by the end.
  * **billing and shipping are separated.** The invoice is a legal document and
    has to carry the billing address, the company name, the CR number and the
    VAT number. Where the curtains are delivered is a different question, and
    often a different address.
  * **the money is fixed.** The totals shown to the customer are computed once,
    here, and written onto the Quotation as real ERPNext discount and tax rows,
    so the tax invoice raised later says the same thing the checkout page did.
  * **a way to pay is chosen.** Card goes to ClickPay and the order is confirmed
    by the payment. Bank transfer places the order now and leaves an unpaid
    invoice for the team to reconcile - a real difference the customer is told
    about rather than a second button that behaves the same.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from kayan_curtain import cart, orders, totals
from kayan_curtain.language import text as say
from kayan_curtain.storefront import storefront_settings
from kayan_curtain.utils import as_system_user

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# What a Saudi National Address short code looks like: four letters then four
# digits, e.g. RRRD2929. Checked loosely - a customer holding a card with a
# slightly different format should not be stopped from buying curtains.
NATIONAL_ADDRESS = re.compile(r"^[A-Za-z]{4}\s?\d{4}$")

ACCESS_FIELD = "cr_access_key"
METHOD_FIELD = "cr_payment_method"

CARD = "card"
BANK = "bank"

# A fifth payment state beside ClickPay's four: the order exists and the invoice
# is outstanding, which is true of no card order at any point.
AWAITING_TRANSFER = "Awaiting Transfer"


# --------------------------------------------------------------- what is on
def methods():
	"""The ways this site can be paid, in the order they are offered."""
	from kayan_curtain import clickpay

	settings = storefront_settings()
	out = []
	if cint(settings.get("card_enabled")) and clickpay.configured():
		out.append({
			"key": CARD,
			"label": _("Pay by card"),
			"note": _("Card details are entered on our payment provider's secure "
			          "page, never here. Your order is confirmed the moment the "
			          "payment goes through."),
			"icon": "fa-regular fa-credit-card",
		})
	if cint(settings.get("bank_transfer_enabled")) and settings.get("bank_iban"):
		out.append({
			"key": BANK,
			"label": _("Bank transfer"),
			"note": _("We will send you the bank details and an invoice. Your "
			          "order is confirmed once the transfer reaches us, usually "
			          "the next working day."),
			"icon": "fa-solid fa-building-columns",
		})
	return out


def bank_details():
	settings = storefront_settings()
	return {
		"bank": settings.get("bank_name") or "",
		"account": settings.get("bank_account_name") or "",
		"number": settings.get("bank_account_number") or "",
		"iban": settings.get("bank_iban") or "",
		"instructions": settings.get("bank_instructions") or "",
	}


def guest_allowed():
	return bool(cint(storefront_settings().get("guest_checkout")))


def national_address_required():
	return bool(cint(storefront_settings().get("require_national_address")))


# ------------------------------------------------------------- what we know
def known_details():
	"""Whatever we can fill in for the person already at the keyboard.

	Only ever read for the signed-in user's own records. A guest is shown an
	empty form even when the email they later type turns out to match a
	customer we have - offering back someone's saved address because a stranger
	guessed their email address would be a way of reading it out loud.
	"""
	if cart.is_guest():
		return {}

	user = frappe.session.user
	values = frappe.db.get_value(
		"User", user, ["first_name", "last_name", "email", "mobile_no", "phone"],
		as_dict=True) or {}

	out = {
		"first_name": values.get("first_name") or "",
		"last_name": values.get("last_name") or "",
		"email": values.get("email") or (user if "@" in user else ""),
		"phone": values.get("mobile_no") or values.get("phone") or "",
	}

	customer = _existing_customer()
	if customer:
		record = frappe.db.get_value(
			"Customer", customer,
			["customer_name", "customer_type", "tax_id"], as_dict=True) or {}
		out["tax_id"] = record.get("tax_id") or ""
		out["cr_number"] = frappe.db.get_value("Customer", customer,
		                                       "cr_number") or ""
		if record.get("customer_type") == "Company":
			out["company_name"] = record.get("customer_name") or ""

		from kayan_curtain import account
		addresses = account.my_addresses()
		out["addresses"] = addresses
		for row in addresses:
			kind = frappe.db.get_value("Address", row["name"], "address_type")
			if kind == "Billing" and not out.get("billing"):
				out["billing"] = row
			if kind == "Shipping" and not out.get("shipping"):
				out["shipping"] = row
		if not out.get("billing") and addresses:
			out["billing"] = addresses[0]
	return out


def _existing_customer():
	"""The signed-in user's Customer, if they already have one. Never creates."""
	if cart.is_guest():
		return None
	contact = frappe.db.get_value("Contact", {"user": frappe.session.user}, "name")
	if not contact:
		return None
	return frappe.db.get_value(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"},
		"link_name")


def context():
	"""Everything the checkout page renders from."""
	info = cart.info()
	return {
		"items": info["items"],
		"totals": info["totals"],
		"shown": info["shown"],
		"count": info["count"],
		"guest": info["guest"],
		"guest_allowed": guest_allowed(),
		"methods": methods(),
		"bank": bank_details(),
		"known": known_details(),
		"national_address_required": national_address_required(),
		"countries": _countries(),
	}


def _countries():
	names = frappe.get_all("Country", pluck="name", order_by="name")
	# the shop is in Riyadh and nearly every order is domestic, so put the
	# common answer where it is one click away rather than forty scrolls down
	return ["Saudi Arabia"] + [n for n in names if n != "Saudi Arabia"]


# ------------------------------------------------------------- the coupon
@frappe.whitelist(allow_guest=True, methods=["POST"])
def apply_coupon(code=None):
	"""Put a coupon on the basket, or say why it cannot go on."""
	code = (code or "").strip()
	basket = cart.get_basket()
	if not basket or not basket.get("items"):
		frappe.throw(say("Your cart is empty."))

	if not code:
		_set_coupon(basket, None)
		return _coupon_answer(basket, say("Coupon removed."))

	problem = totals.coupon_problem(code)
	if problem:
		frappe.throw(problem)

	resolved = totals.resolve_coupon(code)
	_set_coupon(basket, resolved)

	basket.reload()
	if not totals.summarise(basket.get("items"), resolved)["discount"]:
		_set_coupon(basket, None)
		frappe.throw(say("That coupon does not apply to what is in your cart."))

	return _coupon_answer(basket, say("Coupon applied."))


def _set_coupon(basket, value):
	frappe.db.set_value(basket.doctype, basket.name, "coupon_code", value,
	                    update_modified=False)
	frappe.db.commit()


def _coupon_answer(basket, message):
	basket.reload()
	money = totals.summarise(basket.get("items"), basket.get("coupon_code"))
	return {"ok": 1, "message": message, "totals": money,
	        "shown": totals.as_text(money),
	        # the header counter shows the payable total, so a coupon changes it
	        # too - and a header still quoting the pre-discount figure is the
	        # first thing anyone notices
	        "total_text": cart._total_text(basket),
	        "coupon": basket.get("coupon_code") or ""}


# --------------------------------------------------------------- the order
def _clean(value, limit=140):
	return " ".join(str(value or "").split())[:limit]


def _check(details):
	"""Read the form, and refuse it in words the customer can act on."""
	person = {
		"first_name": _clean(details.get("first_name"), 60),
		"last_name": _clean(details.get("last_name"), 60),
		"email": _clean(details.get("email"), 140).lower(),
		"phone": _clean(details.get("phone"), 40),
		"company_name": _clean(details.get("company_name"), 140),
		"cr_number": _clean(details.get("cr_number"), 40),
		"tax_id": _clean(details.get("tax_id"), 40),
	}
	if not person["first_name"]:
		frappe.throw(say("Please enter your first name."))
	if not person["email"] or not EMAIL.match(person["email"]):
		frappe.throw(say("Please enter an email address we can send the invoice to."))
	if not person["phone"]:
		frappe.throw(say("Please enter a phone number, so we can arrange fitting."))

	billing = _address(details, "billing")
	same = cint(details.get("ship_to_billing") or 0)
	shipping = billing if same else _address(details, "shipping")

	return person, billing, shipping, bool(same)


def _address(details, prefix):
	"""One address block off the form."""
	def field(name, limit=140):
		return _clean(details.get("%s_%s" % (prefix, name)), limit)

	out = {
		"building_no": field("building_no", 10),
		"address_line1": field("address_line1"),
		"address_line2": field("address_line2"),
		"district": field("district", 80),
		"city": field("city", 80),
		"state": field("state", 80),
		"pincode": field("pincode", 20),
		"country": field("country", 80) or "Saudi Arabia",
		"national_address": field("national_address", 20).upper(),
	}

	# Built from two separate lookups rather than one sentence with the label
	# interpolated into it. The Arabic pass matches whole strings, so a message
	# assembled by format() is a string that can never be in the dictionary -
	# and this is the text a customer reads when something has gone wrong,
	# which is the worst possible moment to be shown English.
	label = say("Billing address") if prefix == "billing" 		else say("Delivery address")

	def refuse(message):
		frappe.throw("%s: %s" % (label, say(message)))

	problem = address_problem(out)
	if problem:
		refuse(problem)

	code = out["national_address"]
	if code and not NATIONAL_ADDRESS.match(code):
		refuse("a National Address is four letters and four digits, "
		       "like RRRD2929.")
	if not code and national_address_required() and prefix == "billing":
		refuse("please enter your National Address.")
	return out


def _customer_for(person):
	"""The Customer this order belongs to, found or made.

	A guest's email is matched against the contacts we already hold, so a repeat
	customer who never bothers to sign in still builds one history rather than a
	new Customer record every time they order.
	"""
	existing = _existing_customer()
	if existing:
		_update_customer(existing, person)
		return existing

	contact = frappe.db.get_value("Contact Email", {"email_id": person["email"]},
	                              "parent")
	if contact:
		linked = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "parent": contact,
			 "link_doctype": "Customer"}, "link_name")
		if linked and frappe.db.exists("Customer", linked):
			_update_customer(linked, person)
			return linked

	name = person["company_name"] or \
		("%s %s" % (person["first_name"], person["last_name"])).strip()
	doc = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": name,
		"customer_type": "Company" if person["company_name"] else "Individual",
		"tax_id": person["tax_id"] or None,
	})
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	if person["cr_number"]:
		frappe.db.set_value("Customer", doc.name, "cr_number",
		                    person["cr_number"], update_modified=False)
	_contact_for(doc.name, person)
	return doc.name


def _update_customer(customer, person):
	"""Fill in what the customer has just told us, without overwriting a name.

	The VAT and CR numbers are theirs to correct, so a newer answer wins. The
	customer_name is not touched: the team may have tidied it, and an order form
	should not undo that.
	"""
	changes = {}
	if person["tax_id"]:
		changes["tax_id"] = person["tax_id"]
	if person["cr_number"]:
		changes["cr_number"] = person["cr_number"]
	if changes:
		frappe.db.set_value("Customer", customer, changes, update_modified=False)
	_contact_for(customer, person)


def _contact_for(customer, person):
	"""A Contact carrying the buyer's own name, email and phone."""
	contact = frappe.db.get_value("Contact Email", {"email_id": person["email"]},
	                              "parent")
	if contact:
		return contact

	doc = frappe.get_doc({
		"doctype": "Contact",
		"first_name": person["first_name"] or person["email"],
		"last_name": person["last_name"] or None,
		"user": frappe.session.user if not cart.is_guest() else None,
	})
	doc.append("email_ids", {"email_id": person["email"], "is_primary": 1})
	if person["phone"]:
		doc.append("phone_nos", {"phone": person["phone"], "is_primary_mobile_no": 1})
	doc.append("links", {"link_doctype": "Customer", "link_name": customer})
	doc.flags.ignore_mandatory = True
	try:
		doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="kayan_curtain: contact for %s" % customer)
		return None
	return doc.name


BUILDING_NO = re.compile(r"^\d{4}$")
POSTAL_CODE = re.compile(r"^\d{5}$")


def address_problem(values):
	"""The first thing missing or wrong in an address, as a sentence, or None.

	The five parts of a Saudi National Address - building number, street,
	district, city, postal code - are what a fitter needs to find the door, and
	what the invoice has to print. All five are required. The two numbers are
	checked for shape only in Saudi Arabia, where a building number is always
	four digits and a postal code five.

	Shared by the checkout and the account's address book, so an address saved
	in one is never refused by the other.
	"""
	if not values.get("building_no"):
		return "please enter the building number."
	if not values.get("address_line1"):
		return "please enter the street name."
	if not values.get("district"):
		return "please enter the district."
	if not values.get("city"):
		return "please enter the city."
	if not values.get("pincode"):
		return "please enter the postal code."
	if (values.get("country") or "Saudi Arabia") == "Saudi Arabia":
		if not BUILDING_NO.match(values["building_no"]):
			return "the building number is four digits."
		if not POSTAL_CODE.match(values["pincode"]):
			return "the postal code is five digits."
	return None


def _save_address(customer, person, values, kind):
	"""Write one address, reusing an identical one rather than stacking copies."""
	title = person["company_name"] or \
		("%s %s" % (person["first_name"], person["last_name"])).strip() or \
		person["email"]

	for name in frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Address", "link_doctype": "Customer",
			         "link_name": customer}, pluck="parent"):
		row = frappe.db.get_value(
			"Address", name,
			["address_line1", "city", "pincode", "address_type", "building_no"],
			as_dict=True)
		if row and row.address_type == kind \
				and (row.building_no or "") == values["building_no"] \
				and (row.address_line1 or "") == values["address_line1"] \
				and (row.city or "") == values["city"] \
				and (row.pincode or "") == values["pincode"]:
			_stamp_national_address(name, values["national_address"])
			return name

	doc = frappe.get_doc({
		"doctype": "Address",
		"address_title": "%s (%s)" % (title, kind),
		"address_type": kind,
		"building_no": values["building_no"],
		"address_line1": values["address_line1"],
		"district": values["district"],
		"address_line2": values["address_line2"] or None,
		"city": values["city"],
		"state": values["state"] or None,
		"pincode": values["pincode"] or None,
		"country": values["country"],
		"phone": person["phone"] or None,
		"email_id": person["email"],
		"is_primary_address": 1 if kind == "Billing" else 0,
		"is_shipping_address": 1 if kind == "Shipping" else 0,
	})
	doc.append("links", {"link_doctype": "Customer", "link_name": customer})
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	_stamp_national_address(doc.name, values["national_address"])
	return doc.name


def _stamp_national_address(name, code):
	if code:
		frappe.db.set_value("Address", name, "national_address", code,
		                    update_modified=False)


# ------------------------------------------------------- basket -> quotation
def _vat_account(company):
	"""The account VAT is posted to, or None if this site has no tax set up."""
	from kayan_curtain.install import vat_account_for

	return vat_account_for(company)


def apply_money(quotation):
	"""Write the discount and the tax onto the document itself.

	The checkout page has already shown the customer these numbers. Putting the
	same ones on the Quotation as real ERPNext rows is what makes the tax
	invoice agree with the page - and it is ERPNext, not this code, that then
	carries them through to the invoice.
	"""
	money = totals.summarise(quotation.get("items"), quotation.get("coupon_code"))
	inclusive = money["vat_included"]

	quotation.set("taxes", [])
	account = _vat_account(quotation.company) if money["vat_rate"] else None
	if account:
		quotation.append("taxes", {
			"charge_type": "On Net Total",
			"account_head": account,
			"description": "VAT %g%%" % money["vat_rate"],
			"rate": money["vat_rate"],
			"included_in_print_rate": 1 if inclusive else 0,
		})

	if money["discount"]:
		# where the discount comes off depends on whether the line prices are
		# tax-inclusive: off the grand total when the tax is already inside
		# them, off the net when it is added afterwards. Getting this the wrong
		# way round moves the total by the VAT on the discount.
		quotation.apply_discount_on = "Grand Total" if inclusive else "Net Total"
		quotation.discount_amount = money["discount"]
		quotation.additional_discount_percentage = 0
	else:
		quotation.discount_amount = 0
		quotation.additional_discount_percentage = 0
	return money


def build_quotation(customer, billing, shipping, person, method):
	"""The draft order, from whichever kind of basket this visitor has."""
	basket = cart.get_basket()
	if not basket or not basket.get("items"):
		frappe.throw(say("Your cart is empty."))

	cart.reprice(basket)

	if basket.doctype == "Quotation":
		quotation = basket
		quotation.party_name = customer
	else:
		company, currency, price_list = cart._defaults()
		quotation = frappe.get_doc({
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": customer,
			"order_type": "Shopping Cart",
			"transaction_date": frappe.utils.nowdate(),
			"company": company,
			"currency": currency,
			"selling_price_list": price_list,
			"coupon_code": basket.get("coupon_code") or None,
		})
		for row in basket.get("items"):
			line = quotation.append("items", {
				"item_code": row.item_code,
				"qty": row.qty,
				"rate": row.rate,
				"description": row.get("description"),
			})
			line.set(cart.CONFIG_FIELD, row.get(cart.CONFIG_FIELD))

	quotation.customer_address = billing
	quotation.shipping_address_name = shipping
	quotation.contact_email = person["email"]
	quotation.contact_mobile = person["phone"]

	apply_money(quotation)
	orders.stamp_quotation(quotation)

	quotation.flags.ignore_permissions = True
	quotation.flags.ignore_mandatory = True
	# Saving a Quotation makes ERPNext read the Item behind every line, and it
	# reads it with check_permission rather than with our ignore_permissions
	# flag - a storefront customer has no read permission on Item, by design, so
	# the save dies after they have filled in the whole form. The basket was
	# fetched above, while we were still whoever the visitor is; only the write
	# runs as someone allowed to read a catalogue.
	with as_system_user():
		quotation.save(ignore_permissions=True)

	frappe.db.set_value("Quotation", quotation.name, {
		METHOD_FIELD: method,
		ACCESS_FIELD: quotation.get(ACCESS_FIELD) or frappe.generate_hash(length=24),
	}, update_modified=False)
	frappe.db.commit()

	if basket.doctype != "Quotation":
		_retire_guest_cart(basket, quotation.name)

	quotation.reload()
	return quotation


def _retire_guest_cart(basket, quotation_name):
	"""The guest cart has become an order; move its files and let it go."""
	cart.move_attachments(cart.GUEST_DOCTYPE, basket.name, quotation_name)
	frappe.db.set_value(cart.GUEST_DOCTYPE, basket.name, "claimed_by",
	                    quotation_name, update_modified=False)
	frappe.delete_doc(cart.GUEST_DOCTYPE, basket.name, force=True,
	                  ignore_permissions=True)
	frappe.db.commit()
	cart._forget_cart()


# ------------------------------------------------------------------ placing
@frappe.whitelist(allow_guest=True, methods=["POST"])
def place(**details):
	"""Take the form, make the order, and say where the browser goes next."""
	if cart.is_guest() and not guest_allowed():
		frappe.throw(say("Please sign in to place your order."),
		             frappe.PermissionError)

	method = (details.get("payment_method") or "").strip().lower()
	offered = {m["key"] for m in methods()}
	if method not in offered:
		frappe.throw(say("Please choose how you would like to pay."))

	person, billing_values, shipping_values, same = _check(details)

	customer = _customer_for(person)
	billing = _save_address(customer, person, billing_values, "Billing")
	shipping = billing if same else \
		_save_address(customer, person, shipping_values, "Shipping")

	quotation = build_quotation(customer, billing, shipping, person, method)

	if method == CARD:
		from kayan_curtain import clickpay

		payment = clickpay.start_payment(quotation)
		return {"ok": 1, "redirect": payment["redirect_url"]}

	bank_order(quotation)
	return {"ok": 1, "redirect": confirmation_url(quotation)}


def confirmation_url(quotation):
	return "/order-placed?order=%s&key=%s" % (
		quotation.name, quotation.get(ACCESS_FIELD) or "")


def bank_order(quotation):
	"""Place a bank-transfer order, and raise its invoice as a draft.

	Deliberately different from the card path. There the invoice is raised
	because the money has arrived; here it is raised so there is something for
	the customer to pay against and for the team to reconcile - and it stays
	outstanding until somebody confirms the transfer. Calling both of these
	"order placed" without that difference being visible anywhere would leave
	the team unable to tell which orders have been paid for.
	"""
	from kayan_curtain import clickpay

	invoice = None
	try:
		# Nothing is submitted (see orders.py) - the quotation stays a draft
		# and the invoice is made as one. Making it still reads each line's
		# Item through check_permission, which a storefront customer fails, so
		# it runs elevated for the same reason the save did.
		with as_system_user():
			invoice = clickpay._raise_invoice(quotation)
	except Exception:
		frappe.log_error(title="kayan_curtain: bank transfer invoice",
		                 message=frappe.get_traceback())

	frappe.db.set_value("Quotation", quotation.name,
	                    clickpay.STATUS_FIELD, AWAITING_TRANSFER,
	                    update_modified=False)
	frappe.db.commit()

	from kayan_curtain import notify

	notify.order_placed(quotation, "bank")
	return invoice
