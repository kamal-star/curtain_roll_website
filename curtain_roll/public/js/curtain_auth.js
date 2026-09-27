/* Signing in brings the customer back to where they were.
 *
 * Every Login link on the storefront is a bare "/login" - twenty-odd copies in
 * the captured headers and drawers - so Frappe had no idea where the customer
 * came from and sent everyone to the home page. A customer who signed in to
 * check out from a product page had to find the product again.
 *
 * This adds the current page as ?redirect-to= at the moment a Login link is
 * clicked. At the click, not on load, because the header script swaps those same
 * links for "My Account" by matching href="/login" exactly - rewriting them
 * early would quietly break that swap for everyone who is signed in.
 *
 * On the login page itself it does one more thing: when the sign-in succeeds,
 * the login page is replaced in the history rather than left in it. Otherwise
 * Back from the product page goes to the login form, which - now that they are
 * signed in - bounces them forward to the product page again, and Back looks
 * like it does nothing.
 *
 * Logging OUT is handled on the server (renderers.SignOut), since it has to
 * happen whether or not this script has loaded.
 */
(function () {
  "use strict";

  function safe(path) {
    return typeof path === "string" && path.charAt(0) === "/" &&
      path.charAt(1) !== "/" && path.indexOf("\\") === -1 ? path : "";
  }

  function here() {
    return window.location.pathname + window.location.search;
  }

  function isAuthPage(path) {
    var p = (path || "").split("?")[0].replace(/\/+$/, "");
    return p === "/login" || p === "/logout";
  }

  // ------------------------------------------------ Login links: come back
  document.addEventListener("click", function (e) {
    var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!a) return;
    var url;
    try { url = new URL(a.getAttribute("href"), window.location.href); }
    catch (err) { return; }
    if (url.origin !== window.location.origin || url.pathname !== "/login") return;
    if (url.searchParams.get("redirect-to")) return;       // a page chose already
    if (isAuthPage(window.location.pathname)) return;
    url.searchParams.set("redirect-to", here());
    a.setAttribute("href", url.pathname + url.search + url.hash);
  }, true);

  // ---------------------------- on /login: leave no login page in the history
  if (window.location.pathname.replace(/\/+$/, "") !== "/login") return;

  function onReady(fn) {
    if (window.jQuery) return fn(window.jQuery);
    var tries = 0;
    var t = setInterval(function () {
      if (window.jQuery || ++tries > 50) {
        clearInterval(t);
        if (window.jQuery) fn(window.jQuery);
      }
    }, 100);
  }

  onReady(function ($) {
    /* jQuery fires ajaxSuccess after the call's own handlers, so Frappe's
       login script has already set location.href by the time this runs. A
       navigation that has not happened yet is superseded by a newer one -
       so replacing it here sends the browser to the same place, without the
       login page left behind in the history. */
    $(document).ajaxSuccess(function (event, xhr, settings) {
      if (!settings || !/login/.test(settings.url || "")) return;
      var data = xhr && xhr.responseJSON;
      if (!data || (data.message !== "No App" && data.message !== "Logged In")) return;
      var asked = new URLSearchParams(window.location.search).get("redirect-to");
      var target = safe(asked) || safe(data.redirect_to) || safe(data.home_page) || "/";
      if (isAuthPage(target)) target = "/";
      window.location.replace(target);
    });
  });
})();
