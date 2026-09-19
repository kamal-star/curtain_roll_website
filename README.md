# Curtain Roll

The Curtain Roll storefront as an installable Frappe/ERPNext app: a home page,
9 curtain product pages, and the 3D curtain configurator.

```bash
bench get-app /path/to/curtain_roll
bench --site <site> install-app curtain_roll
bench build --app curtain_roll
```

Installing points the site's home page at the storefront and creates an Item
per curtain type. Uninstalling hands the home page back.

## Routes

| Route | Page |
|---|---|
| `/` | Home — category cards |
| `/printed` `/blackout` `/sunscreen` `/zebra` `/wooden` `/vertical` `/metal` `/roman` | Product + 3D configurator |
| `/wavy` | Product (no configurator) |

## How the configurator is wired in

The per-product bundles are **obfuscated and cannot be edited**, so the app
reproduces the exact contract they expect rather than adapting them:

| The bundle needs | Provided by |
|---|---|
| `#c` mount point and `.model-loader` | `templates/includes/product_body.html` |
| global `modelchanger(group, imageUrl, code, $el)` | the bundle itself; swatches call it via `public/js/curtain_configurator.js` |
| jQuery (it calls `$(this)`) | Frappe's `base_scripts`, which renders before the `script` block |
| textures at `/maps/preload/<product>/…` | `www/maps/` — see below |
| its render target `#input-option<N>` | the `.cr-capture` input |

### Why textures live in `www/` and scripts live in `public/`

Frappe's static page renderer lists `js` in `UNSUPPORTED_STATIC_PAGE_TYPES`, so
`.js` **cannot** be served from `www/`. The bundles therefore sit in `public/`
and are referenced as `/assets/curtain_roll/…`, which we control.

The texture paths are the opposite case: they are hardcoded *inside* the
obfuscated bundles as site-root paths, so they must answer at `/maps/preload/…`.
`www/` does serve binary files, so the textures live there.

This is also why **product routes must be a single path segment** (`/blackout`,
never `/products/blackout`) — the bundles resolve textures relative to the page.
It happily matches the original site's SEO URLs.

## Ordering

Add to cart on a product page writes to a **draft Quotation** with
`order_type = "Shopping Cart"`, one per signed-in customer. A guest who clicks
it is sent to login first. The line carries every option the customer picked,
the price breakdown, and the 3D render as an attachment. `/cart` lists the
lines with qty / remove / Place Order, which submits the Quotation.

Each page also carries a **Request a quote** form posting to
`curtain_roll.api.submit_quote`, which creates a **Lead** instead - for
visitors who want a call back rather than a cart.

## Pricing from the desk

Rates are **not** in the code. Each curtain type has a **Curtain Product**
record (search "Curtain Product" in the desk), named after its route:

| Section | What the team sets |
|---|---|
| Base Price | `Per Square Meter` or `Per Piece`, the rate, and the minimum billable area |
| Size Slabs | optional: a different rate for a range of m2, which replaces the base rate |
| Colours | every swatch on the page, each with **Show on site** and its own surcharge |
| Options | Control type, Mounting, Valance box, Installation service ... each with a surcharge |

Every row is charged as **Fixed Amount**, **Per Square Meter**, **Per Metre of
Width**, **Per Metre of Height** or **Percent of Base**; a colour may also
**Override Base Rate**. The area comes from the width and height the customer
types, in cm: `width x height / 10000`.

### Price Driven By

| Mode | What sets the fabric price |
|---|---|
| **Base Rate** | the product's Base Rate. Colours only add or subtract. |
| **Material Rate** | each colour carries its own per-square-metre price, and that IS the fabric price. |

Material Rate is the mode the business actually asked for: a rate per m2 per
fabric, with the options added on top.

### Minimum Order Price

The least the **fabric** can cost, however small the curtain. Motor, box,
handle and installation are added **on top** of it, so a small curtain with a
motor is `minimum + motor`, not `max(minimum, everything)`.

```
100 x 120 cm = 1.20 m2 x 120/m2 = 144   ->  below the 150 minimum, so 150
  + motor                                                            350
  + box, 1.00 m of width x 60/m                                       60
  + installation                                                       80
                                                                    ------
                                                                       640
```

### Installation Tiers

Installation is charged per curtain, but the band is chosen by the **total
number of curtains on the order** - three blackout plus three wooden counts as
six. Fill in the Installation Tiers table, then tick **Price From Tiers** on
the installation choice in the Options table.

That has a consequence worth understanding: **a line's price depends on the
other lines.** Adding a curtain re-prices the ones already in the cart, and
removing one puts them back up. So each cart line stores the options it was
configured with, in a `curtain_config` custom field on Quotation Item, and
`cart.reprice()` recomputes every curtain line whenever the cart changes. The
line's description is prose and cannot be parsed back, which is why the raw
configuration has to be kept.

The product page shows the band for **what is already in the cart plus what is
being configured**, so a visitor adding a fifth curtain sees the cheaper rate
before they commit.

### Starts From

Display only. It is what the page prints before anything is chosen and is never
part of a calculation. Leave it 0 to show the Base Rate instead.

So a 200 x 150 cm blackout at 120/m2, with a +25 colour, a +350 motor, a
+15/m2 valance box and +80 installation prices as
`120x3 + 25 + 350 + 15x3 + 80 = 860`.

**Unticking Show on site removes that colour from the page** - the swatch is
hidden and the input disabled - and the server refuses it even if the form is
tampered with.

A **Size Slab** row left blank would read as "every size, priced at nothing",
so a blank row is dropped on save and a zero-rate slab is ignored when pricing.

### Adding a colour that was never on the original site

Add a row to the **Colours** grid, type the name, upload a **Fabric Photo**,
set the price, save. The swatch appears on the product page straight away,
with working 3D - no files to place, no deploy.

One photo does both jobs, so give it a decent size (roughly square, 500 px or
more). Any format works: jpg, jpeg, png, webp.

That works because of a measured quirk of the obfuscated bundles. They do not
load the image URL they are handed - they *derive* the fabric from it: drop
`/cache`, cut at the last hyphen, put the extension back.

```
.../cache/blackout-materials/7200-150x150.jpg  ->  .../blackout-materials/7200.jpg
/files/probe-x.png                             ->  /files/probe.png
```

`pricing.texture_url()` exploits that: it appends `-x` before the extension,
so the derivation lands exactly on the uploaded file whatever it is called -
hyphens in the filename included. The page script then builds the swatch into
the material list in the theme's own markup, and wires its click to
`modelchanger`.

Such a row is flagged `is_custom`, which is what stops *Reload options from
page* and `after_migrate` from pruning it as "no longer on the page". It also
gets a generated storefront id prefixed `c`, so it can never collide with a
captured one.

Two buttons on the form do the tedious parts: *Bulk edit* sets one rate across
all 65 swatches at once, and *Reload options from page* pulls in swatches added
by a later capture without touching rates already set.

### How it reaches the page

`after_install` and `after_migrate` seed one record per type from
`data/products.json`, so the team opens a form that already lists every swatch
and option and only has to type numbers.

The live total on the product page is **not** computed in the browser. The
Journal3 theme already re-posts the whole option form to
`index.php?route=product/product/add` on every change and writes `json.total`
into `#total_price`; `pricing.price_preview` answers it. The same
`pricing.calculate` prices the quotation line, so the page and the order can
never disagree, and the browser is never trusted with a rate.

`calculate(..., strict=)` is what keeps that usable. The theme repaints the
price only when the response carries no `error`:

```js
if (json['error']) { ...show them... } else { ...repaint the price... }
```

so returning an error for a required option the customer has simply not
reached yet freezes the total on "Starts from" until the very last click. The
preview therefore runs **lenient**: unchosen options make the result
`partial`, which prints as `From SR 1,625.00`, and the prefix drops off once
everything is picked. The cart runs **strict**, so a half-configured blind is
still refused. Genuinely invalid input - a withdrawn colour, a half-filled
size - errors in both.

The theme fires that refresh on the form's `change` event, which a text box
only raises on blur, so the width and height felt dead while being typed in.
The injected script binds `input` on those two boxes as well, debounced to
450 ms.

Per-choice surcharges are written into the swatch markup as the theme's own
`.option-price` span and tooltip. The Journal3 stylesheet hides that span with
`display: none !important`, exactly as on the original site, so the figures
show on hover and in the running total. To print them under each swatch
instead, add to `public/css/curtain.css`:

```css
.product-info .option-price { display: inline !important; }
```

## Adding a product (variants)

A **variant** is a product that is physically the same blind as a captured one
- it reuses that blind's page, its obfuscated 3D bundle and its slat and
bracket textures - but is sold under its own name, at its own prices, and is
previewed in its own room. `/wooden-premium` is one, built from `/wooden`.

Define it in `curtain_roll/data/variants.json`:

```json
{
  "key": "wooden-premium",
  "based_on": "wooden",
  "product_id": "901",
  "heading": "Wooden Premium",
  "title": "Wooden slat blinds shown in a modern apartment",
  "scene_source": "scenes/wooden-premium.jpg",
  "price": 300.0
}
```

then, from the parent directory:

```bash
python make_variants.py     # room image + products.json + catalog_ids.json
python port_pages.py        # the page itself
bench --site <site> migrate # Item + Curtain Product record
```

`after_migrate` creates the Item and seeds a Curtain Product record, so the new
product arrives with all its colours and options listed and is priced entirely
independently of the blind it came from.

### The room

Each configurator loads its room from `/maps/preload/<product>/scenebk.jpg`, an
**equirectangular 4096x2048** panorama, and that path is assembled inside
obfuscated code. In most bundles the filename is not even a literal, so it
cannot be string-replaced.

A variant therefore does not copy the bundle or the texture folder. The
generated page injects a short script **above** the bundle's `<script>` tag
that wraps THREE's loaders and redirects any request for `scenebk` to
`/maps/scenes/<key>.jpg`. Whatever the bundle builds, it hands THREE a finished
URL, so the intercept catches it however it was assembled - and only the room
moves. The slat and bracket textures still come from the base product's folder,
which is the whole point of a variant.

`make_variants.py` resizes the supplied panorama to 4096x2048 and warns if the
source is not 2:1 or is smaller than the captured rooms - a 360 panorama that
is not exactly 2:1 shows a pinched ceiling and a visible seam.

### Fitting a room to the blind: `window`

The blind **cannot be moved or resized** - it is geometry at a fixed distance
from a fixed camera, compiled into the bundle. So the room is fitted to it.

Measure the window in the supplied image and give its outer frame in that
image's own pixels:

```json
"window": [857, 357, 1122, 640]
```

Everything else follows. `make_variants.py` scales the room uniformly until
that window is as wide as the one in the product's **own** captured room, then
pins the window's **top edge**.

### Why the top, and not the centre

A blind hangs from a headrail fixed at the top of the window. It does not float
in the middle of it. In the wooden room the blind's own geometry puts its box
at (1837, 788)-(2234, 1179) and the window is (1838, 785)-(2262, 1215): the
**top edges are flush to within 3 px**, and the window carries on below the
blind. Matching the two centres instead - which this used to do - drops the
blind by half that overhang, and it reads immediately as a blind hung too low.

Width is what decides whether the blind covers the glass, so that is what the
scale is matched on; the leftover height shows below the blind, which is where
a window is supposed to show. The supplied room fits wooden at x1.280, leaving
3.9 degrees of window below the blind - the reference room has 3.9.

`scene_fit` can match on `height` or `uniform` instead, or `none` to skip
scaling, but `width` is the default for this reason.

### The blind is not one fixed size

Mounting changes it. Measured on the vertical blind:

| Mounting | Blind |
|---|---|
| Inside (the default) | 54.4 x 52.8 deg |
| **Outside** | **61.2 x 59.4 deg** - 12% bigger |

That is the bundle's own behaviour, and the captured rooms live with it: in the
vertical room an Outside mount already sits 2.6 deg past each side of the window
and 5.5 deg above it, which is what an outside mount looks like. Fit a room to
the **default** state and accept that Outside overhangs.

The typed width and height, incidentally, do **not** change the model at all.

### Do not scale the room

**A panorama can be rotated. It cannot be zoomed.**

Rotating an equirectangular image is a real rotation of the sphere, so every
straight line in the room stays straight. Scaling one stretches longitude and
latitude linearly, which is not a camera move and not any other rigid
transformation - so straight lines come out bowed.

The maths is unforgiving. A straight horizontal line at elevation `p0` renders
straight only when

    z * sin(2*p0) = sin(2*p0 / z)

which holds only at `z = 1`. At `z = 1.28`, with a cornice 20 degrees above eye
level, the curvature comes out **59% too strong**. The client spotted it
immediately: a ceiling line that sagged in the middle.

So `scene_fit` defaults to **none**. `width`, `height` and `uniform` still
exist, but every one of them bends the room, and the bend grows with the
distance from 1 and with how far the line sits from eye level. Use them only as
a stopgap, and only at small factors.

### Scale the blind instead

The room cannot be scaled, but the **blind** can. It is real geometry, so
widening it distorts nothing at all.

`blind_scale()` works out one factor per axis: the blind keeps the same share
of the window it has in its own captured room. Wooden fills 94% of its window's
width and 91% of its height; vertical 97% and 110%, because a vertical blind
hangs past the bottom of its window.

Against this room's 47.7 x 49.0 deg window:

| | Width | Height | Lands at |
|---|---|---|---|
| wooden | x1.307 | x1.324 | 44.7 x 44.5 deg |
| vertical | x0.832 | x1.028 | 46.3 x 54.1 deg |

Both factors are baked into the page and applied by a watcher in the injected
script.

Three things that took a few goes to get right:

* **The group already carries a scale** - 0.23 on wooden. Setting it rather
  than multiplying it made the blind three times too big.
* **Height goes on `scale.z`, not `scale.y`.** The group is rotated -90 degrees
  about X, so its local Z is world UP and its local Y is depth. Setting
  `scale.y` therefore only makes the blind thicker, which is why it looked like
  vertical scaling "did not take" - the bounding box never moved. Scaling
  `scale.z` works exactly as expected.
* **Aim the headrail at the window's ANGLE, not at its last position.** Pinning
  it to wherever it was a moment ago looks equivalent and is not: changing the
  mounting resets the bundle's scale but *not* its position, so the correction
  made for the previous scale is left behind and the next one stacks on it.
  After a couple of Inside/Outside clicks the blind had walked off the window.
  The page therefore carries the window's own top and centre angles
  (`WINDOW_TOP_DEG`, `WINDOW_CX_DEG`) and aims at those, which cannot drift
  however many times the model is rebuilt. Measured over four switches: top
  21.01 deg and centre 0.18 deg every time.
* **Derive the scale from the bundle's base, never from your own last output.**
  Multiplying what is already there compounds. The bundle resets `scale.x` when
  the mounting changes but never touches `scale.z` again after building the
  model, so a factor applied to `scale.z` landed on top of itself on every
  rebuild: 0.3046, then 0.4034, then 0.7076, with the slats stretching from
  17.5 units to 23.2 and the blind visibly changing shape. `scale.y` is the
  anchor - the bundle sets the group uniformly when it builds it and then only
  drives width, through `scale.x`.
* **The bundle changes the scale itself** when the mounting option changes -
  0.23 to 0.27 on wooden, so Outside is deliberately bigger. The watcher
  re-applies the factor on top of whatever it finds, which keeps that
  behaviour: Outside ends up 1.24x the window's width where the original is
  1.26x. It waits for the value to hold still for a tick first, because
  changing mounting rebuilds the model over several frames and multiplying a
  moving value compounds the factor.

### Which means the window's size has to be right in the render

It is the one thing that cannot be corrected afterwards. The window must
already subtend the right angle, which is a matter of how far the camera stands
from it:

    distance = (window width / 2) / tan(target angle / 2)

The supplied room's window is 47.7 degrees. Wooden needs 37.3, so that room
would have to be re-rendered from **1.31x the distance** - about 3.9 m instead
of 3 m. Vertical needs 56.1, so the opposite: **0.83x**, about 2.5 m.

One room cannot suit both. Either the client renders one per product, or picks
a distance that suits the product it is for.

## Flat products - adding a product with no 3D bundle

The eight captured products each ship a compiled, obfuscated three.js app with
the geometry welded inside, 9 to 50 MB apiece, and there is no way to author a
ninth. A **flat product** sidesteps that entirely: the room is an ordinary
picture and each colour is a transparent PNG laid over it.

`/shutters` was built this way first and then moved to 3D - the flat version
worked, but it did not match the other eight, which are real 3D. It is now a
normal variant of blackout: that blind is already a solid flat panel with a box
above it, which is what a closed roller shutter is, so a slat texture as its
material gives a 3D shutter that rolls, re-lights and responds to the mounting
and control options like every other product.

The flat type stays because it is the only route for a product with no
comparable bundle. Mark one in `data/variants.json`:

```json
{
  "key": "shutters",
  "based_on": "blackout",
  "flat": true,
  "product_id": "903",
  "heading": "Shutters",
  "room_source": "scenes/shutters-room.jpg"
}
```

`based_on` still supplies the page shell - header, nav, the option accordion,
the cart - but the bundle's `<script>` tag is replaced by a compositor instead
of having a room injected above it.

### How it stands in for the bundle

The theme calls three things the bundle used to provide, so the compositor
provides them:

| | |
|---|---|
| `modelchanger(group, url, code, $el)` | every swatch calls this on click |
| `renderer.domElement` | add-to-cart reads `.toDataURL()` off it for the quotation |
| `resetScean()` | called just before that capture |

Because `modelchanger` keeps its signature, the swatches drive it without
knowing anything changed - including the ones the pricing script injects from
the desk. It only acts on the **material** group, though: every other group
passes its own little icon, and painting a 150 px "Manual" icon across the room
is exactly what it did until that filter went in. The canvas is 2D, so it is never tainted and the capture always
works; a WebGL canvas needs `preserveDrawingBuffer` for that.

Two things that caught me out:

* **`#c` is a flex child** and stretches to the height of the options column
  beside it - 2245 px on a full page - so its own height says nothing about how
  tall the picture should be. The canvas takes the room image's proportions
  instead, which lands on 601 x 768, the same as the bundle's.
* **No `-x` on the texture URL.** `texture_url()` appends it to survive the
  obfuscated loaders mangling the path; a flat product loads exactly the URL it
  is handed, so `_color_entry()` skips the trick when the product is flat.

### Why this is the better route

It is sharper. A 360 panorama spends **83% of its width** on parts of the room
the camera never shows; here every pixel of the file lands on screen.

It is also the conclusion the client's own newer site reached: kayancurtain.com
runs A-Frame with an `<a-sky>` room and **twelve flat PNGs** for the blind, at
2088 x 2000. No 3D model at all.

### What a flat product needs

* a room picture - `flatten_room.py` will pull one out of a panorama if that is
  all there is, by gnomonic projection, so straight lines stay straight
* one transparent PNG per colour, **on the room's own canvas** so overlaying is
  exact, uploaded against each row of the Colours table

Everything else - options, pricing, cart, quotation - is unchanged.

### Every product needs its own reference### Every product needs its own reference

The blinds are not the same size, so the windows built around them are not
either:

| | Blind | Its room's window |
|---|---|---|
| wooden | 34.9 x 34.3 deg | 37.3 x 37.8 deg, top at 0.3833 |
| vertical | 54.4 x 52.8 deg | 56.1 x 47.8 deg, top at 0.3652 |

Fitting against the wrong product's reference hangs the blind over the wall.
`WINDOWS` in `make_variants.py` holds them; to add one, grid that product's own
room and read the window off it:

```bash
python grid_window.py <bench>/.../maps/preload/<product>/scenebk.jpg 1780 720 2320 1280 1
```

`blind_geometry.js` prints the blind's own angles from a product page's console,
which is how the reference measurements get checked rather than eyeballed.

One supplied room can serve several products - each fits it to its own blind and
writes its own `/maps/scenes/<key>.jpg`. `wooden-premium` and `vertical-premium`
share one file at x1.280 and x0.851.

Check the result with `verify_room.py <key>`, which draws the blind's real
footprint over the generated room. Its top should sit on the window's top.

### What this cannot fix

Fitting is geometry, not quality:

* **Resolution.** A 2000 px source stretched to 4096 has a quarter of the
  detail the captured rooms carry, and no transform puts it back.
* **Shape.** Scaling the axes differently distorts the room by whatever the
  two factors differ by - about 12% for the supplied room.
* **Light.** The blind is lit by fixed white lights, so a night-time or warm
  room will never sit right behind it.

### What to ask for instead

Measured off the captured wooden room, which is the convention all eight
follow. For a **4096 x 2048** panorama:

| | |
|---|---|
| Window centre | x = 2048 (exactly 50% of width), y ~ 1005 (on the horizon) |
| Window outer frame | ~420 px wide (10.3% of width, 36.9 deg) |
| | ~435 px tall (21.2% of height, 38.2 deg) |

A room rendered to that needs neither `scene_center` nor `scene_zoom`, and
loses none of its sharpness. It is worth asking for before a whole range is
produced.

### Renderer sharpness

The bundles construct their `WebGLRenderer` at **pixel ratio 1**, so on any
display with `devicePixelRatio > 1` the browser upscales a smaller image, and
the preview looks soft for reasons that have nothing to do with the room. The
injected script raises the backing store to the display's own density (capped
at 2), passing `updateStyle=false` so the canvas keeps its CSS size and nothing
in the layout moves. It applies to every product, not just variants.

### What a variant shares with its base

The 3D blind, the option groups, and the product copy. Only the name,
breadcrumb, title, catalogue id, room and prices differ. If a variant needs its
own description text, that has to be added to `variant_rewrite()`.

### The top menu

The menu is baked into every captured page, so `nav_inject()` clones the base
product's `<li>` into every generated page. Without it a new product is
reachable only by typing its URL.

## Layout

```
curtain_roll/
├── data/products.json      extracted from the live site
├── www/                    10 pages (+ maps/ textures)
├── templates/includes/     shared product markup + script order
├── public/
│   ├── configurator/       the 9 bundles (~176 MB)
│   ├── three/              three.js, OrbitControls, OBJLoader, dat.gui
│   └── image/              product and swatch images
├── curtain_roll/doctype/   Curtain Product (+ colour / option / slab rows)
├── pricing.py              rates, the live total, and what the cart is charged
├── cart.py                 cart -> draft Quotation
├── renderers.py            the OpenCart endpoints the theme still calls
├── api.py                  quote endpoint, session info, CSRF token
├── install.py              after_install / after_migrate / before_uninstall
└── utils.py                product lookup + asset path helper
```

Regenerate `products.json` and the pages from a fresh capture with
`extract_products.py` and `build_app.py` in the parent directory.

## Moving to another ERPNext instance

The app is ~670 MB, almost all media (`public/configurator` 168 MB,
`public/image` 173 MB, `www/maps` 73 MB). That size drives the method.

### 1. Check the target's versions

The app carries a workaround for ERPNext 16.35 expecting `Contact.is_billing_contact`,
which Frappe 16.34 does not define — `after_install` adds it as a Custom Field, and
skips itself if a newer Frappe already ships the field.

### 2. Get the app across

**Option A — archive (simplest, no Git host):**

```bash
cd ~/frappe-bench/apps
tar czf /tmp/curtain_roll.tar.gz curtain_roll
# copy across, then on the target:
cd ~/frappe-bench/apps && tar xzf /tmp/curtain_roll.tar.gz
```

**Option B — GitHub + `bench get-app` (recommended).** Measured against GitHub's
limits: no file exceeds 100 MB (hard reject) and none even exceeds the 50 MB warning
— the largest is `Roman.js` at 48 MB. Working tree is ~425 MB (4.4 MB code,
420 MB media). **Git LFS is not required**; a plain push works.

```bash
# once, from the app directory
git remote add origin git@github.com:<org>/curtain_roll.git
git push -u origin main

# on any target bench — this clones, pip installs AND adds to apps.txt for you
bench get-app https://github.com/<org>/curtain_roll --branch main
bench --site <site> install-app curtain_roll
bench --site <site> clear-cache
```

`bench get-app` removes the three manual steps Option A needs (pip install,
apps.txt, assets symlink), so prefer it.

Use a **private** repo: the theme, product photography and configurator bundles
are third-party assets, and a public repo republishes them.

### 3. Install

```bash
cd ~/frappe-bench
./env/bin/pip install -e apps/curtain_roll     # bench install-app alone will NOT do this
printf 'curtain_roll\n' >> sites/apps.txt      # NB: file has no trailing newline
bench --site <site> install-app curtain_roll
ln -sfn ~/frappe-bench/apps/curtain_roll/curtain_roll/public \
        ~/frappe-bench/sites/assets/curtain_roll
bench --site <site> clear-cache
```

**Restart the bench.** A running `bench start` keeps its old `sys.path`; until it
restarts every page 500s with `ModuleNotFoundError`.

### 4. The one thing that does NOT travel

`allowed_referrers` lives in **site_config.json**, not app code. Without it the theme's
AJAX is rejected with `CSRFTokenError`:

```json
"allowed_referrers": ["https://yourdomain.com"]
```

Everything else is handled by `after_install`: the Custom Field, signup enabled, the
home page route, the nav, and an Item per curtain type.

### 5. Case-sensitive filename warning

`www/maps/preload/Zebra/scenebk.jpg` (capital Z) and `.../zebra/` must BOTH exist.
Windows cannot hold both, so round-tripping through a Windows filesystem loses it and
the Zebra configurator 404s. Recreate with:

```bash
mkdir -p curtain_roll/www/maps/preload/Zebra
cp curtain_roll/www/maps/preload/zebra/scenebk.jpg \
   curtain_roll/www/maps/preload/Zebra/scenebk.jpg
```

### 6. Verify after install

- `/` and `/blackout` render with the theme
- a colour click fetches `/assets/curtain_roll/image/catalog/<product>-materials/<code>.jpg`
- textures resolve at `/maps/preload/…` (site root, **not** under `/assets`)
- currency: the storefront prints the **company default currency**, so set a SAR
  company or every price on the site reads in the wrong currency
- open one **Curtain Product** record and set the rates before going live: a
  fresh install seeds them from the captured "starts from" prices
