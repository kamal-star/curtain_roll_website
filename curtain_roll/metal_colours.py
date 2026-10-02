# -*- coding: utf-8 -*-
"""Starter colours for Metal: common aluminium-blind finishes, both widths.

    bench --site <site> execute curtain_roll.metal_colours.add

Safe to run again:
a colour already on a width is left alone. The client can rename, re-price,
disable or replace any of them in Curtain Product -> metal -> Sub Options.

The swatch is also what the 3D blind wears (curtain_options.js recolour()
puts it on the slats as their texture), so it is drawn as brushed aluminium -
fine horizontal grain and a soft sheen down the slat - not a flat square.
"""
import io
import random

import frappe
from PIL import Image, ImageDraw, ImageFilter

from curtain_roll import pricing

COLOURS = (
    # English, Arabic, RGB
    ("White", "أبيض", (240, 240, 236)),
    ("Silver", "فضي", (190, 194, 199)),
    ("Champagne", "شمبانيا", (201, 178, 124)),
    ("Gold", "ذهبي", (184, 145, 63)),
    ("Beige", "بيج", (217, 201, 168)),
    ("Bronze", "برونزي", (122, 82, 48)),
    ("Graphite", "جرافيت", (74, 78, 84)),
    ("Black", "أسود", (34, 34, 36)),
)
WIDTHS = ("5 cm", "2.5 cm")
SIZE = 256


def brushed(rgb, seed):
    rnd = random.Random(seed)
    im = Image.new("RGB", (SIZE, SIZE), rgb)
    draw = ImageDraw.Draw(im)
    # the grain: thin horizontal streaks a shade either side of the colour
    for y in range(SIZE):
        d = rnd.randint(-7, 7)
        draw.line([(0, y), (SIZE, y)],
                  fill=tuple(max(0, min(255, c + d)) for c in rgb))
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    # the sheen: a little lighter across the middle of the slat
    sheen = Image.new("L", (1, SIZE))
    for y in range(SIZE):
        t = 1 - abs(y - SIZE / 2.0) / (SIZE / 2.0)
        sheen.putpixel((0, y), int(38 * t * t))
    sheen = sheen.resize((SIZE, SIZE))
    white = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
    return Image.composite(white, im, sheen)


def swatch_url(name, rgb, seed):
    file_name = "metal-colour-%s.png" % name.lower()
    existing = frappe.db.get_value("File", {"file_name": file_name, "is_private": 0}, "file_url")
    if existing:
        return existing
    buf = io.BytesIO()
    brushed(rgb, seed).save(buf, "PNG")
    doc = frappe.get_doc({"doctype": "File", "file_name": file_name,
                          "content": buf.getvalue(), "is_private": 0})
    doc.insert(ignore_permissions=True)
    return doc.file_url


def add():
    doc = frappe.get_doc("Curtain Product", "metal")
    have = {(r.parent_choice, r.option_label) for r in doc.sub_options
            if r.group_label == "Colour"}
    added = 0
    for width in WIDTHS:
        for i, (label, label_ar, rgb) in enumerate(COLOURS):
            if (width, label) in have:
                continue
            doc.append("sub_options", {
                "parent_choice": width, "group_label": "Colour", "group_label_ar": "اللون",
                "option_label": label, "option_label_ar": label_ar,
                "image": swatch_url(label, rgb, i), "rate": 0,
                "charge_type": "Fixed Amount", "enabled": 1})
            added += 1
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    pricing.clear_cache("metal")
    spec = pricing.get_spec("metal")
    print("added", added, "| colour choices now:",
          sorted({(r["parent"], r["label"]) for r in spec["sub_options"]}))

