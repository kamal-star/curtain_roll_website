# Which pages are generated, and which are not

Most pages under `curtain_roll/www/` are **generated**. They are not the
source. A build script reads the captured Journal3 site, rewrites it and
overwrites them, so an edit made here is lost the next time anyone builds.

Two are no longer generated, and must not be.

## Hand-written — do not regenerate

| page | why |
|---|---|
| `www/home.html` | rewritten by hand: custom markup replacing the captured theme, plus full SEO tags and JSON-LD |
| `www/blackout.html` | same |

Rebuilding these from the capture does not update them, it destroys them:
home went 313 KB → 63 KB in the rewrite and blackout 422 KB → 102 KB, and
every byte of that difference is the old theme waiting to come back.

The generator knows. `port_pages.py` carries a `HAND_WRITTEN` set naming both
routes, skips them, and prints `SKIPPED` so it is visible rather than silent.

`www/about-us.html`, `contact-us.html`, `delivery-and-installation.html`,
`privacy-policy.html` and `terms-and-conditions.html` are hand-written too.
Nothing generates them, so nothing can overwrite them.

## Generated — edit the generator, not the page

`printed`, `sunscreen`, `zebra`, `wooden`, `vertical`, `metal`, `roman`,
`wavy`, and the three variants `wooden-premium`, `vertical-premium`,
`shutters`.

Changing one of these by hand works until the next build and then silently
reverts. The change belongs in the generator.

## Where the generator lives

`port_pages.py`, `make_variants.py`, `make_shell.py` and the rest are **not in
this repository**. They sit in the working directory the app is built from,
along with the captured site they read - roughly 700 MB that has never been
worth pushing.

That is a real single point of failure: this repo holds the generated pages
but nothing able to regenerate them, and the `HAND_WRITTEN` guard that
protects the two pages above is in `port_pages.py`, which means it is on one
machine. If you are working on this repo without that directory, treat every
page in the table above as irreplaceable.

## The account pages and the cart

`/account`, its sub-pages and `/cart` extend `templates/curtain_shell.html`,
which is cut from the *captured* theme's header and footer. They therefore
still look like the old design, which currently matches 11 of the 13 product
and home pages but not the two that were redesigned.

`make_shell.py` cuts that shell from `www/home.html`. Now that home is
hand-written, there is no captured menu left in it to cut, so the script stops
with an explanation rather than writing a broken shell. Moving the account
pages onto the new design means pointing it at a page that has that design and
rewriting its `ACCOUNT_MENU` to match.
