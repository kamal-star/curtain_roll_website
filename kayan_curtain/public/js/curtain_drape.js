/* The Sheer Curtain: a sheer in the middle, blackout curtains either side,
   hung in wave folds from the ceiling to the floor across the whole wall.

   The page borrows the Vertical Kayan page's 3D bundle for its room, camera
   and lights. Its blind is hidden and this curtain is hung in its place,
   built here because no captured product has a curtain like it.

   Where the wall is comes from the room picture itself (WALL, as fractions of
   the 4096 x 2048 panorama: its left and right corners, the ceiling and the
   floor where they meet it in the middle). The room is a sphere around the
   camera with the picture's centre dead ahead, so each fraction is a
   direction, and the curtain is laid on the plane where those directions meet
   the wall's depth - that is what makes its edges land on the corners and its
   hem on the floor, curves and all.

   Colours: the sheer follows the Sheer Colour step (the product's Colours),
   the blackout follows the Blackout Colour choices. Each takes the average
   colour of the swatch photo, so a photo the team uploads in the desk colours
   the curtain without anything else to set. Until the customer picks, the
   first swatch of each is shown.

   The Accordion Door uses the same machinery with its own settings, put on
   its page as window.CR_DRAPE (make_accordion_page.py): its room, the
   doorway's box in that room, how much of the room to open the view on, and
   kind "accordion" - folding slats in the doorway, coloured by the Door
   Colour swatch, opening from the left, the right or the centre. The Smart
   Film is kind "film": the window's glass frosted or clear. With no
   CR_DRAPE the page is the Sheer Curtain. */
(function () {
  "use strict";
  if (!window.THREE) return;
  var THREE = window.THREE;

  var CFG = window.CR_DRAPE || {};
  var KIND = CFG.kind || "sheer";
  function box(px, fallback) {
    px = px || fallback;
    return { left: px[0] / 4096, top: px[1] / 2048, right: px[2] / 4096, bottom: px[3] / 2048 };
  }
  // what is hung, as [left, top, right, bottom] pixels of the 4096 x 2048
  // room. The sheer's: the wall in vertical-premium.jpg, the bottom a little
  // past the skirting line, so the hem rests on the floor.
  var WALL = box(CFG.wall, [1562, 652, 2522, 1330]);
  // what the view opens on; the wall itself unless the page says more
  var VIEW = CFG.view ? box(CFG.view) : WALL;
  // the wall's depth in the scene: where the vertical blind hung
  var DEPTH = -330;
  // across the wall, as fractions of its width: [from, to]
  var LEFT = [0, 0.215], SHEER = [0.175, 0.825], RIGHT = [0.785, 1];

  var DEFAULT_SHEER = [243, 241, 236], DEFAULT_BLACKOUT = [205, 185, 156];

  var built = null;          // { group, sheer: [mesh], blackout: [mesh] }

  // ------------------------------------------------------------ the wall
  function at(u, v, z) {
    var cam = window.camera.position;
    var lon = (u - 0.5) * 2 * Math.PI, lat = (0.5 - v) * Math.PI;
    var d = new THREE.Vector3(Math.sin(lon) * Math.cos(lat), Math.sin(lat),
                              -Math.cos(lon) * Math.cos(lat));
    var t = (z - cam.z) / d.z;
    return cam.clone().add(d.multiplyScalar(t));
  }

  function wall(b) {
    b = b || WALL;
    var um = (b.left + b.right) / 2;
    return {
      left: at(b.left, 0.5, DEPTH).x,
      right: at(b.right, 0.5, DEPTH).x,
      top: at(um, b.top, DEPTH).y,
      bottom: at(um, b.bottom, DEPTH).y
    };
  }

  // ------------------------------------------------------------ the cloth
  /* A panel hung in wave folds. Across, the cloth follows a wave of `folds`
     crests; each vertex is shaded by how squarely it faces the light, which
     is what makes folds read as folds. `gather` squeezes the folds towards
     the outer edge, as a curtain drawn back is bunched at its end. */
  function panel(x0, x1, top, bottom, z, folds, depth, gather, contrast) {
    var cols = Math.max(24, Math.round(folds * 12)), rows = 24;
    // three r122 here: the buffer flavour is the one with attributes
    var geo = new (THREE.PlaneBufferGeometry || THREE.PlaneGeometry)(1, 1, cols, rows);
    var pos = geo.attributes.position;
    var shade = new Float32Array(pos.count * 3);
    var width = x1 - x0, height = top - bottom;
    var light = new THREE.Vector3(-0.35, 0.25, 1).normalize();
    for (var i = 0; i < pos.count; i++) {
      var s = pos.getX(i) + 0.5, t = pos.getY(i) + 0.5;      // 0..1 across, up
      var g = gather ? (gather > 0 ? Math.pow(s, 1 + gather) : 1 - Math.pow(1 - s, 1 - gather)) : s;
      var phase = g * folds * Math.PI * 2;
      // the hem swings a little more than the head, which is held by the track
      var amp = depth * (0.85 + 0.15 * (1 - t));
      pos.setXYZ(i, x0 + s * width, bottom + t * height, z + Math.sin(phase) * amp);
      // slope of the wave -> the normal -> the light it catches
      var slope = Math.cos(phase) * amp * folds * Math.PI * 2 / width;
      var n = new THREE.Vector3(-slope, 0, 1).normalize();
      var lit = (1 - contrast) + contrast * Math.max(0, n.dot(light));
      // a touch darker towards the floor and in the deepest part of each fold
      lit *= 0.94 + 0.06 * t;
      lit *= 0.93 + 0.07 * (0.5 + 0.5 * Math.sin(phase));
      shade[i * 3] = shade[i * 3 + 1] = shade[i * 3 + 2] = lit;
    }
    geo.setAttribute("color", new THREE.BufferAttribute(shade, 3));
    geo.computeVertexNormals();
    return geo;
  }

  function weave() {
    // a faint, tileable weave so a flat colour reads as cloth
    var c = document.createElement("canvas");
    c.width = c.height = 64;
    var x = c.getContext("2d");
    x.fillStyle = "#fff";
    x.fillRect(0, 0, 64, 64);
    for (var i = 0; i < 64; i++) {
      var a = 0.035 + 0.03 * ((i * 7919) % 13) / 13;
      x.fillStyle = "rgba(0,0,0," + a.toFixed(3) + ")";
      x.fillRect(i, 0, 1, 64);
      x.fillStyle = "rgba(0,0,0," + (a * 0.6).toFixed(3) + ")";
      x.fillRect(0, i, 64, 1);
    }
    var tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    return tex;
  }

  // ---------------------------------------------------- the accordion door
  /* Folding slats across the doorway, under a header track. Each slat is a
     flat strip turned a little left or right of the one beside it - that
     zigzag is the whole look of the door.

     Plastic: narrow slats with a groove down the middle and a darker line at
     each hinge. Leather: wider, padded panels - fuller in the middle, soft
     at the folds - folded a little deeper.

     Opening From: Centre puts a pair of handles where the two halves meet;
     Left or Right puts one at that jamb, which is where the door is pulled
     from. Nothing picked yet shows the centre. */
  var doorTex = null, doorRGB = null;

  function checked(gid) {
    return gid ? document.querySelector('input[name="option[' + gid + ']"]:checked') : null;
  }

  function openingMode() {
    var on = checked(CFG.opening_gid);
    return (on && (CFG.opening_values || {})[on.value]) || "centre";
  }

  function leather() {
    var on = checked(CFG.type_gid);
    return !!on && (CFG.leather_values || []).map(String).indexOf(String(on.value)) !== -1;
  }

  // across one slat or panel: [where (0..1), shade]
  var SLAT_PROFILE = [[0, 0.72], [0.035, 0.96], [0.47, 1], [0.49, 0.8], [0.51, 0.8],
                      [0.53, 1], [0.965, 0.96], [1, 0.72]];
  var PANEL_PROFILE = [[0, 0.7], [0.06, 0.84], [0.18, 0.95], [0.35, 1], [0.5, 1.02],
                       [0.65, 1], [0.82, 0.95], [0.94, 0.84], [1, 0.7]];

  function slatGeometry(x0, z0, x1, z1, top, bottom, facing, profile) {
    var PROFILE = profile || SLAT_PROFILE;
    var n = PROFILE.length, rows = 8;
    var pos = [], uv = [], col = [], idx = [];
    for (var r = 0; r <= rows; r++) {
      var t = r / rows, y = bottom + (top - bottom) * t;
      for (var c = 0; c < n; c++) {
        var s = PROFILE[c][0];
        pos.push(x0 + (x1 - x0) * s, y, z0 + (z1 - z0) * s);
        uv.push(s, t);
        // the light from the room's front-left: slats turned towards it are
        // brighter, and a soft fall-off towards the floor
        var lit = PROFILE[c][1] * facing * (0.9 + 0.1 * t);
        col.push(lit, lit, lit);
      }
    }
    for (r = 0; r < rows; r++) {
      for (c = 0; c < n - 1; c++) {
        var a = r * n + c, b = a + 1, d = a + n, e = d + 1;
        idx.push(a, b, d, b, e, d);
      }
    }
    var geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute("uv", new THREE.Float32BufferAttribute(uv, 2));
    geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
    geo.setIndex(idx);
    geo.computeVertexNormals();
    return geo;
  }

  function buildDoor() {
    var w = wall(), W = w.right - w.left, H = w.top - w.bottom;
    var group = new THREE.Group();
    group.name = "cr_drape";
    var mat = new THREE.MeshBasicMaterial({
      color: 0xffffff, vertexColors: true, side: THREE.DoubleSide, map: doorTex || null
    });
    var trim = new THREE.MeshBasicMaterial({ color: 0xffffff });

    // the header the door hangs from, the full width of the opening
    var headH = H * 0.035;
    var head = new THREE.Mesh(new THREE.BoxGeometry(W, headH, 7), trim);
    head.position.set(w.left + W / 2, w.top - headH / 2, DEPTH + 4);
    group.add(head);

    // plastic slats about 4.4% of the height wide, leather panels 7%; an
    // even number of them
    var soft = leather();
    var count = Math.max(6, Math.round(W / (H * (soft ? 0.07 : 0.044)) / 2) * 2);
    var step = W / count, fold = step * (soft ? 0.36 : 0.3);
    var top = w.top - headH, bottom = w.bottom + H * 0.006;
    for (var i = 0; i < count; i++) {
      var z0 = DEPTH + (i % 2 ? fold : 0), z1 = DEPTH + (i % 2 ? 0 : fold);
      var facing = i % 2 ? (soft ? 0.82 : 0.86) : 1;
      group.add(new THREE.Mesh(
        slatGeometry(w.left + i * step, z0, w.left + (i + 1) * step, z1, top, bottom, facing,
                     soft ? PANEL_PROFILE : SLAT_PROFILE), mat));
    }

    // handles: a pair at the meeting slats, or one at the closing jamb
    var hW = step * 0.16, hH = H * 0.1, hy = bottom + (top - bottom) * 0.47;
    function handle(x) {
      var m = new THREE.Mesh(new THREE.BoxGeometry(hW, hH, 3.2), trim);
      m.position.set(x, hy, DEPTH + fold + 2.2);
      group.add(m);
      var shadow = new THREE.Mesh(new THREE.BoxGeometry(hW * 1.25, hH * 1.05, 0.4),
        new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.16 }));
      shadow.position.set(x + hW * 0.35, hy - hH * 0.04, DEPTH + fold + 0.4);
      group.add(shadow);
    }
    var mid = w.left + W / 2, mode = openingMode();
    if (mode === "left") handle(w.left + step * 0.55);
    else if (mode === "right") handle(w.right - step * 0.55);
    else { handle(mid - step * 0.32); handle(mid + step * 0.32); }

    window.scene.add(group);
    built = { group: group, door: mat, trim: trim };
    if (doorRGB) tintDoor();
  }

  function rebuildDoor() {
    if (!built) return;
    if (built.group.parent) built.group.parent.remove(built.group);
    built = null;
    buildDoor();
    redraw();
  }

  function tintDoor() {
    if (!built || !doorRGB) return;
    // the header and handles in the door's own colour, a shade lighter
    built.trim.color.setRGB(Math.min(1, doorRGB[0] / 255 * 1.04 + 0.03),
                            Math.min(1, doorRGB[1] / 255 * 1.04 + 0.03),
                            Math.min(1, doorRGB[2] / 255 * 1.04 + 0.03));
    built.door.map = doorTex;
    built.door.color.setRGB(1, 1, 1);
    if (!doorTex) built.door.color.setRGB(doorRGB[0] / 255, doorRGB[1] / 255, doorRGB[2] / 255);
    built.door.needsUpdate = true;
  }

  // the door's colours are Choices under the picked Door Type
  function doorColourInputs() {
    return Array.prototype.slice.call(document.querySelectorAll('input[type=radio][name^="cr_sub["]'));
  }

  function recolourDoor() {
    var img = swatchImage(pick(doorColourInputs()));
    var src = img && (img.currentSrc || img.src);
    average(img, function (rgb) {
      doorRGB = rgb || [244, 242, 236];
      if (!src) { doorTex = null; tintDoor(); redraw(); return; }
      // the swatch photo itself on every slat, so a wood grain shows as grain
      new THREE.TextureLoader().load(src, function (tex) {
        doorTex = tex;
        tintDoor();
        redraw();
      }, undefined, function () { doorTex = null; tintDoor(); redraw(); });
    });
  }


  // ------------------------------------------------------- the smart film
  /* The window's glass, frosted, laid over the room (make_smart_film.py cut
     it out of the room photo: the panes milky, the frame left clear). It
     sits on a piece of sphere round the camera covering exactly that part of
     the photo, so it lands on the panes whatever the view.

     OFF: frosted - privacy - as strongly as the Transparency picked: the
     higher the percentage the heavier the frost (93% hides the view, 89%
     still lets its shapes through), as the client sells it. ON: clear. The customer switches between them
     with the switch on the view, labelled by what they will see - Frosted
     (power off) and Clear (power on), as real smart film works - and it
     fades, as the film does. Picking a transparency switches it to Frosted,
     the state in which the transparency shows. */
  var film = { on: false, level: 1, target: 1, anim: 0 };

  function transparency() {
    var on = checked(CFG.transparency_gid);
    return on ? (CFG.transparency || {})[on.value] : 0;
  }

  function filmTarget() {
    // switched on, every film is clear, with the faintest veil of its own
    if (film.on) return 0.1;
    // switched off: the frost, full at 93%, about two thirds at 89% - enough
    // apart to see on a screen. Nothing picked yet: full frost.
    var t = transparency();
    return t ? Math.min(1, Math.max(0.5, 1 - (93 - t) * 0.08)) : 1;
  }

  function setFilm(on) {
    film.on = on;
    film.target = filmTarget();
    document.querySelectorAll(".cr-film button").forEach(function (b) {
      b.classList.toggle("on", (b.getAttribute("data-on") === "1") === on);
    });
    if (film.anim) return;
    // on a timer rather than animation frames, which stop while the page is
    // not on screen and would leave the fade half done
    var last = Date.now();
    (function step() {
      var now = Date.now(), dt = Math.min(250, now - last);
      last = now;
      var d = film.target - film.level;
      film.level += d * Math.min(1, dt / 140);
      if (Math.abs(film.target - film.level) < 0.004) film.level = film.target;
      if (built) built.film.opacity = film.level;
      redraw();
      film.anim = film.level === film.target ? 0 : window.setTimeout(step, 16);
    })();
  }

  function buildFilm() {
    var b = CFG.film_box, TWO = Math.PI * 2;
    var geo = new THREE.SphereBufferGeometry(300, 64, 64,
      b[0] / 4096 * TWO, (b[2] - b[0]) / 4096 * TWO,
      b[1] / 2048 * Math.PI, (b[3] - b[1]) / 2048 * Math.PI);
    geo.scale(-1, 1, 1);
    var mat = new THREE.MeshBasicMaterial({ transparent: true, depthWrite: false, opacity: film.level });
    new THREE.TextureLoader().load(CFG.film, function (tex) {
      tex.anisotropy = window.renderer.capabilities.getMaxAnisotropy();
      mat.map = tex;
      mat.needsUpdate = true;
      redraw();
    });
    var mesh = new THREE.Mesh(geo, mat);
    mesh.rotation.y = -Math.PI / 2;          // as the room's sphere is turned
    mesh.position.copy(window.camera.position);
    mesh.renderOrder = 5;
    var group = new THREE.Group();
    group.name = "cr_drape";
    group.add(mesh);
    window.scene.add(group);
    built = { group: group, film: mat };
  }

  function filmSwitch(host) {
    var bar = document.createElement("div");
    bar.className = "cr-film";
    var phrases = window.__crPhrases || {};
    [["0", "Frosted (OFF)"], ["1", "Clear (ON)"]].forEach(function (b) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("data-on", b[0]);
      btn.textContent = phrases[b[1]] || b[1];
      btn.addEventListener("click", function (e) {
        e.preventDefault(); e.stopPropagation();
        setFilm(b[0] === "1");
      });
      bar.appendChild(btn);
    });
    host.appendChild(bar);
    var css = document.createElement("style");
    css.textContent =
      ".cr-film{position:absolute;left:50%;top:14px;transform:translateX(-50%);z-index:5;display:flex;" +
      "background:rgba(255,255,255,.94);border-radius:999px;padding:4px;gap:4px;" +
      "box-shadow:0 2px 10px rgba(0,0,0,.14)}" +
      ".cr-film button{border:0;background:transparent;border-radius:999px;padding:8px 16px;" +
      "font:600 13px/1 inherit;color:#0f172a;cursor:pointer;white-space:nowrap}" +
      ".cr-film button.on{background:var(--brand,#09446c);color:#fff}";
    document.head.appendChild(css);
    setFilm(film.on);
  }

  function build() {
    if (KIND === "accordion") return buildDoor();
    if (KIND === "film") return buildFilm();
    var w = wall();
    var W = w.right - w.left, H = w.top - w.bottom;
    var group = new THREE.Group();
    group.name = "cr_drape";
    var tex = weave();

    function cloth(opacity) {
      var t = tex.clone();
      t.needsUpdate = true;
      return new THREE.MeshBasicMaterial({
        color: 0xffffff, vertexColors: true, map: t, side: THREE.DoubleSide,
        transparent: opacity < 1, opacity: opacity, depthWrite: opacity >= 1
      });
    }

    // the track, just under the ceiling, the full width of the wall
    var rail = new THREE.Mesh(new THREE.BoxGeometry(W, H * 0.012, 6),
      new THREE.MeshBasicMaterial({ color: 0xe9e6df }));
    rail.position.set(w.left + W / 2, w.top - H * 0.006, DEPTH + 10);
    group.add(rail);

    var hang = w.top - H * 0.012;          // under the track
    var sheerMat = cloth(0.8), blackMat = cloth(1);

    var sheer = new THREE.Mesh(
      panel(w.left + W * SHEER[0], w.left + W * SHEER[1], hang, w.bottom, DEPTH + 2,
            44, W * 0.0024, 0, 0.16),
      sheerMat);
    sheer.renderOrder = 2;
    sheer.material.map.repeat.set(44, 40);

    var left = new THREE.Mesh(
      panel(w.left + W * LEFT[0], w.left + W * LEFT[1], hang, w.bottom, DEPTH + 7,
            7, W * 0.0052, -0.3, 0.32),
      blackMat);
    var right = new THREE.Mesh(
      panel(w.left + W * RIGHT[0], w.left + W * RIGHT[1], hang, w.bottom, DEPTH + 7,
            7, W * 0.0052, 0.3, 0.32),
      blackMat);
    blackMat.map.repeat.set(14, 40);
    left.renderOrder = right.renderOrder = 3;

    group.add(sheer, left, right);
    window.scene.add(group);
    built = { group: group, sheer: sheerMat, blackout: blackMat };
  }

  /* The view. It opens on the whole wall, ceiling to floor and corner to
     corner (the bundle frames the window for a blind that fits it, which
     would cut the blackout curtains off). From there the customer zooms in -
     wheel, pinch or the buttons - out as well as in, and drags to look
     around the room.
     The camera only turns where it stands: moving it would pull the room
     photo apart. The bundle's own orbit control is switched off here for the
     same reason. */
  var view = { fit: 0, fov: 0, yaw: 0, pitch: 0, aspect: 0 };
  // the view opens at least this wide - the other product pages' 75 degrees
  // - so the room is seen as a room, not a close-up of the photo
  var OPEN_FOV = CFG.open_fov || 0;
  // zoom: in to a third of the opening view, out to a wide-angle look
  var MIN_FOV = 18, MAX_FOV = 105;
  // looking around: this far either way, at any zoom
  var MAX_YAW = 70 * Math.PI / 180, MAX_PITCH = 35 * Math.PI / 180;

  function fitFov(cam) {
    var w = wall(VIEW), dist = cam.position.z - DEPTH;
    var tanX = Math.max(Math.abs(w.left - cam.position.x), Math.abs(w.right - cam.position.x)) / dist;
    var tanY = Math.max(Math.abs(w.top - cam.position.y), Math.abs(w.bottom - cam.position.y)) / dist;
    var fit = 2 * Math.atan(Math.max(tanX / (cam.aspect || 1), tanY) * 1.04) * 180 / Math.PI;
    return Math.min(MAX_FOV, Math.max(fit, OPEN_FOV));
  }

  function aim() {
    var cam = window.camera;
    if (!cam || !view.fit) return;
    view.fov = Math.min(MAX_FOV, Math.max(Math.min(MIN_FOV, view.fit), view.fov || view.fit));
    view.yaw = Math.max(-MAX_YAW, Math.min(MAX_YAW, view.yaw));
    view.pitch = Math.max(-MAX_PITCH, Math.min(MAX_PITCH, view.pitch));
    cam.fov = view.fov;
    cam.updateProjectionMatrix();
    // The bundle points its camera straight ahead again on every frame, so
    // the room is turned instead - about the camera's own position, which
    // looks exactly the same as turning the camera.
    var q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-view.pitch, view.yaw, 0, "XYZ"));
    window.scene.quaternion.copy(q);
    window.scene.position.copy(cam.position).sub(cam.position.clone().applyQuaternion(q));
    window.scene.updateMatrixWorld(true);
    redraw();
  }

  function frame() {
    var cam = window.camera;
    if (!cam || !cam.isPerspectiveCamera) return;
    if (window.controls && window.controls.enabled) window.controls.enabled = false;
    var fit = fitFov(cam);
    if (Math.abs(fit - view.fit) > 0.01 || cam.aspect !== view.aspect) {
      // first time, or the page was resized: keep the zoom as a ratio
      var ratio = view.fit ? view.fov / view.fit : 1;
      view.fit = fit;
      view.aspect = cam.aspect;
      view.fov = fit * ratio;
      aim();
    } else if (Math.abs(cam.fov - view.fov) > 0.01) {
      aim();                // something else moved the camera: put it back
    }
    controlsOnce();
  }

  function zoomBy(factor) {
    view.fov = view.fov / factor;
    aim();
  }

  var wired = false;
  function controlsOnce() {
    if (wired || !window.renderer) return;
    var canvas = window.renderer.domElement, host = canvas.parentNode;
    if (!host) return;
    wired = true;

    // + / - / back to the whole wall
    if (getComputedStyle(host).position === "static") host.style.position = "relative";
    var bar = document.createElement("div");
    bar.className = "cr-zoom";
    [["+", "Zoom in", function () { zoomBy(1.25); }],
     ["−", "Zoom out", function () { zoomBy(1 / 1.25); }],
     ["↺", "Whole view", function () { view.fov = view.fit; view.yaw = view.pitch = 0; aim(); }]]
      .forEach(function (b) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = b[0];
        btn.title = b[1];
        btn.setAttribute("aria-label", b[1]);
        btn.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); b[2](); });
        bar.appendChild(btn);
      });
    host.appendChild(bar);
    if (KIND === "film") filmSwitch(host);
    var css = document.createElement("style");
    css.textContent =
      ".cr-zoom{position:absolute;right:12px;top:12px;z-index:5;display:flex;flex-direction:column;" +
      "gap:6px}.cr-zoom button{width:36px;height:36px;border-radius:50%;border:1px solid rgba(0,0,0,.08);" +
      "background:rgba(255,255,255,.92);color:#0f172a;font-size:19px;line-height:1;cursor:pointer;" +
      "box-shadow:0 2px 8px rgba(0,0,0,.12);padding:0}.cr-zoom button:hover{background:#fff}";
    document.head.appendChild(css);

    // the wheel zooms the curtain, not the page, while over the picture
    canvas.addEventListener("wheel", function (e) {
      e.preventDefault();
      zoomBy(Math.exp(-e.deltaY * 0.0015));
    }, { passive: false });

    // drag to look around; two fingers pinch to zoom.
    // Vertical one-finger swipes still scroll the page on a phone.
    canvas.style.touchAction = "pan-y";
    var pts = {}, last = null, pinch = 0;
    function spread() {
      var p = Object.keys(pts).map(function (k) { return pts[k]; });
      return p.length < 2 ? 0 : Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
    }
    canvas.addEventListener("pointerdown", function (e) {
      pts[e.pointerId] = { x: e.clientX, y: e.clientY };
      last = { x: e.clientX, y: e.clientY };
      pinch = spread();
      try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* old browsers */ }
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!pts[e.pointerId]) return;
      pts[e.pointerId] = { x: e.clientX, y: e.clientY };
      if (Object.keys(pts).length >= 2) {
        var now = spread();
        if (pinch && now) zoomBy(now / pinch);
        pinch = now;
        return;
      }
      var perPx = view.fov * Math.PI / 180 / (canvas.clientHeight || 400);
      view.yaw -= (e.clientX - last.x) * perPx;
      if (e.pointerType === "mouse") view.pitch += (e.clientY - last.y) * perPx;
      last = { x: e.clientX, y: e.clientY };
      aim();
    });
    function up(e) {
      delete pts[e.pointerId];
      pinch = spread();
      var rest = Object.keys(pts)[0];
      last = rest ? pts[rest] : null;
    }
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);
  }

  /* What stands in front of the curtain - the sofa's arm, the olive tree and
     its pot. The room is one photo around the camera, so the curtain covers
     them too. Those pixels of the photo are drawn again nearer the camera,
     through a mask (make_sheer_mask.py): a copy of the room's sphere shrunk
     towards the camera, which the camera sees exactly as it sees the room. */
  var front = null;
  var MASK = CFG.hasOwnProperty("mask") ? CFG.mask
    : "/assets/kayan_curtain/image/sheer-curtain-front.png";
  var version = (function () {
    var me = document.currentScript && document.currentScript.src || "";
    var m = me.match(/[?&]v=(\d+)/);
    return m ? "?v=" + m[1] : "";
  })();

  function inFront() {
    if (!MASK) return;
    var room = null;
    window.scene.children.forEach(function (o) { if (o.name === "mesh3d") room = o; });
    if (!room || !room.material || !room.material.map || !room.material.map.image) return;
    if (!front) {
      var mask = new THREE.TextureLoader().load(MASK + version, redraw);
      front = new THREE.Mesh(room.geometry, new THREE.MeshBasicMaterial({
        map: room.material.map, alphaMap: mask, transparent: true, depthWrite: false,
        side: room.material.side
      }));
      front.name = "cr_drape_front";
      front.renderOrder = 10;
    }
    if (front.material.map !== room.material.map) front.material.map = room.material.map;
    if (front.parent !== window.scene) window.scene.add(front);
    // the room's sphere, shrunk towards the camera to well inside the curtain
    var cam = window.camera.position;
    room.updateMatrixWorld(true);
    if (!room.geometry.boundingSphere) room.geometry.computeBoundingSphere();
    var radius = room.geometry.boundingSphere.radius * room.scale.x;
    var k = 120 / radius;
    front.position.copy(cam).add(room.position.clone().sub(cam).multiplyScalar(k));
    front.quaternion.copy(room.quaternion);
    front.scale.copy(room.scale).multiplyScalar(k);
  }

  // -------------------------------------------------------- the blind away
  function hideBlind() {
    window.scene.children.forEach(function (o) {
      if (o.name === "mesh_group" || /_text_Mesh$/.test(o.name || "")) {
        if (o.visible) o.visible = false;
      }
    });
  }

  // --------------------------------------------------------------- colours
  var averages = {};

  function average(img, done) {
    var src = img && (img.currentSrc || img.src);
    if (!src) return done(null);
    if (averages[src]) return done(averages[src]);
    function measure() {
      try {
        var c = document.createElement("canvas");
        c.width = c.height = 16;
        var x = c.getContext("2d");
        x.drawImage(img, 0, 0, 16, 16);
        var d = x.getImageData(0, 0, 16, 16).data, r = 0, g = 0, b = 0, n = 0;
        for (var i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
        averages[src] = [r / n, g / n, b / n];
        done(averages[src]);
      } catch (e) { done(null); }
    }
    if (img.complete && img.naturalWidth) measure();
    else {
      img.addEventListener("load", measure, { once: true });
      img.addEventListener("error", function () { done(null); }, { once: true });
      img.loading = "eager";
    }
  }

  function swatchImage(input) {
    if (!input) return null;
    var row = input.closest("label, .swatch-card, .cr-sub-swatch") || input.parentNode;
    return row && row.querySelector("img");
  }

  function sheerInputs() {
    // the Sheer Colour step: the page's own swatch tray
    return Array.prototype.filter.call(
      document.querySelectorAll('.swatches-scroll-tray input[type=radio][name^="option["]'),
      function (i) { return !i.disabled; });
  }

  function blackoutInputs() {
    return Array.prototype.slice.call(
      document.querySelectorAll('input[type=radio][name^="cr_sub["][name*="blackout"]'));
  }

  function pick(list) {
    var on = list.filter(function (i) { return i.checked; })[0];
    if (on) return on;
    // nothing picked yet: show the first one on offer
    return list.filter(function (i) {
      var row = i.closest(".swatch-card, .cr-sub-swatch");
      return !row || row.style.display !== "none";
    })[0] || null;
  }

  function tint(material, rgb, fallback) {
    var c = rgb || fallback;
    material.color.setRGB(c[0] / 255, c[1] / 255, c[2] / 255);
    material.needsUpdate = true;
  }

  function recolour() {
    if (!built) return;
    if (KIND === "accordion") return recolourDoor();
    if (KIND === "film") return setFilm(film.on);
    average(swatchImage(pick(sheerInputs())), function (rgb) {
      // a sheer is never darker than its photo looks: light comes through it
      if (rgb) rgb = rgb.map(function (v) { return Math.min(255, v * 1.04 + 6); });
      tint(built.sheer, rgb, DEFAULT_SHEER);
      redraw();
    });
    average(swatchImage(pick(blackoutInputs())), function (rgb) {
      tint(built.blackout, rgb, DEFAULT_BLACKOUT);
      redraw();
    });
  }

  function redraw() {
    try {
      if (window.renderer && window.camera && window.scene) window.renderer.render(window.scene, window.camera);
    } catch (e) { /* the bundle's own loop draws anyway */ }
  }

  document.addEventListener("change", function (e) {
    var t = e.target;
    if (!t || !t.name) return;
    // a transparency shows in the frost: picking one shows the film off
    if (KIND === "film" && t.name === "option[" + CFG.transparency_gid + "]") return setFilm(false);
    if (KIND === "accordion" && (t.name === "option[" + CFG.opening_gid + "]" ||
                                 t.name === "option[" + CFG.type_gid + "]")) rebuildDoor();
    if (/^option\[/.test(t.name) || /^cr_sub\[/.test(t.name)) recolour();
  }, true);

  // ------------------------------------------------------------------ go
  var tries = 0, lastBlackout = null;
  var timer = setInterval(function () {
    try {
      if (!window.scene || !window.camera) { if (++tries > 150) clearInterval(timer); return; }
      hideBlind();          // the bundle shows its blind again when it rebuilds
      if (!built) { build(); recolour(); }
      // the bundle starts a new scene of its own as it loads - follow it
      if (built.group.parent !== window.scene) window.scene.add(built.group);
      inFront();
      frame();
      // the blackout swatches - or the door's colours - arrive with the
      // page's choices, after us, and are rebuilt when the door type changes
      var list = KIND === "accordion" ? doorColourInputs() : blackoutInputs();
      var sig = list.map(function (i) { return i.value; }).join(",");
      if (sig !== lastBlackout) { lastBlackout = sig; recolour(); }
    } catch (e) {
      if (window.console) console.warn("[kayan] drape", e);
    }
  }, 300);
})();
