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

  // --------------------------- choices that depend on another choice
  /* Handle type and side under Manual; motor and position under Motorized;
     a slat width's own colours under that width. They are rows on the Curtain
     Product record, each naming the choice it sits under, and they are drawn
     here - inside that choice's card, which is inside #product, so the page's
     own Add to Cart sends them.

     Only the rows under the choice that is picked exist in the page at any
     moment. The others are not hidden, they are gone: a hidden radio is still
     posted, and a Manual handle would ride along on a motorised blind, or a
     5 cm colour on a 2.5 cm blind. The server ignores them either way, but the
     form should say what it means.

     A row with a swatch photo is drawn as a swatch. Under the colour or
     material step it also colours the blind: the photo replaces the texture on
     every part that wears the product's own fabric texture. On the metal blind
     that is both sets of slats, the head box and the bottom bar - the 3D
     bundle ignores a colour sent through modelchanger(), so it is applied to
     the model directly, as the printed blind's picture is. */
  function subOptions(spec) {
    var rows = spec.sub_options || [];
    if (!rows.length) return;

    var arabic = document.documentElement.getAttribute("dir") === "rtl";
    var chosen = {};              // group key -> row id, kept across redraws

    // one host per parent group, inside that group's card
    var parents = {};
    rows.forEach(function (r) { parents[r.parent_gid] = true; });

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

    function refresh() {
      if (window.jQuery) window.jQuery("#product").trigger("change");
    }

    Object.keys(parents).forEach(function (gid) {
      var first = document.querySelector('input[name="option[' + gid + ']"]');
      var card = cardOf(first);
      if (!card) return;

      var host = document.createElement("div");
      host.className = "cr-sub";
      var tray = first.closest(".segmented-grid, .swatches-scroll-tray");
      if (tray && tray.parentNode) tray.parentNode.insertBefore(host, tray.nextSibling);
      else card.appendChild(host);

      var colours = String(gid) === String(spec.material_group);

      function build() {
        var picked = document.querySelector('input[name="option[' + gid + ']"]:checked');
        var value = picked ? picked.value : null;
        host.textContent = "";
        if (!value) return;

        var groups = {}, order = [];
        rows.forEach(function (r) {
          if (String(r.parent_gid) !== String(gid) || String(r.parent_value) !== String(value)) return;
          if (!groups[r.key]) { groups[r.key] = []; order.push(r.key); }
          groups[r.key].push(r);
        });

        var s = size();
        order.forEach(function (key) {
          var list = groups[key], head0 = list[0];
          var title = (arabic && head0.group_ar) || head0.group;
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

          var swatches = offered.some(function (r) { return r.image; });
          var tray = document.createElement("div");
          tray.className = swatches ? "cr-sub-swatches" : "cr-sub-chips";

          offered.forEach(function (r) {
            var item = document.createElement("label");
            item.className = swatches ? "cr-sub-swatch" : "cr-chip";
            item.title = (arabic && r.label_ar) || r.label;
            var input = document.createElement("input");
            input.type = "radio";
            input.name = "cr_sub[" + key + "]";
            input.value = r.id;
            input.checked = r.id === keep;
            input.addEventListener("change", function () {
              chosen[key] = r.id;
              if (colours && r.image) recolour(r.image);
              chain3d(head0.group, r.label);
              refresh();
            });
            item.appendChild(input);
            if (swatches) {
              var img = document.createElement("img");
              img.alt = item.title;
              img.loading = "lazy";
              if (r.image) img.src = r.image;
              item.appendChild(img);
            }
            var name = document.createElement("span");
            name.textContent = (arabic && r.label_ar) || r.label;
            item.appendChild(name);
            if (r.price_text) {
              var cost = document.createElement("small");
              cost.textContent = r.price_text;
              item.appendChild(cost);
            }
            tray.appendChild(item);
          });
          box.appendChild(tray);
          host.appendChild(box);

          // the colour already picked is the one the blind should wear
          var current = offered.filter(function (r) { return r.id === keep; })[0];
          if (colours && current && current.image) recolour(current.image);
          if (current) chain3d(head0.group, current.label);
        });
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
      build();
    });

    subStyle();
    refresh();
  }

  /* Colour the blind with a swatch photo.

     "The product's own fabric texture" is whichever texture most visible
     parts of the blind wear - on the metal blind, the 19 slats of the width
     on show, alongside the head box and bottom bar. Every part that wore it
     when the page loaded is recoloured, visible or not, so switching width
     afterwards keeps the colour. The room itself is left out. */
  /* The chain, in the 3D view, following the Manual choices.

     The bundles know "Manual Operating Side" and "Handle type" themselves,
     but find the chain by its place in the scene's list of parts - and in
     these scenes that place holds the bottom bar, so asking modelchanger()
     moved and recoloured the bottom bar instead. The chain is found here by
     name: RTL_Puller and its weights.

     Side: the chain starts on the right. Left mirrors it across the centre of
     the head box, measured in the blind's own coordinates, so it stays put
     when the typed size rescales the model.
     Type: the bundle's own two finishes - dark shiny steel, light plastic. */
  var CHAIN = /^(RTL_Puller|Machine$)/;
  var chainTex = null;

  function chainParts() {
    var parts = [];
    if (window.scene) {
      window.scene.traverse(function (o) { if (o.isMesh && CHAIN.test(o.name)) parts.push(o); });
    }
    return parts;
  }

  function chain3d(group, label) {
    var T = window.THREE, parts = chainParts();
    if (!T || !parts.length) return;
    var g = String(group || "").toLowerCase(), v = String(label || "").toLowerCase();

    if (/side|position/.test(g) && /left|right/.test(v)) {
      var box = window.scene.getObjectByName("Box");
      var middle = 0;
      if (box && box.geometry) {
        if (!box.geometry.boundingBox) box.geometry.computeBoundingBox();
        middle = (box.geometry.boundingBox.min.x + box.geometry.boundingBox.max.x) / 2;
      }
      var left = /left/.test(v);
      parts.forEach(function (o) {
        o.scale.x = left ? -Math.abs(o.scale.x || 1) : Math.abs(o.scale.x || 1);
        o.position.x = left ? 2 * middle : 0;
        [].concat(o.material).forEach(function (m) { if (m) m.side = T.DoubleSide; });
      });
    } else if (/handle|chain/.test(g) && /metal|steel|plastic/.test(v)) {
      var metal = /metal|steel/.test(v);
      if (metal && !chainTex) {
        chainTex = new T.TextureLoader().load("/maps/preload/zebra/RTL_Puller_texture.jpg");
        chainTex.wrapS = chainTex.wrapT = T.RepeatWrapping;
      }
      parts.forEach(function (o) {
        if (!/^RTL_Puller$/.test(o.name)) return;      // the chain, not its weights
        o.material = new T.MeshPhongMaterial(metal
          ? { color: 0x5a5a5a, shininess: 40, specular: 0xffffff, map: chainTex, side: T.DoubleSide }
          : { color: 0xd2d2d2, shininess: 50, specular: 0x979797, side: T.DoubleSide });
      });
    } else {
      return;
    }
    if (window.renderer && window.camera) window.renderer.render(window.scene, window.camera);
  }

  var fabricParts = null;

  function fabric() {
    if (fabricParts || !window.scene) return fabricParts;
    var count = {}, byMap = {};
    window.scene.traverse(function (o) {
      if (!o.isMesh || o.name === "mesh3d") return;
      var m = [].concat(o.material)[0];
      var src = m && m.map && m.map.image && m.map.image.src;
      if (!src) return;
      (byMap[src] = byMap[src] || []).push(o);
      if (o.visible) count[src] = (count[src] || 0) + 1;
    });
    var best = null;
    Object.keys(count).forEach(function (src) {
      if (!best || count[src] > count[best]) best = src;
    });
    fabricParts = best ? byMap[best] : [];
    return fabricParts;
  }

  var colourTextures = {};

  function recolour(url) {
    var T = window.THREE;
    var parts = fabric();
    if (!T || !parts || !parts.length) return;
    function apply(tex) {
      parts.forEach(function (o) {
        [].concat(o.material).forEach(function (m) {
          if (m.map === tex) return;
          m.map = tex;
          if (m.color) m.color.set(0xffffff);
          m.needsUpdate = true;
        });
      });
      if (window.renderer && window.camera) window.renderer.render(window.scene, window.camera);
    }
    if (colourTextures[url]) return apply(colourTextures[url]);
    new T.TextureLoader().load(url, function (tex) {
      if (T.sRGBEncoding) tex.encoding = T.sRGBEncoding;
      tex.wrapS = tex.wrapT = T.RepeatWrapping;
      colourTextures[url] = tex;
      apply(tex);
    });
  }

  // ------------------------------------------- the customer's own picture
  /* For a printed blind: an upload step, the picture on the blind in the 3D
     room, and the original file sent to the server for the team to print.

     The captured 3D bundle has no way to take a picture - its modelchanger()
     ignores one under every group name tried - so the picture is put on the
     blind's fabric (the Valance_Front mesh) with three.js directly. Two things
     measured on the model decide how:

       * its texture runs upside down: a picture's top lands at the bottom, left
         and right correct - so the texture is not flipped on upload.
       * the 3D blind keeps the same shape whatever size is typed; it always
         fills the room's window. So the picture is cropped to the blind as
         SHOWN - cover, centred, never stretched - and the team prints the
         original at the ordered size.

     A PDF is drawn from its first page, with pdf.js, fetched only when a PDF
     is actually chosen - no one else pays for it. */
  var PDFJS = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/";
  var MAX_MB = 20;
  var printed = null;           // { tex, aspect } once a picture is on the blind

  function blindMesh() {
    return window.scene && window.scene.getObjectByName &&
      window.scene.getObjectByName("Valance_Front");
  }

  function fitPicture() {
    var mesh = blindMesh();
    if (!printed || !mesh || !window.THREE) return;
    var g = mesh.geometry;
    if (!g.boundingBox) g.computeBoundingBox();
    var b = g.boundingBox, s = new window.THREE.Vector3();
    mesh.getWorldScale(s);
    var shown = ((b.max.x - b.min.x) * s.x) / ((b.max.z - b.min.z) * s.z || 1);
    var t = printed.tex;
    t.repeat.set(1, 1);
    t.offset.set(0, 0);
    if (printed.aspect > shown) {          // wider than the blind: crop the sides
      t.repeat.x = shown / printed.aspect;
      t.offset.x = (1 - t.repeat.x) / 2;
    } else {                               // taller: crop top and bottom
      t.repeat.y = printed.aspect / shown;
      t.offset.y = (1 - t.repeat.y) / 2;
    }
  }

  function paintPicture() {
    var mesh = blindMesh();
    if (!printed || !mesh) return;
    var m = mesh.material;
    if (m.map !== printed.tex) {
      m.map = printed.tex;
      if (m.color) m.color.set(0xffffff);
      m.needsUpdate = true;
    }
    fitPicture();
    if (window.renderer && window.camera) window.renderer.render(window.scene, window.camera);
  }

  function showOnBlind(canvas) {
    var T = window.THREE;
    if (!T || !blindMesh()) return false;
    var tex = new T.CanvasTexture(canvas);
    tex.flipY = false;                     // the model's fabric runs upside down
    if (T.sRGBEncoding) tex.encoding = T.sRGBEncoding;
    printed = { tex: tex, aspect: canvas.width / canvas.height };
    paintPicture();
    return true;
  }

  function loadScript(src) {
    return new Promise(function (ok, bad) {
      var s = document.createElement("script");
      s.src = src; s.onload = ok; s.onerror = bad;
      document.head.appendChild(s);
    });
  }

  /* Draw the chosen file onto a canvas no larger than 2048px on its long side:
     a phone photo is 12 megapixels, and a texture that size costs every
     visitor's graphics memory for no visible gain. */
  function toCanvas(file) {
    var LIMIT = 2048;
    function sized(w, h) {
      var k = Math.min(1, LIMIT / Math.max(w, h));
      var c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(w * k));
      c.height = Math.max(1, Math.round(h * k));
      return c;
    }
    if (file.type === "application/pdf" || /\.pdf$/i.test(file.name)) {
      var ready = window.pdfjsLib ? Promise.resolve() :
        loadScript(PDFJS + "pdf.min.js").then(function () {
          window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS + "pdf.worker.min.js";
        });
      return ready
        .then(function () { return file.arrayBuffer(); })
        .then(function (data) { return window.pdfjsLib.getDocument({ data: data }).promise; })
        .then(function (pdf) { return pdf.getPage(1); })
        .then(function (page) {
          var base = page.getViewport({ scale: 1 });
          var scale = Math.min(4, LIMIT / Math.max(base.width, base.height));
          var view = page.getViewport({ scale: scale });
          var c = sized(view.width, view.height);
          return page.render({ canvasContext: c.getContext("2d"), viewport: view })
            .promise.then(function () { return c; });
        });
    }
    return new Promise(function (ok, bad) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        var c = sized(img.naturalWidth, img.naturalHeight);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        ok(c);
      };
      img.onerror = function () { URL.revokeObjectURL(url); bad(new Error("image")); };
      img.src = url;
    });
  }

  function sendFile(file, retried) {
    var body = new FormData();
    body.append("file", file, file.name);
    return fetch("/api/method/curtain_roll.print_upload.upload", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-Frappe-CSRF-Token": (window.frappe && window.frappe.csrf_token) || "" },
      body: body
    }).then(function (r) {
      // a stale token from a page left open: fetch a fresh one, try once more
      if (r.status === 400 && !retried) {
        return fetch("/api/method/curtain_roll.api.csrf_token", { credentials: "same-origin" })
          .then(function (t) { return t.json(); })
          .then(function (t) {
            window.frappe = window.frappe || {};
            window.frappe.csrf_token = ((t && t.message) || {}).token || "";
            return sendFile(file, true);
          });
      }
      return r.json().then(function (j) {
        if (r.ok && j.message && j.message.token) return j.message;
        var why = "";
        try { why = JSON.parse(JSON.parse(j._server_messages)[0]).message; } catch (e) { why = ""; }
        throw new Error(why || say("The picture could not be uploaded. Please try again."));
      });
    });
  }

  function printUpload(spec) {
    if (!spec.allow_upload) return;
    var sizeBox = document.querySelector('input[name^="option["][name$="[width]"]');
    var sizeCard = cardOf(sizeBox);
    if (!sizeCard) return;

    var card = document.createElement("div");
    card.className = "option-card cr-print-card";
    card.innerHTML =
      '<div class="option-header"><h4><span class="option-step-number">1</span> ' +
      '<span class="cr-print-title"></span></h4></div>' +
      '<div class="cr-print-body" id="input-optioncrprint">' +
      '<input type="file" class="cr-print-file" hidden ' +
      'accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf">' +
      '<input type="hidden" name="cr_print" value="">' +
      '<button type="button" class="cr-print-pick"><i class="fa-solid fa-cloud-arrow-up"></i> ' +
      '<span></span></button>' +
      '<div class="cr-print-chosen" hidden><img alt=""><div class="cr-print-meta">' +
      '<b class="cr-print-name"></b><span class="cr-print-state"></span>' +
      '<button type="button" class="cr-print-change"></button></div></div>' +
      '<p class="cr-print-note"></p></div>';
    card.querySelector(".cr-print-title").textContent = say("Your Picture");
    card.querySelector(".cr-print-pick span").textContent = say("Upload a picture");
    card.querySelector(".cr-print-change").textContent = say("Choose another");
    card.querySelector(".cr-print-note").textContent =
      say("JPG, PNG or PDF, up to 20 MB. It is printed across the whole blind.");
    sizeCard.parentNode.insertBefore(card, sizeCard);

    var fileInput = card.querySelector(".cr-print-file");
    var token = card.querySelector('input[name="cr_print"]');
    var pick = card.querySelector(".cr-print-pick");
    var chosen = card.querySelector(".cr-print-chosen");
    var thumb = chosen.querySelector("img");
    var state = card.querySelector(".cr-print-state");

    function status(text, bad) {
      state.textContent = text;
      state.className = "cr-print-state" + (bad ? " cr-print-bad" : "");
    }
    function open() { fileInput.value = ""; fileInput.click(); }
    pick.addEventListener("click", open);
    card.querySelector(".cr-print-change").addEventListener("click", open);

    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) return;
      if (!/\.(jpe?g|png|pdf)$/i.test(file.name)) {
        pick.hidden = false; chosen.hidden = true;
        card.querySelector(".cr-print-note").textContent = say("Please upload a JPG, PNG or PDF file.");
        return;
      }
      if (file.size > MAX_MB * 1024 * 1024) {
        card.querySelector(".cr-print-note").textContent =
          say("That file is too large. The limit is 20 MB.");
        return;
      }
      token.value = "";                    // the old picture no longer counts
      pick.hidden = true;
      chosen.hidden = false;
      chosen.querySelector(".cr-print-name").textContent = file.name;
      thumb.removeAttribute("src");
      status(say("Preparing the preview…"));

      var preview = toCanvas(file).then(function (canvas) {
        thumb.src = canvas.toDataURL("image/jpeg", 0.7);
        showOnBlind(canvas);
      });
      var upload = sendFile(file).then(function (answer) {
        token.value = answer.token;
      });
      Promise.all([preview, upload]).then(function () {
        status(say("Uploaded"));
        if (window.jQuery) window.jQuery("#product").trigger("change");
      }).catch(function (err) {
        status((err && err.message) || say("The picture could not be uploaded. Please try again."), true);
      });
    });

    // the bundle redraws the blind when options change; put the picture back
    if (window.jQuery) window.jQuery("#product").on("change", function () { setTimeout(paintPicture, 300); });
    setInterval(paintPicture, 1500);
    printStyle();
  }

  function printStyle() {
    if (document.getElementById("cr-print-style")) return;
    var css = document.createElement("style");
    css.id = "cr-print-style";
    css.textContent =
      ".cr-print-pick{display:flex;align-items:center;justify-content:center;gap:10px;" +
      "width:100%;padding:18px;border:2px dashed var(--brand,#09446c);border-radius:14px;" +
      "background:var(--brand-light,#eaf3f8);color:var(--brand,#09446c);font:inherit;" +
      "font-weight:700;font-size:14.5px;cursor:pointer}" +
      ".cr-print-pick:hover{background:#dcebf4}" +
      ".cr-print-chosen{display:flex;gap:12px;align-items:center}" +
      ".cr-print-chosen[hidden],.cr-print-pick[hidden]{display:none}" +
      ".cr-print-chosen img{width:84px;height:60px;object-fit:cover;border-radius:8px;" +
      "border:1px solid var(--border,#e1ebf2);background:#f2f5f8;flex:none}" +
      ".cr-print-meta{display:flex;flex-direction:column;gap:3px;min-width:0}" +
      ".cr-print-name{font-size:13.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}" +
      ".cr-print-state{font-size:12.5px;color:#0a8a3c;font-weight:600}" +
      ".cr-print-state.cr-print-bad{color:#c0392b}" +
      ".cr-print-change{align-self:flex-start;border:0;background:none;padding:0;" +
      "color:var(--brand,#09446c);font:inherit;font-size:12.5px;text-decoration:underline;cursor:pointer}" +
      ".cr-print-note{margin:10px 0 0;font-size:12px;color:var(--text-muted,#54667a)}";
    document.head.appendChild(css);
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
      ".cr-sub-none{font-size:12.5px;color:#c0392b;font-weight:600}" +
      // colour swatches: a photo tile with the name under it
      ".cr-sub-swatches{display:grid;grid-template-columns:repeat(auto-fill,minmax(68px,1fr));gap:8px}" +
      ".cr-sub-swatch{position:relative;display:flex;flex-direction:column;align-items:center;" +
      "gap:4px;cursor:pointer;padding:5px;border:1.5px solid var(--border,#e1ebf2);" +
      "border-radius:12px;background:var(--surface,#fff);font-size:11.5px;font-weight:600;" +
      "text-align:center;color:var(--text,#0f172a)}" +
      ".cr-sub-swatch input{position:absolute;opacity:0;pointer-events:none}" +
      ".cr-sub-swatch img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:8px;" +
      "background:#eef2f5}" +
      ".cr-sub-swatch small{font-weight:500;color:var(--text-muted,#54667a);font-size:10.5px}" +
      ".cr-sub-swatch:has(input:checked){border-color:var(--brand,#09446c);" +
      "box-shadow:0 0 0 3px var(--brand-soft,rgba(9,68,108,.15))}";
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
    printUpload(spec);
    renumber();
    // after the page's own script has had its turn at disabling rows
    setTimeout(function () { hideEmptyGroups(); renumber(); }, 400);
    setTimeout(function () { hideEmptyGroups(); renumber(); }, 1500);
  }

  /* A colour priced per square metre carries its price inside the swatch's
     name - "7200 (+SR 120.00 / m²)" - and the swatch name is one clipped line
     about 60px wide, so the price ran out of the card and across the next one
     (Blackout, Shutters). The price gets a line of its own under the code. */
  function swatchPriceStyle() {
    if (document.getElementById("cr-swatch-price")) return;
    var css = document.createElement("style");
    css.id = "cr-swatch-price";
    css.textContent =
      ".swatch-label .option-value{white-space:normal;overflow:visible;" +
      "text-overflow:clip;line-height:1.2;overflow-wrap:anywhere}" +
      ".swatch-label .option-price{display:block;margin-top:2px;font-size:9px;" +
      "font-weight:700;color:var(--brand,#09446c);white-space:normal}";
    document.head.appendChild(css);
  }

  function load() {
    var key = productKey();
    if (!key) return;
    // no size boxes means this is not a product page, whatever the URL says
    if (!document.querySelector('input[name^="option["][name$="[width]"]')) return;
    swatchPriceStyle();

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
