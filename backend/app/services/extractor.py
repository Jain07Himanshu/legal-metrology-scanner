"""
Field & Entity Extraction (NER + Regular Expressions) for Legal Metrology Scanner.
Extracts MRP, Net Quantity, Units, Manufacturer Address, Consumer Care details, Dates, and Claims.
"""
import re
from typing import Dict, Any, List, Optional, Tuple
from app.models.schemas import DeclarationFields, ActiveClaim, BoundingBox
from app.config import LEGAL_UNITS, ILLEGAL_UNITS

class FieldExtractor:

    @classmethod
    def extract_all(cls, ocr_results: Dict[str, Any]) -> Tuple[DeclarationFields, Dict[str, BoundingBox]]:
        """
        Parses OCR results across all sides and compiles the structured DeclarationFields.
        Returns extracted fields along with bounding box references for UI overlays.
        """
        combined_text = ""
        side_texts: Dict[str, str] = {}
        side_lines: Dict[str, List[Dict[str, Any]]] = {}
        bbox_map: Dict[str, BoundingBox] = {}

        for side, res in ocr_results.items():
            text = res.get("full_text", "")
            side_texts[side] = text
            side_lines[side] = res.get("lines", [])
            combined_text += f"\n--- {side.upper()} ---\n" + text

        fields = DeclarationFields(raw_extracted_text=side_texts)

        # 1. Extract Generic Name
        cls._extract_generic_name(side_texts, fields, bbox_map, side_lines)

        # 2. Extract MRP & Pricing
        cls._extract_mrp(combined_text, fields, bbox_map, side_lines)

        # 3. Extract Net Quantity & Unit Validity
        cls._extract_net_quantity(combined_text, fields, bbox_map, side_lines)

        # 4. Extract Manufacturer / Packer / Importer Details
        cls._extract_manufacturer_details(combined_text, fields, bbox_map, side_lines)

        # 5. Extract Consumer Care Grievance Details
        cls._extract_consumer_care(combined_text, fields, bbox_map, side_lines)

        # 6. Extract Manufacturing & Expiry Dates
        cls._extract_dates_and_batch(combined_text, fields, bbox_map, side_lines)

        # 7. Extract Country of Origin
        cls._extract_country_of_origin(combined_text, fields, bbox_map, side_lines)

        # 8. Extract Statutory Certifications (FSSAI / BIS)
        cls._extract_certifications(combined_text, fields)

        # 9. Extract Food, Ingredients & Nutrition Details
        cls._extract_food_and_nutrition(combined_text, fields)

        # 10. Extract Active Claims for Section 15 Lab Verification
        cls._extract_active_claims(combined_text, fields)

        # 11. Estimate Font Heights
        cls._estimate_font_sizes(fields, bbox_map)

        return fields, bbox_map

    @classmethod
    def _find_line_bbox(cls, regex_pattern: str, side_lines: Dict[str, List[Dict[str, Any]]]) -> Optional[BoundingBox]:
        """Helper to find bounding box of a line matching regex."""
        for side, lines in side_lines.items():
            for line in lines:
                if re.search(regex_pattern, line.get("text", ""), re.IGNORECASE):
                    box_dict = line.get("bbox", {})
                    return BoundingBox(
                        x=box_dict.get("x", 0.1),
                        y=box_dict.get("y", 0.1),
                        width=box_dict.get("width", 0.4),
                        height=box_dict.get("height", 0.05),
                        page_side=side
                    )
        return None

    @classmethod
    def _extract_generic_name(cls, side_texts: Dict[str, str], fields: DeclarationFields, bbox_map: Dict[str, BoundingBox], side_lines: Dict[str, List[Dict[str, Any]]]):
        front_text = (
            side_texts.get("front")
            or side_texts.get("FRONT Panel")
            or side_texts.get("Photo 1")
            or side_texts.get("Photo 1 Panel")
            or (list(side_texts.values())[0] if side_texts else "")
        )
        # Common commodities or generic patterns
        lines = [l.strip() for l in front_text.split("\n") if len(l.strip()) > 2]
        
        # Look for explicit Generic Name tag across any panel
        combined_all = "\n".join(side_texts.values())
        match = re.search(r'(?:Generic Name|Product Name|Commodity|Item)\s*[:\-]\s*([A-Za-z0-9\s,\-]+)', combined_all, re.IGNORECASE)
        if match:
            fields.generic_name = match.group(1).strip()
        elif lines:
            # Often first 1-2 lines on front panel are Brand and Generic Name
            fields.brand_name = lines[0]
            if len(lines) > 1:
                fields.generic_name = lines[1]
            else:
                fields.generic_name = lines[0]
        else:
            fields.generic_name = "Packaged Commodity"

        bbox = cls._find_line_bbox(r'(?:Generic Name|Product Name|Basmati|Biscuit|Oil|Serum|Flour|Soap|Atta)', side_lines)
        if bbox:
            bbox_map["generic_name"] = bbox

    @classmethod
    def _extract_mrp(cls, text: str, fields: DeclarationFields, bbox_map: Dict[str, BoundingBox], side_lines: Dict[str, List[Dict[str, Any]]]):
        # Match MRP strings e.g. "MRP Rs. 249.00 (incl. of all taxes)", "MRP ₹ 150 (inclusive of all taxes)"
        mrp_pattern = re.compile(
            r'(?:M\.?R\.?P\.?|Maximum Retail Price|Price|Max\. Retail Price)\s*[:\-]?\s*(?:Rs\.?|₹|INR)?\s*([0-9]+(?:\.[0-9]{1,2})?)',
            re.IGNORECASE
        )
        match = mrp_pattern.search(text)
        if match:
            fields.mrp_amount = float(match.group(1))
            fields.raw_mrp_string = match.group(0)
            fields.currency_symbol = "₹" if "₹" in text else "Rs."

        # Check for mandatory tax inclusivity phrase
        tax_pattern = re.compile(
            r'(?:incl(?:usive)?\s*(?:of)?\s*(?:all)?\s*taxes|incl\.?\s*taxes|inclusive\s*of\s*all\s*taxes)',
            re.IGNORECASE
        )
        if tax_pattern.search(text):
            fields.tax_phrase_present = True
        else:
            fields.tax_phrase_present = False

        # Check Unit Sale Price (USP) under 2022 Amendment
        usp_pattern = re.compile(
            r'(?:Unit Sale Price|USP|U\.S\.P\.?)\s*[:\-]?\s*(?:Rs\.?|₹)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(?:/|per)\s*(?:g|kg|ml|l|piece|unit|100g|100ml)',
            re.IGNORECASE
        )
        usp_match = usp_pattern.search(text)
        if usp_match:
            fields.unit_sale_price = usp_match.group(0).strip()

        # Check for smudged or price sticker overlay
        if re.search(r'(?:sticker price|affixed sticker|overwritten price|dual mrp)', text, re.IGNORECASE):
            fields.has_price_sticker_overlay = True

        bbox = cls._find_line_bbox(r'(?:M\.?R\.?P\.?|Maximum Retail Price)', side_lines)
        if bbox:
            bbox_map["mrp"] = bbox

    @classmethod
    def _extract_net_quantity(cls, text: str, fields: DeclarationFields, bbox_map: Dict[str, BoundingBox], side_lines: Dict[str, List[Dict[str, Any]]]):
        # Match Net Quantity patterns e.g. "Net Qty: 500 g", "Net Weight: 1 kg", "Net Content: 200 ml", "Net Qty: 100 gm"
        qty_pattern = re.compile(
            r'(?:Net\s*(?:Qty|Quantity|Weight|Wt|Content|Volume|Vol))\s*[:\-]?\s*([0-9]+(?:\.[0-9]{1,3})?)\s*([A-Za-z\.]+)',
            re.IGNORECASE
        )
        match = qty_pattern.search(text)
        if not match:
            # Fallback simple number + unit
            match = re.search(r'\b([0-9]+(?:\.[0-9]{1,3})?)\s*(g|kg|gm|gms|ml|l|L|mL|N|U|KG|GM)\b', text)

        if match:
            val_str = match.group(1)
            unit_str = match.group(2).strip()
            fields.net_quantity_value = float(val_str)
            fields.net_quantity_unit = unit_str
            fields.raw_net_quantity_string = f"{val_str} {unit_str}"

            # Check legality of the unit
            # Normalize casing
            if unit_str in ILLEGAL_UNITS:
                fields.is_standard_unit = False
                fields.illegal_unit_found = unit_str
            elif unit_str.lower() in [u.lower() for cat in LEGAL_UNITS.values() for u in cat]:
                # Check for capital 'KG' or 'G' which violates SI rule
                if unit_str in ["KG", "G", "ML", "LTS", "Gm"]:
                    fields.is_standard_unit = False
                    fields.illegal_unit_found = unit_str
                else:
                    fields.is_standard_unit = True
            else:
                fields.is_standard_unit = False
                fields.illegal_unit_found = unit_str

        bbox = cls._find_line_bbox(r'(?:Net\s*(?:Qty|Quantity|Weight|Content|Volume)|\b(?:500\s*g|1\s*kg|200\s*ml|100\s*gm)\b)', side_lines)
        if bbox:
            bbox_map["net_quantity"] = bbox

    @classmethod
    def _extract_manufacturer_details(cls, text: str, fields: DeclarationFields, bbox_map: Dict[str, BoundingBox], side_lines: Dict[str, List[Dict[str, Any]]]):
        # 1. Broad prefix pattern matching
        mfr_pattern = re.compile(
            r'(?:Manufactured\s*(?:&|and)?\s*Packed\s*by|Manufactured\s*in\s*India\s*by|Manufactured\s*by|Mfg\.?\s*(?:&|and)?\s*Pkd\.?\s*by|Mfg\.?\s*by|Mfd\.?\s*by|Produced\s*by|Packed\s*by|Pkd\.?\s*by|Marketed\s*by|Mkt\.?\s*by|Imported\s*(?:&|and)?\s*Distributed\s*by|Imported\s*by|Distributed\s*by|Packaged\s*by|Processor|Manufacturer|Packer|Marketer|Importer|Regd\.?\s*Office|Factory)\s*[:\-]?\s*([^\n\r]+(?:\n[^\n\r]+){0,5})',
            re.IGNORECASE
        )
        match = mfr_pattern.search(text)
        if match:
            full_block = match.group(0).strip()
            lines = [l.strip() for l in full_block.split("\n") if l.strip()]
            fields.mfr_name = lines[0] if lines else "Identified Manufacturer"
            fields.mfr_address = ", ".join(lines[1:]) if len(lines) > 1 else full_block
        else:
            # Fallback: Look for company entity names (Pvt Ltd, Ltd, LLP, Industries, Foods, Labs)
            company_match = re.search(
                r'([A-Z0-9][A-Za-z0-9\s,\.\-&]+(?:Pvt\.?\s*Ltd\.?|Private\s*Limited|Ltd\.?|Limited|LLP|Industries|Enterprises|Foods|Agro|Laboratories|Labs|Cosmetics|Healthcare|Beverages|Products|Mills)[^\n\r]*(?:\n[^\n\r]+){0,3})',
                text
            )
            if company_match:
                full_block = company_match.group(0).strip()
                lines = [l.strip() for l in full_block.split("\n") if l.strip()]
                fields.mfr_name = lines[0] if lines else "Identified Manufacturer"
                fields.mfr_address = ", ".join(lines[1:]) if len(lines) > 1 else full_block

        # 2. Extract PIN code (6-digit postal index code anywhere in text or near address)
        pin_match = re.search(r'\b([1-9][0-9]{2}\s?[0-9]{3})\b', text)
        if pin_match:
            fields.mfr_pin = pin_match.group(1).replace(" ", "")

        bbox = cls._find_line_bbox(r'(?:Manufactured|Mfg|Marketed|Packed|Pvt\.?\s*Ltd|Limited|Imported)', side_lines)
        if bbox:
            bbox_map["manufacturer"] = bbox

    @classmethod
    def _extract_consumer_care(cls, text: str, fields: DeclarationFields, bbox_map: Dict[str, BoundingBox], side_lines: Dict[str, List[Dict[str, Any]]]):
        # 1. Phone extraction - toll-free, mobile (+91), or landline with STD codes
        phone_matches = re.findall(
            r'(?:1800[\s\-]?[0-9]{2,4}[\s\-]?[0-9]{2,4}[\s\-]?[0-9]{0,4}|1860[\s\-]?[0-9]{2,4}[\s\-]?[0-9]{2,4}|\+?91[\s\-]?[6-9][0-9]{4}[\s\-]?[0-9]{5}|\+?91[\s\-]?[6-9][0-9]{9}|0[0-9]{2,4}[\s\-]?[0-9]{6,8}|[6-9][0-9]{4}[\s\-]?[0-9]{5}|[6-9][0-9]{9})',
            text
        )
        if phone_matches:
            # Pick first valid phone candidate and clean it
            clean_phone = phone_matches[0].strip().rstrip(",.- ")
            fields.consumer_care_phone = clean_phone

        # 2. Email extraction across the entire packaging text
        email_match = re.search(r'\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b', text)
        if email_match:
            fields.consumer_care_email = email_match.group(1).strip().rstrip(".,;")

        # 3. Officer Name / Grievance Designation
        care_officer_match = re.search(r'(?:Consumer\s*Care|Customer\s*Care|Customer\s*Support|Grievance|Helpdesk)\s*(?:Executive|Officer|Manager|Cell|Representative)?', text, re.IGNORECASE)
        if care_officer_match:
            fields.consumer_care_name = care_officer_match.group(0).strip()
        elif fields.consumer_care_phone or fields.consumer_care_email:
            fields.consumer_care_name = "Consumer Care Executive"

        # 4. Care Address
        care_addr_match = re.search(r'(?:Write\s*to|Customer\s*Care\s*Address|Address)\s*[:\-]?\s*([^\n\r]+)', text, re.IGNORECASE)
        if care_addr_match:
            fields.consumer_care_address = care_addr_match.group(1).strip()
        elif fields.consumer_care_phone or fields.consumer_care_email:
            fields.consumer_care_address = "Provided at Consumer Care coordinates / Registered Office"

        bbox = cls._find_line_bbox(r'(?:Consumer\s*Care|Customer\s*Care|Helpline|feedback|care@|Toll\s*Free|Tollfree|Contact)', side_lines)
        if bbox:
            bbox_map["consumer_care"] = bbox

    @classmethod
    def _extract_dates_and_batch(cls, text: str, fields: DeclarationFields, bbox_map: Dict[str, BoundingBox], side_lines: Dict[str, List[Dict[str, Any]]]):
        # Mfg Date
        mfg_match = re.search(
            r'(?:Mfg\.?\s*Date|Date\s*of\s*Mfg|Packed\s*on|PKD|Mfg|Mfg\.?|Packed)\s*[:\-]?\s*([0-9]{1,2}[/\-\.][0-9]{2,4}|[A-Za-z]{3,9}\s*[0-9]{2,4})',
            text,
            re.IGNORECASE
        )
        if mfg_match:
            fields.mfg_date = mfg_match.group(1).strip()

        # Expiry / Best Before
        exp_match = re.search(
            r'(?:Exp\.?\s*Date|Expiry\s*Date|Use\s*by|Best\s*Before)\s*[:\-]?\s*([0-9]{1,2}[/\-\.][0-9]{2,4}|[A-Za-z]{3,9}\s*[0-9]{2,4}|[0-9]{1,2}\s*Months)',
            text,
            re.IGNORECASE
        )
        if exp_match:
            fields.expiry_date = exp_match.group(1).strip()

        # Batch No
        batch_match = re.search(
            r'(?:Batch\s*(?:No\.?|Number)|Lot\s*(?:No\.?|Number)|B\.?\s*No\.?)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)',
            text,
            re.IGNORECASE
        )
        if batch_match:
            fields.batch_number = batch_match.group(1).strip()

        bbox = cls._find_line_bbox(r'(?:Mfg|PKD|Exp|Batch|Lot)', side_lines)
        if bbox:
            bbox_map["dates_and_batch"] = bbox

    @classmethod
    def _extract_country_of_origin(cls, text: str, fields: DeclarationFields, bbox_map: Dict[str, BoundingBox], side_lines: Dict[str, List[Dict[str, Any]]]):
        origin_match = re.search(
            r'(?:Country\s*of\s*Origin|Made\s*in|Product\s*of)\s*[:\-]?\s*([A-Za-z\s]+)',
            text,
            re.IGNORECASE
        )
        if origin_match:
            country = origin_match.group(1).split("\n")[0].strip()
            # Clean trailing punctuation
            country = re.sub(r'[^A-Za-z\s]', '', country).strip()
            fields.country_of_origin = country

        bbox = cls._find_line_bbox(r'(?:Country\s*of\s*Origin|Made\s*in|Product\s*of)', side_lines)
        if bbox:
            bbox_map["country_of_origin"] = bbox

    @classmethod
    def _extract_certifications(cls, text: str, fields: DeclarationFields):
        # FSSAI
        fssai_match = re.search(r'\b(?:fssai|Lic\.?\s*No\.?)\s*[:\-]?\s*([1-2][0-9]{13})\b', text, re.IGNORECASE)
        if fssai_match:
            fields.fssai_license = fssai_match.group(1).strip()

        # BIS / ISI
        bis_match = re.search(r'\b(?:ISI|BIS|CM/L[\s\-]?\s*[0-9]+|IS\s*[0-9]+)\b', text, re.IGNORECASE)
        if bis_match:
            fields.bis_isi_mark = bis_match.group(0).strip()

    @classmethod
    def _extract_food_and_nutrition(cls, text: str, fields: DeclarationFields):
        """Extracts ingredients list, vegetarian green/brown dot status, and nutritional values table."""
        # 1. Ingredients List
        ing_match = re.search(
            r'(?:Ingredients?|Contains)\s*[:\-]?\s*([^\n\r]+(?:\n[^\n\r]+){0,4})',
            text,
            re.IGNORECASE
        )
        if ing_match:
            fields.ingredients_text = ing_match.group(1).strip()

        # 2. Vegetarian / Non-Vegetarian Status
        if re.search(r'(?:100%\s*Vegetarian|Green\s*Dot|Veg\s*Logo|Vegetarian|Vegan|\bVeg\b)', text, re.IGNORECASE):
            fields.vegetarian_status = "VEGETARIAN (Green Dot)"
        elif re.search(r'(?:Non[\s\-]?Veg|Contains\s*Egg|Contains\s*Fish|Contains\s*Meat|Brown\s*Dot)', text, re.IGNORECASE):
            fields.vegetarian_status = "NON-VEGETARIAN (Brown Dot)"
        else:
            fields.vegetarian_status = "Standard Packaged Commodity"

        # 3. Nutritional Values extraction
        nutri_dict = {}
        nutri_patterns = [
            ("Energy", r'(?:Energy|Calories)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*(?:kcal|kj|Cal))'),
            ("Protein", r'(?:Protein)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Carbohydrates", r'(?:Carbohydrates?|Total\s*Carbs?|Carbs)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Total Sugars", r'(?:Total\s*Sugars?|Sugars?|of\s*which\s*sugars?)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Added Sugars", r'(?:Added\s*Sugars?)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Total Fat", r'(?:Total\s*Fat|Fat)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Saturated Fat", r'(?:Saturated\s*Fat|Saturates)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Trans Fat", r'(?:Trans\s*Fat)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Dietary Fibre", r'(?:Dietary\s*Fibre?|Fiber|Fibre)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*g)'),
            ("Sodium", r'(?:Sodium|Salt)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*(?:mg|g))'),
            ("Cholesterol", r'(?:Cholesterol)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?\s*mg)'),
        ]
        for name, pat in nutri_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                nutri_dict[name] = m.group(1).strip()

        fields.nutritional_values = nutri_dict

    @classmethod
    def _extract_active_claims(cls, text: str, fields: DeclarationFields):
        """
        Extracts active chemical, percentage, and nutritional claims.
        Flags them for Section 15 statutory laboratory verification.
        """
        claims: List[ActiveClaim] = []

        # Percentage composition claims (e.g. 20% Vitamin C, 10% Niacinamide, 100% Pure, 0% Trans Fat)
        claim_matches = re.finditer(
            r'([0-9]+(?:\.[0-9]+)?\s*%\s*(?:Vitamin\s*[A-Z]|Niacinamide|Salicylic\s*Acid|Fruit\s*Extract|Pure\s*Badam\s*Oil|Cotton|Almond\s*Oil|Active\s*Ingredients|Zinc|Protein|Juice|Aloe\s*Vera))',
            text,
            re.IGNORECASE
        )
        for m in claim_matches:
            full_claim = m.group(1).strip()
            claims.append(
                ActiveClaim(
                    claim_text=full_claim,
                    claim_type="chemical_or_active_percentage",
                    claimed_percentage_or_val=full_claim,
                    label_ingredient_declaration="Cross-check with Schedule V / Ingredients list",
                    status="FLAGGED_FOR_LAB",
                    legal_rationale="Under Section 15 of the Legal Metrology Act, 2009, numerical active composition claims cannot be verified by optical surface inspection alone and are flagged for statutory chemical testing."
                )
            )

        # Protein / Nutrition claims (e.g. 24g Protein per scoop, 0g Trans Fat)
        nutri_matches = re.finditer(
            r'([0-9]+\s*g\s*(?:Protein|BCAA|Fiber|Calcium|Collagen))',
            text,
            re.IGNORECASE
        )
        for m in nutri_matches:
            c_text = m.group(1).strip()
            claims.append(
                ActiveClaim(
                    claim_text=c_text,
                    claim_type="nutritional_claim",
                    claimed_percentage_or_val=c_text,
                    status="FLAGGED_FOR_LAB",
                    legal_rationale="Declared macro-nutrient potency requires quantitative HPLC / Kjeldahl laboratory assay to verify compliance against FSSAI/Legal Metrology standards."
                )
            )

        fields.active_claims = claims

    @classmethod
    def _estimate_font_sizes(cls, fields: DeclarationFields, bbox_map: Dict[str, BoundingBox]):
        # Default estimable character heights (normalized ratio * 120mm label height)
        if "mrp" in bbox_map:
            h_norm = bbox_map["mrp"].height
            fields.estimated_mrp_font_height_mm = round(h_norm * 120.0, 2)
        else:
            fields.estimated_mrp_font_height_mm = 2.8

        if "net_quantity" in bbox_map:
            h_norm = bbox_map["net_quantity"].height
            fields.estimated_qty_font_height_mm = round(h_norm * 120.0, 2)
        else:
            fields.estimated_qty_font_height_mm = 2.4
