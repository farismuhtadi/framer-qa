"""
comparator.py — Pixel-level image comparison between a live screenshot
and a Figma export, producing a diff image and a similarity score.

The diff image highlights changed pixels in red over a faded version
of the live screenshot, making it easy to spot design deviations at a glance.
"""

import io
import numpy as np
from PIL import Image, ImageFilter, ImageDraw, ImageFont


def compare_images(
    live_path: str,
    figma_path: str,
    diff_output_path: str,
    threshold: int = 10,
) -> tuple[float, list[dict]]:
    """
    Compares two PNG images pixel by pixel.

    Args:
        live_path:        Path to the live website screenshot.
        figma_path:       Path to the Figma export.
        diff_output_path: Where to save the diff PNG.
        threshold:        0–255 sensitivity. Lower = stricter.

    Returns:
        (similarity, regions) where:
          similarity — 0–100 float (100 = pixel-perfect)
          regions    — list of dicts {index, x1, y1, x2, y2, cx, cy}
                       each describing a numbered changed region drawn on the diff
    """
    live_img  = Image.open(live_path).convert("RGBA")
    figma_img = Image.open(figma_path).convert("RGBA")

    # Align sizes: pad both to same width, trim to shorter height
    live_img, figma_img = _align_sizes(live_img, figma_img)

    live_arr  = np.array(live_img,  dtype=np.int32)
    figma_arr = np.array(figma_img, dtype=np.int32)

    # Per-channel diff, ignoring alpha
    diff = np.abs(live_arr[:, :, :3] - figma_arr[:, :, :3])
    diff_mask = np.any(diff > threshold, axis=2)  # H×W bool

    total_pixels   = diff_mask.size
    changed_pixels = int(diff_mask.sum())
    similarity     = (total_pixels - changed_pixels) / total_pixels * 100.0

    # ── Build diff overlay ────────────────────────────────────────────────────
    live_arr = np.array(live_img, dtype=np.uint8)

    # Dilate mask into visible blobs
    mask_img     = Image.fromarray((diff_mask * 255).astype(np.uint8), "L")
    mask_dilated = mask_img.filter(ImageFilter.MaxFilter(size=9))
    blob_mask    = np.array(mask_dilated) > 0

    base = live_arr.astype(np.float32)
    base[:, :, :3] *= 0.55  # dim base

    red_r, red_g, red_b = 239, 68, 68
    ab = 0.75
    base[blob_mask, 0] = base[blob_mask, 0] * (1 - ab) + red_r * ab
    base[blob_mask, 1] = base[blob_mask, 1] * (1 - ab) + red_g * ab
    base[blob_mask, 2] = base[blob_mask, 2] * (1 - ab) + red_b * ab

    diff_img = Image.fromarray(base.astype(np.uint8), "RGBA").convert("RGB")

    # ── Find changed regions and draw numbered boxes ───────────────────────────
    regions = _find_regions(diff_mask, max_regions=8, min_area=400)
    _draw_region_labels(diff_img, regions)

    diff_img.save(diff_output_path, format="PNG")
    return similarity, regions


def _find_regions(diff_mask: np.ndarray, max_regions: int = 8, min_area: int = 400) -> list[dict]:
    """
    Finds bounding boxes of the largest changed regions in the diff mask.
    Uses a coarse grid to cluster nearby changed pixels, then maps back to
    image coordinates. Returns at most max_regions entries sorted by area.
    """
    h, w = diff_mask.shape

    # Dilate heavily so nearby scattered pixels merge into one region
    mask_img = Image.fromarray((diff_mask * 255).astype(np.uint8), "L")
    merged   = mask_img.filter(ImageFilter.MaxFilter(size=51))
    merged_arr = np.array(merged) > 0

    # Scan horizontal bands of contiguous changed rows
    row_has_change = np.any(merged_arr, axis=1)
    bands: list[tuple[int, int]] = []
    in_band = False
    r_start = 0
    for i, has in enumerate(row_has_change):
        if has and not in_band:
            r_start, in_band = i, True
        elif not has and in_band:
            bands.append((r_start, i))
            in_band = False
    if in_band:
        bands.append((r_start, h))

    regions: list[dict] = []
    for idx, (r0, r1) in enumerate(bands):
        band = merged_arr[r0:r1, :]
        col_mask = np.any(band, axis=0)
        if not col_mask.any():
            continue
        c0 = int(np.argmax(col_mask))
        c1 = int(w - np.argmax(col_mask[::-1]))
        area = (r1 - r0) * (c1 - c0)
        if area < min_area:
            continue
        cx, cy = (c0 + c1) // 2, (r0 + r1) // 2
        regions.append({"index": idx + 1, "x1": c0, "y1": r0, "x2": c1, "y2": r1, "cx": cx, "cy": cy})

    # Keep largest regions only
    regions.sort(key=lambda r: (r["x2"] - r["x1"]) * (r["y2"] - r["y1"]), reverse=True)
    regions = regions[:max_regions]

    # Re-number after filtering
    for i, r in enumerate(regions):
        r["index"] = i + 1

    return regions


def _draw_region_labels(img: Image.Image, regions: list[dict]) -> None:
    """Draws numbered orange boxes on the diff image for each changed region."""
    if not regions:
        return

    draw  = ImageDraw.Draw(img)
    orange = (251, 146, 60)   # Tailwind orange-400
    white  = (255, 255, 255)
    pad    = 4
    badge  = 20               # badge circle diameter

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    except Exception:
        font = ImageFont.load_default()

    for r in regions:
        x1, y1, x2, y2 = r["x1"], r["y1"], r["x2"], r["y2"]
        label = str(r["index"])

        # Dashed-look border (draw a thin rect, then inner rect for dash effect)
        draw.rectangle([x1, y1, x2, y2], outline=orange, width=2)

        # Numbered badge in top-left corner of the box
        bx, by = x1 + pad, y1 + pad
        draw.ellipse([bx, by, bx + badge, by + badge], fill=orange)
        try:
            tw = draw.textlength(label, font=font)
        except Exception:
            tw = 8
        draw.text((bx + (badge - tw) / 2, by + 3), label, fill=white, font=font)


def _align_sizes(img_a: Image.Image, img_b: Image.Image):
    """
    Pads both images to the same width, then trims to the shorter height.
    This handles cases where the live page is longer/shorter than the Figma frame.
    """
    w = max(img_a.width, img_b.width)
    h = min(img_a.height, img_b.height)

    def fit(img):
        # Pad width if needed (white background)
        if img.width < w:
            padded = Image.new("RGBA", (w, img.height), (255, 255, 255, 255))
            padded.paste(img, (0, 0))
            img = padded
        # Crop to shared height
        return img.crop((0, 0, w, h))

    return fit(img_a), fit(img_b)


def similarity_label(score: float) -> str:
    """Returns a human-readable label for a similarity score."""
    if score >= 98:
        return "Pixel-perfect"
    elif score >= 90:
        return "Minor differences"
    elif score >= 70:
        return "Noticeable differences"
    elif score >= 50:
        return "Significant differences"
    else:
        return "Major differences"


def similarity_color(score: float) -> str:
    """Returns a CSS color class for the score."""
    if score >= 95:
        return "pass"
    elif score >= 80:
        return "warn"
    else:
        return "fail"
