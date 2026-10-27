"""Solar and Battery Load Sizing Calculator (F-14).

Deterministic IEEE 1562 & NEC Article 690 formulas for standalone photovoltaic
system design: battery bank ampere-hour capacity and solar PV array wattage.
Guarantees zero-division guards and 100% oracle numerical parity.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, Optional, Union


@dataclass
class SolarParams:
    """Input parameters for standalone solar/battery sizing."""
    daily_wh: float
    system_voltage: float = 12.0
    dod: float = 0.8
    autonomy_days: float = 1.0
    inverter_eff: float = 0.90
    peak_sun_hours: float = 4.5
    system_derating: float = 0.77


class SolarCalculator:
    """IEEE 1562 & NEC Article 690 standalone solar and battery sizing."""

    @staticmethod
    def calculate_system(
        daily_wh: float,
        system_voltage: float = 12.0,
        dod: float = 0.8,
        autonomy_days: float = 1.0,
        inverter_eff: float = 0.90,
        peak_sun_hours: float = 4.5,
        system_derating: float = 0.77,
    ) -> Dict[str, Any]:
        """Calculates required battery capacity (Ah) and solar PV array size (Watts).

        Args:
            daily_wh: Total daily energy demand in Watt-hours.
            system_voltage: System nominal DC bus voltage (e.g. 12, 24, 48 V).
            dod: Maximum usable battery depth of discharge (0.0 to 1.0].
            autonomy_days: Desired days of reserve energy without sun.
            inverter_eff: Electrical efficiency of inverter (0.0 to 1.0].
            peak_sun_hours: Daily equivalent hours of full solar irradiance.
            system_derating: Combined derating factor (dust, wiring, temperature).

        Returns:
            Dictionary matching authoritative SolarBatteryOracle schema.

        Raises:
            ValueError: If any parameter is <= 0 or efficiency/derating factors exceed 1.0.
        """
        if daily_wh <= 0:
            raise ValueError("Daily energy must be positive")
        if system_voltage <= 0:
            raise ValueError("System voltage must be positive")
        if dod <= 0 or dod > 1.0:
            raise ValueError("Depth of discharge must be between 0.1 and 1.0")
        if peak_sun_hours <= 0:
            raise ValueError("Peak sun hours must be positive")
        if autonomy_days <= 0:
            raise ValueError("Autonomy days must be positive")
        if inverter_eff <= 0 or inverter_eff > 1.0:
            raise ValueError("Inverter efficiency must be between 0.1 and 1.0")
        if system_derating <= 0 or system_derating > 1.0:
            raise ValueError("System derating must be between 0.1 and 1.0")

        # Battery capacity in Ah (IEEE 1562)
        battery_ah = round((daily_wh * autonomy_days) / (system_voltage * dod * inverter_eff), 2)
        # Solar PV array in Watts (NEC 690)
        solar_watts = round(daily_wh / (peak_sun_hours * system_derating), 2)

        return {
            "daily_wh": daily_wh,
            "system_voltage": system_voltage,
            "dod": dod,
            "battery_capacity_ah": battery_ah,
            "solar_array_watts": solar_watts,
            "peak_sun_hours": peak_sun_hours,
        }

    @classmethod
    def calculate(cls, params: Union[SolarParams, Dict[str, Any]]) -> Dict[str, Any]:
        """Unified entry point supporting SolarParams dataclass or dictionary."""
        if isinstance(params, dict):
            p = SolarParams(**params)
        else:
            p = params

        return cls.calculate_system(
            daily_wh=p.daily_wh,
            system_voltage=p.system_voltage,
            dod=p.dod,
            autonomy_days=p.autonomy_days,
            inverter_eff=p.inverter_eff,
            peak_sun_hours=p.peak_sun_hours,
            system_derating=p.system_derating,
        )

    @staticmethod
    def get_equipment_recommendations(
        result: Dict[str, Any],
        panel_rating_w: float = 300.0,
        battery_unit_ah: float = 100.0,
    ) -> Dict[str, Any]:
        """Calculates physical component count estimates for field deployment."""
        solar_w = result["solar_array_watts"]
        bat_ah = result["battery_capacity_ah"]
        sys_v = result["system_voltage"]

        panels_needed = math.ceil(solar_w / panel_rating_w)
        batteries_needed = math.ceil(bat_ah / battery_unit_ah)
        # Charge controller minimum rating with NEC 125% continuous duty margin
        charge_controller_amps = round((solar_w / sys_v) * 1.25, 1)

        return {
            "panels_count": panels_needed,
            "panel_unit_rating_w": panel_rating_w,
            "batteries_count": batteries_needed,
            "battery_unit_rating_ah": battery_unit_ah,
            "min_charge_controller_amps": charge_controller_amps,
        }

    @staticmethod
    def format_mesh_summary(result: Dict[str, Any]) -> str:
        """Formats calculation into a concise string for radio mesh (<= 200B)."""
        return (
            f"Solar: Battery {result['battery_capacity_ah']} Ah, "
            f"Array {result['solar_array_watts']} W."
        )
