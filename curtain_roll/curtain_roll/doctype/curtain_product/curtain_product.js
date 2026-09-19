// Desk helpers for pricing a curtain type.
frappe.ui.form.on("Curtain Product", {
	refresh(frm) {
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

	rate_basis(frm) {
		if (frm.doc.rate_basis === "Per Square Meter" && !frm.doc.min_billable_sqm) {
			frm.set_value("min_billable_sqm", 1);
		}
	},
});

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
