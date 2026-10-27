"""Survival Calculators and Source Verification Package for Project eMyrge.

Provides 100% deterministic, zero-hallucination survival engineering engines:
- Water Purification (F-13): Bleach, Iodine, Boiling, SODIS
- Solar & Battery Sizing (F-14): IEEE 1562 & NEC 690 PV / battery sizing
- Medical & Rehydration (F-15): WHO ORS, pediatric/adult paracetamol & ibuprofen
- Electrical & Unit Formulas (F-16): Ohm's law, DC voltage drop, AWG wire tables
- Source Verification Audit Pass (F-17): Numerical discrepancy & hallucination detector
- Calculator Auto-Router (F-18): Safety intent classification and parameter extraction
"""

from .water_purification import WaterCalculator, WaterParams
from .solar_battery import SolarCalculator, SolarParams
from .medical_rehydration import MedicalCalculator, MedicalParams
from .electrical_formulas import (
    ElectricalCalculator,
    ElectricalParams,
    AWG_RESISTANCE_OHM_PER_KM,
)
from .source_audit import (
    SourceAudit,
    AuditReport,
    FlaggedClaim,
    ClaimStatus,
    CalculatorRouter,
    CalculatorRouteResult,
    CalculatorType,
)

__all__ = [
    "WaterCalculator",
    "WaterParams",
    "SolarCalculator",
    "SolarParams",
    "MedicalCalculator",
    "MedicalParams",
    "ElectricalCalculator",
    "ElectricalParams",
    "AWG_RESISTANCE_OHM_PER_KM",
    "SourceAudit",
    "AuditReport",
    "FlaggedClaim",
    "ClaimStatus",
    "CalculatorRouter",
    "CalculatorRouteResult",
    "CalculatorType",
]
