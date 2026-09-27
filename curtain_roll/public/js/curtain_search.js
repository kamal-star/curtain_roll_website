/* The storefront's search box.
 *
 * Why a script rather than a form in the markup: the site is eighteen captured
 * pages, each carrying its own frozen copy of the header inside {% raw %}, plus
 * the shell the pages written since extend. Wiring search by editing HTML means
 * twenty edits now and twenty more the next time the captures are regenerated.
 * One script, injected on every page by the same hook that adds the language
 * switch, adopts whatever search boxes it finds - including the ones on pages
 * nobody has thought of yet.
 *
 * It degrades honestly. With scripting off, /search is still a plain GET form
 * that works; this only adds submitting from the header and the suggestions
 * under the box.
 */
(function () {
  "use strict";

  var ENDPOINT = "/api/method/curtain_roll.search.suggest";
  var MIN_CHARS = 2;      // fabric codes are four digits, so not more than this
  var PAUSE = 160;        // ms of quiet before asking the server
  var phrases = window.__crPhrases || {};

  function say(text) {
    return phrases[text] || text;
  }

  function go(query) {
    var q = (query || "").trim();
    if (!q) return;
    window.location.href = "/search?q=" + encodeURIComponent(q);
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  /* One search input, with its own dropdown and its own in-flight request. */
  function attach(input) {
    if (input.dataset.crSearch) return;
    input.dataset.crSearch = "1";

    var host = input.parentElement;
    if (!host) return;
    if (getComputedStyle(host).position === "static") host.style.position = "relative";

    var panel = el("div", "cr-sg");
    panel.hidden = true;
    panel.setAttribute("role", "listbox");
    host.appendChild(panel);

    var timer = null;
    var pending = null;
    var rows = [];
    var at = -1;

    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");

    function close() {
      panel.hidden = true;
      input.setAttribute("aria-expanded", "false");
      rows = [];
      at = -1;
    }

    function mark() {
      rows.forEach(function (row, i) {
        row.classList.toggle("cr-sg-on", i === at);
        row.setAttribute("aria-selected", i === at ? "true" : "false");
      });
      // a highlighted row the shopper cannot see is the same as no highlight
      if (at >= 0 && rows[at]) rows[at].scrollIntoView({ block: "nearest" });
    }

    function draw(answer) {
      var hits = (answer && answer.results) || [];
      panel.textContent = "";
      rows = [];
      at = -1;

      if (!hits.length) {
        panel.appendChild(el("div", "cr-sg-none", say("Nothing matched.")));
        panel.hidden = false;
        input.setAttribute("aria-expanded", "true");
        return;
      }

      if (answer.guessed) {
        panel.appendChild(el("div", "cr-sg-note", say("Closest matches")));
      }

      hits.forEach(function (hit) {
        var row = el("a", "cr-sg-row");
        row.href = hit.route;
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", "false");

        var shot = el("span", "cr-sg-shot");
        if (hit.image) {
          shot.style.backgroundImage = "url('" + hit.image.replace(/'/g, "%27") + "')";
        } else {
          var glyph = el("i", hit.icon || "fa-solid fa-magnifying-glass");
          shot.className = "cr-sg-shot cr-sg-glyph";
          shot.appendChild(glyph);
        }
        row.appendChild(shot);

        var body = el("span", "cr-sg-body");
        body.appendChild(el("span", "cr-sg-name", hit.label));
        if (hit.blurb) body.appendChild(el("span", "cr-sg-blurb", hit.blurb));
        row.appendChild(body);

        if (hit.price) row.appendChild(el("span", "cr-sg-price", hit.price));
        panel.appendChild(row);
        rows.push(row);
      });

      var all = el("button", "cr-sg-all", say("See all results"));
      all.type = "button";
      all.addEventListener("click", function () { go(input.value); });
      panel.appendChild(all);

      panel.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    function ask() {
      var q = input.value.trim();
      if (q.length < MIN_CHARS) return close();

      if (pending) pending.abort();
      // AbortController is everywhere we support, but an old browser losing
      // the abort should still get its suggestions
      pending = window.AbortController ? new AbortController() : null;

      fetch(ENDPOINT + "?q=" + encodeURIComponent(q) + "&limit=6", {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: pending ? pending.signal : undefined
      })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          // the shopper has typed on since this went out
          if (input.value.trim() !== q) return;
          if (data && data.message) draw(data.message);
        })
        .catch(function () { /* offline, or superseded - leave the box alone */ });
    }

    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(ask, PAUSE);
    });

    input.addEventListener("focus", function () {
      if (rows.length && input.value.trim().length >= MIN_CHARS) {
        panel.hidden = false;
      }
    });

    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        if (at >= 0 && rows[at]) window.location.href = rows[at].href;
        else go(input.value);
        return;
      }
      if (e.key === "Escape") return close();
      if (panel.hidden || !rows.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        at = (at + 1) % rows.length;
        mark();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        at = at <= 0 ? rows.length - 1 : at - 1;
        mark();
      }
    });

    document.addEventListener("click", function (e) {
      if (!host.contains(e.target)) close();
    });

    // the magnifier beside the box looks like a button, so make it one
    var icon = host.querySelector(".search-field-icon");
    if (icon) {
      icon.style.cursor = "pointer";
      icon.style.pointerEvents = "auto";
      icon.addEventListener("click", function () { go(input.value); });
    }
  }

  function wire() {
    // including the results page's own form: its GET still works with
    // scripting off, and this only adds the suggestions under it
    document.querySelectorAll("input.search-field, input[type=search]")
      .forEach(attach);

    // arriving on /search, the header box should show what is being searched
    var q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      document.querySelectorAll("input.search-field").forEach(function (input) {
        if (!input.value) input.value = q;
      });
    }
  }

  var css = document.createElement("style");
  css.textContent = [
    ".cr-sg{position:absolute;z-index:1200;inset-inline-start:0;inset-inline-end:0;",
    "top:calc(100% + 8px);background:#fff;border:1px solid var(--border,#e1ebf2);",
    "border-radius:14px;box-shadow:0 18px 44px -10px rgba(9,68,108,.28);",
    "overflow:hidden;max-height:min(70vh,430px);overflow-y:auto;text-align:start}",
    ".cr-sg-row{display:flex;align-items:center;gap:12px;padding:10px 14px;",
    "text-decoration:none;color:var(--text,#0f172a);border-bottom:1px solid ",
    "var(--border,#eef4f8)}",
    ".cr-sg-row:hover,.cr-sg-on{background:var(--brand-light,#eaf3f8);",
    "text-decoration:none}",
    ".cr-sg-shot{flex:0 0 auto;width:52px;height:40px;border-radius:8px;",
    "background:var(--brand-light,#eaf3f8);background-size:cover;",
    "background-position:center}",
    ".cr-sg-glyph{display:flex;align-items:center;justify-content:center;",
    "color:var(--brand,#09446c);font-size:15px}",
    ".cr-sg-body{flex:1 1 auto;min-width:0}",
    ".cr-sg-name{display:block;font-size:14px;font-weight:600;line-height:1.35}",
    ".cr-sg-blurb{display:block;font-size:12px;line-height:1.4;margin-top:2px;",
    "color:var(--text-muted,#54667a);white-space:nowrap;overflow:hidden;",
    "text-overflow:ellipsis}",
    ".cr-sg-price{flex:0 0 auto;font-size:13px;font-weight:700;white-space:nowrap;",
    "color:var(--brand,#09446c)}",
    ".cr-sg-note,.cr-sg-none{padding:10px 14px;font-size:12.5px;",
    "color:var(--text-muted,#54667a)}",
    ".cr-sg-all{display:block;width:100%;border:0;background:var(--bg,#f8fbfd);",
    "padding:11px 14px;font:inherit;font-size:13px;font-weight:600;",
    "color:var(--brand,#09446c);cursor:pointer;text-align:center}",
    ".cr-sg-all:hover{background:var(--brand-light,#eaf3f8)}"
  ].join("");
  document.head.appendChild(css);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
