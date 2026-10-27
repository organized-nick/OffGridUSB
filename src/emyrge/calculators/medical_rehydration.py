"""Medical & Rehydration Dosing Calculator (F-15).

Deterministic WHO Guidelines for Diarrhoeal Diseases (Oral Rehydration Therapy)
and weight-based pediatric/adult analgesics (paracetamol, ibuprofen).
Enforces clinical safety envelope [2.0 kg, 250.0 kg] and adult dosage caps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Union


@dataclass
class MedicalParams:
    """Input parameters for medical/rehydration dosing."""
    weight_kg: float
    medication: str = "paracetamol"  # "paracetamol", "ibuprofen", "ors"


class MedicalCalculator:
    """WHO Oral Rehydration Therapy & pediatric/adult analgesic dosing."""

    CLINICAL_MIN_WEIGHT_KG: float = 2.0
    CLINICAL_MAX_WEIGHT_KG: float = 250.0

    @classmethod
    def _validate_weight(cls, weight_kg: float) -> None:
        """Validates weight against clinical safety envelope [2 kg, 250 kg]."""
        if weight_kg < cls.CLINICAL_MIN_WEIGHT_KG or weight_kg > cls.CLINICAL_MAX_WEIGHT_KG:
            raise ValueError("Weight must be between 2 kg and 250 kg")

    @classmethod
    def calculate_ors(cls, weight_kg: float) -> Dict[str, Any]:
        """Calculates WHO Oral Rehydration Salts (ORS) solution volume.

        Formula: 75 mL/kg over 4 hours for mild to moderate dehydration.

        Args:
            weight_kg: Patient weight in kilograms [2.0, 250.0].

        Returns:
            Dictionary matching authoritative MedicalDosingOracle schema.

        Raises:
            ValueError: If weight_kg is outside clinical bounds [2.0, 250.0].
        """
        cls._validate_weight(weight_kg)

        volume_4h_ml = round(weight_kg * 75.0, 1)
        hourly_rate_ml = round(volume_4h_ml / 4.0, 1)

        return {
            "weight_kg": weight_kg,
            "total_ors_ml_4h": volume_4h_ml,
            "hourly_rate_ml": hourly_rate_ml,
            "reassessment_interval_hours": 4,
        }

    @classmethod
    def calculate_paracetamol(cls, weight_kg: float) -> Dict[str, Any]:
        """Calculates weight-based paracetamol (acetaminophen) dosing.

        Formula: 15 mg/kg per dose (capped at 1000 mg), 60 mg/kg/day (capped at 4000 mg).

        Args:
            weight_kg: Patient weight in kilograms [2.0, 250.0].

        Returns:
            Dictionary matching authoritative MedicalDosingOracle schema.

        Raises:
            ValueError: If weight_kg is outside clinical bounds [2.0, 250.0].
        """
        cls._validate_weight(weight_kg)

        calculated_single_mg = weight_kg * 15.0
        single_dose_mg = min(1000.0, round(calculated_single_mg, 1))
        calculated_daily_mg = weight_kg * 60.0
        max_daily_mg = min(4000.0, round(calculated_daily_mg, 1))

        return {
            "medication": "paracetamol",
            "weight_kg": weight_kg,
            "single_dose_mg": single_dose_mg,
            "interval_hours": "4-6",
            "max_daily_mg": max_daily_mg,
            "clamped_to_adult_max": calculated_single_mg > 1000.0,
        }

    @classmethod
    def calculate_ibuprofen(cls, weight_kg: float) -> Dict[str, Any]:
        """Calculates weight-based ibuprofen dosing.

        Formula: 10 mg/kg per dose (capped at 400 mg), 40 mg/kg/day (capped at 1200 mg).

        Args:
            weight_kg: Patient weight in kilograms [2.0, 250.0].

        Returns:
            Dictionary matching authoritative MedicalDosingOracle schema.

        Raises:
            ValueError: If weight_kg is outside clinical bounds [2.0, 250.0].
        """
        cls._validate_weight(weight_kg)

        calculated_single_mg = weight_kg * 10.0
        single_dose_mg = min(400.0, round(calculated_single_mg, 1))
        calculated_daily_mg = weight_kg * 40.0
        max_daily_mg = min(1200.0, round(calculated_daily_mg, 1))

        return {
            "medication": "ibuprofen",
            "weight_kg": weight_kg,
            "single_dose_mg": single_dose_mg,
            "interval_hours": "6-8",
            "max_daily_mg": max_daily_mg,
            "clamped_to_adult_max": calculated_single_mg > 400.0,
        }

    @classmethod
    def calculate(cls, params: Union[MedicalParams, Dict[str, Any]]) -> Dict[str, Any]:
        """Unified entry point supporting MedicalParams dataclass or dictionary."""
        if isinstance(params, dict):
            p = MedicalParams(**params)
        else:
            p = params

        med = p.medication.lower()
        if med == "ors":
            return cls.calculate_ors(p.weight_kg)
        elif med in ("paracetamol", "acetaminophen", "tylenol"):
            return cls.calculate_paracetamol(p.weight_kg)
        elif med in ("ibuprofen", "advil", "motrin"):
            return cls.calculate_ibuprofen(p.weight_kg)
        else:
            raise ValueError(f"Unknown medication or regimen: '{p.medication}'")

    @staticmethod
    def format_mesh_summary(result: Dict[str, Any]) -> str:
        """Formats calculation into a concise string for radio mesh (<= 200B)."""
        med = result.get("medication")
        if med == "paracetamol":
            return f"Paracetamol: {result['single_dose_mg']} mg every {result['interval_hours']}h."
        elif med == "ibuprofen":
            return f"Ibuprofen: {result['single_dose_mg']} mg every {result['interval_hours']}h."
        elif "total_ors_ml_4h" in result:
            return (
                f"ORS: {result['total_ors_ml_4h']} mL over 4h "
                f"({result['hourly_rate_ml']} mL/h)."
            )
        return str(result)

    # Unit Conversion Helpers
    @staticmethod
    def lbs_to_kg(lbs: float) -> float:
        """Converts pounds to kilograms."""
        return round(lbs * 0.45359237, 2)

    @staticmethod
    def kg_to_lbs(kg: float) -> float:
        """Converts kilograms to pounds."""
        return round(kg / 0.45359237, 2)
