/* The English / العربية switch.
 *
 * Built here rather than in the markup because the storefront's 18 pages are
 * frozen captures of the old site - each carries its own copy of the header,
 * and editing them by hand would mean 18 edits that the next regeneration
 * throws away. The header is already assembled at runtime for the account and
 * cart links (applySession), so this follows the same approach.
 */
(function () {
  "use strict";

  var LANGS = { en: "English", ar: "العربية" };

  function currentLang() {
    var m = document.cookie.match(/(?:^|;\s*)preferred_language=([^;]+)/);
    var fromCookie = m ? decodeURIComponent(m[1]).toLowerCase().split("-")[0] : "";
    if (LANGS[fromCookie]) return fromCookie;
    var onHtml = (document.documentElement.getAttribute("lang") || "en").toLowerCase();
    return LANGS[onHtml] ? onHtml : "en";
  }

  function csrf() {
    return (window.frappe && window.frappe.csrf_token) || "";
  }

  function choose(lang) {
    var body = new FormData();
    body.append("lang", lang);
    fetch("/api/method/curtain_roll.language.set_language", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-Frappe-CSRF-Token": csrf() },
      body: body
    }).then(function (r) {
      // A stale token gives 400 before the call runs. The cookie is the whole
      // point of the request, so fetch a fresh token and try once more rather
      // than leaving a switch that silently does nothing.
      if (r.status === 400) {
        return fetch("/api/method/curtain_roll.api.csrf_token",
                     { credentials: "same-origin" })
          .then(function (t) { return t.json(); })
          .then(function (t) {
            window.frappe = window.frappe || {};
            window.frappe.csrf_token = ((t && t.message) || {}).token || "";
            return choose(lang);
          });
      }
      window.location.reload();
    }).catch(function () { window.location.reload(); });
  }

  function build() {
    if (document.getElementById("cr-lang")) return;

    var now = currentLang();
    var other = now === "ar" ? "en" : "ar";

    var pill = document.createElement("a");
    pill.id = "cr-lang";
    pill.href = "#";
    pill.className = "btn-header-pill cr-lang-pill";
    pill.setAttribute("lang", other);
    pill.setAttribute("aria-label", "Switch language to " + LANGS[other]);
    pill.innerHTML = '<i class="fa-solid fa-globe"></i><span>' + LANGS[other] + "</span>";
    pill.addEventListener("click", function (e) {
      e.preventDefault();
      choose(other);
    });

    // the redesigned header first, then the old Journal3 one, then give up
    // gracefully rather than dropping the control somewhere it looks broken
    var host = document.querySelector(".header-actions");
    if (host) {
      var cart = host.querySelector("#cart");
      host.insertBefore(pill, cart || null);
      return;
    }
    host = document.querySelector("#language, .language-currency");
    if (host) { host.appendChild(pill); }
  }

  /* The page rewrites parts of itself after loading - applySession puts the
   * account links in the header, and the cart total is redrawn on every
   * change. The server never sees that text, so the few strings involved are
   * handed over in window.__crPhrases and applied here as they appear. */
  function localise(root) {
    var table = window.__crPhrases;
    if (!table) return;

    var walker = document.createTreeWalker(root || document.body,
                                           NodeFilter.SHOW_TEXT, null);
    var node, pending = [];
    while ((node = walker.nextNode())) {
      var parent = node.parentNode;
      if (!parent) continue;
      var tag = parent.nodeName;
      if (tag === "SCRIPT" || tag === "STYLE" || parent.id === "cr-lang") continue;

      var text = node.nodeValue;
      var body = text.replace(/\s+/g, " ").trim();
      if (!body) continue;

      if (table[body]) {
        pending.push([node, text.replace(body, table[body])]);
      } else if (/item\(s\)/.test(body)) {
        // "1 item(s) - SR 380.00" is assembled in the page's own script
        pending.push([node, text.replace(/item\(s\)/g, "منتج")]);
      }
    }
    pending.forEach(function (pair) { pair[0].nodeValue = pair[1]; });
  }

  function watch() {
    if (!window.__crPhrases) return;
    localise();
    // applySession and the cart both run after us, so keep applying rather
    // than guessing at a delay. Cheap: it only walks what actually changed.
    var timer = null;
    new MutationObserver(function () {
      clearTimeout(timer);
      timer = setTimeout(function () { localise(); }, 60);
    }).observe(document.body, { childList: true, subtree: true,
                                characterData: true });
  }

  function start() {
    // A marker, so a failure here is visible instead of silent: reading
    // window.__crLang in the console says exactly how far this got.
    window.__crLang = { started: true, built: false, watching: false };
    try {
      build();
      window.__crLang.built = true;
      watch();
      window.__crLang.watching = true;
    } catch (err) {
      window.__crLang.error = String(err && err.stack || err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
