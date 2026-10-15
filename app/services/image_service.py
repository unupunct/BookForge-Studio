"""Image preparation for rendering: crop, filters, colour conversion, DPI-limited resampling."""
from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageColor, ImageEnhance, ImageFilter, ImageOps

from ..domain.book import MAX_IMAGE_PIXELS, Asset

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

_cache: dict[tuple, tuple[bytes, str]] = {}

FX_NAMES = ("grayscale", "sepia", "brightness", "contrast", "saturation", "blur", "tint", "tint_alpha")


def open_image(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return ImageOps.exif_transpose(im)


def apply_fx(im: Image.Image, fx: dict | tuple | None, flip: bool = False) -> Image.Image:
    """Non-destructive filters used by cover art: the stored asset is never modified."""
    if flip:
        im = ImageOps.mirror(im)
    if not fx:
        return im
    f = dict(fx)
    alpha = im.getchannel("A") if im.mode in ("RGBA", "LA") else None
    rgb = im.convert("RGB")
    if f.get("grayscale"):
        rgb = ImageOps.grayscale(rgb).convert("RGB")
    if f.get("sepia"):
        g = ImageOps.grayscale(rgb)
        rgb = ImageOps.colorize(g, black="#2B1B0E", white="#F2E3C6", mid="#9C7A4E")
    if f.get("saturation") not in (None, 1.0):
        rgb = ImageEnhance.Color(rgb).enhance(float(f["saturation"]))
    if f.get("brightness") not in (None, 1.0):
        rgb = ImageEnhance.Brightness(rgb).enhance(float(f["brightness"]))
    if f.get("contrast") not in (None, 1.0):
        rgb = ImageEnhance.Contrast(rgb).enhance(float(f["contrast"]))
    if f.get("blur"):
        rgb = rgb.filter(ImageFilter.GaussianBlur(float(f["blur"])))
    if f.get("tint") and f.get("tint_alpha"):
        try:
            col = Image.new("RGB", rgb.size, ImageColor.getrgb(str(f["tint"])))
            rgb = Image.blend(rgb, col, max(min(float(f["tint_alpha"]), 1.0), 0.0))
        except ValueError:
            pass
    if alpha is not None:
        rgb = rgb.convert("RGBA")
        rgb.putalpha(alpha)
    return rgb


def prepare_image(asset: Asset, crop: tuple[float, float, float, float] | None,
                  width_pt: float, max_dpi: int, jpeg_quality: int,
                  fx: dict | tuple | None = None, flip: bool = False) -> tuple[bytes, str]:
    """Return (encoded bytes, format) ready for embedding.

    Never upsamples; only downsamples when the effective resolution exceeds `max_dpi`.
    """
    key = (asset.sha256, crop, round(width_pt), max_dpi, jpeg_quality, tuple(fx) if fx else None, flip)
    hit = _cache.get(key)
    if hit:
        return hit
    im = open_image(asset.data)
    if crop:
        l, t, r, b = crop
        w, h = im.size
        box = (int(max(l, 0) * w), int(max(t, 0) * h), int(min(r, 1) * w), int(min(b, 1) * h))
        if box[2] > box[0] and box[3] > box[1]:
            im = im.crop(box)
    target_px = int(width_pt / 72.0 * max_dpi)
    if target_px > 0 and im.width > target_px:
        ratio = target_px / im.width
        im = im.resize((target_px, max(int(im.height * ratio), 1)), Image.LANCZOS)
    im = apply_fx(im, fx, flip)
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    out = io.BytesIO()
    if has_alpha:
        im.convert("RGBA").save(out, "PNG")
        result = (out.getvalue(), "PNG")
    else:
        im.convert("RGB").save(out, "JPEG", quality=jpeg_quality, subsampling=0 if jpeg_quality >= 90 else 2)
        result = (out.getvalue(), "JPEG")
    if len(_cache) > 64:
        _cache.clear()
    _cache[key] = result
    return result


def effective_dpi(asset: Asset, width_pt: float, crop: Any = None) -> float:
    px = asset.width or 0
    if crop:
        px = px * max(crop[2] - crop[0], 0.01)
    return px / (width_pt / 72.0) if width_pt > 0 else 0.0
