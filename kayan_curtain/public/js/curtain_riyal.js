/* The Saudi Riyal sign, wherever the storefront shows a price.
 *
 * The sign the central bank introduced in 2025 is in Unicode (U+20C1, since
 * version 17) but almost no phone or computer has a font that draws it yet -
 * typing the character in would show most customers an empty box. So it is
 * drawn here instead, from an outline traced off the artwork the client
 * supplied, as a mask filled with the text colour: it follows the price it sits
 * in, black in a table, white on a blue button, and scales with the font.
 *
 * Done in the page rather than where prices are written, on purpose. A price
 * is written in at least five places - the pricing module, the totals, the
 * header counter, the frozen configurator script in every product page, and
 * ERPNext's own money formatting on the account pages - and everywhere that is
 * not a screen needs the text to stay as it is: the PDF invoice, the payment
 * gateway's description, the quotation lines the team reads in the desk. So the
 * data keeps "SR" and "ر.س", and only what a browser shows is changed.
 *
 * Prices the page redraws later - the live total as a blind is configured, the
 * cart after a coupon, the search suggestions - are caught by a
 * MutationObserver, so a price is never shown in the old form for longer than
 * it takes to appear.
 *
 * Loaded without `defer`, at the end of the body: the page above is already
 * parsed, so this runs before first paint on most pages and the old currency
 * text is not seen flashing in.
 */
(function () {
  "use strict";

  if (window.__crRiyal) return;
  window.__crRiyal = true;

  // traced from the client's artwork; 898 x 1000
  var PATH =
    "M411 0 L424 0 L424 483 L530 462 L530 136 L572 89 L636 51 L631 436 " +
    "L890 381 L898 390 L869 496 L636 542 L631 653 L898 597 L873 703 L856 716 " +
    "L530 784 L530 568 L436 585 L424 589 L419 733 L335 847 L0 924 L30 809 " +
    "L318 750 L318 614 L59 669 L51 669 L51 653 L81 555 L318 504 L318 81 Z " +
    "M890 814 L898 814 L894 852 L869 928 L530 1000 L542 924 L559 886 Z";

  var SVG = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 898 1000'>" +
            "<path d='" + PATH + "'/></svg>";
  var URL = 'url("data:image/svg+xml;utf8,' + encodeURIComponent(SVG) + '")';

  var css = document.createElement("style");
  css.textContent =
    ".cr-sar{display:inline-block;width:.74em;height:.82em;" +
    "vertical-align:-.07em;background-color:currentColor;" +
    "-webkit-mask:" + URL + " no-repeat center/contain;" +
    "mask:" + URL + " no-repeat center/contain;" +
    // a screen reader reads the label; the mask has no text of its own
    "font-size:inherit;flex:none}" +
    // backgrounds are dropped when printing unless asked for, and the sign IS
    // a background
    "@media print{.cr-sar{-webkit-print-color-adjust:exact;print-color-adjust:exact}}";
  (document.head || document.documentElement).appendChild(css);

  var NUMBER = "\\d[\\d,]*(?:\\.\\d+)?";
  // "SR 360.00", "SAR 360.00", "ر.س 360.00" - the sign goes where the code was
  var BEFORE = new RegExp("(?:\\bSA?R|ر\\.س)\\s?(?=" + NUMBER + ")", "g");
  // "360.00 ر.س", "360.00 SAR" - same, after the number
  var AFTER = new RegExp("(" + NUMBER + ")\\s?(?:ر\\.س|SA?R\\b)", "g");
  var ANY = new RegExp("\\bSA?R\\b|ر\\.س");

  var SKIP = { SCRIPT: 1, STYLE: 1, NOSCRIPT: 1, TEXTAREA: 1, INPUT: 1,
               SELECT: 1, OPTION: 1, TITLE: 1, CODE: 1, PRE: 1 };

  function sign() {
    var el = document.createElement("span");
    el.className = "cr-sar";
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", "SAR");
    return el;
  }

  function skipped(node) {
    for (var el = node.parentNode; el && el.nodeType === 1; el = el.parentNode) {
      if (SKIP[el.tagName]) return true;
      if (el.isContentEditable) return true;
      if (el.hasAttribute("data-no-sar")) return true;
    }
    return false;
  }

  /* Split one text node into text + sign + text. Returns true if it changed. */
  function convert(node) {
    // A page that adds an empty element and then fills it produces two
    // records in one batch. Sweeping the first converts the text already, so
    // by the second record that text node has been replaced and has no parent.
    // Without this check replaceChild throws, and the throw abandons every
    // record after it - which is how the product page's live total and all its
    // swatch surcharges were left saying "SR".
    if (!node.parentNode || !node.isConnected) return false;
    var text = node.nodeValue;
    if (!text || !ANY.test(text) || skipped(node)) return false;

    // mark where each currency code sits, whichever side of the number it is
    var marked = text
      .replace(AFTER, "$1\u0000")
      .replace(BEFORE, "\u0000");
    if (marked.indexOf("\u0000") === -1) return false;

    var parts = marked.split("\u0000");
    var frag = document.createDocumentFragment();
    parts.forEach(function (part, i) {
      if (i > 0) {
        frag.appendChild(sign());
        // a thin gap between the sign and a number that follows it
        if (/^\d/.test(part)) part = " " + part;
      }
      if (/\d$/.test(part) && i < parts.length - 1) part = part + " ";
      if (part) frag.appendChild(document.createTextNode(part));
    });
    node.parentNode.replaceChild(frag, node);
    return true;
  }

  function sweep(root) {
    if (!root) return;
    if (root.nodeType === 3) { convert(root); return; }
    if (root.nodeType !== 1 || SKIP[root.tagName]) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    var found = [];
    for (var n = walker.nextNode(); n; n = walker.nextNode()) {
      if (ANY.test(n.nodeValue)) found.push(n);
    }
    found.forEach(convert);
  }

  // the printable invoice keeps its text currency, so it reads the same as
  // the PDF of it
  if (document.body && document.body.hasAttribute("data-no-sar")) return;

  sweep(document.body);

  var observer = new MutationObserver(function (records) {
    records.forEach(function (r) {
      // each record on its own: one that fails must not cost the rest
      try {
        if (r.type === "characterData") {
          convert(r.target);
        } else {
          Array.prototype.forEach.call(r.addedNodes, sweep);
        }
      } catch (e) { /* leave that one price as text */ }
    });
  });
  observer.observe(document.body, { childList: true, subtree: true,
                                    characterData: true });
})();
