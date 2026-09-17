/*
 * Glue between the ERPNext product page and the obfuscated curtain configurator.
 *
 * The bundle is a black box. All we may rely on is its published surface:
 *   window.modelchanger(group, imageUrl, code, $el)  - change a material
 *   #input-option<N>                                 - where it writes its render
 *   #c / .model-loader                               - where it mounts
 *
 * So this file only (a) forwards swatch clicks into modelchanger and
 * (b) reads the capture field when the quote form is submitted.
 */
(function () {
	"use strict";

	var READY_TIMEOUT_MS = 20000;

	function onReady(fn) {
		if (document.readyState !== "loading") fn();
		else document.addEventListener("DOMContentLoaded", fn);
	}

	// The bundle calls $(this); without jQuery it throws on the first swatch.
	function waitForDeps(cb) {
		var started = Date.now();
		(function poll() {
			var haveJq = typeof window.jQuery === "function";
			var haveMc = typeof window.modelchanger === "function";
			if (haveJq && haveMc) return cb(null);
			if (Date.now() - started > READY_TIMEOUT_MS) {
				return cb(new Error(
					"configurator not ready (jQuery=" + haveJq + ", modelchanger=" + haveMc + ")"));
			}
			setTimeout(poll, 120);
		})();
	}

	function bindSwatches() {
		var swatches = document.querySelectorAll(".cr-swatches input[type=radio]");
		if (!swatches.length) return;

		Array.prototype.forEach.call(swatches, function (el) {
			el.addEventListener("change", function () {
				if (typeof window.modelchanger !== "function") return;
				try {
					window.modelchanger(
						el.getAttribute("data-cr-group"),
						el.getAttribute("data-cr-image"),
						el.getAttribute("data-cr-code"),
						window.jQuery(el)
					);
				} catch (e) {
					if (window.console) console.warn("[curtain-roll] modelchanger failed", e);
				}
			});
		});
	}

	function capturedImage() {
		var field = document.querySelector(".cr-capture");
		return field && field.value ? field.value : "";
	}

	function selectionSummary() {
		var out = [];
		document.querySelectorAll(".cr-group").forEach(function (group) {
			var label = group.querySelector(".cr-group-label");
			var picked = group.querySelector("input[type=radio]:checked");
			if (label && picked) {
				out.push(label.textContent.trim() + ": " + (picked.getAttribute("data-cr-code") || ""));
			}
		});
		return out.join(" | ");
	}

	function bindQuoteForm() {
		var form = document.getElementById("cr-quote-form");
		if (!form) return;
		var result = form.querySelector(".cr-quote-result");
		var button = form.querySelector(".cr-submit");

		form.addEventListener("submit", function (ev) {
			ev.preventDefault();
			result.textContent = "";
			result.className = "cr-quote-result";
			button.disabled = true;

			var data = new FormData(form);
			var payload = {
				product: form.getAttribute("data-product"),
				name: data.get("name"),
				phone: data.get("phone"),
				email: data.get("email"),
				city: data.get("city"),
				notes: data.get("notes"),
				selections: selectionSummary(),
				captured_image: capturedImage()
			};

			fetch("/api/method/curtain_roll.api.submit_quote", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-Frappe-CSRF-Token": (window.frappe && window.frappe.csrf_token) || ""
				},
				body: JSON.stringify(payload)
			})
				.then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
				.then(function (res) {
					var msg = res.body && res.body.message;
					if (res.ok && msg && msg.ok) {
						form.reset();
						result.classList.add("is-ok");
						result.textContent = msg.message;
					} else {
						result.classList.add("is-error");
						result.textContent = (msg && msg.message) ||
							(res.body && res.body._server_messages) ||
							"Could not send the request. Please try again.";
					}
				})
				.catch(function () {
					result.classList.add("is-error");
					result.textContent = "Network error. Please try again.";
				})
				.finally(function () { button.disabled = false; });
		});
	}

	onReady(function () {
		bindQuoteForm();
		waitForDeps(function (err) {
			if (err) {
				if (window.console) console.warn("[curtain-roll] " + err.message);
				var loader = document.querySelector(".model-loader");
				if (loader) loader.classList.add("is-failed");
				return;
			}
			bindSwatches();
			var loader = document.querySelector(".model-loader");
			if (loader) loader.style.display = "none";
		});
	});
})();
