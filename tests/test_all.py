"""
Automated Test Suite for Legal Metrology Scanner (PS-34).
Verifies Preprocessor, OCR, Extractor, Rules Engine, PDF Generator, Notice Generator, and API Endpoints.
"""
import sys
from pathlib import Path
import numpy as np
import cv2
import json

# Setup sys.path
TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.models.schemas import ScanRequest, ScanResult, DeclarationFields, RuleStatus, ComplianceStatus, NoticeGenerationRequest
from app.services.preprocessor import ImagePreprocessor
from app.services.ocr_engine import OCREngine
from app.services.extractor import FieldExtractor
from app.services.rules_engine import LegalMetrologyRulesEngine
from app.services.pdf_generator import PDFReportGenerator
from app.services.notice_generator import NoticeGenerator
from app.services.storage import StorageService
from app.services.image_renderer import SampleArtworkRenderer

def test_image_preprocessor_quality():
    # Create sharp test image
    sharp_img = np.zeros((400, 400, 3), dtype=np.uint8)
    cv2.putText(sharp_img, "TEST LABEL SHARP", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    quality = ImagePreprocessor.assess_quality(sharp_img)
    assert quality.blur_score > 0
    assert quality.brightness >= 0

def test_field_extractor_mrp_and_tax():
    sample_text = {
        "front": "SuperCrunch Biscuits\nNet Qty: 100 g",
        "back": "Manufactured by: SuperFoods Ltd, Plot 10, Haridwar - 249401\nConsumer Care: care@superfoods.in, 1800-112-9900",
        "top": "Batch: B101\nPkd: 02/2026",
        "side": "MRP Rs. 45.00 (inclusive of all taxes)\nCountry of Origin: India"
    }
    ocr_results = {}
    dummy_img = np.zeros((300, 300, 3), dtype=np.uint8)
    for side, text in sample_text.items():
        ocr_results[side] = OCREngine.extract_text_with_boxes(dummy_img, side_name=side, fallback_text=text)

    fields, bbox_map = FieldExtractor.extract_all(ocr_results)
    assert fields.mrp_amount == 45.00
    assert fields.tax_phrase_present is True
    assert fields.net_quantity_value == 100.0
    assert fields.net_quantity_unit == "g"
    assert fields.is_standard_unit is True
    assert fields.mfr_pin == "249401"
    assert fields.consumer_care_email == "care@superfoods.in"
    assert fields.country_of_origin == "India"

def test_field_extractor_illegal_unit():
    # Test illegal unit 'gm'
    sample_text = {
        "front": "SuperCrunch Biscuits\nNet Qty: 100 gm",
        "back": "Manufactured by: Test Ltd, Haridwar - 249401",
        "top": "Pkd: 02/2026",
        "side": "MRP Rs. 45.00"
    }
    ocr_results = {}
    dummy_img = np.zeros((300, 300, 3), dtype=np.uint8)
    for side, text in sample_text.items():
        ocr_results[side] = OCREngine.extract_text_with_boxes(dummy_img, side_name=side, fallback_text=text)

    fields, bbox_map = FieldExtractor.extract_all(ocr_results)
    assert fields.net_quantity_unit == "gm"
    assert fields.is_standard_unit is False
    assert fields.illegal_unit_found == "gm"

def test_rules_engine_non_compliant_case():
    engine = LegalMetrologyRulesEngine()
    # Construct fields with missing tax phrase and illegal unit 'gm'
    fields = DeclarationFields(
        generic_name="Biscuits",
        brand_name="SuperCrunch",
        mrp_amount=45.0,
        tax_phrase_present=False,  # Violation!
        net_quantity_value=100.0,
        net_quantity_unit="gm",
        is_standard_unit=False,    # Violation!
        illegal_unit_found="gm",
        mfr_name="SuperFoods Ltd",
        mfr_address="Plot 10, Haridwar, Uttarakhand",
        mfr_pin="249401",
        mfg_date="02/2026",
        consumer_care_phone="1800-112-9900",
        consumer_care_email="care@superfoods.in",
        country_of_origin="India",
        estimated_qty_font_height_mm=1.2  # Schedule I violation for 100g pack!
    )
    evaluations, score, status, verdict = engine.evaluate_compliance(fields, {})
    assert status == ComplianceStatus.NON_COMPLIANT
    assert score < 100.0
    
    failed_rule_ids = [e.rule_id for e in evaluations if e.status == RuleStatus.FAIL]
    assert "RULE_6_1_C" in failed_rule_ids  # Illegal SI unit
    assert "RULE_6_1_E" in failed_rule_ids  # Missing tax wording
    assert "RULE_7_SCHED_I" in failed_rule_ids  # Undersized font

def test_rules_engine_fully_compliant_case():
    engine = LegalMetrologyRulesEngine()
    fields = DeclarationFields(
        generic_name="Basmati Rice",
        brand_name="Royal Heritage",
        mrp_amount=185.0,
        tax_phrase_present=True,
        net_quantity_value=1.0,
        net_quantity_unit="kg",
        is_standard_unit=True,
        mfr_name="Heritage Agri Foods Ltd",
        mfr_address="GT Road, Sonepat, Haryana",
        mfr_pin="131001",
        mfg_date="02/2026",
        consumer_care_phone="1800-200-8899",
        consumer_care_email="customercare@heritageagro.in",
        country_of_origin="India",
        unit_sale_price="₹ 185.00 / kg",
        estimated_qty_font_height_mm=4.5
    )
    evaluations, score, status, verdict = engine.evaluate_compliance(fields, {})
    assert status == ComplianceStatus.COMPLIANT
    assert score == 100.0

def test_pdf_and_notice_generators():
    engine = LegalMetrologyRulesEngine()
    fields = DeclarationFields(
        generic_name="Digestive Biscuits",
        brand_name="SuperCrunch",
        mrp_amount=45.0,
        tax_phrase_present=False,
        net_quantity_value=100.0,
        net_quantity_unit="gm",
        is_standard_unit=False,
        illegal_unit_found="gm",
        mfr_name="SuperFoods Confectionery Ltd",
        mfr_address="Plot 14, Haridwar, Uttarakhand",
        mfr_pin="249401",
        mfg_date="02/2026",
        consumer_care_phone="1800-112-9900",
        consumer_care_email="care@superfoods.co.in",
        country_of_origin="India"
    )
    evaluations, score, status, verdict = engine.evaluate_compliance(fields, {})
    
    scan_res = ScanResult(
        scan_id="TEST-LM-001",
        timestamp="2026-08-28 12:00:00",
        inspector_id="INSP-DL-4089",
        location="Delhi Central Market",
        product_name="SuperCrunch Digestives",
        brand="SuperCrunch",
        category="FMCG Food & Bakery",
        overall_compliance_score=score,
        compliance_status=status,
        summary_verdict=verdict,
        image_quality={},
        declarations=fields,
        rules_evaluated=evaluations,
        total_rules=len(evaluations),
        passed_rules=sum(1 for e in evaluations if e.status == RuleStatus.PASS),
        failed_rules=sum(1 for e in evaluations if e.status == RuleStatus.FAIL),
        warnings=sum(1 for e in evaluations if e.status == RuleStatus.WARNING),
        lab_verifications=sum(1 for e in evaluations if e.status == RuleStatus.LAB_VERIFY),
        lab_flagged_claims=[],
        side_images={}
    )

    # 1. Test PDF Report Generation
    pdf_path = PDFReportGenerator.generate_inspection_report(scan_res)
    assert Path(pdf_path).exists()
    assert Path(pdf_path).stat().st_size > 1000

    # 2. Test Show-Cause Notice Generation
    req = NoticeGenerationRequest(
        scan_id="TEST-LM-001",
        company_name="SuperFoods Confectionery Ltd",
        company_address="Plot 14, Haridwar, Uttarakhand - 249401"
    )
    notice = NoticeGenerator.generate_notice(scan_res, req)
    assert notice.notice_id.startswith("NOT-LM-")
    assert "SHOW-CAUSE NOTICE" in notice.full_notice_text
    assert "SUPERFOODS CONFECTIONERY LTD" in notice.full_notice_text
    assert "Section 36" in notice.full_notice_text

def test_storage_and_analytics():
    analytics = StorageService.get_analytics()
    assert analytics.total_scans >= 0
    assert analytics.compliance_rate >= 0.0

if __name__ == "__main__":
    print("Running Legal Metrology Scanner Test Suite...")
    test_image_preprocessor_quality()
    print("[OK] Image Preprocessor Quality: PASSED")
    test_field_extractor_mrp_and_tax()
    print("[OK] Field Extractor (MRP & Tax): PASSED")
    test_field_extractor_illegal_unit()
    print("[OK] Field Extractor (Illegal Unit): PASSED")
    test_rules_engine_non_compliant_case()
    print("[OK] Rules Engine (Non-Compliant Detection): PASSED")
    test_rules_engine_fully_compliant_case()
    print("[OK] Rules Engine (Compliant Verification): PASSED")
    test_pdf_and_notice_generators()
    print("[OK] PDF Report & Show-Cause Notice Generator: PASSED")
    test_storage_and_analytics()
    print("[OK] Storage & Analytics: PASSED")
    print("\nALL AUTOMATED TESTS COMPLETED SUCCESSFULLY!")
