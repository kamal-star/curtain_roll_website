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

The blind hangs at the middle of the bundle's world and **cannot be moved or
resized** - it is geometry at a fixed distance from a fixed camera, compiled in.
Measured off the running scene it is **34.9 deg wide by 34.3 deg tall, 3.5 deg
above the horizon**, and every captured room puts a window right there:
**36.9 x 38.2 deg, dead centre**, leaving a little reveal around the blind.

So the room has to be fitted to the blind. Measure the window in the supplied
image and give its outer frame in that image's own pixels:

```json
"window": [347.5, 395.0, 636.0, 675.0]
```

`reproject()` derives everything else - where to aim, and how much to scale
each axis so the window ends up 36.9 x 38.2 deg. **Measure once; do not hand-
compute the transform.** Deriving it by hand is how the scale got inverted the
first time, and how `scene_zoom` ended up eyeballed at 1.25 when the real
answer was 1.41 across and 1.25 up. Those differ because a window is rarely the
same shape as the one the blind was built for, which a single uniform zoom
cannot fix.

An equirectangular image is linear in longitude and latitude, so aiming is a
translation and fitting is a scale. It is done in **one resample straight from
the supplied file** - rolling, then scaling, then resizing would interpolate
three times and throw away detail a small source cannot spare. The margins that
opens up are filled by tiling sideways (a panorama is a loop, so it is
seamless) and by repeating the top and bottom rows, which is what the poles
look like anyway.

Check the result with `verify_room.py <key>`, which draws the target box over
the generated room. The window should sit inside it.

`scene_center` / `scene_center_y` / `scene_zoom` still work if `window` is
absent, but there is no good reason to use them.

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
