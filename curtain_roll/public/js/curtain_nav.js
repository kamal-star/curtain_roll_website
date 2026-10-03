/* The category bar under the header: reachable when it is wider than the screen.

   The bar is one row of pills that scrolls sideways, with its scrollbar
   hidden. A finger can swipe it, but with a mouse the pills past the right
   edge - Roman Kayan, Wavy, Printed - could not be reached at all.

   So, only while the row is wider than its box:
     * arrow buttons at each end, shown only when there is more that way;
     * the mouse wheel scrolls the row sideways while the pointer is on it
       (and hands back to the page once the row is at its end);
     * the current page's pill is brought into view on load.

   Arabic runs the row right to left. scrollLeft then counts down from 0 into
   negative numbers, so positions are taken as distances from the start and
   every move is signed by the direction. */
(function () {
  "use strict";

  function setup(list) {
    var strip = list.closest(".catalog-nav-strip") || list.parentNode;
    if (!strip || strip.querySelector(".cr-nav-arrow")) return;

    // read at the moment of use, not once: the Arabic layout's direction can
    // arrive after this runs, and a stale "ltr" scrolls the row the wrong way
    function rtl() { return getComputedStyle(list).direction === "rtl"; }
    function sign() { return rtl() ? -1 : 1; }

    style();
    if (getComputedStyle(strip).position === "static") strip.style.position = "relative";

    function arrow(which) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "cr-nav-arrow cr-nav-" + which;
      b.setAttribute("aria-label", which === "next" ? "More categories" : "Previous categories");
      b.innerHTML = '<i class="fa-solid fa-chevron-' +
        ((which === "next") !== rtl() ? "right" : "left") + '"></i>';
      b.addEventListener("click", function () {
        // Aim at a position inside the row, never past its end. A smooth
        // scroll that overshoots is clamped in a left-to-right row, but in a
        // right-to-left one Chrome drops it and the row does not move at all.
        var step = Math.max(160, list.clientWidth * 0.7);
        var at = Math.min(room(), Math.max(0, travelled() + (which === "next" ? step : -step)));
        list.scrollTo({ left: sign() * at, behavior: "smooth" });
      });
      strip.appendChild(b);
      return b;
    }
    var prev = arrow("prev"), next = arrow("next");

    function travelled() { return Math.abs(list.scrollLeft); }
    function room() { return list.scrollWidth - list.clientWidth; }

    function update() {
      // the chevrons follow the direction too
      [[prev, "prev"], [next, "next"]].forEach(function (p) {
        var i = p[0].querySelector("i");
        if (i) i.className = "fa-solid fa-chevron-" + ((p[1] === "next") !== rtl() ? "right" : "left");
      });
      var spare = room();
      var at = travelled();
      prev.classList.toggle("cr-show", spare > 2 && at > 2);
      next.classList.toggle("cr-show", spare > 2 && at < spare - 2);
    }

    list.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);

    list.addEventListener("wheel", function (e) {
      if (room() <= 2) return;
      var d = Math.abs(e.deltaY) > Math.abs(e.deltaX) ? e.deltaY : 0;
      if (!d) return;                          // a sideways swipe already scrolls it
      var at = travelled();
      if ((d > 0 && at >= room() - 1) || (d < 0 && at <= 0)) return;   // let the page scroll
      e.preventDefault();
      list.scrollLeft += sign() * d;
    }, { passive: false });

    // the current page's pill, if it is cut off
    var active = list.querySelector(".active");
    if (active) {
      var box = list.getBoundingClientRect(), a = active.getBoundingClientRect();
      if (a.left < box.left || a.right > box.right) {
        var centre = (a.left + a.right) / 2 - (box.left + box.right) / 2;
        list.scrollLeft += centre;
      }
    }
    update();
    setTimeout(update, 400);                   // after the web fonts settle the widths
  }

  function style() {
    if (document.getElementById("cr-nav-style")) return;
    var css = document.createElement("style");
    css.id = "cr-nav-style";
    css.textContent =
      ".cr-nav-arrow{position:absolute;top:50%;transform:translateY(-50%);z-index:3;" +
      "width:34px;height:34px;border-radius:50%;border:1px solid var(--border-color,#dde3ea);" +
      "background:#fff;color:var(--brand,#0b3c5d);box-shadow:0 2px 10px rgba(15,35,60,.14);" +
      "display:none;align-items:center;justify-content:center;cursor:pointer;padding:0;font-size:13px}" +
      ".cr-nav-arrow.cr-show{display:flex}" +
      ".cr-nav-arrow:hover{background:var(--brand,#0b3c5d);color:#fff}" +
      ".cr-nav-prev{left:-4px}.cr-nav-next{right:-4px}" +
      "[dir=rtl] .cr-nav-prev{left:auto;right:-4px}[dir=rtl] .cr-nav-next{right:auto;left:-4px}";
    document.head.appendChild(css);
  }

  function run() {
    document.querySelectorAll(".catalog-nav-list").forEach(setup);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
