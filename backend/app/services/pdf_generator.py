"""
ReportLab PDF Generator for Official Legal Metrology Inspection Certificates.
Produces high-quality, government-format compliance audit reports and violation memos.
"""
from pathlib import Path
import datetime
from typing import Dict, Any, List
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.units import inch
from app.models.schemas import ScanResult, RuleStatus
from app.config import REPORT_DIR

class PDFReportGenerator:

    @classmethod
    def generate_inspection_report(cls, scan_data: ScanResult) -> str:
        """
        Generates official PDF audit certificate and saves to reports directory.
        Returns the absolute file path.
        """
        pdf_filename = f"Inspection_Report_{scan_data.scan_id}.pdf"
        pdf_path = REPORT_DIR / pdf_filename

        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()

        # Custom Styles
        title_style = ParagraphStyle(
            "GovTitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            alignment=1,  # Center
            textColor=colors.HexColor("#1e3a8a")
        )
        subtitle_style = ParagraphStyle(
            "GovSubtitle",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.HexColor("#475569")
        )
        doc_header_style = ParagraphStyle(
            "DocHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            alignment=1,
            textColor=colors.HexColor("#0f172a")
        )
        section_style = ParagraphStyle(
            "SectionHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#1e3a8a")
        )
        body_style = ParagraphStyle(
            "GovBody",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1e293b")
        )
        body_bold = ParagraphStyle(
            "GovBodyBold",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#0f172a")
        )

        story = []

        # 1. Government Emblem & Header
        story.append(Paragraph("GOVERNMENT OF INDIA", title_style))
        story.append(Paragraph("MINISTRY OF CONSUMER AFFAIRS, FOOD & PUBLIC DISTRIBUTION", subtitle_style))
        story.append(Paragraph("DEPARTMENT OF CONSUMER AFFAIRS • DIRECTORATE OF LEGAL METROLOGY", subtitle_style))
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1e3a8a"), spaceAfter=6))

        story.append(Paragraph("STATUTORY COMPLIANCE INSPECTION CERTIFICATE & AUDIT MEMO", doc_header_style))
        story.append(Paragraph(f"Under The Legal Metrology Act, 2009 & Legal Metrology (Packaged Commodities) Rules, 2011", subtitle_style))
        story.append(Spacer(1, 8))

        # 2. Inspection Metadata Table
        meta_data = [
            [
                Paragraph("<b>Inspection ID:</b>", body_style), Paragraph(scan_data.scan_id, body_bold),
                Paragraph("<b>Date & Time:</b>", body_style), Paragraph(scan_data.timestamp, body_style)
            ],
            [
                Paragraph("<b>Inspector ID:</b>", body_style), Paragraph(scan_data.inspector_id, body_style),
                Paragraph("<b>Location / Depot:</b>", body_style), Paragraph(scan_data.location, body_style)
            ],
            [
                Paragraph("<b>Commodity Name:</b>", body_style), Paragraph(scan_data.product_name, body_bold),
                Paragraph("<b>Brand / Trademark:</b>", body_style), Paragraph(scan_data.brand, body_style)
            ],
            [
                Paragraph("<b>Category:</b>", body_style), Paragraph(scan_data.category, body_style),
                Paragraph("<b>Overall Score:</b>", body_style), Paragraph(f"<b>{scan_data.overall_compliance_score}%</b>", body_bold)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[1.3*inch, 2.2*inch, 1.3*inch, 2.2*inch])
        meta_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        # 3. Overall Verdict Banner
        verdict_bg = "#dcfce7" if scan_data.compliance_status == "COMPLIANT" else ("#fee2e2" if scan_data.compliance_status == "NON_COMPLIANT" else "#fef3c7")
        verdict_border = "#16a34a" if scan_data.compliance_status == "COMPLIANT" else ("#dc2626" if scan_data.compliance_status == "NON_COMPLIANT" else "#d97706")
        verdict_text_color = "#15803d" if scan_data.compliance_status == "COMPLIANT" else ("#b91c1c" if scan_data.compliance_status == "NON_COMPLIANT" else "#b45309")

        verdict_p = Paragraph(
            f"<b>OFFICIAL AUDIT VERDICT:</b> {scan_data.summary_verdict}",
            ParagraphStyle("VerdictText", parent=body_style, textColor=colors.HexColor(verdict_text_color), fontSize=8.5, leading=12)
        )
        verdict_table = Table([[verdict_p]], colWidths=[7.0*inch])
        verdict_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(verdict_bg)),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(verdict_border)),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(verdict_table)
        story.append(Spacer(1, 8))

        # 4. Extracted Mandatory Declarations Summary
        story.append(Paragraph("A. STATUTORY DECLARATIONS EXTRACTED", section_style))
        story.append(Spacer(1, 3))
        
        decl = scan_data.declarations
        decl_data = [
            [
                Paragraph("<b>MRP:</b>", body_style),
                Paragraph(f"₹ {decl.mrp_amount:.2f} ({'Incl. of all taxes' if decl.tax_phrase_present else 'TAX WORDING MISSING'})" if decl.mrp_amount else "Not Detected", body_style),
                Paragraph("<b>Net Quantity:</b>", body_style),
                Paragraph(f"{decl.net_quantity_value} {decl.net_quantity_unit} ({'SI Unit' if decl.is_standard_unit else 'NON-STANDARD UNIT'})" if decl.net_quantity_value else "Not Detected", body_style)
            ],
            [
                Paragraph("<b>Manufacturer:</b>", body_style),
                Paragraph(f"{decl.mfr_name or 'Not Detected'} (PIN: {decl.mfr_pin or 'Missing'})", body_style),
                Paragraph("<b>Mfg / PKD Date:</b>", body_style),
                Paragraph(f"{decl.mfg_date or 'Not Detected'} (Exp: {decl.expiry_date or 'N/A'})", body_style)
            ],
            [
                Paragraph("<b>Consumer Care:</b>", body_style),
                Paragraph(f"Tel: {decl.consumer_care_phone or 'N/A'}, Email: {decl.consumer_care_email or 'N/A'}", body_style),
                Paragraph("<b>Country of Origin:</b>", body_style),
                Paragraph(f"{decl.country_of_origin or 'Not Declared'}", body_style)
            ]
        ]
        decl_table = Table(decl_data, colWidths=[1.2*inch, 2.3*inch, 1.2*inch, 2.3*inch])
        decl_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(decl_table)
        story.append(Spacer(1, 8))

        # 5. Statutory Rule Evaluation Breakdown Table
        story.append(Paragraph("B. RULE-BY-RULE STATUTORY COMPLIANCE BREAKDOWN", section_style))
        story.append(Spacer(1, 3))

        rule_headers = [
            Paragraph("<b>Clause</b>", body_bold),
            Paragraph("<b>Rule & Requirement</b>", body_bold),
            Paragraph("<b>Observed Value on Label</b>", body_bold),
            Paragraph("<b>Status</b>", body_bold)
        ]
        
        rule_rows = [rule_headers]
        for r in scan_data.rules_evaluated:
            status_color = "#16a34a" if r.status == RuleStatus.PASS else ("#dc2626" if r.status == RuleStatus.FAIL else ("#d97706" if r.status == RuleStatus.WARNING else "#2563eb"))
            status_p = Paragraph(f"<b><font color='{status_color}'>{r.status.value}</font></b>", body_style)
            
            rule_rows.append([
                Paragraph(r.legal_section, body_style),
                Paragraph(f"<b>{r.rule_name}</b><br/><font color='#64748b'>{r.explanation[:95]}...</font>", body_style),
                Paragraph(r.observed_value, body_style),
                status_p
            ])

        rule_table = Table(rule_rows, colWidths=[1.4*inch, 2.6*inch, 2.1*inch, 0.9*inch])
        rule_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(rule_table)
        story.append(Spacer(1, 8))

        # 6. Section 15 Lab Verification Section if any
        if scan_data.lab_flagged_claims:
            story.append(Paragraph("C. SECTION 15 LABORATORY SAMPLING RECOMMENDATIONS", section_style))
            story.append(Spacer(1, 2))
            for claim in scan_data.lab_flagged_claims:
                claim_p = Paragraph(
                    f"• <b>Active Claim:</b> {claim.claim_text} | <b>Directive:</b> {claim.legal_rationale}",
                    body_style
                )
                story.append(claim_p)
                story.append(Spacer(1, 2))
            story.append(Spacer(1, 6))

        # 7. Official Endorsement & Signature Block
        story.append(Spacer(1, 10))
        sig_data = [
            [
                Paragraph("<b>Enforcement Officer Remarks:</b><br/>Scanned via automated Legal Metrology Scanner system. Verified against Statutory Gazette standards.", body_style),
                Paragraph("<b>OFFICIAL SEAL & SIGNATURE:</b><br/><br/>__________________________________<br/><b>Inspector of Legal Metrology</b><br/>Govt. of NCT of Delhi / Central Zone", body_style)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[4.0*inch, 3.0*inch])
        sig_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(KeepTogether(sig_table))

        # Build Document
        doc.build(story)
        return str(pdf_path)
