"""
Image Generator for Benchmark Sample Packaging Artwork.
Generates realistic package label images with text, tables, borders, and barcodes for the 4 sides.
"""
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import cv2
import io
import base64
from typing import Dict, Any

class SampleArtworkRenderer:

    @classmethod
    def render_side_label(cls, title: str, content_lines: list, side_name: str, bg_theme: str = "#f8fafc") -> str:
        """
        Renders a crisp 800x600 package label image and returns its base64 JPEG string.
        """
        width, height = 700, 520
        
        # Determine color palette based on side
        header_color = "#1e3a8a" if side_name == "front" else ("#0f766e" if side_name == "back" else "#475569")
        
        img = Image.new("RGB", (width, height), color="#ffffff")
        draw = ImageDraw.Draw(img)

        # Outer Packaging Box & Border
        draw.rectangle([(10, 10), (width - 10, height - 10)], outline="#94a3b8", width=3)
        draw.rectangle([(16, 16), (width - 16, height - 16)], outline="#cbd5e1", width=1)

        # Top Header Banner
        draw.rectangle([(16, 16), (width - 16, 75)], fill=header_color)
        
        # Try default fonts
        draw.text((30, 26), f"PACKAGE {side_name.upper()} PANEL • STATUTORY DECLARATIONS", fill="#ffffff")
        draw.text((30, 48), title.upper()[:45], fill="#e2e8f0")

        # Body Content Rendering
        y_cursor = 95
        for line in content_lines:
            line_str = str(line).strip()
            if not line_str:
                y_cursor += 12
                continue
                
            if "MRP" in line_str or "M.R.P" in line_str:
                # Highlight MRP block
                draw.rectangle([(25, y_cursor - 4), (width - 25, y_cursor + 28)], fill="#fee2e2", outline="#ef4444", width=1)
                draw.text((35, y_cursor + 4), line_str, fill="#b91c1c")
                y_cursor += 36
            elif "Net" in line_str or "Quantity" in line_str or "Weight" in line_str:
                # Highlight Net Qty block
                draw.rectangle([(25, y_cursor - 4), (width - 25, y_cursor + 26)], fill="#ecfdf5", outline="#10b981", width=1)
                draw.text((35, y_cursor + 4), line_str, fill="#047857")
                y_cursor += 34
            elif "Manufactured by" in line_str or "Imported" in line_str:
                draw.text((30, y_cursor), line_str, fill="#1e293b")
                y_cursor += 20
            elif "Consumer" in line_str or "Grievance" in line_str:
                draw.rectangle([(25, y_cursor - 2), (width - 25, y_cursor + 22)], fill="#eff6ff", outline="#3b82f6", width=1)
                draw.text((35, y_cursor + 2), line_str, fill="#1d4ed8")
                y_cursor += 28
            else:
                draw.text((30, y_cursor), line_str, fill="#334155")
                y_cursor += 18

            if y_cursor > height - 60:
                break

        # Bottom Barcode & Verification Seal Simulation
        draw.rectangle([(width - 220, height - 55), (width - 30, height - 20)], fill="#f1f5f9", outline="#94a3b8", width=1)
        # Barcode lines
        for bx in range(width - 210, width - 40, 5):
            draw.line([(bx, height - 50), (bx, height - 32)], fill="#0f172a", width=2)
        draw.text((width - 195, height - 30), "8 901234 567890", fill="#475569")

        # Official Compliance Mark Placeholder
        draw.rectangle([(30, height - 55), (140, height - 20)], fill="#f8fafc", outline="#64748b", width=1)
        draw.text((40, height - 44), "LEGAL METROLOGY", fill="#475569")

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("utf-8")

    @classmethod
    def generate_sample_images(cls, sample_dict: Dict[str, Any]) -> Dict[str, str]:
        """
        Takes a sample item from samples.json and returns a dict mapping side -> base64 data url.
        """
        sides_images = {}
        sample_name = sample_dict.get("name", "Product Label")
        sides_dict = sample_dict.get("sides", {})

        for side_key in ["front", "back", "top", "side"]:
            text_content = sides_dict.get(side_key, f"{sample_name}\nPanel {side_key.upper()}")
            lines = text_content.split("\n")
            sides_images[side_key] = cls.render_side_label(sample_name, lines, side_key)

        return sides_images
