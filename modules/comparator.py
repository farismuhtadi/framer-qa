"""
comparator.py — Pixel-level image comparison between a live screenshot
and a Figma export, producing a diff image and a similarity score.

The diff image highlights changed pixels in red over a faded version
of the live screenshot, making it easy to spot design deviations at a glance.
"""

import io
import numpy as np
from PIL import Image, ImageFilter


def compare_images(
    live_path: str,
    figma_path: str,
    diff_output_path: str,
    threshold: int = 10,
) -> float:
    """
    Compares two PNG images pixel by pixel.

    Args:
        live_path:        Path to the live website screenshot.
        figma_path:       Path to the Figma export.
        diff_output_path: Where to save the diff PNG.
        threshold:        0–255 sensitivity. Lower = stricter.

    Returns:
        Similarity score as a percentage (0–100).
        100.0 means pixel-perfect match.
    """
    live_img  = Image.open(live_path).convert("RGBA")
    figma_img = Image.open(figma_path).convert("RGBA")

    # Align sizes: crop/pad both to the same width; trim to shorter height
    live_img, figma_img = _align_sizes(live_img, figma_img)

    live_arr  = np.array(live_img,  dtype=np.int32)
    figma_arr = np.array(figma_img, dtype=np.int32)

    # Compute per-channel absolute difference, ignoring alpha channel
    diff = np.abs(live_arr[:, :, :3] - figma_arr[:, :, :3])  # H×W×3

    # A pixel is "different" if any channel exceeds the threshold
    diff_mask = np.any(diff > threshold, axis=2)  # H×W bool

    total_pixels = diff_mask.size
    changed_pixels = int(diff_mask.sum())
    similarity = (total_pixels - changed_pixels) / total_pixels * 100.0

    # Build diff image:
    # - Base: slightly faded live screenshot for context
    # - Changed pixels: dilated bright red blobs so small diffs are visible
    live_arr = np.array(live_img, dtype=np.uint8)

    # Dilate the diff mask to turn scattered pixels into visible blobs
    mask_img    = Image.fromarray((diff_mask * 255).astype(np.uint8), "L")
    mask_dilated = mask_img.filter(ImageFilter.MaxFilter(size=9))  # 9px dilation radius
    blob_mask   = np.array(mask_dilated) > 0  # H×W bool

    # Dim the base image (keeps context readable)
    base = live_arr.astype(np.float32)
    base[:, :, :3] = base[:, :, :3] * 0.55

    # Paint dilated blobs red with some transparency for a heatmap feel
    red_r, red_g, red_b = 239, 68, 68  # Tailwind red-500
    alpha_blend = 0.75  # 75% red over dimmed base
    base[blob_mask, 0] = base[blob_mask, 0] * (1 - alpha_blend) + red_r * alpha_blend
    base[blob_mask, 1] = base[blob_mask, 1] * (1 - alpha_blend) + red_g * alpha_blend
    base[blob_mask, 2] = base[blob_mask, 2] * (1 - alpha_blend) + red_b * alpha_blend

    diff_img = Image.fromarray(base.astype(np.uint8), "RGBA").convert("RGB")
    diff_img.save(diff_output_path, format="PNG")

    return similarity


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
