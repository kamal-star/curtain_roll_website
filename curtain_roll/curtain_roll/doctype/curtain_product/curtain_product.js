// Desk helpers for pricing a curtain type.
frappe.ui.form.on("Curtain Product", {
	refresh(frm) {
		room_editor(frm);
		if (frm.is_new()) return;

		frm.add_custom_button(__("View page"), () => {
			window.open("/" + frm.doc.product_key, "_blank");
		});

		frm.add_custom_button(__("Reload options from page"), () => {
			frappe.confirm(
				__("Pull any new colours and options off the storefront page? Rates you have already set are kept."),
				() => {
					frappe.call({
						method: "curtain_roll.pricing.resync",
						args: { product_key: frm.doc.product_key },
						freeze: true,
						freeze_message: __("Reading the page..."),
						callback: () => frm.reload_doc(),
					});
				}
			);
		});

		// Pricing 65 swatches one row at a time is unreasonable, so offer the
		// two edits the team actually makes in bulk.
		frm.add_custom_button(__("Set rate on all colours"), () => {
			bulk(frm, "colors", __("Colours"));
		}, __("Bulk edit"));

		frm.add_custom_button(__("Show / hide all colours"), () => {
			frappe.prompt(
				[{ fieldname: "enabled", label: __("Show on site"), fieldtype: "Check", default: 1 }],
				(v) => {
					(frm.doc.colors || []).forEach((r) => (r.enabled = v.enabled));
					frm.refresh_field("colors");
					frm.dirty();
				},
				__("Show / hide all colours")
			);
		}, __("Bulk edit"));

		frm.add_custom_button(__("Set rate on all options"), () => {
			bulk(frm, "options", __("Options"));
		}, __("Bulk edit"));
	},

	onload_post_render(frm) {
		room_editor(frm);
	},

	room_image(frm) {
		room_editor(frm);
	},

	room_scene(frm) {
		room_editor(frm);
	},

	rate_basis(frm) {
		if (frm.doc.rate_basis === "Per Square Meter" && !frm.doc.min_billable_sqm) {
			frm.set_value("min_billable_sqm", 1);
		}
	},
});

/* 3D Room: the uploaded picture with a box to drag over its window.

   Drag inside the box to move it, a corner to resize it, or anywhere else on
   the picture to draw a new one. The box is kept as fractions of the picture
   in room_window, which the page turns into where the blind hangs. A 360
   picture shows the window small, so it can be zoomed. */
function room_editor(frm) {
	const field = frm.get_field("room_editor");
	if (!field || !field.$wrapper) return;
	const $w = field.$wrapper.empty();
	if (frm.is_new()) return;
	if (!frm.doc.room_scene) {
		if (frm.doc.room_image) {
			$w.html(`<p class="text-muted small">${__("Save to prepare the picture, then place the window box here.")}</p>`);
		}
		return;
	}

	const parse = (t) => {
		const b = String(t || "").split(",").map(Number);
		return b.length === 4 && b.every((x) => isFinite(x)) && b[0] < b[2] && b[1] < b[3] ? b : null;
	};
	let box = parse(frm.doc.room_window) || [0.44, 0.37, 0.56, 0.6];
	let zoom = 3;

	$w.html(`
		<div class="cr-room-tools" style="display:flex;gap:10px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
			<span class="text-muted small">${__("Drag the box over the window where the blind should hang.")}</span>
			<label class="small" style="margin:0 0 0 auto">${__("Zoom")}
				<input type="range" min="1" max="6" step="0.5" value="${zoom}" class="cr-room-zoom" style="vertical-align:middle;width:120px">
			</label>
			<button class="btn btn-xs btn-default cr-room-centre">${__("Centre on box")}</button>
			<button class="btn btn-xs btn-default cr-room-view">${__("View page")}</button>
		</div>
		<div class="cr-room-scroll" style="position:relative;overflow:auto;max-height:520px;border:1px solid var(--border-color);border-radius:8px;background:#111">
			<div class="cr-room-stage" style="position:relative;user-select:none;touch-action:none">
				<img class="cr-room-img" src="${frm.doc.room_scene}" draggable="false" style="display:block;width:100%;height:auto">
				<div class="cr-room-box" style="position:absolute;border:2px solid #ffcc00;box-shadow:0 0 0 9999px rgba(0,0,0,.35);cursor:move">
					${["nw", "ne", "sw", "se"].map((c) => `<span data-c="${c}" style="position:absolute;width:12px;height:12px;background:#ffcc00;border-radius:2px;${c[0] === "n" ? "top:-7px" : "bottom:-7px"};${c[1] === "w" ? "left:-7px" : "right:-7px"};cursor:${c}-resize"></span>`).join("")}
				</div>
			</div>
		</div>
		<div class="text-muted small cr-room-status" style="margin-top:6px"></div>`);

	const $scroll = $w.find(".cr-room-scroll"), $stage = $w.find(".cr-room-stage"),
		$box = $w.find(".cr-room-box"), $status = $w.find(".cr-room-status");

	function layout() {
		$stage.css("width", zoom * 100 + "%");
		$box.css({
			left: box[0] * 100 + "%", top: box[1] * 100 + "%",
			width: (box[2] - box[0]) * 100 + "%", height: (box[3] - box[1]) * 100 + "%",
		});
		$status.text(frm.doc.room_window
			? __("Window placed. Save, then use View page to check the blind.")
			: __("Not placed yet - the page keeps its own room until you place the box and save."));
	}
	function centre() {
		const s = $scroll[0], st = $stage[0];
		s.scrollLeft = ((box[0] + box[2]) / 2) * st.offsetWidth - s.clientWidth / 2;
		s.scrollTop = ((box[1] + box[3]) / 2) * st.offsetHeight - s.clientHeight / 2;
	}
	function commit() {
		const v = box.map((x) => Math.max(0, Math.min(1, x)).toFixed(4)).join(",");
		if (v !== frm.doc.room_window) frm.set_value("room_window", v);
		layout();
	}
	function at(e) {
		const r = $stage[0].getBoundingClientRect();
		const p = e.touches ? e.touches[0] : e;
		return [(p.clientX - r.left) / r.width, (p.clientY - r.top) / r.height];
	}

	let drag = null;
	$stage.on("pointerdown", (e) => {
		const p = at(e.originalEvent);
		const corner = $(e.target).data("c");
		if (corner) drag = { mode: corner, start: p, orig: box.slice() };
		else if ($(e.target).closest(".cr-room-box").length) drag = { mode: "move", start: p, orig: box.slice() };
		else drag = { mode: "draw", start: p, orig: [p[0], p[1], p[0], p[1]] };
		$stage[0].setPointerCapture(e.originalEvent.pointerId);
		e.preventDefault();
	});
	$stage.on("pointermove", (e) => {
		if (!drag) return;
		const p = at(e.originalEvent), dx = p[0] - drag.start[0], dy = p[1] - drag.start[1], o = drag.orig;
		if (drag.mode === "move") {
			const w = o[2] - o[0], h = o[3] - o[1];
			const l = Math.max(0, Math.min(1 - w, o[0] + dx)), t = Math.max(0, Math.min(1 - h, o[1] + dy));
			box = [l, t, l + w, t + h];
		} else if (drag.mode === "draw") {
			box = [Math.min(o[0], p[0]), Math.min(o[1], p[1]), Math.max(o[0], p[0]), Math.max(o[1], p[1])];
		} else {
			const b = o.slice();
			if (drag.mode.includes("w")) b[0] = Math.min(o[2] - 0.005, o[0] + dx);
			if (drag.mode.includes("e")) b[2] = Math.max(o[0] + 0.005, o[2] + dx);
			if (drag.mode.includes("n")) b[1] = Math.min(o[3] - 0.005, o[1] + dy);
			if (drag.mode.includes("s")) b[3] = Math.max(o[1] + 0.005, o[3] + dy);
			box = b;
		}
		layout();
	});
	$stage.on("pointerup pointercancel", () => {
		if (!drag) return;
		drag = null;
		if (box[2] - box[0] > 0.003 && box[3] - box[1] > 0.003) commit();
	});
	$w.find(".cr-room-zoom").on("input", function () {
		zoom = Number(this.value);
		layout();
		centre();
	});
	$w.find(".cr-room-centre").on("click", (e) => { e.preventDefault(); centre(); });
	$w.find(".cr-room-view").on("click", (e) => {
		e.preventDefault();
		window.open("/" + frm.doc.product_key, "_blank");
	});
	$w.find(".cr-room-img").on("load", () => { layout(); centre(); });
	layout();
}

function bulk(frm, table, title) {
	frappe.prompt(
		[
			{
				fieldname: "charge_type",
				label: __("Charge Type"),
				fieldtype: "Select",
				options: ["Fixed Amount", "Per Square Meter", "Percent of Base"],
				default: "Fixed Amount",
				reqd: 1,
			},
			{ fieldname: "rate", label: __("Rate"), fieldtype: "Currency", default: 0 },
			{
				fieldname: "only_group",
				label: __("Limit to option group (blank = all)"),
				fieldtype: "Data",
				depends_on: `eval:${table === "options"}`,
			},
		],
		(v) => {
			(frm.doc[table] || []).forEach((r) => {
				if (v.only_group && r.group_label !== v.only_group) return;
				r.charge_type = v.charge_type;
				r.rate = v.rate;
			});
			frm.refresh_field(table);
			frm.dirty();
		},
		__("Set rate on {0}", [title]),
		__("Apply")
	);
}
