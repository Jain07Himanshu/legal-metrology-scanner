"""
Pydantic schemas and data models for Legal Metrology Scanner.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
import datetime

class ComplianceStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    FLAGGED_FOR_LAB = "FLAGGED_FOR_LAB"
    MANUAL_REVIEW = "MANUAL_REVIEW"

class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    LAB_VERIFY = "LAB_VERIFY"
    INCONCLUSIVE = "INCONCLUSIVE"

class SideType(str, Enum):
    FRONT = "front"
    BACK = "back"
    TOP = "top"
    SIDE = "side"

class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float
    page_side: str = "back"

class ImageQualityMetrics(BaseModel):
    blur_score: float
    is_sharp: bool
    glare_percentage: float
    has_excessive_glare: bool
    brightness: float
    dpi_estimate: float
    quality_verdict: str  # "Good", "Acceptable", "Poor"

class SideImage(BaseModel):
    side_type: SideType
    image_base64: Optional[str] = None
    image_url: Optional[str] = None
    quality_metrics: Optional[ImageQualityMetrics] = None

class ActiveClaim(BaseModel):
    claim_text: str
    claim_type: str  # "chemical", "nutritional", "organic", "purity"
    claimed_percentage_or_val: Optional[str] = None
    label_ingredient_declaration: Optional[str] = None
    status: str = "FLAGGED_FOR_LAB"
    legal_rationale: str

class DeclarationFields(BaseModel):
    generic_name: Optional[str] = None
    brand_name: Optional[str] = None
    category: Optional[str] = "FMCG"
    
    # MRP & Price
    mrp_amount: Optional[float] = None
    currency_symbol: Optional[str] = None
    tax_phrase_present: bool = False
    raw_mrp_string: Optional[str] = None
    unit_sale_price: Optional[str] = None
    has_price_sticker_overlay: bool = False
    
    # Net Quantity
    net_quantity_value: Optional[float] = None
    net_quantity_unit: Optional[str] = None
    raw_net_quantity_string: Optional[str] = None
    is_standard_unit: bool = True
    illegal_unit_found: Optional[str] = None
    
    # Dates
    mfg_date: Optional[str] = None
    expiry_date: Optional[str] = None
    shelf_life_statement: Optional[str] = None
    
    # Manufacturer / Packer / Importer
    mfr_name: Optional[str] = None
    mfr_address: Optional[str] = None
    mfr_pin: Optional[str] = None
    packer_name: Optional[str] = None
    importer_name: Optional[str] = None
    
    # Consumer Care
    consumer_care_name: Optional[str] = None
    consumer_care_phone: Optional[str] = None
    consumer_care_email: Optional[str] = None
    consumer_care_address: Optional[str] = None
    
    # Origin & Batch
    country_of_origin: Optional[str] = None
    batch_number: Optional[str] = None
    fssai_license: Optional[str] = None
    bis_isi_mark: Optional[str] = None
    
    # Font Size & Dimensions
    estimated_mrp_font_height_mm: Optional[float] = None
    estimated_qty_font_height_mm: Optional[float] = None
    principal_display_panel_area_sqcm: Optional[float] = None
    
    # Food, Ingredients & Nutrition
    ingredients_text: Optional[str] = None
    nutritional_values: Dict[str, str] = {}
    vegetarian_status: Optional[str] = None
    
    # Composition Claims
    active_claims: List[ActiveClaim] = []
    raw_extracted_text: Dict[str, str] = {}  # side -> text

class RuleEvaluation(BaseModel):
    rule_id: str
    rule_name: str
    legal_section: str
    status: RuleStatus
    confidence: float
    observed_value: str
    expected_requirement: str
    explanation: str
    penalty_clause: str
    bounding_box: Optional[BoundingBox] = None
    requires_physical_check: bool = False

class ScanRequest(BaseModel):
    product_name: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = "Packaged Commodity"
    sides: Optional[Dict[str, str]] = {}
    sides_text: Optional[Dict[str, str]] = {}
    images: Optional[List[str]] = []
    image_base64: Optional[str] = None
    ocr_text: Optional[str] = None
    inspector_id: Optional[str] = "INSP-DL-4089"
    location: Optional[str] = "Enforcement Inspection Point"
    notes: Optional[str] = None

class CorrectnessAudit(BaseModel):
    units_correctness: Dict[str, Any] = {}
    mrp_syntax_correctness: Dict[str, Any] = {}
    pin_code_correctness: Dict[str, Any] = {}
    contact_syntax_correctness: Dict[str, Any] = {}
    date_chronology_correctness: Dict[str, Any] = {}
    is_fully_correct: bool = True
    summary: str = ""

class CompletenessAudit(BaseModel):
    overall_completeness_pct: float = 100.0
    mandatory_elements_total: int = 12
    mandatory_elements_present: int = 12
    missing_elements: List[str] = []
    checklist: Dict[str, bool] = {}
    summary: str = ""

class PlacementAudit(BaseModel):
    pdp_generic_name_placed: bool = True
    pdp_net_quantity_placed: bool = True
    is_placement_compliant: bool = True
    placement_verdict: str = "Proper Principal Display Panel (PDP) Placement"
    panel_distribution: Dict[str, str] = {}
    summary: str = ""

class ReadabilityAndFontSizeAudit(BaseModel):
    estimated_character_height_mm: float = 2.5
    statutory_min_height_mm: float = 2.0
    font_size_status: RuleStatus = RuleStatus.PASS
    contrast_ratio: str = "7.5:1 (High Contrast)"
    contrast_verdict: str = "EXCELLENT"
    is_contrast_legible: bool = True
    blur_score: float = 95.0
    readability_verdict: str = "Meets Schedule I character height & legibility criteria"

# ─── AI Declaration & Label Verification Models ──────────────────────────────

class DeclVerifStatus(str, Enum):
    PASS = "PASS"
    POTENTIAL_ISSUE = "POTENTIAL_ISSUE"
    MANUAL_REVIEW = "MANUAL_REVIEW"

class DeclDimensionResult(BaseModel):
    status: DeclVerifStatus
    detail: str
    evidence_text: Optional[str] = None
    confidence: Optional[float] = None

class ConflictEvidence(BaseModel):
    panel: str
    value: str
    context: Optional[str] = None

class DeclarationCard(BaseModel):
    declaration_id: str
    declaration_type: str   # "mandatory"|"nutritional"|"claim"|"ingredient"|"certification"
    label: str
    detected_value: str
    panel_found_on: str
    bounding_box: Optional[BoundingBox] = None
    overall_status: DeclVerifStatus
    presence: DeclDimensionResult
    completeness: DeclDimensionResult
    correctness: DeclDimensionResult
    readability: DeclDimensionResult
    placement: DeclDimensionResult
    font_size: DeclDimensionResult
    conflict_evidence: List[ConflictEvidence] = []
    ocr_confidence: float = 0.95
    flag_reason: Optional[str] = None

class DeclarationAnalysisSummary(BaseModel):
    total_declarations_detected: int
    pass_count: int
    potential_issue_count: int
    manual_review_count: int
    missing_mandatory_declarations: List[str] = []
    cards: List[DeclarationCard] = []
    overall_analysis_status: DeclVerifStatus
    summary_text: str

# ─────────────────────────────────────────────────────────────────────────────

class ScanResult(BaseModel):
    scan_id: str
    timestamp: str
    inspector_id: str
    location: str
    product_name: str
    brand: str
    category: str
    overall_compliance_score: float
    compliance_status: ComplianceStatus
    summary_verdict: str
    
    # 4-Pillar Audits
    correctness_audit: Optional[CorrectnessAudit] = None
    completeness_audit: Optional[CompletenessAudit] = None
    placement_audit: Optional[PlacementAudit] = None
    readability_audit: Optional[ReadabilityAndFontSizeAudit] = None

    # AI Declaration & Label Verification
    declaration_analysis: Optional[DeclarationAnalysisSummary] = None

    # Quality metrics per side
    image_quality: Dict[str, ImageQualityMetrics]
    
    # Structured Extracted Fields
    declarations: DeclarationFields
    
    # Statutory Rule Evaluations
    rules_evaluated: List[RuleEvaluation]
    total_rules: int
    passed_rules: int
    failed_rules: int
    warnings: int
    lab_verifications: int
    
    # Claims flagged for Lab testing
    lab_flagged_claims: List[ActiveClaim]
    
    # Evidence photo paths/urls
    side_images: Dict[str, str]
    
    # Generated Report link
    pdf_report_path: Optional[str] = None
    pdf_report_url: Optional[str] = None
    
    officer_notes: Optional[str] = None

class NoticeGenerationRequest(BaseModel):
    scan_id: str
    company_name: str
    company_address: str
    recipient_designation: str = "Managing Director / Director in Charge"
    officer_name: str = "Shri R. K. Sharma"
    officer_designation: str = "Inspector, Legal Metrology (Enforcement)"
    jurisdiction: str = "Central Division, NCT of Delhi"
    notice_type: str = "SHOW_CAUSE"  # "SHOW_CAUSE" or "SEIZURE_MEMO"

class NoticeGenerationResponse(BaseModel):
    notice_id: str
    notice_date: str
    statutory_act: str
    company_name: str
    legal_sections_invoked: List[str]
    violations_summary: List[str]
    full_notice_text: str
    pdf_notice_url: Optional[str] = None

class AnalyticsSummary(BaseModel):
    total_scans: int
    compliant_scans: int
    non_compliant_scans: int
    lab_flagged_scans: int
    compliance_rate: float
    top_violated_rules: List[Dict[str, Any]]
    brand_violation_counts: List[Dict[str, Any]]
    category_breakdown: List[Dict[str, Any]]
    recent_inspections: List[Dict[str, Any]]
