/* A room to hang something in, without a product's 3D bundle.

   The Sheer Curtain and the Accordion Door draw their own product
   (curtain_drape.js). They only ever borrowed the Vertical blind's bundle for
   the room, the camera and the renderer - and that bundle is 40 MB, plus the
   blind's own textures, all downloaded to be hidden. This is the part they
   used: the room photo on a sphere round the camera, a camera, a renderer,
   and a drawing loop.

   It provides what the rest of the page expects from a bundle:
     window.scene / camera / renderer  - curtain_drape.js, the size and colour
                                         scripts, and Add to Cart's picture of
                                         the view (hence preserveDrawingBuffer)
     window.modelchanger               - the installation choices call it
   The room is named "mesh3d", as the bundles name theirs.

   The page says which room with data-room on this script's tag. */
(function () {
  "use strict";
  if (!window.THREE) return;
  var THREE = window.THREE;
  var me = document.currentScript;
  var ROOM = me && me.getAttribute("data-room");
  var host = document.getElementById("c");
  if (!ROOM || !host) return;

  // the installation pills and the like still announce themselves to a bundle
  if (typeof window.modelchanger !== "function") window.modelchanger = function () {};

  var renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  var camera = new THREE.PerspectiveCamera(75, 1, 1, 5000);
  camera.position.set(0, 0, 0);
  var scene = new THREE.Scene();
  window.renderer = renderer;
  window.camera = camera;
  window.scene = scene;

  function size() {
    var w = host.clientWidth || 600, h = host.clientHeight || 600;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }

  /* The photo on the inside of a sphere centred on the camera, its middle
     dead ahead (-z) - the bundles' layout, which curtain_drape.js measures
     against. */
  new THREE.TextureLoader().load(ROOM, function (tex) {
    tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    var geo = new THREE.SphereBufferGeometry(1920, 96, 64);
    geo.scale(-1, 1, 1);
    var room = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: tex }));
    room.name = "mesh3d";
    room.rotation.y = -Math.PI / 2;
    scene.add(room);

    // the canvas goes in only now, so the page's loader stays up until
    // there is a room to see (it hides itself once #c holds a canvas)
    host.appendChild(renderer.domElement);
    size();
    if (window.ResizeObserver) new ResizeObserver(size).observe(host);
    else window.addEventListener("resize", size);
    (function loop() {
      renderer.render(scene, camera);
      window.requestAnimationFrame(loop);
    })();
  });
})();
