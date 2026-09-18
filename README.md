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

`webshop` is not installed, so there is no cart. Each product page carries a
**Request a quote** form posting to `curtain_roll.api.submit_quote`, which
creates a **Lead** and attaches the configurator render as a private File.
That matches how the business actually sells — sizing is done on site, and the
original storefront collected no dimensions either.

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
├── api.py                  quote endpoint
├── install.py              after_install / before_uninstall
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

**Option B — Git remote.** Individual bundles sit under GitHub's 100 MB hard limit
(largest `Roman.js`, 47 MB) but several pass the 50 MB warning and the repo is large.
Use **Git LFS** for `*.js` bundles, `www/maps/**` and `public/image/**`.

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
- currency: quotations use the company default — set a SAR company and price list
