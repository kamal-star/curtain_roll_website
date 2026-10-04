/* The wishlist's two hearts, on every storefront page.
 *
 * The redesigned pages were built without the old theme's wishlist: no link
 * in the header, no button beside Add to Cart. The list itself never went
 * away - it is stored per customer and shown at /account/wishlist - it just
 * had no way in. Both hearts are drawn here, so every page gets them and a
 * regenerated page does not lose them again.
 *
 * A page that still carries the old theme's own (Wavy) is left alone.
 *
 * Signed out, the heart sends the shopper to sign in and back to the same
 * page: a saved list has to belong to someone.
 */
(function () {
  "use strict";

  var phrases = window.__crPhrases || {};
  function say(text) { return phrases[text] || text; }

  var API = "/api/method/kayan_curtain.api.";
  var header = null, button = null;

  function csrf() {
    return (window.frappe && window.frappe.csrf_token) || "";
  }

  function productId() {
    var input = document.querySelector('#product input[name="product_id"]');
    return input ? input.value : "";
  }

  function style() {
    if (document.getElementById("cr-wish-style")) return;
    var css = document.createElement("style");
    css.id = "cr-wish-style";
    css.textContent = [
      ".cr-wish-link{position:relative;background:#fff;border:1.5px solid var(--border,#dfe3e8);",
      "color:var(--brand,#09446c);padding:8px 12px;text-decoration:none}",
      ".cr-wish-link:hover{background:var(--brand-light,#eef4f8);border-color:var(--brand,#09446c)}",
      ".cr-wish-link i{margin:0!important;font-size:16px}",
      ".cr-wish-link .cr-wish-count{position:absolute;top:-6px;right:-6px;min-width:18px;height:18px;",
      "padding:0 5px;border-radius:9px;background:#da0a22;color:#fff;font-size:11px;font-weight:800;",
      "line-height:18px;text-align:center}",
      "[dir=rtl] .cr-wish-link .cr-wish-count{right:auto;left:-6px}",
      ".cr-wish-link .cr-wish-count:empty{display:none}",
      ".cr-wish-btn{flex:0 0 auto;width:48px;height:48px;border-radius:50%;cursor:pointer;",
      "display:inline-flex;align-items:center;justify-content:center;background:#fff;",
      "border:1.5px solid var(--border,#dfe3e8);color:var(--brand,#09446c);font-size:19px;",
      "transition:transform .15s,border-color .15s}",
      ".cr-wish-btn:hover{border-color:#da0a22;color:#da0a22;transform:translateY(-1px)}",
      ".cr-wish-btn.saved{color:#da0a22;border-color:#da0a22;background:#fff5f6}",
      ".cr-wish-btn[disabled]{opacity:.6;cursor:wait}",
      "@media (max-width:900px){.cr-wish-link{padding:7px 10px}.cr-wish-btn{width:44px;height:44px}}",
      // a phone header already holds menu, logo, search, language and cart:
      // the heart goes borderless, and the gaps close up, so the cart stays on
      "@media (max-width:480px){.header-actions{gap:4px!important}",
      ".cr-wish-link{border:0;padding:6px;background:transparent}",
      ".cr-wish-link i{font-size:18px}",
      ".header-actions .mobile-search-toggle{width:36px;height:36px}",
      // the short label (EN / ع) says it alone; the globe is what costs the room
      ".header-actions .cr-lang-pill{padding-left:9px;padding-right:9px}",
      ".header-actions .cr-lang-pill i{display:none}}"
    ].join("");
    document.head.appendChild(css);
  }

  function drawHeader() {
    var cart = document.getElementById("cart");
    var actions = cart && cart.closest(".header-actions");
    if (!actions || actions.querySelector(".wishlist-badge, .cr-wish-link")) return;
    header = document.createElement("a");
    header.href = "/account/wishlist";
    header.className = "btn-header-pill cr-wish-link";
    header.title = say("Wishlist");
    header.setAttribute("aria-label", say("Wishlist"));
    header.innerHTML = '<i class="fa-regular fa-heart"></i><span class="cr-wish-count"></span>';
    actions.insertBefore(header, cart);
  }

  function drawButton() {
    var cart = document.getElementById("button-cart");
    if (!cart || !productId()) return;
    var dock = cart.parentNode;
    if (dock.querySelector(".btn-wishlist, .cr-wish-btn")) return;
    button = document.createElement("button");
    button.type = "button";
    button.className = "cr-wish-btn";
    button.title = say("Add to Wishlist");
    button.setAttribute("aria-label", say("Add to Wishlist"));
    button.setAttribute("aria-pressed", "false");
    button.innerHTML = '<i class="fa-regular fa-heart"></i>';
    button.addEventListener("click", toggle);
    cart.parentNode.insertBefore(button, cart.nextSibling);
  }

  function show(state) {
    if (header) {
      header.querySelector(".cr-wish-count").textContent = state.count ? String(state.count) : "";
    }
    if (button) {
      var saved = !!state.saved;
      button.classList.toggle("saved", saved);
      button.setAttribute("aria-pressed", saved ? "true" : "false");
      button.querySelector("i").className = saved ? "fa-solid fa-heart" : "fa-regular fa-heart";
    }
  }

  function note(message) {
    var old = document.getElementById("cr-wish-note");
    if (old) old.remove();
    var box = document.createElement("div");
    box.id = "cr-wish-note";
    box.setAttribute("role", "status");
    box.style.cssText = "position:fixed;top:20px;right:20px;z-index:99999;background:#fff;" +
      "border:1px solid #e6e8eb;border-radius:10px;box-shadow:0 10px 30px rgba(0,0,0,.14);" +
      "padding:14px 18px;max-width:320px;font-size:14px;color:#14181d";
    if (document.documentElement.getAttribute("dir") === "rtl") {
      box.style.right = "auto";
      box.style.left = "20px";
    }
    var text = document.createElement("div");
    text.style.fontWeight = "700";
    text.textContent = message;
    var link = document.createElement("a");
    link.href = "/account/wishlist";
    link.textContent = say("View Wishlist");
    link.style.cssText = "display:inline-block;margin-top:8px;color:#09446c;font-weight:700";
    box.appendChild(text);
    box.appendChild(link);
    document.body.appendChild(box);
    setTimeout(function () { if (box.parentNode) box.remove(); }, 5000);
  }

  function post(retried) {
    var body = new URLSearchParams();
    body.set("product_id", productId());
    return fetch(API + "wishlist_toggle", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/x-www-form-urlencoded",
                 "X-Frappe-CSRF-Token": csrf() },
      body: body.toString()
    }).then(function (r) {
      // a stale token is refused before the call runs: fetch a fresh one and
      // try once more, as the language switch does
      if (r.status === 400 && !retried) {
        return fetch(API + "csrf_token", { credentials: "same-origin" })
          .then(function (t) { return t.json(); })
          .then(function (t) {
            window.frappe = window.frappe || {};
            window.frappe.csrf_token = ((t && t.message) || {}).token || "";
            return post(true);
          });
      }
      return r.json();
    });
  }

  function toggle() {
    button.disabled = true;
    post(false)
      .then(function (d) {
        var m = d.message || {};
        if (m.redirect) {
          // back to this very page after signing in
          window.location.href = "/login?redirect-to=" +
            encodeURIComponent(location.pathname + location.search);
          return;
        }
        if (typeof m.saved === "boolean") {
          show(m);
          note(say(m.saved ? "Saved to your wishlist." : "Removed from your wishlist."));
        }
      })
      .catch(function () {})
      .then(function () { button.disabled = false; });
  }

  function start() {
    style();
    drawHeader();
    drawButton();
    if (!header && !button) return;
    var id = button ? productId() : "";
    fetch(API + "wishlist_state" + (id ? "?product_id=" + encodeURIComponent(id) : ""),
          { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { show(d.message || {}); })
      .catch(function () {});
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
