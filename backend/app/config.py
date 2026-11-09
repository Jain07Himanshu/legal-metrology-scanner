"""
Configuration and settings for Legal Metrology Scanner backend.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
RULES_FILE = BASE_DIR / "app" / "rules" / "legal_metrology_rules.yaml"
SAMPLE_DATA_FILE = BASE_DIR / "sample_data" / "samples.json"
HISTORY_FILE = DATA_DIR / "inspection_history.json"

# Ensure runtime directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# Image Preprocessing Thresholds
BLUR_LAPLACIAN_THRESHOLD = 80.0  # Images below this are flagged as blurry
GLARE_LUMINANCE_THRESHOLD = 235  # Pixel brightness threshold for glare hotspot
MIN_RECOMMENDED_DPI = 150        # Recommended DPI for accurate millimeter font measurement

# Legal Metrology Font Size Lookup Table (Schedule I / Rule 7)
# Maps Net Quantity (Q in g/ml) to minimum character height in mm
FONT_SIZE_SCHEDULE = [
    {"max_qty": 50, "min_height_mm": 1.0, "blown_moulded_mm": 2.0},
    {"max_qty": 200, "min_height_mm": 2.0, "blown_moulded_mm": 4.0},
    {"max_qty": 1000, "min_height_mm": 4.0, "blown_moulded_mm": 6.0},
    {"max_qty": float("inf"), "min_height_mm": 6.0, "blown_moulded_mm": 8.0}
]

# Standard Legal SI Units under Rule 11 & Schedule II
LEGAL_UNITS = {
    "mass": ["g", "kg"],
    "volume": ["ml", "mL", "l", "L"],
    "length": ["cm", "m"],
    "count": ["N", "U", "units", "pieces", "tabs", "capsules"]
}

# Explicitly Illegal / Non-Standard Units prohibited by Legal Metrology Rules
ILLEGAL_UNITS = ["gm", "gms", "GM", "GMS", "Gm", "gm.", "KG.", "KGS", "kgs", "ml.", "lts", "Ltr", "ltrs", "no.", "nos"]

# Statutory Penalty References under Legal Metrology Act, 2009
ACT_SECTIONS = {
    "SECTION_36_1": "Section 36(1) - Penalty for manufacturing, packing, importing, selling, distributing packaged commodities without mandatory declarations (Fine up to ₹25,000 for 1st offence, ₹50,000 for 2nd, up to ₹1,00,000 or imprisonment for subsequent).",
    "SECTION_36_2": "Section 36(2) - Penalty for manufacturing or selling non-standard packages / quantity discrepancy.",
    "SECTION_39": "Section 39 - Offences by Companies (Nominated Director / Officer in charge liability).",
    "RULE_18_2": "Rule 18(2) - Prohibition of affixing higher price stickers or altering printed Maximum Retail Price."
}
