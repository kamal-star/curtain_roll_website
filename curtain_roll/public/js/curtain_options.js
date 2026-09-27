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
