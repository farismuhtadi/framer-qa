"""
figma.py — Figma REST API client for exporting frame images.

Usage:
    client = FigmaClient(api_token, file_id)
    png_bytes = client.export_frame(node_id, width=1440)

How to find node IDs in Figma:
    1. Open your Figma file
    2. Click on a top-level frame
    3. Look at the browser URL: ...?node-id=123-456
    4. Use "123:456" as the node_id (replace hyphen with colon)
"""

import requests
import io
from PIL import Image


FIGMA_API_BASE = "https://api.figma.com/v1"


class FigmaClient:
    def __init__(self, api_token: str, file_id: str):
        self.api_token = api_token
        self.file_id   = file_id
        self.session   = requests.Session()
        self.session.headers.update({
            "X-Figma-Token": api_token,
            "User-Agent": "FramerQA/1.0",
        })

    def export_frame(self, node_id: str, target_width: int, scale: float = 2.0) -> bytes | None:
        """
        Exports a Figma frame as a PNG at the given scale.
        Returns PNG bytes, or None on failure.

        The exported image is scaled so its width matches target_width,
        preserving aspect ratio — this makes pixel diff more meaningful.
        """
        # Figma uses colon-separated node IDs in API calls
        node_id_api = node_id.replace("-", ":")

        url = f"{FIGMA_API_BASE}/images/{self.file_id}"
        params = {
            "ids":    node_id_api,
            "format": "png",
            "scale":  scale,
        }

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"   ❌ Figma API error for node {node_id}: {e}")
            return None

        if data.get("err"):
            print(f"   ❌ Figma export error: {data['err']}")
            return None

        image_url = data.get("images", {}).get(node_id_api)
        if not image_url:
            print(f"   ❌ No image URL returned for node {node_id}")
            return None

        # Download the exported image
        try:
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()
            png_bytes = img_resp.content
        except Exception as e:
            print(f"   ❌ Failed to download Figma image: {e}")
            return None

        # Resize to match target viewport width
        try:
            img = Image.open(io.BytesIO(png_bytes))
            orig_w, orig_h = img.size
            if orig_w != target_width:
                ratio    = target_width / orig_w
                new_h    = int(orig_h * ratio)
                img      = img.resize((target_width, new_h), Image.LANCZOS)
                buf      = io.BytesIO()
                img.save(buf, format="PNG")
                png_bytes = buf.getvalue()
        except Exception as e:
            print(f"   ⚠️  Image resize failed (using original): {e}")

        return png_bytes

    def list_frames(self) -> list[dict]:
        """
        Returns all top-level frames in the Figma file,
        useful for discovering node IDs without opening the browser.
        """
        url = f"{FIGMA_API_BASE}/files/{self.file_id}"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"   ❌ Failed to fetch Figma file: {e}")
            return []

        frames = []
        for page in data.get("document", {}).get("children", []):
            for child in page.get("children", []):
                if child.get("type") == "FRAME":
                    frames.append({
                        "name":    child["name"],
                        "node_id": child["id"],
                        "page":    page["name"],
                    })
        return frames
