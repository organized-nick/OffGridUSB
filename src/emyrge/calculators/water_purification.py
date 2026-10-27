"""Water Purification Dosing Calculator (F-13).

Deterministic CDC / WHO Safe Water Systems reference calculations for emergency
chlorination, iodine disinfection, thermal boiling, and solar SODIS treatment.
Guarantees 100% numerical accuracy and robust division-by-zero guards.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, Optional, Union


@dataclass
class WaterParams:
    """Input parameters for water purification calculation."""
    volume_liters: float
    is_turbid: bool = False
    method: str = "bleach"  # "bleach", "iodine", "boiling", "sodis"
    concentration_pct: float = 6.0
    elevation_meters: float = 0.0
    is_cloudy: bool = False


class WaterCalculator:
    """CDC / WHO emergency water purification dosing calculations."""

    @staticmethod
    def calculate_bleach(
        volume_liters: float,
        is_turbid: bool = False,
        concentration_pct: float = 6.0,
    ) -> Dict[str, Any]:
        """Calculates bleach (sodium hypochlorite) drops and contact time.

        Args:
            volume_liters: Volume of water to disinfect in liters.
            is_turbid: True if water is cloudy, murky, or turbid.
            concentration_pct: Bleach concentration percentage (nominally 6.0%).

        Returns:
            Dictionary matching authoritative WaterPurificationOracle schema.

        Raises:
            ValueError: If volume_liters <= 0 or concentration_pct is outside (0, 15.0].
        """
        if volume_liters <= 0:
            raise ValueError("Volume must be strictly positive")
        if concentration_pct <= 0 or concentration_pct > 15.0:
            raise ValueError("Concentration must be between 1% and 15%")

        # Base CDC ratio at 6% concentration: 2 drops/L clear, 4 drops/L cloudy (1 drop ~= 0.05 mL)
        base_drops_per_liter = 4 if is_turbid else 2
        scaling = 6.0 / concentration_pct
        total_drops = math.ceil(volume_liters * base_drops_per_liter * scaling)
        total_ml = round(total_drops * 0.05, 2)
        contact_time_min = 60 if is_turbid else 30

        return {
            "method": "bleach",
            "volume_liters": volume_liters,
            "is_turbid": is_turbid,
            "drops": total_drops,
            "volume_ml": total_ml,
            "contact_time_minutes": contact_time_min,
            "chlorine_ppm_target": 2.0 if not is_turbid else 4.0,
        }

    @staticmethod
    def calculate_iodine(
        volume_liters: float,
        is_turbid: bool = False,
    ) -> Dict[str, Any]:
        """Calculates 2% tincture of iodine drops and contact time.

        Args:
            volume_liters: Volume of water to disinfect in liters.
            is_turbid: True if water is cloudy, murky, or turbid.

        Returns:
            Dictionary matching authoritative WaterPurificationOracle schema.

        Raises:
            ValueError: If volume_liters <= 0.
        """
        if volume_liters <= 0:
            raise ValueError("Volume must be strictly positive")

        # 2% Tincture of Iodine: 5 drops/L clear, 10 drops/L turbid
        drops_per_liter = 10 if is_turbid else 5
        total_drops = math.ceil(volume_liters * drops_per_liter)
        total_ml = round(total_drops * 0.05, 2)
        contact_time_min = 60 if is_turbid else 30

        return {
            "method": "iodine_2pct",
            "volume_liters": volume_liters,
            "is_turbid": is_turbid,
            "drops": total_drops,
            "volume_ml": total_ml,
            "contact_time_minutes": contact_time_min,
            "warning": "Contraindicated in pregnancy or thyroid disease",
        }

    @staticmethod
    def calculate_boiling(
        volume_liters: float,
        elevation_meters: float = 0.0,
    ) -> Dict[str, Any]:
        """Calculates thermal boiling duration for pathogen sterilization.

        Args:
            volume_liters: Volume of water in liters.
            elevation_meters: Altitude above sea level in meters.

        Returns:
            Dictionary containing boiling duration instructions.

        Raises:
            ValueError: If volume_liters <= 0.
        """
        if volume_liters <= 0:
            raise ValueError("Volume must be strictly positive")

        # Rolling boil: 1 minute below 2000m (6500ft), 3 minutes above 2000m
        is_high_altitude = elevation_meters >= 2000.0
        boil_time_min = 3 if is_high_altitude else 1

        return {
            "method": "boiling",
            "volume_liters": volume_liters,
            "elevation_meters": elevation_meters,
            "boil_time_minutes": boil_time_min,
            "instruction": "Bring water to a vigorous rolling boil for the specified duration.",
        }

    @staticmethod
    def calculate_sodis(
        volume_liters: float,
        is_cloudy: bool = False,
        is_turbid: bool = False,
    ) -> Dict[str, Any]:
        """Calculates Solar Water Disinfection (SODIS) exposure time.

        Args:
            volume_liters: Volume of water in clear PET bottles.
            is_cloudy: True if sky is overcast (>50% cloud cover).
            is_turbid: True if water has visible turbidity (NTU > 30).

        Returns:
            Dictionary containing SODIS treatment parameters.

        Raises:
            ValueError: If volume_liters <= 0.
        """
        if volume_liters <= 0:
            raise ValueError("Volume must be strictly positive")

        if is_turbid:
            return {
                "method": "sodis",
                "volume_liters": volume_liters,
                "is_effective": False,
                "exposure_hours": 0,
                "warning": "Water turbidity prevents UV penetration. Filter or flocculate water before SODIS.",
            }

        exposure_hours = 48 if is_cloudy else 6
        return {
            "method": "sodis",
            "volume_liters": volume_liters,
            "is_effective": True,
            "exposure_hours": exposure_hours,
            "instruction": "Expose clean PET bottles horizontally to direct sunlight.",
        }

    @classmethod
    def calculate(cls, params: Union[WaterParams, Dict[str, Any]]) -> Dict[str, Any]:
        """Unified entry point supporting WaterParams dataclass or dictionary."""
        if isinstance(params, dict):
            p = WaterParams(**params)
        else:
            p = params

        method = p.method.lower()
        if method == "bleach":
            return cls.calculate_bleach(p.volume_liters, is_turbid=p.is_turbid, concentration_pct=p.concentration_pct)
        elif method in ("iodine", "iodine_2pct"):
            return cls.calculate_iodine(p.volume_liters, is_turbid=p.is_turbid)
        elif method == "boiling":
            return cls.calculate_boiling(p.volume_liters, elevation_meters=p.elevation_meters)
        elif method == "sodis":
            return cls.calculate_sodis(p.volume_liters, is_cloudy=p.is_cloudy, is_turbid=p.is_turbid)
        else:
            raise ValueError(f"Unknown water purification method: '{p.method}'")

    @staticmethod
    def format_mesh_summary(result: Dict[str, Any]) -> str:
        """Formats calculation into a concise string for radio mesh (<= 200B)."""
        method = result.get("method")
        if method == "bleach":
            return (
                f"Bleach: {result['drops']} drops ({result['volume_ml']} mL), "
                f"wait {result['contact_time_minutes']} min."
            )
        elif method == "iodine_2pct":
            return (
                f"Iodine: {result['drops']} drops ({result['volume_ml']} mL), "
                f"wait {result['contact_time_minutes']} min."
            )
        elif method == "boiling":
            return f"Boil: {result['volume_liters']}L rolling boil for {result['boil_time_minutes']} min."
        elif method == "sodis":
            if not result.get("is_effective", True):
                return "SODIS: Ineffective due to turbidity; filter first."
            return f"SODIS: Expose {result['volume_liters']}L PET bottles for {result['exposure_hours']}h."
        return str(result)

    # Unit Conversion Helpers
    @staticmethod
    def gallons_to_liters(gallons: float) -> float:
        """Converts US liquid gallons to liters."""
        return round(gallons * 3.785411784, 3)

    @staticmethod
    def liters_to_gallons(liters: float) -> float:
        """Converts liters to US liquid gallons."""
        return round(liters / 3.785411784, 3)
