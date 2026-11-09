"""
FastAPI Main Application for Legal Metrology Scanner (PS-34).
Integrates Computer Vision, Multi-Panel OCR, Rule Engine, PDF Reporting, and Enforcement API.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import json
import uuid
import datetime
import os

from app.models.schemas import (
    ScanRequest, ScanResult, NoticeGenerationRequest, NoticeGenerationResponse,
    AnalyticsSummary, ImageQualityMetrics, BoundingBox
)
from app.services.preprocessor import ImagePreprocessor
from app.services.ocr_engine import OCREngine
from app.services.extractor import FieldExtractor
from app.services.rules_engine import LegalMetrologyRulesEngine
from app.services.declaration_verifier import DeclarationVerifier
from app.services.pdf_generator import PDFReportGenerator
from app.services.notice_generator import NoticeGenerator
from app.services.storage import StorageService
from app.services.image_renderer import SampleArtworkRenderer
from app.config import REPORT_DIR, SAMPLE_DATA_FILE, BASE_DIR

app = FastAPI(
    title="Legal Metrology Compliance Scanner",
    description="Automated Compliance Checking for Packaged Commodities Rules 2011 & Legal Metrology Act 2009",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Rules Engine
rules_engine = LegalMetrologyRulesEngine()

# Mount Static Directories
STATIC_DIR = BASE_DIR.parent / "frontend" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/reports", StaticFiles(directory=str(REPORT_DIR)), name="reports")

@app.get("/")
async def serve_index():
    index_file = BASE_DIR.parent / "frontend" / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Legal Metrology Scanner API running. Frontend available at /index.html"}

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Legal Metrology Compliance Scanner API",
        "version": "1.0.0",
        "timestamp": datetime.datetime.now().isoformat()
    }

@app.get("/api/samples")
async def get_benchmark_samples():
    """
    Returns list of pre-configured benchmark products with generated 4-side artwork.
    """
    if not SAMPLE_DATA_FILE.exists():
        return []
    try:
        with open(SAMPLE_DATA_FILE, "r", encoding="utf-8") as f:
            samples = json.load(f)
        
        # Enrich each sample with rendered visual artwork images
        enriched = []
        for s in samples:
            item = dict(s)
            item["rendered_images"] = SampleArtworkRenderer.generate_sample_images(s)
            enriched.append(item)
        return enriched
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/samples/{sample_id}")
async def get_single_sample(sample_id: str):
    """
    Returns a specific benchmark test case by ID.
    """
    if not SAMPLE_DATA_FILE.exists():
        raise HTTPException(status_code=404, detail="Samples data not found")
    try:
        with open(SAMPLE_DATA_FILE, "r", encoding="utf-8") as f:
            samples = json.load(f)
        for s in samples:
            if s.get("id") == sample_id:
                item = dict(s)
                item["rendered_images"] = SampleArtworkRenderer.generate_sample_images(s)
                return item
        raise HTTPException(status_code=404, detail="Sample not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scan", response_model=ScanResult)
async def perform_compliance_scan(req: ScanRequest):
    """
    Executes end-to-end 4-side compliance scan:
    Preprocessing -> OCR & Bounding Box extraction -> NER Entity Parser -> Rules Engine -> PDF generation -> Repository storage.
    """
    try:
        scan_id = f"LM-{datetime.datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Determine image inputs
        image_qualities: dict[str, ImageQualityMetrics] = {}
        ocr_results: dict[str, dict] = {}
        processed_side_images: dict[str, str] = {}

        # If multiple images provided as list
        sides_dict = req.sides or {}
        if req.images and len(req.images) > 0:
            for idx, img in enumerate(req.images):
                key = f"Photo {idx+1}"
                if key not in sides_dict:
                    sides_dict[key] = img
        elif req.image_base64 and not sides_dict:
            sides_dict = {"Photo 1": req.image_base64}
        elif not sides_dict:
            sides_dict = {"Photo 1": ""}

        # Build dictionary of per-side OCR text
        side_text_map: dict[str, str] = {}
        if req.sides_text:
            for k, v in req.sides_text.items():
                if v and str(v).strip():
                    v_str = str(v).strip()
                    side_text_map[k] = v_str
                    side_text_map[k.lower()] = v_str
                    side_text_map[k.lower().replace(" panel", "").strip()] = v_str

        # Also parse sections from combined ocr_text if present (e.g. "--- FRONT PANEL ---\n...")
        if req.ocr_text:
            import re
            sections = re.split(r'---\s*(.*?)\s*---', req.ocr_text)
            if len(sections) > 1:
                for i in range(1, len(sections), 2):
                    sec_name = sections[i].strip()
                    sec_text = sections[i+1].strip() if i+1 < len(sections) else ""
                    if sec_text:
                        side_text_map[sec_name] = sec_text
                        side_text_map[sec_name.lower()] = sec_text
                        side_text_map[sec_name.lower().replace(" panel", "").strip()] = sec_text

        # Process each provided image / panel
        for side_name, img_data in sides_dict.items():
            norm_key = side_name.lower().replace(" panel", "").strip()
            fallback_text = (
                side_text_map.get(side_name)
                or side_text_map.get(side_name.lower())
                or side_text_map.get(norm_key)
            )

            # Check if img_data itself was passed as plain OCR text instead of data:image
            if isinstance(img_data, str) and not img_data.startswith("data:image") and len(img_data.strip()) > 0:
                fallback_text = img_data
                img_data = SampleArtworkRenderer.render_side_label(
                    req.product_name or "Packaged Commodity",
                    fallback_text.split("\n"),
                    side_name
                )
            elif not fallback_text and len(sides_dict) == 1 and req.ocr_text:
                fallback_text = req.ocr_text
            
            cv2_img, pil_img = ImagePreprocessor.decode_image(img_data)
            
            # Quality assessment
            quality = ImagePreprocessor.assess_quality(cv2_img)
            image_qualities[side_name] = quality
            
            # Enhance contrast & deskew
            deskewed, _ = ImagePreprocessor.deskew(cv2_img)
            enhanced = ImagePreprocessor.enhance_contrast_and_clarity(deskewed)
            
            processed_side_images[side_name] = ImagePreprocessor.encode_image_base64(enhanced)
            
            # OCR with spatial bounding boxes
            ocr_res = OCREngine.extract_text_with_boxes(enhanced, side_name=side_name, fallback_text=fallback_text)
            ocr_results[side_name] = ocr_res

        # 2. Extract Statutory Declarations & Entities
        declarations, bbox_map = FieldExtractor.extract_all(ocr_results)
        
        # Override with user-provided names if available
        if req.product_name and req.product_name.strip() and req.product_name != "Unnamed Commodity":
            declarations.generic_name = req.product_name
        if req.brand and req.brand.strip() and req.brand != "Unknown Brand":
            declarations.brand_name = req.brand
        if req.category and req.category.strip():
            declarations.category = req.category

        # Fallback names if not detected
        product_title = declarations.generic_name or req.product_name or "Scanned Commodity"
        brand_title = declarations.brand_name or req.brand or "Manufacturer Brand"

        # 3. Evaluate Statutory Rules + 4-Pillar Audits
        (evaluations, score, status, verdict,
         correctness_audit, completeness_audit,
         placement_audit, readability_audit) = rules_engine.evaluate_compliance(declarations, bbox_map)

        passed_count = sum(1 for e in evaluations if e.status == "PASS")
        failed_count = sum(1 for e in evaluations if e.status == "FAIL")
        warning_count = sum(1 for e in evaluations if e.status == "WARNING")
        lab_count = sum(1 for e in evaluations if e.status == "LAB_VERIFY")

        # 4. AI Declaration & Label Verification (5-dimension per-card analysis)
        declaration_analysis = DeclarationVerifier.run(ocr_results, declarations, bbox_map)

        # 5. Construct ScanResult
        scan_result = ScanResult(
            scan_id=scan_id,
            timestamp=timestamp_str,
            inspector_id=req.inspector_id or "INSP-DL-4089",
            location=req.location or "Central Enforcement Depot, New Delhi",
            product_name=product_title,
            brand=brand_title,
            category=declarations.category or "Packaged Commodity",
            overall_compliance_score=score,
            compliance_status=status,
            summary_verdict=verdict,
            correctness_audit=correctness_audit,
            completeness_audit=completeness_audit,
            placement_audit=placement_audit,
            readability_audit=readability_audit,
            declaration_analysis=declaration_analysis,
            image_quality=image_qualities,
            declarations=declarations,
            rules_evaluated=evaluations,
            total_rules=len(evaluations),
            passed_rules=passed_count,
            failed_rules=failed_count,
            warnings=warning_count,
            lab_verifications=lab_count,
            lab_flagged_claims=declarations.active_claims,
            side_images=processed_side_images,
            officer_notes=req.notes
        )

        # 5. Generate Official PDF Inspection Report
        pdf_path = PDFReportGenerator.generate_inspection_report(scan_result)
        scan_result.pdf_report_path = pdf_path
        scan_result.pdf_report_url = f"/reports/Inspection_Report_{scan_id}.pdf"

        # 6. Save to Persistent Historical Repository
        StorageService.save_scan(scan_result)

        return scan_result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Compliance scanning error: {str(e)}")

@app.get("/api/history")
async def get_inspection_history(
    status: str = Query(None, description="Filter by status: COMPLIANT, NON_COMPLIANT, FLAGGED_FOR_LAB"),
    category: str = Query(None, description="Filter by category"),
    search: str = Query(None, description="Search by product name, brand, or ID"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    Retrieves searchable inspection history from repository.
    """
    return StorageService.query_history(status=status, category=category, search_query=search, limit=limit)

@app.get("/api/history/{scan_id}")
async def get_single_inspection_record(scan_id: str):
    """
    Retrieves full audit details for a specific scan.
    """
    record = StorageService.get_scan_by_id(scan_id)
    if not record:
        raise HTTPException(status_code=404, detail="Scan record not found")
    return record

@app.post("/api/notice/generate", response_model=NoticeGenerationResponse)
async def generate_show_cause_notice(req: NoticeGenerationRequest):
    """
    Drafts an official Show-Cause Legal Notice under Section 36 & 39 for a non-compliant scan.
    """
    scan_dict = StorageService.get_scan_by_id(req.scan_id)
    if not scan_dict:
        raise HTTPException(status_code=404, detail="Referenced scan ID not found")
    
    scan_data = ScanResult(**scan_dict)
    notice_response = NoticeGenerator.generate_notice(scan_data, req)
    return notice_response

@app.get("/api/analytics", response_model=AnalyticsSummary)
async def get_dashboard_analytics():
    """
    Returns aggregated metrics: total scans, compliance rates, top violated rules, and brand rankings.
    """
    # If history is empty, populate initial benchmark demo scans for immediate visual analytics
    history = StorageService._load_history()
    if len(history) == 0 and SAMPLE_DATA_FILE.exists():
        # Pre-seed benchmark scans
        with open(SAMPLE_DATA_FILE, "r", encoding="utf-8") as f:
            samples = json.load(f)
        for s in samples:
            req = ScanRequest(
                product_name=s.get("name"),
                brand=s.get("brand"),
                category=s.get("category"),
                sides=s.get("sides", {})
            )
            try:
                # Synchronous scan seeding
                ocr_results = {}
                for side, text in s.get("sides", {}).items():
                    cv2_img, _ = ImagePreprocessor.decode_image(text)
                    ocr_res = OCREngine.extract_text_with_boxes(cv2_img, side_name=side, fallback_text=text)
                    ocr_results[side] = ocr_res
                declarations, bbox_map = FieldExtractor.extract_all(ocr_results)
                declarations.brand_name = s.get("brand")
                evaluations, score, status, verdict = rules_engine.evaluate_compliance(declarations, bbox_map)
                
                scan_id = f"LM-DEMO-{uuid.uuid4().hex[:6].upper()}"
                res = ScanResult(
                    scan_id=scan_id,
                    timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    inspector_id="INSP-DL-4089",
                    location="State Enforcement Hub, New Delhi",
                    product_name=s.get("name"),
                    brand=s.get("brand"),
                    category=s.get("category"),
                    overall_compliance_score=score,
                    compliance_status=status,
                    summary_verdict=verdict,
                    image_quality={},
                    declarations=declarations,
                    rules_evaluated=evaluations,
                    total_rules=len(evaluations),
                    passed_rules=sum(1 for e in evaluations if e.status == "PASS"),
                    failed_rules=sum(1 for e in evaluations if e.status == "FAIL"),
                    warnings=sum(1 for e in evaluations if e.status == "WARNING"),
                    lab_verifications=sum(1 for e in evaluations if e.status == "LAB_VERIFY"),
                    lab_flagged_claims=declarations.active_claims,
                    side_images={},
                    pdf_report_url=f"/reports/Inspection_Report_{scan_id}.pdf"
                )
                PDFReportGenerator.generate_inspection_report(res)
                StorageService.save_scan(res)
            except Exception as e:
                print("Error seeding sample:", e)

    return StorageService.get_analytics()
