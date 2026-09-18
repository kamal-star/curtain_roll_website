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

	function sizeValues() {
		var w = document.querySelector("[data-cr-size=width]");
		var h = document.querySelector("[data-cr-size=height]");
		return {
			width: w && w.value ? w.value.trim() : "",
			height: h && h.value ? h.value.trim() : ""
		};
	}

	function updateArea() {
		var box = document.querySelector("[data-cr-area]");
		if (!box) return;
		var s = sizeValues();
		var w = parseFloat(s.width), h = parseFloat(s.height);
		if (w > 0 && h > 0) {
			box.textContent = w + " x " + h + " cm  =  " + ((w * h) / 10000).toFixed(2) + " m²";
			box.classList.add("is-set");
		} else {
			box.innerHTML = "&nbsp;";
			box.classList.remove("is-set");
		}
	}

	function selectionSummary() {
		var out = [];
		document.querySelectorAll(".cr-group").forEach(function (group) {
			var label = group.querySelector(".cr-group-label");
			if (!label) return;
			var name = label.textContent.trim();
			var picked = group.querySelector("input[type=radio]:checked");
			if (picked) {
				out.push(name + ": " +
					(picked.getAttribute("data-cr-code") || picked.getAttribute("data-cr-label") || picked.value));
				return;
			}
			if (group.classList.contains("cr-size-group")) {
				var s = sizeValues();
				if (s.width || s.height) out.push(name + ": " + s.width + " x " + s.height + " cm");
			}
		});
		var qty = document.getElementById("cr-qty");
		if (qty && qty.value) out.push("Quantity: " + qty.value);
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
			var size = sizeValues();
			var qty = document.getElementById("cr-qty");
			var payload = {
				product: form.getAttribute("data-product"),
				name: data.get("name"),
				phone: data.get("phone"),
				email: data.get("email"),
				city: data.get("city"),
				notes: data.get("notes"),
				width: size.width,
				height: size.height,
				quantity: qty ? qty.value : "1",
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

	// Collapsible option groups, matching the original's accordion.
	// Groups start closed; opening one does not close the others (the original
	// behaves the same way once a panel is expanded).
	function bindAccordion() {
		document.querySelectorAll(".cr-group-head").forEach(function (head) {
			head.addEventListener("click", function () {
				var body = document.getElementById(head.getAttribute("aria-controls"));
				if (!body) return;
				var open = head.getAttribute("aria-expanded") === "true";
				head.setAttribute("aria-expanded", open ? "false" : "true");
				body.hidden = open;
				head.closest(".cr-group").classList.toggle("is-open", !open);
			});
		});
	}

	function bindSize() {
		document.querySelectorAll("[data-cr-size]").forEach(function (el) {
			el.addEventListener("input", updateArea);
			el.addEventListener("change", updateArea);
		});
		updateArea();
	}

	onReady(function () {
		bindQuoteForm();
		bindAccordion();
		bindSize();
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
