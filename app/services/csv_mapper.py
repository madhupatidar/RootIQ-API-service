"""CSV schema mapper for different investigation export formats."""

from __future__ import annotations

from app.models import ExceptionInput

TYPE_REGISTRY = {
    "OV": {
        "category": "Overage",
        "checks": [
            ("OD400_CHK", "OD400_CHK_RESP", "OD400 Document Check"),
            ("BL_CHK", "BL_CHK_RESP", "Bill of Lading Check"),
            ("DR_CHK", "DR_CHK_RESP", "Delivery Receipt Check"),
            ("PS_CHK", "PS_CHK_RESP", "Packing Slip Check"),
            ("CONSIGNEE_CHK", "CONSIGNEE_CHK_RESP", "Consignee Contact Check"),
            ("SHIPMENTCHK", "SHIPMENTCHK_RESP", "Same-Day Shipment Check"),
        ],
    },
    # Phase 2 — add NB, AS, DS, BNF, PR, RD, RF, DD, OH, MSD here
    # Each entry follows the same shape:
    # "TYPE_CODE": {
    #     "category": "<Overage|Shortage|Damage|On-Hand|Misdelivery>",
    #     "checks": [("CHK_COL", "RESP_COL", "Human Label"), ...]
    # }
}


TYPE_CATEGORY_MAP = {
    "OV": "Overage",
    "NB": "Overage",
    "AS": "Shortage",
    "DS": "Shortage",
    "BNF": "Shortage",
    "PR": "Damage",
    "RD": "Damage",
    "RF": "Damage",
    "DD": "Damage",
    "OH": "On-Hand",
    "MSD": "Misdelivery",
}


KNOWN_TYPES = set(TYPE_CATEGORY_MAP.keys())
SUPPORTED_TYPES = set(TYPE_REGISTRY.keys())


def get_type_checks(type_code: str) -> list[tuple[str, str, str]]:
    type_info = TYPE_REGISTRY.get(type_code.upper(), {})
    checks = type_info.get("checks", [])
    return list(checks)


def map_ovp014_to_exception_input(row: dict[str, str]) -> ExceptionInput:
    """Map OVP014 investigation CSV format to ExceptionInput.
    
    OVP014 columns:
    - TYPE: Exception type (OV, NB)
    - Pronumber: PRO number
    - EntryUser: User who entered
    - OD400_CHK, BL_CHK, DR_CHK, PS_CHK, CONSIGNEE_CHK, SHIPMENTCHK: Investigation checks (Y/N)
    - xxx_CHK_RESP: Investigation responses (text)
    - ERROR_MESSAGE: Investigation notes
    - DATEADDED, DATEUPDATED: Dates (often empty/whitespace)
    - ENTRYSTATUS: Investigation status (Complete/In Progress)
    """
    
    # Build a normalized header map to support variants like "OD400 Check" vs "OD400_CHK"
    def _normalize_key(k: str) -> str:
        return "".join(ch.lower() for ch in (k or "") if ch.isalnum())

    norm_map: dict[str, str] = { _normalize_key(k): k for k in row.keys() }

    def _lookup(*variants: str) -> str:
        for v in variants:
            k = norm_map.get(_normalize_key(v))
            if k:
                return (row.get(k) or "").strip()
        return ""

    # Map investigation answers from check/response field pairs (support spaced or underscored names)
    check_pairs = [
        (("OD400_CHK", "OD400 Check"), ("OD400_CHK_RESP", "OD400 Check Response")),
        (("BL_CHK", "BL Check"), ("BL_CHK_RESP", "BL Check Response")),
        (("DR_CHK", "DR Check"), ("DR_CHK_RESP", "DR Check Response")),
        (("PS_CHK", "PS Check"), ("PS_CHK_RESP", "PS Check Response")),
        (("CONSIGNEE_CHK", "Consignee Check"), ("CONSIGNEE_CHK_RESP", "Consignee Check Response")),
        (("SHIPMENTCHK", "Shipment Check"), ("SHIPMENTCHK_RESP", "Shipment Check Response")),
    ]

    investigation_answers: dict[str, str] = {}
    for (chk_variants, resp_variants) in check_pairs:
        check_value = _lookup(*chk_variants)
        resp_value = _lookup(*resp_variants)
        if check_value:
            # store under the canonical column name
            investigation_answers[chk_variants[0]] = check_value
        if resp_value:
            investigation_answers[resp_variants[0]] = resp_value

    # Map investigation status: accept variants like "Investigation Status" or ENTRYSTATUS
    entry_status = _lookup("ENTRYSTATUS", "Investigation Status", "EntryStatus")
    investigation_status = "0" if entry_status.lower() == "complete" else "1"

    # Parse dates - DATEADDED/DATEUPDATED might be empty or whitespace-padded
    date_added = _lookup("DATEADDED", "DateAdded", "DATE_ADDED")
    date_updated = _lookup("DATEUPDATED", "DateUpdated", "DATE_UPDATED")

    # Clearing codes (optional) — append to remarks if present
    clearing_code = _lookup("Clearing Code", "ClearingCode")
    clearing_code_full = _lookup("Clearing Code Full Form", "ClearingCodeFullForm")

    remarks = _lookup("ERROR_MESSAGE", "Error Message", "Remarks")
    if clearing_code or clearing_code_full:
        appended = f"Clearing Code: {clearing_code} {clearing_code_full}".strip()
        if remarks:
            remarks = remarks + "\n" + appended
        else:
            remarks = appended

    return ExceptionInput(
        # Identity
        osdType=_lookup("TYPE", "Exception Type") or "OV",
        osdNumber=_lookup("Exception Number", "osdNumber", "OSDNumber"),
        proNumber=_lookup("Pronumber", "Pro Number", "proNumber"),

        # Time - use entry user/date if available
        entryBy=_lookup("EntryUser", "Entry User"),
        createdDate=date_added,
        lastUpdatedDate=date_updated,

        # Investigation
        investigationStatus=investigation_status,
        remarks=remarks,

        # Default fallbacks for required numeric fields
        totalValue="0",
        value1k="0",
        totalPieces="0",
        pieces="0",
        weight="0",
        numberOfPallets="0",
        handlingUnits="0",
    )
