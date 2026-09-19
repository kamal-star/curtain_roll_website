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

Every row is charged as **Fixed Amount**, **Per Square Meter** or **Percent of
Base**; a colour may also **Override Base Rate**. The area comes from the width
and height the customer types, in cm: `width x height / 10000`.

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

Per-choice surcharges are written into the swatch markup as the theme's own
`.option-price` span and tooltip. The Journal3 stylesheet hides that span with
`display: none !important`, exactly as on the original site, so the figures
show on hover and in the running total. To print them under each swatch
instead, add to `public/css/curtain.css`:

```css
.product-info .option-price { display: inline !important; }
```

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
