# -*- coding: utf-8 -*-
"""Aramex delivery for "Without installation": the city list and the price.

Two Aramex services, from the integration pack Aramex sent Kayan
(ShippingAPI.V2):

  * Location API, FetchCities - every city Aramex delivers to in Saudi
    Arabia. The customer searches it on the product page.
  * Rate Calculator API, CalculateRate - the price of sending a parcel of a
    given weight from our city to theirs.

The account details are secrets and live only in the site's
site_config.json, never in this repository:

    "aramex_username", "aramex_password", "aramex_account_number",
    "aramex_account_pin", "aramex_account_entity" (e.g. "RUH"),
    "aramex_account_country_code" (default "SA"),
    "aramex_base_url" (default the live https://ws.aramex.net/ShippingAPI.V2;
                       the test one is https://ws.uat.aramex.net/ShippingAPI.V2,
                       which Aramex only answers once our IP is whitelisted)

What is not secret - whether delivery is offered, the city we ship from, the
parcel weight per square metre - is in Curtain Storefront Settings.

Every answer is cached: the live price is asked for on each keystroke of the
size boxes, and Aramex must not be asked the same question twice an hour.

"aramex_mock": 1 in site_config makes both calls answer with made-up cities
and prices - for a developer machine only, so the page can be built and
tested before the account exists.
"""

import json

import frappe
from frappe.utils import cint, flt

from kayan_curtain.storefront import storefront_settings

LIVE_URL = "https://ws.aramex.net/ShippingAPI.V2"
CITIES_KEY = "curtain_roll_aramex_cities"
RATE_KEY = "curtain_roll_aramex_rate:%s:%s"


# ------------------------------------------------------------------ set-up
AUTH_FAILED_KEY = "curtain_roll_aramex_auth_failed"
# Aramex's answers that mean the account itself is refused, not this request.
# ERR75 bad login, ERR82 account/PIN/entity mismatch, ERR03 account blocked.
AUTH_CODES = ("ERR75", "ERR82", "ERR03")
AUTH_PAUSE = 6 * 60 * 60


def enabled():
	"""Delivery is offered: switched on in the settings, an account to use, and
	that account not refused by Aramex in the last few hours."""
	settings = storefront_settings()
	return bool(cint(settings.get("aramex_enabled"))) and configured() \
		and not frappe.cache().get_value(AUTH_FAILED_KEY)


def configured():
	conf = frappe.conf
	if cint(conf.get("aramex_mock")):
		return True
	return all(conf.get(k) for k in ("aramex_username", "aramex_password",
	                                  "aramex_account_number", "aramex_account_pin",
	                                  "aramex_account_entity"))


def _client_info():
	conf = frappe.conf
	return {
		"UserName": conf.get("aramex_username"),
		"Password": conf.get("aramex_password"),
		"Version": "v1.0",
		"AccountNumber": conf.get("aramex_account_number"),
		"AccountPin": conf.get("aramex_account_pin"),
		"AccountEntity": conf.get("aramex_account_entity"),
		"AccountCountryCode": conf.get("aramex_account_country_code") or "SA",
		"Source": 24,
	}


def _country():
	return frappe.conf.get("aramex_account_country_code") or "SA"


def _post(path, payload):
	"""POST to Aramex; the parsed answer, or raise with Aramex's own words."""
	import requests

	url = (frappe.conf.get("aramex_base_url") or LIVE_URL).rstrip("/") + path
	body = dict(payload, ClientInfo=_client_info(),
	            Transaction={"Reference1": "", "Reference2": "", "Reference3": "",
	                         "Reference4": "", "Reference5": ""})
	response = requests.post(url, json=body, timeout=20,
	                         headers={"Accept": "application/json"})
	try:
		data = response.json()
	except ValueError:
		raise AramexError("Aramex answered %s with no data" % response.status_code)
	if data.get("HasErrors"):
		codes = [str(n.get("Code") or "") for n in data.get("Notifications") or []]
		notes = "; ".join("%s %s" % (n.get("Code") or "", n.get("Message") or "")
		                  for n in data.get("Notifications") or [])
		if any(c in AUTH_CODES for c in codes):
			# The account is refused. Asking again with the same details only
			# counts more wrong attempts - Aramex blocks the account after a
			# few (ERR03) - so stop asking for a while: the delivery box hides
			# itself (enabled() is False) and the team sees this once.
			frappe.cache().set_value(AUTH_FAILED_KEY, notes, expires_in_sec=AUTH_PAUSE)
			frappe.log_error(title="kayan_curtain: Aramex refused the account - paused 6 hours",
			                 message=notes + "\n\nFix the aramex_* values in site_config.json, then "
			                 "end the pause at once with: bench --site <site> execute "
			                 "kayan_curtain.aramex.clear_pause  (or wait 6 hours).")
		raise AramexError(notes.strip() or "Aramex reported an error")
	return data


class AramexError(Exception):
	pass


def clear_pause():
	"""End the pause after an account refusal, once the details are fixed.

	bench --site <site> execute kayan_curtain.aramex.clear_pause
	"""
	frappe.cache().delete_value(AUTH_FAILED_KEY)
	return "Aramex pause cleared"


def _address(city):
	return {"Line1": "", "Line2": "", "Line3": "", "City": city,
	        "StateOrProvinceCode": "", "PostCode": "", "CountryCode": _country()}


# ------------------------------------------------------------------ cities
def cities():
	"""Every Saudi city Aramex delivers to, sorted. Cached for a day."""
	cached = frappe.cache().get_value(CITIES_KEY)
	if cached:
		return cached
	if cint(frappe.conf.get("aramex_mock")):
		found = ["Abha", "Al Khobar", "Dammam", "Jeddah", "Jubail", "Madinah",
		         "Makkah", "Riyadh", "Tabuk", "Taif"]
	else:
		data = _post("/Location/Service_1_0.svc/json/FetchCities",
		             {"CountryCode": _country(), "NameStartsWith": "", "State": None})
		found = sorted({c.strip() for c in (data.get("Cities") or []) if c and c.strip()})
	frappe.cache().set_value(CITIES_KEY, found, expires_in_sec=24 * 60 * 60)
	return found


@frappe.whitelist(allow_guest=True)
def city_list():
	"""For the product page's search box. Empty when delivery is not offered."""
	if not enabled():
		return []
	try:
		return cities()
	except Exception:
		frappe.log_error(title="kayan_curtain: Aramex city list")
		return []


# -------------------------------------------------------------------- rate
def parcel_weight(area_sqm):
	"""Kilograms for one curtain of this many square metres."""
	settings = storefront_settings()
	per_sqm = flt(settings.get("aramex_weight_per_sqm")) or 1.5
	minimum = flt(settings.get("aramex_min_weight")) or 1.0
	return max(minimum, round(flt(area_sqm) * per_sqm * 2) / 2.0)    # nearest 0.5 kg


def rate(city, weight_kg):
	"""Aramex's price to send `weight_kg` to `city`, in SAR. Cached for an hour."""
	weight_kg = max(0.5, round(flt(weight_kg) * 2) / 2.0)
	key = RATE_KEY % (city, weight_kg)
	cached = frappe.cache().get_value(key)
	if cached is not None:
		return flt(cached)

	settings = storefront_settings()
	if cint(frappe.conf.get("aramex_mock")):
		amount = 25.0 + 4.0 * weight_kg + (0 if city == "Riyadh" else 15.0)
	else:
		origin = settings.get("aramex_origin_city") or "Riyadh"
		weight = {"Value": weight_kg, "Unit": "KG"}
		# every member below is required by Aramex's deserialiser, empty or
		# not - leave one out and it answers with an HTML "Request Error"
		# (checked against the live service, 2026-10-02)
		data = _post("/RateCalculator/Service_1_0.svc/json/CalculateRate", {
			"OriginAddress": _address(origin),
			"DestinationAddress": _address(city),
			"ShipmentDetails": {
				"Dimensions": None,
				"ActualWeight": weight,
				"ChargeableWeight": weight,
				"DescriptionOfGoods": "Curtains",
				"GoodsOriginCountry": _country(),
				"NumberOfPieces": 1,
				"ProductGroup": "DOM",
				"ProductType": settings.get("aramex_product_type") or "ONP",
				"PaymentType": "P",
				"PaymentOptions": "",
				"Services": "",
				"CashOnDeliveryAmount": None,
				"InsuranceAmount": None,
				"CashAdditionalAmount": None,
				"CustomsValueAmount": None,
				"Items": [],
			},
			"PreferredCurrencyCode": "SAR",
		})
		amount = flt((data.get("TotalAmount") or {}).get("Value"))
		if amount <= 0:
			raise AramexError("Aramex returned no price: %s" % json.dumps(data)[:300])
	frappe.cache().set_value(key, amount, expires_in_sec=60 * 60)
	return amount
