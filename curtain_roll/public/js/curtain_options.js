/* What a product page is allowed to offer.
 *
 * Two things the team sets per product in the desk, applied to the page:
 *
 *   * the sizes this blind can actually be made in, shown under the width and
 *     height boxes and checked as the customer types. The server checks them
 *     again and is the one that decides - this only means nobody configures a
 *     whole blind before being told the size is impossible.
 *   * whether the fabric swatches and the motorised option are offered at all.
 *
 * It lives here rather than in the pages because every product page is a
 * frozen capture with its own copy of the configurator script. Editing them
 * means thirteen edits now and thirteen more after the next regeneration, and
 * the injected route is the one the language switch and the search box already
 * take.
 *
 * It also repairs something the in-page script gets wrong. Its applyGroup ends
 * with:
 *
 *     if (inputs.length && dropped === inputs.length) {
 *         var card = input.closest(".option-card");   // `input` is the
 *     }                                              // forEach parameter
 *
 * - and `input` is out of scope by then, so the one case that line exists for,
 * a group whose every choice has been withdrawn, throws ReferenceError and
 * leaves an empty card on the page. Hiding empty cards is done here instead.
 */
(function () {
  "use strict";

  var phrases = window.__crPhrases || {};

  function say(text) {
    return phrases[text] || text;
  }

  function fill(template, a, b) {
    return say(template).replace("{0}", a).replace("{1}", b);
  }

  function num(value) {
    var n = parseFloat(value);
    return isFinite(n) && n > 0 ? n : 0;
  }

  /* Which product this page is for. The pages carry it on the add-to-cart
     form as product_id, and the pricing endpoint is keyed by the storefront
     key, so the page's own script has already worked it out - read it from
     the same place rather than guessing from the URL. */
  function productKey() {
    var path = window.location.pathname.replace(/^\/+|\/+$/g, "");
    return path.split("/")[0] || "";
  }

  function cardOf(node) {
    return node && node.closest ? node.closest(".option-card") : null;
  }

  // ------------------------------------------------------------- the sizes
  function applyLimits(gid, limits) {
    var width = document.querySelector('input[name="option[' + gid + '][width]"]');
    var height = document.querySelector('input[name="option[' + gid + '][height]"]');
    if (!width || !height) return;

    var pairs = [
      [width, num(limits.min_width), num(limits.max_width),
       "Width must be between {0} and {1} cm.",
       "Width must be at least {0} cm.", "Width can be at most {0} cm."],
      [height, num(limits.min_height), num(limits.max_height),
       "Height must be between {0} and {1} cm.",
       "Height must be at least {0} cm.", "Height can be at most {0} cm."]
    ];

    var any = false;
    pairs.forEach(function (row) {
      var box = row[0], low = row[1], high = row[2];
      if (!low && !high) return;
      any = true;

      // the boxes are type=text in the capture, so min/max would be ignored;
      // the check below is what actually enforces it in the browser
      if (low) box.setAttribute("data-cr-min", low);
      if (high) box.setAttribute("data-cr-max", high);

      var note = document.createElement("span");
      note.className = "cr-size-note";
      note.textContent = low && high ? fill(row[3], low, high)
        : low ? fill(row[4], low) : fill(row[5], high);
      var field = box.closest(".dimension-field") || box.parentNode;
      if (field && !field.querySelector(".cr-size-note")) field.appendChild(note);

      box.addEventListener("input", function () { check(box, low, high, row); });
      box.addEventListener("blur", function () { check(box, low, high, row); });
    });

    if (any) style();
  }

  function check(box, low, high, row) {
    var value = parseFloat(String(box.value).replace(",", "."));
    var bad = isFinite(value) && value > 0 &&
      ((low && value < low) || (high && value > high));
    box.classList.toggle("cr-size-bad", !!bad);
    var field = box.closest(".dimension-field") || box.parentNode;
    var note = field && field.querySelector(".cr-size-note");
    if (note) note.classList.toggle("cr-size-bad-note", !!bad);
  }

  function style() {
    if (document.getElementById("cr-size-style")) return;
    var css = document.createElement("style");
    css.id = "cr-size-style";
    css.textContent =
      ".cr-size-note{display:block;margin-top:5px;font-size:11.5px;line-height:1.4;" +
      "color:var(--text-muted,#54667a)}" +
      ".cr-size-bad{border-color:#c0392b !important;" +
      "box-shadow:0 0 0 3px rgba(192,57,43,.12) !important}" +
      ".cr-size-bad-note{color:#c0392b;font-weight:600}";
    document.head.appendChild(css);
  }

  // ------------------------------------------------- the sections on offer
  function hideGroup(gid) {
    var input = document.querySelector('input[name="option[' + gid + ']"]');
    var card = cardOf(input) ||
      cardOf(document.getElementById("input-option" + gid));
    if (card) card.style.display = "none";
  }

  /* Any group whose every choice has been withdrawn. This is the in-page
     script's broken branch, done where it works. */
  function hideEmptyGroups() {
    var seen = {};
    document.querySelectorAll('input[type=radio][name^="option["]')
      .forEach(function (input) {
        var name = input.getAttribute("name");
        if (seen[name]) return;
        seen[name] = true;
        var all = document.querySelectorAll('input[name="' + name + '"]');
        var live = 0;
        all.forEach(function (one) {
          var row = one.closest(".swatch-card, .segmented-pill") || one.parentNode;
          var hidden = one.disabled ||
            (row && row.style && row.style.display === "none");
          if (!hidden) live++;
        });
        if (all.length && !live) {
          var card = cardOf(input);
          if (card) card.style.display = "none";
        }
      });
  }

  // -------------------------------- the choices under Manual / Motorized
  /* Handle type and operating side under Manual; motor and motor position
     under Motorized. They are rows on the Curtain Product record, not part of
     the captured page, so they are drawn here - inside the Control type card,
     which is inside #product, so the page's own Add to Cart sends them.

     Only the choices under the control that is picked exist in the page at
     any moment. The others are not hidden, they are gone: a hidden radio is
     still posted, and a Manual handle would ride along on a motorised blind.
     The server ignores it either way, but the form should say what it means. */
  var MOTOR = /motor|كهربائي/i;

  function subOptions(spec) {
    var gid = spec.control_group, rows = spec.sub_options || [];
    if (!gid || !rows.length) return;
    var card = cardOf(document.querySelector('input[name="option[' + gid + ']"]'));
    if (!card) return;

    var host = document.createElement("div");
    host.className = "cr-sub";
    var grid = card.querySelector(".segmented-grid");
    if (grid) grid.parentNode.insertBefore(host, grid.nextSibling);
    else card.appendChild(host);

    var arabic = document.documentElement.getAttribute("dir") === "rtl";
    var chosen = {};              // group key -> row id, kept across redraws

    function parent() {
      var picked = document.querySelector('input[name="option[' + gid + ']"]:checked');
      if (!picked) return null;
      var entry = (spec.options && spec.options[gid] || {})[picked.value];
      if (!entry) return null;
      return MOTOR.test(entry.label || "") ? "Motorized" : "Manual";
    }

    function size() {
      var w = document.querySelector('input[name^="option["][name$="[width]"]');
      var h = document.querySelector('input[name^="option["][name$="[height]"]');
      return { w: w ? parseFloat(w.value) || 0 : 0, h: h ? parseFloat(h.value) || 0 : 0 };
    }

    function fits(r, s) {
      if (!s.w || !s.h) return true;   // no size typed yet: offer everything
      if (r.min_width && s.w < r.min_width) return false;
      if (r.max_width && s.w > r.max_width) return false;
      if (r.min_height && s.h < r.min_height) return false;
      if (r.max_height && s.h > r.max_height) return false;
      return true;
    }

    function build() {
      var p = parent();
      host.textContent = "";
      if (!p) return;

      var groups = {}, order = [];
      rows.forEach(function (r) {
        if (r.parent !== p) return;
        if (!groups[r.key]) { groups[r.key] = []; order.push(r.key); }
        groups[r.key].push(r);
      });

      var s = size();
      order.forEach(function (key) {
        var list = groups[key], first = list[0];
        var title = (arabic && first.group_ar) || first.group;
        var box = document.createElement("div");
        box.className = "cr-sub-group";
        // where the theme puts this group's error, if the server has one
        box.id = "input-optioncrsub-" + key;

        var head = document.createElement("div");
        head.className = "cr-sub-title";
        head.textContent = title;
        box.appendChild(head);

        var offered = list.filter(function (r) { return fits(r, s); });
        if (!offered.length) {
          var none = document.createElement("div");
          none.className = "cr-sub-none";
          none.textContent = fill("No {0} is available for this size. Please contact us.", title);
          box.appendChild(none);
          host.appendChild(box);
          return;
        }

        var keep = offered.some(function (r) { return r.id === chosen[key]; })
          ? chosen[key] : offered[0].id;
        chosen[key] = keep;

        var chips = document.createElement("div");
        chips.className = "cr-sub-chips";
        offered.forEach(function (r) {
          var chip = document.createElement("label");
          chip.className = "cr-chip";
          var input = document.createElement("input");
          input.type = "radio";
          input.name = "cr_sub[" + key + "]";
          input.value = r.id;
          input.checked = r.id === keep;
          input.addEventListener("change", function () {
            chosen[key] = r.id;
            refresh();
          });
          var name = document.createElement("span");
          name.textContent = (arabic && r.label_ar) || r.label;
          chip.appendChild(input);
          chip.appendChild(name);
          if (r.price_text) {
            var cost = document.createElement("small");
            cost.textContent = r.price_text;
            chip.appendChild(cost);
          }
          chips.appendChild(chip);
        });
        box.appendChild(chips);
        host.appendChild(box);
      });
    }

    function refresh() {
      if (window.jQuery) window.jQuery("#product").trigger("change");
    }

    document.querySelectorAll('input[name="option[' + gid + ']"]').forEach(function (r) {
      r.addEventListener("change", function () { build(); refresh(); });
    });
    var timer = null;
    document.querySelectorAll('input[name^="option["][name$="[width]"], ' +
                              'input[name^="option["][name$="[height]"]')
      .forEach(function (box) {
        // the page itself re-prices on typing; this only re-offers the motors
        box.addEventListener("input", function () {
          clearTimeout(timer);
          timer = setTimeout(build, 350);
        });
      });

    subStyle();
    build();
    refresh();
  }

  function subStyle() {
    if (document.getElementById("cr-sub-style")) return;
    var css = document.createElement("style");
    css.id = "cr-sub-style";
    css.textContent =
      ".cr-sub{margin-top:14px;display:flex;flex-direction:column;gap:12px}" +
      ".cr-sub:empty{display:none}" +
      ".cr-sub-group{border-top:1px dashed var(--border,#e1ebf2);padding-top:12px}" +
      ".cr-sub-title{font-size:12.5px;font-weight:700;margin-bottom:8px;" +
      "color:var(--text,#0f172a)}" +
      ".cr-sub-chips{display:flex;flex-wrap:wrap;gap:8px}" +
      ".cr-chip{position:relative;display:inline-flex;align-items:center;gap:6px;cursor:pointer;" +
      "padding:8px 14px;border:1.5px solid var(--border,#e1ebf2);" +
      "border-radius:999px;background:var(--surface,#fff);font-size:13px;" +
      "font-weight:600;color:var(--text,#0f172a);transition:all .2s}" +
      ".cr-chip input{position:absolute;opacity:0;pointer-events:none}" +
      ".cr-chip small{font-weight:500;color:var(--text-muted,#54667a);font-size:11.5px}" +
      ".cr-chip:has(input:checked){border-color:var(--brand,#09446c);" +
      "background:var(--brand-light,#eaf3f8);color:var(--brand,#09446c)}" +
      ".cr-chip:has(input:focus-visible){box-shadow:0 0 0 3px var(--brand-soft,rgba(9,68,108,.15))}" +
      ".cr-sub-none{font-size:12.5px;color:#c0392b;font-weight:600}";
    document.head.appendChild(css);
  }

  /* The cards are numbered in the capture. Take one away and the page reads
     2, 3, 4 - which looks like a step has gone missing, because it has. */
  function renumber() {
    var n = 0;
    document.querySelectorAll(".option-card").forEach(function (card) {
      var mark = card.querySelector(".option-step-number");
      if (!mark || card.style.display === "none") return;
      mark.textContent = String(++n);
    });
  }

  function apply(spec) {
    if (!spec) return;
    if (spec.size_group && spec.limits) applyLimits(spec.size_group, spec.limits);
    // material_group, not color_group: the server blanks color_group when the
    // material is off, precisely so nothing asks for a colour any more
    if (spec.show_material === false && spec.material_group) {
      hideGroup(spec.material_group);
    }
    subOptions(spec);
    renumber();
    // after the page's own script has had its turn at disabling rows
    setTimeout(function () { hideEmptyGroups(); renumber(); }, 400);
    setTimeout(function () { hideEmptyGroups(); renumber(); }, 1500);
  }

  function load() {
    var key = productKey();
    if (!key) return;
    // no size boxes means this is not a product page, whatever the URL says
    if (!document.querySelector('input[name^="option["][name$="[width]"]')) return;

    fetch("/api/method/curtain_roll.pricing.get_pricing?product_key=" +
          encodeURIComponent(key), { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { apply((j && j.message) || null); })
      .catch(function () { /* the page still works without the hints */ });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
