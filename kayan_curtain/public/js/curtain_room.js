/* A room picture the team chose for a product, with the blind fitted to it.

   In Curtain Product -> 3D Room the team uploads a 360-degree room picture
   and drags a box over its window. The server then puts, ahead of the 3D
   bundle on that product's page,

       window.CR_ROOM = { url: "...", box: [left, top, right, bottom], anchor: -425 }

   (the box as fractions of the picture) and this script. It does three things:

     * hands the bundle that picture instead of the room it would load - its
       own (".../scenebk.jpg"), or a Kayan page's room ("/maps/scenes/...");
     * fits the blind to the marked box: the box's edges are turned into
       directions from the camera, met at the blind's own depth, and the blind
       is scaled and moved until its main parts fill that rectangle. It is
       measured, not computed from the model's nominal size, so it lands the
       same on every product;
     * keeps the size labels on their arrows, and the room's sphere pushed
       out so it cannot eat a larger blind's corners.

   Mounting: every model brings the blind nearer the camera for Outside. At
   the depth the page opens with (`anchor`) the blind fills the box; nearer
   than that it is made a little bigger, over the window, as an outside-
   mounted blind is.

   Pages without a chosen room never load this file and behave as before. */
(function () {
  "use strict";
  var cfg = window.CR_ROOM;
  if (!cfg || !cfg.url || !cfg.box || cfg.box.length !== 4 || !window.THREE) return;

  var THREE = window.THREE;
  var GROW = [1.10, 1.08];            // Outside: this much bigger than the box
  // hanging parts - chains, cords, pull strings - are not the blind's extent
  var HANGING = /^(Arrow_|.*Puller|Thread|Strings?$|Chain)/;

  // ---------------------------------------------------------- the picture
  function redirect(proto) {
    if (!proto || proto.__crRoomOverride) return;
    var load = proto.load;
    if (typeof load !== "function") return;
    proto.load = function (url) {
      if (typeof url === "string" &&
          (url.indexOf("scenebk") !== -1 || url.indexOf("/maps/scenes/") !== -1)) {
        arguments[0] = cfg.url;
      }
      return load.apply(this, arguments);
    };
    proto.__crRoomOverride = true;
  }
  ["ImageLoader", "TextureLoader", "FileLoader", "CubeTextureLoader", "ImageBitmapLoader"]
    .forEach(function (name) { if (THREE[name]) redirect(THREE[name].prototype); });

  // ------------------------------------------------------------- geometry
  function group() {
    var g = null;
    (window.scene && window.scene.children || []).forEach(function (o) {
      if (o.name === "mesh_group") g = o;
    });
    return g;
  }

  function mainBox(g) {
    var box = new THREE.Box3(), found = false;
    g.traverse(function (o) {
      if (!o.isMesh || !o.visible || HANGING.test(o.name || "")) return;
      for (var p = o; p && p !== g; p = p.parent) if (!p.visible) return;
      box.expandByObject(o);
      found = true;
    });
    return found ? box : null;
  }

  /* Where the picture's point (u, v) - fractions across and down - is seen,
     at depth z. The room is a sphere around the camera with the picture's
     centre dead ahead, so a fraction is a longitude and a latitude. */
  function at(u, v, z) {
    var cam = window.camera.position;
    var lon = (u - 0.5) * 2 * Math.PI, lat = (0.5 - v) * Math.PI;
    var d = new THREE.Vector3(Math.sin(lon) * Math.cos(lat), Math.sin(lat),
                              -Math.cos(lon) * Math.cos(lat));
    if (Math.abs(d.z) < 1e-6) return null;
    var t = (z - cam.z) / d.z;
    return t > 0 ? cam.clone().add(d.multiplyScalar(t)) : null;
  }

  function target(z) {
    var l = cfg.box[0], t = cfg.box[1], r = cfg.box[2], b = cfg.box[3];
    var um = (l + r) / 2, vm = (t + b) / 2;
    var L = at(l, vm, z), R = at(r, vm, z), T = at(um, t, z), B = at(um, b, z);
    if (!L || !R || !T || !B) return null;
    return { left: L.x, right: R.x, top: T.y, bottom: B.y };
  }

  // ------------------------------------------------------------------ fit
  var anchor = typeof cfg.anchor === "number" ? cfg.anchor : null;

  function fit() {
    if (!window.scene || !window.camera) return;
    var g = group();
    if (!g || !g.children.length) return;
    if (anchor === null) anchor = g.position.z;     // the depth it opened with
    g.updateMatrixWorld(true);
    var box = mainBox(g);
    if (!box || !isFinite(box.max.x)) return;

    var want = target(box.max.z);
    if (!want) return;
    if (g.position.z > anchor + 1) {                // Outside: over the window
      var w = want.right - want.left, h = want.top - want.bottom, cx = (want.left + want.right) / 2;
      var w2 = w * GROW[0], h2 = h * GROW[1];
      want.left = cx - w2 / 2; want.right = cx + w2 / 2;
      want.top += (h2 - h) / 2; want.bottom = want.top - h2;
    }

    var changed = false;
    var fx = (want.right - want.left) / (box.max.x - box.min.x);
    var fy = (want.top - want.bottom) / (box.max.y - box.min.y);
    // the group is turned -90 degrees about X: its x is across, its z is up
    if (isFinite(fx) && Math.abs(fx - 1) > 0.002) { g.scale.x *= fx; changed = true; }
    if (isFinite(fy) && Math.abs(fy - 1) > 0.002) { g.scale.z *= fy; changed = true; }
    if (changed) { g.updateMatrixWorld(true); box = mainBox(g); }

    var dx = (want.left + want.right) / 2 - (box.min.x + box.max.x) / 2;
    var dy = want.top - box.max.y;
    if (Math.abs(dx) > 0.05 || Math.abs(dy) > 0.05) {
      g.position.x += dx; g.position.y += dy;
      g.updateMatrixWorld(true);
      changed = true;
    }
    if (labels(g)) changed = true;
    if (changed && window.renderer) window.renderer.render(window.scene, window.camera);
  }

  // the size labels follow their arrows (the bundle places them for its own,
  // unmoved blind)
  function labels(g) {
    var moved = false;
    function arrow(name) {
      var a = null;
      g.traverse(function (o) { if (!a && o.name === name && o.visible) a = o; });
      return a ? new THREE.Box3().setFromObject(a) : null;
    }
    function shift(name, ab, tx, ty) {
      var t = null;
      window.scene.children.forEach(function (o) { if (o.name === name) t = o; });
      if (!t || !t.visible) return;
      var b = new THREE.Box3().setFromObject(t);
      if (!isFinite(b.min.x)) return;
      var dx = tx(b), dy = ty(b), dz = (ab.max.z + 0.5) - b.min.z;
      if (Math.abs(dx) > 0.05 || Math.abs(dy) > 0.05 || Math.abs(dz) > 0.05) {
        t.position.x += dx; t.position.y += dy; t.position.z += dz;
        t.updateMatrixWorld(true);
        moved = true;
      }
    }
    var top = arrow("Arrow_Top"), left = arrow("Arrow_Left");
    if (top) shift("horizontal_text_Mesh", top,
      function (b) { return (top.min.x + top.max.x) / 2 - (b.min.x + b.max.x) / 2; },
      function (b) { return top.max.y + 2 - b.min.y; });
    if (left) shift("vertical_text_Mesh", left,
      function (b) { return left.min.x - 2 - b.max.x; },
      function (b) { return (left.min.y + left.max.y) / 2 - (b.min.y + b.max.y) / 2; });
    return moved;
  }

  // the room sphere pushed out, so a larger blind's corners stay in front of it
  function push() {
    if (!window.scene || !window.camera) return;
    var room = null;
    window.scene.children.forEach(function (o) { if (o.name === "mesh3d") room = o; });
    if (!room || room.__crPushed) return;
    room.scale.multiplyScalar(4);
    room.updateMatrixWorld(true);
    room.__crPushed = true;
    if (room.geometry) {
      room.geometry.computeBoundingSphere();
      var reach = room.geometry.boundingSphere.radius * room.scale.x * 1.3;
      if (window.camera.far < reach) {
        window.camera.far = reach;
        window.camera.updateProjectionMatrix();
      }
    }
  }

  setInterval(function () {
    try { push(); fit(); } catch (e) { if (window.console) console.warn("[kayan] room fit", e); }
  }, 400);
})();
