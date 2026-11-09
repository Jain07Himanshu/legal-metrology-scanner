"""
Notice Generator for Legal Metrology Enforcement Actions.
Drafts statutory Show-Cause Notices and Seizure Memos under Sections 36 & 39 of Legal Metrology Act, 2009.
"""
import datetime
from typing import List
from app.models.schemas import ScanResult, NoticeGenerationRequest, NoticeGenerationResponse, RuleStatus

class NoticeGenerator:

    @classmethod
    def generate_notice(cls, scan_data: ScanResult, req: NoticeGenerationRequest) -> NoticeGenerationResponse:
        """
        Drafts a formal statutory Show-Cause Notice citing specific violations detected during scanning.
        """
        now = datetime.datetime.now()
        notice_id = f"NOT-LM-{now.strftime('%Y%m%d')}-{scan_data.scan_id[:8]}"
        date_str = now.strftime("%d-%B-%Y")

        # Collect failed rules
        failed_evals = [r for r in scan_data.rules_evaluated if r.status == RuleStatus.FAIL]
        sections_invoked = list(set([r.legal_section for r in failed_evals]))
        if not sections_invoked:
            sections_invoked = ["Section 36(1) of Legal Metrology Act, 2009"]

        violations_points = []
        for idx, f in enumerate(failed_evals, 1):
            violations_points.append(
                f"{idx}. VIOLATION OF {f.legal_section.upper()}:\n"
                f"   • Rule Description: {f.rule_name}\n"
                f"   • Observed Condition on Label: {f.observed_value}\n"
                f"   • Statutory Standard: {f.expected_requirement}\n"
                f"   • Legal Implication: {f.explanation}\n"
                f"   • Statutory Penalty Provision: {f.penalty_clause}\n"
            )

        violations_text = "\n".join(violations_points) if violations_points else "1. General non-compliance with packaging standards.\n"

        notice_template = f"""================================================================================
GOVERNMENT OF NCT OF DELHI / STATE ENFORCEMENT DIRECTORATE
OFFICE OF THE CONTROLLER OF LEGAL METROLOGY
CENTRAL ENFORCEMENT DIVISION, VIKAS BHAWAN, NEW DELHI - 110002
================================================================================

NOTICE NO: {notice_id}
DATED: {date_str}

SHOW-CAUSE NOTICE UNDER SECTION 36 & SECTION 39 OF THE LEGAL METROLOGY ACT, 2009
READ WITH THE LEGAL METROLOGY (PACKAGED COMMODITIES) RULES, 2011

TO,
THE {req.recipient_designation.upper()}
M/S {req.company_name.upper()}
ADDRESS: {req.company_address}

SUBJECT: NOTICE OF CONTRAVENTION OF STATUTORY PACKAGING DECLARATIONS IN RESPECT OF '{scan_data.product_name.upper()}' (BRAND: {scan_data.brand.upper()})

WHEREAS, an official inspection was carried out by the undersigned Legal Metrology Officer on {scan_data.timestamp} at {scan_data.location}, during which sample packages of '{scan_data.product_name}' (Brand: {scan_data.brand}, Category: {scan_data.category}, Batch No: {scan_data.declarations.batch_number or 'N/A'}) were scanned and examined for compliance with the statutory provisions of the Legal Metrology Act, 2009 and the Legal Metrology (Packaged Commodities) Rules, 2011;

AND WHEREAS, upon scrutiny through automated optical and dimensional compliance verification, the following grave statutory non-compliances and violations were observed on the packaging:

--------------------------------------------------------------------------------
PARTICULARS OF CONTRAVENTIONS DETECTED:
--------------------------------------------------------------------------------
{violations_text}
--------------------------------------------------------------------------------

NOW, THEREFORE, by virtue of the powers vested in the undersigned under Section 15 and Section 36 of the Legal Metrology Act, 2009, you are hereby called upon to:

1. SHOW CAUSE in writing within FIFTEEN (15) DAYS from the date of receipt of this notice as to why legal proceedings under Section 36(1) / Section 36(2) and Section 39 of the Legal Metrology Act, 2009 should not be initiated against you, your directors, and the company before the competent Court of Metropolitan Magistrate.
2. IMMEDIATELY SUSPEND retail distribution of the non-compliant batch and furnish the total quantity manufactured, distributed, and in stock.
3. State whether you wish to compound the said offence under Section 48 of the Act by depositing the prescribed compounding fee.

PLEASE TAKE NOTE that in the event of failure to furnish a satisfactory written explanation within the stipulated period of 15 days, it shall be presumed that you have no defense to offer, and criminal complaint proceedings shall be filed without any further notice.

GIVEN UNDER MY HAND AND OFFICIAL SEAL OF THIS OFFICE.


____________________________________
({req.officer_name})
{req.officer_designation}
{req.jurisdiction}
Directorate of Legal Metrology
================================================================================
"""

        return NoticeGenerationResponse(
            notice_id=notice_id,
            notice_date=date_str,
            statutory_act="Legal Metrology Act, 2009 & Packaged Commodities Rules, 2011",
            company_name=req.company_name,
            legal_sections_invoked=sections_invoked,
            violations_summary=[f"{f.rule_name} ({f.legal_section})" for f in failed_evals],
            full_notice_text=notice_template
        )
