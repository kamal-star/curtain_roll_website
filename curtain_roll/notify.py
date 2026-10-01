# -*- coding: utf-8 -*-
"""Who hears about a website order, and what they are told.

Two moments are the website's own, and are sent from here:

  * an order is placed for bank transfer, or a card payment goes through (or
    is held for review): the team gets a bell notification in ERPNext (and an
    email, if addresses are set), and the customer gets an email.

    These cannot be ERPNext Notifications: the order's payment status is
    written with db.set_value, inside a row lock, and a Notification only
    fires on a document event. The wording is still the team's to change -
    it lives in the Email Templates named "Kayan: ...".

Everything after that is something the team does in ERPNext - confirming the
order, issuing the invoice, sending it out - so those are ordinary ERPNext
Notifications (also named "Kayan: ..."), created once by ensure_setup() and
edited, switched off or given an SMS channel in the desk like any other.

Nothing here is allowed to stop an order: a mail server that is down must not
turn a paid order into an error page. Every send is wrapped and logged.
"""

import frappe

from curtain_roll.storefront import storefront_settings

ORDER_RECEIVED = "Kayan: Order Received"
PAYMENT_RECEIVED = "Kayan: Payment Received"


# ------------------------------------------------------------------ sending
def order_placed(quotation, event):
	"""Tell the team and the customer. event: "bank", "paid" or "pending"."""
	try:
		_alert_team(quotation, event)
	except Exception:
		frappe.log_error(title="curtain_roll: team alert for %s" % quotation.name)
	if event == "pending":
		return    # the customer hears once the payment is actually confirmed
	try:
		_email_customer(quotation, ORDER_RECEIVED if event == "bank" else PAYMENT_RECEIVED)
	except Exception:
		frappe.log_error(title="curtain_roll: customer email for %s" % quotation.name)


def _money(quotation):
	from curtain_roll import totals

	return totals.as_text(
		totals.summarise(quotation.get("items"), quotation.get("coupon_code")))["total"]


TEAM_SUBJECT = {
	"bank": "New website order {0} from {1} - {2}, awaiting bank transfer",
	"paid": "Website order {0} from {1} - {2}, paid by card",
	"pending": "Website order {0} from {1} - {2}: card payment held for review",
}


def _alert_team(quotation, event):
	settings = storefront_settings()
	subject = TEAM_SUBJECT[event].format(
		quotation.name, quotation.customer_name or quotation.party_name, _money(quotation))

	role = settings.get("alert_role")
	users = _users_with(role) if role else []
	if users:
		from frappe.desk.doctype.notification_log.notification_log import \
			enqueue_create_notification

		# no from_user: Frappe skips the recipient who is also the sender, and
		# the one person certain to hold every role is Administrator
		enqueue_create_notification(users, {
			"type": "Alert",
			"document_type": "Quotation",
			"document_name": quotation.name,
			"subject": frappe.utils.escape_html(subject),
		})

	emails = [e.strip() for e in (settings.get("alert_emails") or "").replace(";", ",").split(",")
	          if e.strip()]
	if emails:
		link = frappe.utils.get_url("/app/quotation/%s" % quotation.name)
		frappe.sendmail(
			recipients=emails, subject=subject,
			message="<p>%s</p><p><a href=\"%s\">%s</a></p>" % (
				frappe.utils.escape_html(subject), link, "Open the order in ERPNext"),
			reference_doctype="Quotation", reference_name=quotation.name)


def inquiry_received(inquiry):
	"""A Contact Us message: the same people who hear about orders hear this."""
	settings = storefront_settings()
	subject = "Website enquiry from %s (%s)%s" % (
		inquiry.full_name, inquiry.phone,
		" - %s" % inquiry.inquiry_type if inquiry.inquiry_type else "")
	role = settings.get("alert_role")
	users = _users_with(role) if role else []
	if users:
		from frappe.desk.doctype.notification_log.notification_log import \
			enqueue_create_notification

		enqueue_create_notification(users, {
			"type": "Alert", "document_type": "Curtain Inquiry",
			"document_name": inquiry.name, "subject": frappe.utils.escape_html(subject),
		})
	emails = [e.strip() for e in (settings.get("alert_emails") or "").replace(";", ",").split(",")
	          if e.strip()]
	if emails:
		link = frappe.utils.get_url("/app/curtain-inquiry/%s" % inquiry.name)
		frappe.sendmail(
			recipients=emails, subject=subject,
			message="<p><b>%s</b><br>%s<br>%s</p><p>%s</p><p><a href=\"%s\">Open in ERPNext</a></p>" % (
				frappe.utils.escape_html(inquiry.full_name), frappe.utils.escape_html(inquiry.phone),
				frappe.utils.escape_html(inquiry.email or ""),
				frappe.utils.escape_html(inquiry.message).replace("\n", "<br>"), link),
			reference_doctype="Curtain Inquiry", reference_name=inquiry.name)


def _users_with(role):
	users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"},
	                       pluck="parent")
	if not users:
		return []
	# emails, not user ids: enqueue_create_notification looks users up by email
	# (Administrator's id and email differ)
	return frappe.get_all("User", filters={"name": ["in", users], "enabled": 1,
	                                       "user_type": "System User"}, pluck="email")


def _email_customer(quotation, template):
	settings = storefront_settings()
	if frappe.utils.cint(settings.get("no_customer_emails")):
		return
	to = (quotation.get("contact_email") or "").strip()
	if not to or not frappe.db.exists("Email Template", template):
		return

	from curtain_roll import checkout

	t = frappe.get_doc("Email Template", template)
	context = {
		"doc": quotation,
		"customer_name": quotation.customer_name or "",
		"order_no": quotation.name,
		"total": _money(quotation),
		"bank": checkout.bank_details(),
		"order_url": frappe.utils.get_url(checkout.confirmation_url(quotation)),
		"items": quotation.get("items"),
	}
	body = t.response_html if t.use_html else t.response
	frappe.sendmail(
		recipients=[to],
		subject=frappe.render_template(t.subject, context),
		message=frappe.render_template(body or "", context),
		reference_doctype="Quotation", reference_name=quotation.name)


# ------------------------------------------------------------------- set-up
_STYLE = ('style="font-family:Arial,sans-serif;font-size:14px;color:#14181d;'
          'line-height:1.6;max-width:560px"')

ORDER_RECEIVED_HTML = """<div """ + _STYLE + """>
<p>Dear {{ customer_name }},</p>
<p>Thank you for your order <b>{{ order_no }}</b>. We will start on it as soon as your
bank transfer reaches us.</p>
<table cellpadding="4" style="border-collapse:collapse">
{% if bank.bank %}<tr><td>Bank</td><td><b>{{ bank.bank }}</b></td></tr>{% endif %}
{% if bank.account %}<tr><td>Account name</td><td><b>{{ bank.account }}</b></td></tr>{% endif %}
{% if bank.number %}<tr><td>Account number</td><td><b>{{ bank.number }}</b></td></tr>{% endif %}
<tr><td>IBAN</td><td><b>{{ bank.iban }}</b></td></tr>
<tr><td>Amount</td><td><b>{{ total }}</b></td></tr>
<tr><td>Reference</td><td><b>{{ order_no }}</b></td></tr>
</table>
{% if bank.instructions %}<p>{{ bank.instructions }}</p>{% endif %}
<p><a href="{{ order_url }}">View your order</a></p>
<hr>
<div dir="rtl" style="text-align:right">
<p>عزيزنا {{ customer_name }}،</p>
<p>شكراً لطلبك رقم <b>{{ order_no }}</b>. سنبدأ في تنفيذه فور وصول التحويل البنكي.</p>
<p>المبلغ: <b>{{ total }}</b> — المرجع: <b>{{ order_no }}</b><br>
الآيبان: <b>{{ bank.iban }}</b>{% if bank.number %} — رقم الحساب: <b>{{ bank.number }}</b>{% endif %}</p>
<p><a href="{{ order_url }}">عرض الطلب</a></p>
</div>
<p>Kayan Andalus</p>
</div>"""

PAYMENT_RECEIVED_HTML = """<div """ + _STYLE + """>
<p>Dear {{ customer_name }},</p>
<p>We have received your payment of <b>{{ total }}</b> for order <b>{{ order_no }}</b>.
Our team will contact you to arrange measuring and fitting.</p>
<p><a href="{{ order_url }}">View your order</a></p>
<hr>
<div dir="rtl" style="text-align:right">
<p>عزيزنا {{ customer_name }}،</p>
<p>تم استلام دفعتك بمبلغ <b>{{ total }}</b> للطلب رقم <b>{{ order_no }}</b>.
سيتواصل معك فريقنا لترتيب القياس والتركيب.</p>
<p><a href="{{ order_url }}">عرض الطلب</a></p>
</div>
<p>Kayan Andalus</p>
</div>"""

TEMPLATES = (
	(ORDER_RECEIVED,
	 "Your order {{ order_no }} - bank transfer details / تفاصيل التحويل لطلبك",
	 ORDER_RECEIVED_HTML),
	(PAYMENT_RECEIVED,
	 "Payment received for order {{ order_no }} / تم استلام الدفع",
	 PAYMENT_RECEIVED_HTML),
)

# (name, doctype, condition, subject, message, attach the print)
STATUS_NOTIFICATIONS = (
	("Kayan: Order Confirmed", "Sales Order",
	 'doc.order_type == "Shopping Cart"',
	 "Your order is confirmed - {{ doc.name }} / تم تأكيد طلبك",
	 """<p>Dear {{ doc.customer_name }},</p>
<p>Your order is confirmed ({{ doc.name }}, {{ doc.get_formatted("grand_total") }}).
We will be in touch to arrange delivery and fitting.</p>
<hr><div dir="rtl" style="text-align:right">
<p>عزيزنا {{ doc.customer_name }}، تم تأكيد طلبك ({{ doc.name }}). سنتواصل معك لترتيب التوصيل والتركيب.</p></div>
<p>Kayan Andalus</p>""", 0),
	("Kayan: Invoice Issued", "Sales Invoice",
	 'doc.get("cr_quotation")',
	 "Your invoice {{ doc.name }} / فاتورتك",
	 """<p>Dear {{ doc.customer_name }},</p>
<p>Please find your tax invoice {{ doc.name }} attached
({{ doc.get_formatted("grand_total") }}).</p>
<hr><div dir="rtl" style="text-align:right">
<p>عزيزنا {{ doc.customer_name }}، مرفق فاتورتك الضريبية رقم {{ doc.name }}.</p></div>
<p>Kayan Andalus</p>""", 1),
	("Kayan: Out for Delivery", "Delivery Note",
	# doc.get("items"), never doc.items: the condition is also evaluated
	# against a plain dict, where .items is the dict method
	 'doc.get("items") and frappe.db.get_value("Sales Order", '
	 'doc.get("items")[0].get("against_sales_order"), "order_type") == "Shopping Cart"',
	 "Your order is on its way - {{ doc.name }} / طلبك في الطريق",
	 """<p>Dear {{ doc.customer_name }},</p>
<p>Your order is on its way. Our team will contact you before arriving.</p>
<hr><div dir="rtl" style="text-align:right">
<p>عزيزنا {{ doc.customer_name }}، طلبك في الطريق إليك، وسيتواصل معك فريقنا قبل الوصول.</p></div>
<p>Kayan Andalus</p>""", 0),
)


def ensure_setup():
	"""The Email Templates and Notifications, made once and never overwritten.

	Once they exist they are the team's: a migrate that put the wording back
	would undo every edit they made.
	"""
	for name, subject, html in TEMPLATES:
		if frappe.db.exists("Email Template", name):
			continue
		try:
			frappe.get_doc({"doctype": "Email Template", "name": name, "subject": subject,
			                "use_html": 1, "response_html": html}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title="curtain_roll: email template %s" % name)

	for name, doctype, condition, subject, message, attach in STATUS_NOTIFICATIONS:
		if frappe.db.exists("Notification", name) or not frappe.db.exists("DocType", doctype):
			continue
		try:
			frappe.get_doc({
				"doctype": "Notification", "name": name, "enabled": 1,
				"channel": "Email", "document_type": doctype, "event": "Submit",
				"condition": condition, "subject": subject, "message": message,
				"message_type": "HTML", "attach_print": attach,
				"recipients": [{"receiver_by_document_field": "contact_email"}],
			}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title="curtain_roll: notification %s" % name)
