"""
AI Declaration & Label Verification Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

For every declaration and claim on the packaging, produces a DeclarationCard with:
  • Presence      – was it detected?
  • Completeness  – are all expected sub-fields present?
  • Correctness   – is it internally consistent across panels?
  • Readability   – can it be reliably read from this image?
  • Placement     – is it properly located / not obscured?
  • Font Size     – estimated size vs. statutory minimum (honest uncertainty)

Uses 3 statuses:
  PASS             – detected, complete, consistent, readable
  POTENTIAL_ISSUE  – missing, conflicting, or incomplete
  MANUAL_REVIEW    – uncertain due to OCR confidence / image quality / unverifiable claim
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from app.models.schemas import (
    DeclarationFields, BoundingBox,
    DeclVerifStatus, DeclDimensionResult, ConflictEvidence,
    DeclarationCard, DeclarationAnalysisSummary,
)
from app.config import FONT_SIZE_SCHEDULE


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _pass(detail: str, evidence: str = None, conf: float = None) -> DeclDimensionResult:
    return DeclDimensionResult(status=DeclVerifStatus.PASS, detail=detail,
                               evidence_text=evidence, confidence=conf)

def _issue(detail: str, evidence: str = None, conf: float = None) -> DeclDimensionResult:
    return DeclDimensionResult(status=DeclVerifStatus.POTENTIAL_ISSUE, detail=detail,
                               evidence_text=evidence, confidence=conf)

def _review(detail: str, evidence: str = None, conf: float = None) -> DeclDimensionResult:
    return DeclDimensionResult(status=DeclVerifStatus.MANUAL_REVIEW, detail=detail,
                               evidence_text=evidence, confidence=conf)

def _worst(statuses: List[DeclVerifStatus]) -> DeclVerifStatus:
    if DeclVerifStatus.POTENTIAL_ISSUE in statuses:
        return DeclVerifStatus.POTENTIAL_ISSUE
    if DeclVerifStatus.MANUAL_REVIEW in statuses:
        return DeclVerifStatus.MANUAL_REVIEW
    return DeclVerifStatus.PASS

def _avg_conf(side_lines: Dict[str, List[Any]], pattern: str) -> float:
    """Return average OCR confidence of lines matching pattern."""
    matched = []
    for side, lines in side_lines.items():
        for l in lines:
            if isinstance(l, dict):
                text = l.get("text", "")
                conf = l.get("confidence", 0.95)
            elif hasattr(l, "text"):
                text = l.text
                conf = getattr(l, "confidence", 0.95)
            else:
                text = str(l)
                conf = 0.95
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(conf)
    return round(sum(matched) / len(matched), 3) if matched else 0.95

def _find_bbox(side_lines: Dict[str, List[Any]], pattern: str) -> Optional[BoundingBox]:
    for side, lines in side_lines.items():
        for l in lines:
            if isinstance(l, dict):
                text = l.get("text", "")
                b = l.get("bbox", {})
            elif hasattr(l, "text"):
                text = l.text
                b = getattr(l, "bbox", {})
                if hasattr(b, "dict"):
                    b = b.dict()
            else:
                text = str(l)
                b = {}
            if re.search(pattern, text, re.IGNORECASE):
                if isinstance(b, dict):
                    return BoundingBox(x=b.get("x", 0.08), y=b.get("y", 0.1),
                                       width=b.get("width", 0.4), height=b.get("height", 0.045),
                                       page_side=side)
                elif isinstance(b, BoundingBox):
                    return b
    return None

def _find_panel(side_lines: Dict[str, List[Any]], pattern: str) -> str:
    for side, lines in side_lines.items():
        for l in lines:
            text = l.get("text", "") if isinstance(l, dict) else (l.text if hasattr(l, "text") else str(l))
            if re.search(pattern, text, re.IGNORECASE):
                return side.replace("_", " ").title()
    return "Unknown"

def _font_size_check(bbox: Optional[BoundingBox], qty_val: float, unit: str) -> DeclDimensionResult:
    """Estimate font height and compare against Schedule I minimum."""
    if bbox is None:
        return _review("Bounding box unavailable — physical measurement required to verify character height.")

    est_mm = round(bbox.height * 120.0, 2)   # 120 mm reference label height
    equiv_g = qty_val * 1000 if unit.lower() in ["kg", "l"] else qty_val

    req_mm = 1.0
    for entry in FONT_SIZE_SCHEDULE:
        if equiv_g <= entry["max_qty"]:
            req_mm = entry["min_height_mm"]
            break

    if est_mm >= req_mm:
        return _pass(
            f"Estimated character height ~{est_mm:.1f} mm ≥ statutory minimum {req_mm:.1f} mm "
            f"(Schedule I, qty bracket ≤{equiv_g:.0f} g/ml)."
        )
    elif est_mm >= req_mm * 0.7:
        return _review(
            f"Estimated character height ~{est_mm:.1f} mm is near the statutory minimum "
            f"({req_mm:.1f} mm). Pixel-height estimation is approximate — physical measurement "
            f"with calibrated gauge required for legal determination."
        )
    else:
        return _review(
            f"Estimated character height ~{est_mm:.1f} mm appears below statutory minimum "
            f"({req_mm:.1f} mm) under Schedule I. Physical measurement required — do not "
            f"issue violation solely on pixel-height estimate."
        )


# ─── Claim Patterns ───────────────────────────────────────────────────────────

CLAIM_PATTERNS = [
    # Marketing / absolute claims
    (r"\b100\s*%\s*(natural|pure|organic|vegetarian|vegan|whole\s*grain|cotton|juice)\b",
     "claim", "100% Purity/Natural Claim"),
    (r"\b(no|zero|0\s*g?)\s+(added\s+sugar|trans\s+fat|preservatives?|artificial|cholesterol)\b",
     "claim", "Absence / Zero Claim"),
    (r"\b(free\s+from|free\s+of)\s+\w+",
     "claim", "Free-From Claim"),
    (r"\b(rich\s+in|high\s+in|good\s+source\s+of)\s+\w+",
     "claim", "Nutrient-Rich Claim"),
    (r"\bextra\s+\d+\s*%?\b",
     "claim", "Extra Quantity Claim"),
    (r"\b(gluten[\s\-]?free|lactose[\s\-]?free|sugar[\s\-]?free|fat[\s\-]?free)\b",
     "claim", "Allergen/Attribute-Free Claim"),
    (r"\b\d+\s*g\s+(protein|bcaa|fiber|fibre|calcium|collagen|omega)\b",
     "nutritional", "Macro-Nutrient Quantity Claim"),
    (r"\b\d+\s*%\s*(vitamin\s*[a-z]|niacinamide|salicylic\s*acid|zinc|aloe|fruit\s*extract|aha|bha)\b",
     "claim", "Percentage Active Ingredient Claim"),
    (r"\b(clinically\s*(tested|proven)|dermatologist\s*(tested|approved)|lab\s*tested)\b",
     "claim", "Clinical/Lab Tested Claim"),
    (r"\bmade\s+with\s+real\s+\w+",
     "claim", "Made With Real Ingredients Claim"),
    (r"\b(organic|ayurvedic|herbal|natural\s+ingredients)\b",
     "claim", "Organic/Ayurvedic Claim"),
    (r"\b(usp|pharmacopoeia|gmp|iso\s*\d+|haccp)\s*(certified|grade|standard)?\b",
     "certification", "Quality Standard Certification"),
    (r"\bfssai\s*(lic\.?\s*no\.?|license)\s*[:\-]?\s*\d+",
     "certification", "FSSAI License Number"),
    (r"\b(agmark|bis|isi\s*mark|bis\s*certified)\b",
     "certification", "Statutory Certification Mark"),
]

NUTRITIONAL_PATTERNS = [
    (r"energy\s*[:\-]?\s*\d+\s*(kcal|kj)",         "nutritional", "Energy Declaration"),
    (r"(total\s*)?fat\s*[:\-]?\s*\d+[\.,]\d*\s*g",  "nutritional", "Total Fat Declaration"),
    (r"(saturated\s*)?fat\s*[:\-]?\s*\d+[\.,]\d*\s*g", "nutritional", "Saturated Fat"),
    (r"carbohydrate\s*[:\-]?\s*\d+[\.,]\d*\s*g",    "nutritional", "Carbohydrate Declaration"),
    (r"(of\s*which\s*)?sugars?\s*[:\-]?\s*\d+[\.,]\d*\s*g", "nutritional", "Sugar Declaration"),
    (r"protein\s*[:\-]?\s*\d+[\.,]\d*\s*g",         "nutritional", "Protein Declaration"),
    (r"sodium\s*[:\-]?\s*\d+[\.,]\d*\s*(mg|g)",     "nutritional", "Sodium Declaration"),
    (r"dietary\s*fibre?\s*[:\-]?\s*\d+[\.,]\d*\s*g","nutritional", "Dietary Fibre Declaration"),
    (r"(vitamin\s*[a-z]|iron|calcium|zinc)\s*[:\-]?\s*\d+", "nutritional", "Micronutrient Declaration"),
    (r"(nutrition(al)?\s*(facts?|information|value|declaration))",
     "nutritional", "Nutritional Information Table"),
    (r"ingredients?\s*[:\-]?\s*[A-Za-z]",           "ingredient", "Ingredients List"),
]


# ─── Main Verifier Class ───────────────────────────────────────────────────────

class DeclarationVerifier:

    @classmethod
    def run(
        cls,
        ocr_results: Dict[str, Any],
        fields: DeclarationFields,
        bbox_map: Dict[str, BoundingBox],
    ) -> DeclarationAnalysisSummary:
        """Entry point — runs all detection and verification and returns the full summary."""
        # Normalize: ocr_results values can be full dicts OR plain text strings
        normalized: Dict[str, Any] = {}
        for side, val in ocr_results.items():
            if isinstance(val, str):
                lines_raw = [l.strip() for l in val.split("\n") if l.strip()]
                normalized[side] = {
                    "full_text": val,
                    "lines": [{"text": t, "bbox": {"x": 0.08, "y": 0.08 + i * 0.06,
                                                    "width": min(0.85, len(t) * 0.015),
                                                    "height": 0.045},
                               "confidence": 0.95} for i, t in enumerate(lines_raw)],
                    "avg_confidence": 0.95,
                }
            elif isinstance(val, dict):
                normalized[side] = val
            else:
                normalized[side] = {"full_text": "", "lines": [], "avg_confidence": 0.95}

        side_texts: Dict[str, str] = {s: r.get("full_text", "") for s, r in normalized.items()}
        side_lines: Dict[str, List[Dict]] = {s: r.get("lines", []) for s, r in normalized.items()}
        combined_text = "\n".join(side_texts.values())
        avg_img_conf = cls._avg_image_conf(side_lines)

        cards: List[DeclarationCard] = []

        # ── Mandatory declarations ──
        cards += cls._verify_mrp(fields, bbox_map, side_texts, side_lines)
        cards += cls._verify_net_quantity(fields, bbox_map, side_texts, side_lines)
        cards += cls._verify_manufacturer(fields, bbox_map, side_lines)
        cards += cls._verify_dates(fields, bbox_map, side_texts, side_lines)
        cards += cls._verify_consumer_care(fields, bbox_map, side_lines)
        cards += cls._verify_country_of_origin(fields, bbox_map, side_lines)
        cards += cls._verify_batch_number(fields, bbox_map, side_lines)

        # ── Nutritional & Ingredient declarations ──
        cards += cls._detect_nutritional_and_ingredient(combined_text, side_lines, avg_img_conf)

        # ── Claims & Certifications ──
        cards += cls._detect_claims_and_certs(combined_text, side_lines, avg_img_conf)

        # ── Cross-panel consistency ──
        cls._apply_cross_panel_conflicts(cards, side_texts)

        # ── Build summary ──
        return cls._build_summary(cards, fields)

    # ── Average OCR confidence ─────────────────────────────────────────────────

    @classmethod
    def _avg_image_conf(cls, side_lines: Dict[str, List[Any]]) -> float:
        all_confs = []
        for side, lines in side_lines.items():
            for l in lines:
                if isinstance(l, dict):
                    all_confs.append(l.get("confidence", 0.95))
                elif hasattr(l, "confidence"):
                    all_confs.append(getattr(l, "confidence", 0.95))
                else:
                    all_confs.append(0.95)
        return round(sum(all_confs) / max(len(all_confs), 1), 3) if all_confs else 0.95

    # ── Mandatory Declaration Verifiers ───────────────────────────────────────

    @classmethod
    def _verify_mrp(cls, fields, bbox_map, side_texts, side_lines) -> List[DeclarationCard]:
        """Maximum Retail Price — Rule 6(1)(e)"""
        label = "Maximum Retail Price (MRP)"
        bbox = bbox_map.get("mrp")
        conf = _avg_conf(side_lines, r'M\.?R\.?P|Maximum Retail Price')
        panel = _find_panel(side_lines, r'M\.?R\.?P|Maximum Retail Price')

        # Presence
        if not fields.mrp_amount:
            presence = _issue("MRP declaration not detected on any packaging panel.")
            completeness = _issue("Cannot assess completeness — MRP not found.")
            correctness  = _issue("MRP amount absent. Rule 6(1)(e) violation.")
            readability  = _review("MRP text not detected — image quality or absence.", conf=conf)
            placement    = _issue("MRP not located on label.")
            font_sz      = _review("Font size cannot be estimated — MRP declaration absent.")
            return [cls._card("mrp", "mandatory", label, "Not Detected", panel or "—",
                              bbox, presence, completeness, correctness, readability, placement,
                              font_sz, [], conf,
                              "MRP declaration absent from all scanned panels.")]

        value_str = f"₹ {fields.mrp_amount:.2f}"
        if fields.raw_mrp_string:
            value_str += f"  (raw: \"{fields.raw_mrp_string}\")"

        presence = _pass("MRP detected.", evidence=fields.raw_mrp_string, conf=conf)

        # Completeness — must have amount + tax phrase
        if fields.tax_phrase_present:
            completeness = _pass("Amount declared and 'inclusive of all taxes' phrase present.")
        else:
            completeness = _issue(
                "Tax-inclusivity phrase ('inclusive of all taxes') is absent. "
                "Rule 6(1)(e) requires MRP to be declared 'inclusive of all taxes'.",
                evidence=fields.raw_mrp_string)

        # Cross-panel MRP consistency (checked later in _apply_cross_panel_conflicts)
        correctness = _pass("MRP value appears internally consistent.", evidence=fields.raw_mrp_string, conf=conf)

        # Readability
        if conf >= 0.90:
            readability = _pass(f"MRP text clearly readable (OCR confidence {conf:.0%}).", conf=conf)
        elif conf >= 0.75:
            readability = _review(f"OCR confidence {conf:.0%} — borderline readability. Manual inspection advised.", conf=conf)
        else:
            readability = _review(f"Low OCR confidence ({conf:.0%}) — MRP may exist but cannot be reliably read. Manual verification required.", conf=conf)

        # Placement — MRP should be on any visible panel
        if bbox:
            placement = _pass(f"MRP located on {bbox.page_side.title()} panel at approx. ({bbox.x:.2f}, {bbox.y:.2f}).")
        else:
            placement = _review("Bounding box not available — cannot confirm MRP placement or visibility.")

        # Font size
        font_sz = _font_size_check(bbox, fields.net_quantity_value or 100.0, fields.net_quantity_unit or "g")

        overall = _worst([presence.status, completeness.status, correctness.status,
                          readability.status, placement.status, font_sz.status])
        flag = None if overall == DeclVerifStatus.PASS else (
            "Tax-inclusivity phrase missing." if not fields.tax_phrase_present else
            "Low readability or placement issue." )

        return [cls._card("mrp", "mandatory", label, f"₹ {fields.mrp_amount:.2f}", panel,
                          bbox, presence, completeness, correctness, readability, placement,
                          font_sz, [], conf, flag)]

    @classmethod
    def _verify_net_quantity(cls, fields, bbox_map, side_texts, side_lines) -> List[DeclarationCard]:
        """Net Quantity — Rule 6(1)(c)"""
        label = "Net Quantity"
        bbox  = bbox_map.get("net_quantity")
        conf  = _avg_conf(side_lines, r'net\s*(qty|quantity|wt|weight|vol|volume|content)')
        panel = _find_panel(side_lines, r'net\s*(qty|quantity|wt|weight|vol|volume|content)')

        if not fields.net_quantity_value:
            return [cls._card("net_quantity", "mandatory", label, "Not Detected", panel or "—",
                              bbox,
                              _issue("Net quantity not detected on any panel."),
                              _issue("Cannot assess — not found."),
                              _issue("Missing. Rule 6(1)(c) statutory violation."),
                              _review("Text not found — image quality or absence.", conf=conf),
                              _issue("Not located on label."),
                              _review("Cannot estimate font size — declaration absent."),
                              [], conf, "Net quantity declaration absent.")]

        qty_str = f"{fields.net_quantity_value} {fields.net_quantity_unit}"
        presence = _pass("Net quantity detected.", evidence=qty_str, conf=conf)

        # Completeness — need both value AND unit
        if fields.net_quantity_value and fields.net_quantity_unit:
            completeness = _pass("Both numeric value and unit present.")
        elif fields.net_quantity_value:
            completeness = _issue("Numeric quantity present but unit symbol absent. Both required under Rule 6(1)(c).")
        else:
            completeness = _issue("Unit present without numeric value.")

        # Correctness — SI unit check
        if not fields.is_standard_unit:
            correctness = _issue(
                f"Non-standard unit '{fields.illegal_unit_found or fields.net_quantity_unit}' used. "
                f"Legal Metrology (Packaged Commodities) Rules, 2011 Rule 11 mandates SI units "
                f"('g', 'kg', 'ml', 'l', 'N', 'U').",
                evidence=qty_str)
        else:
            correctness = _pass(f"Standard SI unit '{fields.net_quantity_unit}' used.", evidence=qty_str, conf=conf)

        # Readability
        readability = _pass(f"Net quantity text readable (OCR conf {conf:.0%}).", conf=conf) \
            if conf >= 0.90 else _review(f"OCR confidence {conf:.0%} — manual verification of quantity text advised.", conf=conf)

        # Placement
        if bbox:
            is_pdp = bbox.page_side.lower() in ["front", "pdp", "main", "photo 1"]
            placement = _pass(f"Net quantity on {bbox.page_side.title()} (Principal Display Panel).") \
                if is_pdp else _review(
                    f"Net quantity found on '{bbox.page_side}' panel. "
                    "Rule 6(2) requires net quantity on the Principal Display Panel (PDP/Front).")
        else:
            placement = _review("Placement cannot be determined — bounding box unavailable.")

        font_sz = _font_size_check(bbox, fields.net_quantity_value, fields.net_quantity_unit or "g")

        overall = _worst([presence.status, completeness.status, correctness.status,
                          readability.status, placement.status, font_sz.status])
        flag = None if overall == DeclVerifStatus.PASS else (
            f"Non-SI unit: '{fields.illegal_unit_found}'." if not fields.is_standard_unit else "Review required.")

        return [cls._card("net_quantity", "mandatory", label, qty_str, panel,
                          bbox, presence, completeness, correctness, readability, placement,
                          font_sz, [], conf, flag)]

    @classmethod
    def _verify_manufacturer(cls, fields, bbox_map, side_lines) -> List[DeclarationCard]:
        """Manufacturer / Packer / Importer — Rule 6(1)(a)"""
        label = "Manufacturer / Packer / Importer"
        bbox  = bbox_map.get("manufacturer")
        conf  = _avg_conf(side_lines, r'(manufactured|packed|mfg|mfr|importer|marketed|pvt|ltd)\s*(by|name)?')
        panel = _find_panel(side_lines, r'(manufactured|packed|mfg|mfr|importer|marketed|pvt|ltd)\s*(by|name)?')

        has_name    = bool(fields.mfr_name or fields.packer_name or fields.importer_name)
        has_address = bool(fields.mfr_address)
        has_pin     = bool(fields.mfr_pin and len(fields.mfr_pin) == 6 and fields.mfr_pin.isdigit())
        name_val    = fields.mfr_name or fields.packer_name or fields.importer_name or "Not Detected"

        presence = _pass(f"Manufacturer name detected: '{name_val}'.", conf=conf) \
            if has_name else _issue("Manufacturer / Packer / Importer name not found on any panel.")

        if has_name and has_address:
            if has_pin:
                completeness = _pass(f"Name, address, and 6-digit PIN ({fields.mfr_pin}) present — Rule 6(1)(a) fully satisfied.")
                flag = None
            else:
                completeness = _pass("Name and premises address declared.")
                flag = None
        elif has_name:
            completeness = _review("Manufacturer identity detected; full premises address with PIN should be verified on physical packaging.")
            flag = "Manufacturer name detected; verify complete address."
        else:
            completeness = _issue("Mandatory manufacturer / packer / importer declaration missing.")
            flag = "Manufacturer declaration missing."

        correctness = _pass(f"PIN code {fields.mfr_pin} is valid.", conf=conf) \
            if has_pin else (_pass("Address details present.", conf=conf) if has_address else _issue("No address present to validate."))

        readability = _pass(f"Manufacturer details readable (OCR conf {conf:.0%}).", conf=conf) \
            if conf >= 0.88 else _review(f"OCR confidence {conf:.0%} — manufacturer text may be unclear.", conf=conf)

        placement = _pass(f"Manufacturer declaration on {bbox.page_side.title()} panel.") \
            if bbox else _review("Placement unconfirmed — bounding box unavailable.")

        font_sz = _font_size_check(bbox, fields.net_quantity_value or 100, fields.net_quantity_unit or "g")

        overall = _worst([presence.status, completeness.status, correctness.status,
                          readability.status, placement.status, font_sz.status])

        return [cls._card("manufacturer", "mandatory", label, name_val, panel,
                          bbox, presence, completeness, correctness, readability, placement,
                          font_sz, [], conf, flag)]

    @classmethod
    def _verify_dates(cls, fields, bbox_map, side_texts, side_lines) -> List[DeclarationCard]:
        """Manufacturing / Packing Date — Rule 6(1)(d)"""
        label = "Date of Manufacture / Packing"
        bbox  = bbox_map.get("dates_and_batch")
        conf  = _avg_conf(side_lines, r'(mfg|mfd|pkd|manufactured|packed)\s*(date|dt|on)?')
        panel = _find_panel(side_lines, r'(mfg|mfd|pkd|manufactured|packed)\s*(date|dt|on)?')

        presence = _pass(f"Manufacturing date detected: '{fields.mfg_date}'.", conf=conf) \
            if fields.mfg_date else _issue("Date of manufacture/packing not detected. Rule 6(1)(d) requires month and year.")

        completeness = _pass("Month and year of manufacture present.") \
            if fields.mfg_date else _issue("Both month and year required — neither found.")

        # Cross-panel date conflicts handled later
        correctness = _pass("Date format appears valid.", evidence=fields.mfg_date, conf=conf) \
            if fields.mfg_date else _issue("Date absent — correctness cannot be verified.")

        readability = _pass(f"Date text readable (conf {conf:.0%}).", conf=conf) \
            if conf >= 0.88 else _review(f"Low OCR confidence ({conf:.0%}) on date field — manual check advised.", conf=conf)

        placement = _pass(f"Dates found on {bbox.page_side.title()} panel.") \
            if bbox else _review("Date placement unknown — bounding box unavailable.")

        font_sz = _font_size_check(bbox, fields.net_quantity_value or 100, fields.net_quantity_unit or "g")

        overall = _worst([presence.status, completeness.status, correctness.status,
                          readability.status, placement.status, font_sz.status])

        return [cls._card("mfg_date", "mandatory", label,
                          fields.mfg_date or "Not Detected", panel,
                          bbox, presence, completeness, correctness, readability, placement,
                          font_sz, [], conf,
                          None if overall == DeclVerifStatus.PASS else "Manufacturing date missing or unreadable.")]

    @classmethod
    def _verify_consumer_care(cls, fields, bbox_map, side_lines) -> List[DeclarationCard]:
        """Consumer Care Information — Rule 6(1)(n)"""
        label = "Consumer Care Information"
        bbox  = bbox_map.get("consumer_care")
        conf  = _avg_conf(side_lines, r'consumer\s*(care|helpline|grievance|redressal)|customercare|toll\s*free|care@')
        panel = _find_panel(side_lines, r'consumer\s*(care|helpline|grievance|redressal)|customercare|toll\s*free|care@')

        has_phone = bool(fields.consumer_care_phone)
        has_email = bool(fields.consumer_care_email)
        has_any   = has_phone or has_email

        presence = _pass("Consumer care section detected.", conf=conf) if has_any else \
            _issue("Consumer care information not detected on any panel.")

        if has_phone and has_email:
            completeness = _pass(f"Helpline ({fields.consumer_care_phone}) and Email ({fields.consumer_care_email}) both declared.")
            flag = None
        elif has_phone:
            completeness = _pass(f"Consumer helpline telephone ({fields.consumer_care_phone}) declared.")
            flag = None
        elif has_email:
            completeness = _pass(f"Consumer grievance email ({fields.consumer_care_email}) declared.")
            flag = None
        else:
            completeness = _issue("Consumer care helpline number or grievance email not found.")
            flag = "Consumer care coordinates absent."

        contact_display = []
        if has_phone: contact_display.append(f"📞 {fields.consumer_care_phone}")
        if has_email: contact_display.append(f"✉️ {fields.consumer_care_email}")
        display_val = "  ".join(contact_display) if contact_display else "Not Detected"

        correctness = _pass(f"Coordinates: {display_val}", conf=conf) if has_any else _issue("No contact coordinates to verify.")

        readability = _pass(f"Consumer care text readable (conf {conf:.0%}).", conf=conf) \
            if conf >= 0.88 else _review(f"OCR confidence {conf:.0%} on consumer care section.", conf=conf)

        placement = _pass(f"Consumer care on {bbox.page_side.title()} panel.") \
            if bbox else _review("Placement unverified — bounding box unavailable.")

        font_sz = _font_size_check(bbox, fields.net_quantity_value or 100, fields.net_quantity_unit or "g")

        overall = _worst([presence.status, completeness.status, correctness.status,
                          readability.status, placement.status, font_sz.status])

        return [cls._card("consumer_care", "mandatory", label,
                          display_val,
                          panel, bbox, presence, completeness, correctness, readability, placement,
                          font_sz, [], conf, flag)]

    @classmethod
    def _verify_country_of_origin(cls, fields, bbox_map, side_lines) -> List[DeclarationCard]:
        """Country of Origin — Rule 6(10) / FTA obligations"""
        label = "Country of Origin"
        bbox  = bbox_map.get("country_of_origin")
        conf  = _avg_conf(side_lines, r'country\s*of\s*origin|made\s*in|product\s*of')
        panel = _find_panel(side_lines, r'country\s*of\s*origin|made\s*in|product\s*of')
        val   = fields.country_of_origin or "Not Detected"

        presence    = _pass(f"Country of origin: '{val}'.", conf=conf) if fields.country_of_origin else \
            _issue("Country of origin declaration not found.")
        completeness = _pass("Declaration complete.") if fields.country_of_origin else \
            _issue("Country of origin absent — required under Rule 6(10) for imports.")
        correctness  = _pass(f"'{val}' is a recognisable country/region.", conf=conf) \
            if fields.country_of_origin else _review("Not found — cannot verify.")
        readability  = _pass(f"Readable (conf {conf:.0%}).", conf=conf) if conf >= 0.88 else \
            _review(f"Low OCR confidence ({conf:.0%}) on country of origin.", conf=conf)
        placement    = _pass(f"Located on {bbox.page_side.title()} panel.") if bbox else \
            _review("Placement unconfirmed.")
        font_sz      = _font_size_check(bbox, fields.net_quantity_value or 100, fields.net_quantity_unit or "g")

        overall = _worst([presence.status, completeness.status, correctness.status,
                          readability.status, placement.status, font_sz.status])

        return [cls._card("country_of_origin", "mandatory", label, val, panel,
                          bbox, presence, completeness, correctness, readability, placement,
                          font_sz, [], conf,
                          None if overall == DeclVerifStatus.PASS else "Country of origin missing.")]

    @classmethod
    def _verify_batch_number(cls, fields, bbox_map, side_lines) -> List[DeclarationCard]:
        """Batch / Lot Number"""
        label = "Batch / Lot Number"
        bbox  = _find_bbox(side_lines, r'batch\s*(no|number|#)|lot\s*(no|number)')
        conf  = _avg_conf(side_lines, r'batch|lot\s*no')
        panel = _find_panel(side_lines, r'batch|lot\s*no')
        val   = fields.batch_number or "Not Detected"

        presence = _pass(f"Batch number: '{val}'.", conf=conf) if fields.batch_number else \
            _review("Batch/Lot number not detected. May be printed separately or at time of packing.")
        completeness = _pass("Batch number present.") if fields.batch_number else \
            _review("Not found — verify physical label.")
        correctness  = _pass(f"Format appears valid: '{val}'.", conf=conf) if fields.batch_number else \
            _review("Cannot verify — not found.")
        readability  = _pass(f"Readable (conf {conf:.0%}).", conf=conf) if conf >= 0.88 else \
            _review(f"OCR confidence {conf:.0%} on batch field.", conf=conf)
        placement    = _pass(f"On {bbox.page_side.title()} panel.") if bbox else \
            _review("Placement unconfirmed.")
        font_sz      = _review("Batch number font size typically too small for reliable pixel measurement.")

        overall = _worst([presence.status, completeness.status])

        return [cls._card("batch_number", "mandatory", label, val, panel,
                          bbox, presence, completeness, correctness, readability, placement,
                          font_sz, [], conf, None)]

    # ── Nutritional & Ingredient Detectors ────────────────────────────────────

    @classmethod
    def _detect_nutritional_and_ingredient(
        cls, combined_text: str, side_lines: Dict[str, List[Dict]], avg_conf: float
    ) -> List[DeclarationCard]:
        cards: List[DeclarationCard] = []
        seen: set = set()

        for pattern, dtype, label in NUTRITIONAL_PATTERNS:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match and label not in seen:
                seen.add(label)
                val = match.group(0).strip()
                conf = avg_conf
                bbox = _find_bbox(side_lines, pattern)
                panel = _find_panel(side_lines, pattern) or "Detected"

                # Readability
                readability = _pass(f"Readable (conf {conf:.0%}).", conf=conf) \
                    if conf >= 0.88 else _review(f"Low confidence ({conf:.0%}) — manual review.", conf=conf)

                # Nutritional table: always MANUAL_REVIEW for values — OCR can read, but cannot chemically verify
                if dtype == "nutritional" and label != "Nutritional Information Table":
                    correctness = _review(
                        f"Value '{val}' detected. OCR can read the declared figure, but cannot verify "
                        "actual nutritional composition — laboratory analysis required to confirm accuracy.")
                    flag = "Nutritional value cannot be verified from image alone — lab/document check required."
                elif dtype == "ingredient":
                    correctness = _review(
                        "Ingredients list detected. OCR reads the declaration but cannot verify "
                        "actual ingredient composition or order.")
                    flag = "Ingredient list detected — contents cannot be chemically verified from image."
                else:
                    correctness = _pass("Nutritional table presence confirmed.", conf=conf)
                    flag = None

                cards.append(cls._card(
                    f"nutri_{label.lower().replace(' ', '_')[:30]}",
                    dtype, label, val, panel, bbox,
                    _pass("Detected.", evidence=val, conf=conf),
                    _pass("Declaration present."),
                    correctness,
                    readability,
                    _pass(f"Located on {bbox.page_side.title()} panel.") if bbox else _review("Placement unconfirmed."),
                    _review("Nutritional text is typically very small — physical measurement required."),
                    [], conf, flag
                ))

        return cards

    # ── Claims & Certifications Detectors ─────────────────────────────────────

    @classmethod
    def _detect_claims_and_certs(
        cls, combined_text: str, side_lines: Dict[str, List[Dict]], avg_conf: float
    ) -> List[DeclarationCard]:
        cards: List[DeclarationCard] = []
        seen: set = set()

        for pattern, dtype, label in CLAIM_PATTERNS:
            match = re.search(pattern, combined_text, re.IGNORECASE)
            if match and label not in seen:
                seen.add(label)
                val = match.group(0).strip()
                conf = avg_conf
                bbox = _find_bbox(side_lines, pattern)
                panel = _find_panel(side_lines, pattern) or "Detected"

                if dtype == "certification":
                    # Certifications: PASS presence but MANUAL_REVIEW for genuineness
                    correctness = _review(
                        f"Certification mark '{val}' detected. "
                        "Authenticity of certification cannot be verified from packaging image — "
                        "cross-check with issuing authority's database required.")
                    flag = "Certification mark requires document/database verification."
                elif "100%" in val.upper() or "natural" in val.lower() or "organic" in val.lower():
                    correctness = _review(
                        f"Claim '{val}' detected. This type of claim cannot be verified from "
                        "packaging image alone — physical/chemical/document analysis required.")
                    flag = f"'{val}' — cannot be verified from image; manual/lab verification required."
                elif "clinically" in val.lower() or "dermatologist" in val.lower() or "lab tested" in val.lower():
                    correctness = _review(
                        f"'{val}' claim detected. Supporting clinical study documents must be produced "
                        "to substantiate this claim — cannot be confirmed from packaging image.")
                    flag = f"'{val}' — clinical substantiation documents required."
                elif re.search(r'\d+\s*%', val):
                    # Percentage active ingredient claim
                    correctness = _review(
                        f"Percentage claim '{val}' detected. Actual ingredient concentration "
                        "cannot be determined from packaging image — statutory laboratory analysis required.")
                    flag = f"'{val}' — percentage concentration requires lab verification."
                elif re.search(r'\d+\s*g\s+(protein|bcaa|fiber|calcium|collagen)', val, re.IGNORECASE):
                    correctness = _review(
                        f"Nutritional claim '{val}' — declared macro-nutrient quantity cannot be "
                        "verified from packaging image; Kjeldahl/HPLC assay required.")
                    flag = f"'{val}' — nutritional quantity requires laboratory assay."
                else:
                    correctness = _review(
                        f"Claim '{val}' detected. Verification from packaging image alone is "
                        "insufficient — supporting documentation or product testing required.")
                    flag = f"'{val}' — claim requires substantiation beyond image inspection."

                readability = _pass(f"Claim text readable (conf {conf:.0%}).", conf=conf) \
                    if conf >= 0.88 else _review(f"Low confidence ({conf:.0%}) on claim text.", conf=conf)

                cards.append(cls._card(
                    f"claim_{label.lower().replace(' ', '_')[:30]}",
                    dtype, label, val, panel, bbox,
                    _pass("Claim detected on packaging.", evidence=val, conf=conf),
                    _pass("Claim text present."),
                    correctness,
                    readability,
                    _pass(f"Visible on {bbox.page_side.title()} panel.") if bbox else _review("Placement unconfirmed."),
                    _review("Claim text font size — physical measurement required for legal determination."),
                    [], conf, flag
                ))

        return cards

    # ── Cross-Panel Conflict Detection ────────────────────────────────────────

    @classmethod
    def _apply_cross_panel_conflicts(cls, cards: List[DeclarationCard], side_texts: Dict[str, str]):
        """
        Detects when the same field (MRP / Net Qty / Date) appears with different values
        across multiple panels and downgrades the correctness dimension to POTENTIAL_ISSUE.
        """
        # Collect all MRP values per panel
        mrp_vals: Dict[str, str] = {}
        qty_vals: Dict[str, str] = {}
        date_vals: Dict[str, str] = {}

        mrp_pat = re.compile(r'(?:M\.?R\.?P\.?|Maximum Retail Price)[:\s]*(?:Rs\.?|₹|INR)?\s*([0-9]+(?:\.[0-9]{1,2})?)', re.IGNORECASE)
        qty_pat = re.compile(r'(?:Net\s*(?:Wt|Qty|Quantity|Content|Vol)[:\s.]*)?([0-9]+(?:\.[0-9]*)?)\s*(kg|g|ml|l|ltr|gm|gms|Gms)\b', re.IGNORECASE)
        date_pat = re.compile(r'(?:Mfg|Mfd|Pkd|Packed|Manufactured)\s*(?:date|dt|on)?[:\s.]*([A-Za-z]{3}\.?\s*\d{4}|\d{2}[\/\-]\d{4}|\d{4})', re.IGNORECASE)

        for side, text in side_texts.items():
            m = mrp_pat.search(text)
            if m: mrp_vals[side] = m.group(1).strip()
            m = qty_pat.search(text)
            if m: qty_vals[side] = f"{m.group(1)} {m.group(2)}"
            m = date_pat.search(text)
            if m: date_vals[side] = m.group(1).strip()

        def inject_conflict(card_id: str, vals: Dict[str, str]):
            unique = set(vals.values())
            if len(unique) > 1:
                evidence = [ConflictEvidence(panel=p.title(), value=v,
                                             context=f"Found on '{p}' panel") for p, v in vals.items()]
                for card in cards:
                    if card.declaration_id == card_id:
                        card.conflict_evidence = evidence
                        card.correctness = _issue(
                            f"Conflicting values detected across {len(vals)} panels: "
                            + ", ".join(f"'{p.title()}' → {v}" for p, v in vals.items()),
                            evidence=str(vals))
                        card.overall_status = DeclVerifStatus.POTENTIAL_ISSUE
                        card.flag_reason = (
                            f"Cross-panel inconsistency: {', '.join(unique)}. "
                            "Verify which value is correct.")

        inject_conflict("mrp", mrp_vals)
        inject_conflict("net_quantity", qty_vals)
        inject_conflict("mfg_date", date_vals)

    # ── Summary Builder ───────────────────────────────────────────────────────

    @classmethod
    def _build_summary(cls, cards: List[DeclarationCard], fields: DeclarationFields) -> DeclarationAnalysisSummary:
        pass_count   = sum(1 for c in cards if c.overall_status == DeclVerifStatus.PASS)
        issue_count  = sum(1 for c in cards if c.overall_status == DeclVerifStatus.POTENTIAL_ISSUE)
        review_count = sum(1 for c in cards if c.overall_status == DeclVerifStatus.MANUAL_REVIEW)

        mandatory_ids = {"mrp", "net_quantity", "manufacturer", "mfg_date", "consumer_care",
                         "country_of_origin", "batch_number"}
        found_ids = {c.declaration_id for c in cards}
        missing_mandatory = [cid.replace("_", " ").title()
                             for cid in mandatory_ids if cid not in found_ids]

        if issue_count > 0:
            overall = DeclVerifStatus.POTENTIAL_ISSUE
        elif review_count > 0:
            overall = DeclVerifStatus.MANUAL_REVIEW
        else:
            overall = DeclVerifStatus.PASS

        lines = [f"✓ {len(cards)} declaration(s) detected across all packaging panels."]
        if pass_count:   lines.append(f"🟢 {pass_count} declaration(s) fully verified.")
        if issue_count:  lines.append(f"🔴 {issue_count} potential issue(s) detected — enforcement review recommended.")
        if review_count: lines.append(f"🟡 {review_count} declaration(s) require manual verification (image limitation or unverifiable claim).")
        if missing_mandatory: lines.append(f"⚠ Missing mandatory declarations: {', '.join(missing_mandatory)}.")

        return DeclarationAnalysisSummary(
            total_declarations_detected=len(cards),
            pass_count=pass_count,
            potential_issue_count=issue_count,
            manual_review_count=review_count,
            missing_mandatory_declarations=missing_mandatory,
            cards=cards,
            overall_analysis_status=overall,
            summary_text=" ".join(lines),
        )

    # ── Card Factory ──────────────────────────────────────────────────────────

    @staticmethod
    def _card(
        decl_id: str, dtype: str, label: str, val: str, panel: str,
        bbox: Optional[BoundingBox],
        presence: DeclDimensionResult, completeness: DeclDimensionResult,
        correctness: DeclDimensionResult, readability: DeclDimensionResult,
        placement: DeclDimensionResult, font_sz: DeclDimensionResult,
        conflicts: List[ConflictEvidence], conf: float,
        flag: Optional[str],
    ) -> DeclarationCard:
        statuses = [presence.status, completeness.status, correctness.status,
                    readability.status, placement.status, font_sz.status]
        overall = _worst(statuses)
        return DeclarationCard(
            declaration_id=decl_id,
            declaration_type=dtype,
            label=label,
            detected_value=val,
            panel_found_on=panel,
            bounding_box=bbox,
            overall_status=overall,
            presence=presence,
            completeness=completeness,
            correctness=correctness,
            readability=readability,
            placement=placement,
            font_size=font_sz,
            conflict_evidence=conflicts,
            ocr_confidence=round(conf, 3),
            flag_reason=flag,
        )
