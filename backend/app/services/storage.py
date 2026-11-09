"""
Storage & History Repository for Legal Metrology Scanner.
Handles persistence of scan audits, officer notes, search queries, and real-time analytics aggregation.
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.models.schemas import ScanResult, AnalyticsSummary, ComplianceStatus, RuleStatus
from app.config import HISTORY_FILE

class StorageService:

    @classmethod
    def _load_history(cls) -> List[Dict[str, Any]]:
        if not HISTORY_FILE.exists():
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def _save_history(cls, history: List[Dict[str, Any]]):
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    @classmethod
    def save_scan(cls, scan_result: ScanResult):
        history = cls._load_history()
        # Check if already exists
        for idx, item in enumerate(history):
            if item.get("scan_id") == scan_result.scan_id:
                history[idx] = json.loads(scan_result.json())
                cls._save_history(history)
                return
        history.insert(0, json.loads(scan_result.json()))
        cls._save_history(history)

    @classmethod
    def get_scan_by_id(cls, scan_id: str) -> Optional[Dict[str, Any]]:
        history = cls._load_history()
        for item in history:
            if item.get("scan_id") == scan_id:
                return item
        return None

    @classmethod
    def query_history(
        cls,
        status: Optional[str] = None,
        category: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        history = cls._load_history()
        filtered = []

        for item in history:
            if status and item.get("compliance_status") != status:
                continue
            if category and item.get("category") != category:
                continue
            if search_query:
                sq = search_query.lower()
                p_name = item.get("product_name", "").lower()
                brand = item.get("brand", "").lower()
                loc = item.get("location", "").lower()
                scan_id = item.get("scan_id", "").lower()
                if sq not in p_name and sq not in brand and sq not in loc and sq not in scan_id:
                    continue
            filtered.append(item)

        return filtered[:limit]

    @classmethod
    def get_analytics(cls) -> AnalyticsSummary:
        history = cls._load_history()
        total = len(history)

        compliant = 0
        non_compliant = 0
        lab_flagged = 0

        rule_violation_counts: Dict[str, Dict[str, Any]] = {}
        brand_violation_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}

        for item in history:
            st = item.get("compliance_status")
            if st == "COMPLIANT":
                compliant += 1
            elif st == "NON_COMPLIANT":
                non_compliant += 1
            elif st == "FLAGGED_FOR_LAB":
                lab_flagged += 1

            cat = item.get("category", "General")
            category_counts[cat] = category_counts.get(cat, 0) + 1

            brand = item.get("brand", "Unknown")
            if st == "NON_COMPLIANT":
                brand_violation_counts[brand] = brand_violation_counts.get(brand, 0) + 1

            for r in item.get("rules_evaluated", []):
                if r.get("status") == "FAIL":
                    r_id = r.get("rule_id", "UNKNOWN")
                    r_name = r.get("rule_name", r_id)
                    clause = r.get("legal_section", "")
                    if r_id not in rule_violation_counts:
                        rule_violation_counts[r_id] = {
                            "rule_id": r_id,
                            "rule_name": r_name,
                            "legal_section": clause,
                            "count": 0
                        }
                    rule_violation_counts[r_id]["count"] += 1

        top_rules = sorted(list(rule_violation_counts.values()), key=lambda x: x["count"], reverse=True)[:6]
        brand_rankings = [{"brand": b, "violations": c} for b, c in sorted(brand_violation_counts.items(), key=lambda x: x[1], reverse=True)[:6]]
        category_breakdown = [{"category": k, "count": v} for k, v in category_counts.items()]

        compliance_rate = round((compliant / max(total, 1)) * 100.0, 1) if total > 0 else 100.0

        return AnalyticsSummary(
            total_scans=total,
            compliant_scans=compliant,
            non_compliant_scans=non_compliant,
            lab_flagged_scans=lab_flagged,
            compliance_rate=compliance_rate,
            top_violated_rules=top_rules,
            brand_violation_counts=brand_rankings,
            category_breakdown=category_breakdown,
            recent_inspections=history[:8]
        )
