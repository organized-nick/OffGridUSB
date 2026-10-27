"""Electrical & Unit Formulas Calculator (F-16).

Deterministic Ohm's Law solver, DC circuit power calculations, two-conductor
voltage drop analysis per NEC standards, and survival unit conversions.
Enforces zero-division guards and short-circuit prevention.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, Optional, Union


# Standard annealed copper wire direct-current resistance at 20°C (NEC Chapter 9, Table 8)
AWG_RESISTANCE_OHM_PER_KM: Dict[str, float] = {
    "14": 8.286,
    "12": 5.211,
    "10": 3.277,
    "8": 2.061,
    "6": 1.296,
    "4": 0.815,
    "2": 0.513,
    "1/0": 0.323,
    "2/0": 0.256,
    "4/0": 0.161,
}


@dataclass
class ElectricalParams:
    """Input parameters for electrical calculations."""
    mode: str = "ohms_law"  # "ohms_law" or "voltage_drop"
    # Ohm's law parameters
    v: Optional[float] = None
    i: Optional[float] = None
    r: Optional[float] = None
    p: Optional[float] = None
    # Voltage drop parameters
    source_voltage: Optional[float] = None
    current_a: Optional[float] = None
    one_way_length_meters: Optional[float] = None
    wire_resistance_ohm_per_km: Optional[float] = None
    wire_awg: Optional[str] = None


class ElectricalCalculator:
    """Ohm's Law solver, DC voltage drop analysis, and electrical conversions."""

    @staticmethod
    def solve_ohms_law(
        v: Optional[float] = None,
        i: Optional[float] = None,
        r: Optional[float] = None,
        p: Optional[float] = None,
    ) -> Dict[str, float]:
        """Solves DC circuit parameters (V, I, R, P) given any two known variables.

        Args:
            v: Voltage in Volts (V >= 0).
            i: Current in Amperes (I >= 0).
            r: Resistance in Ohms (R > 0).
            p: Power in Watts (P >= 0).

        Returns:
            Dictionary matching authoritative ElectricalOhmOracle schema:
            {"voltage_v": float, "current_a": float, "resistance_ohm": float, "power_w": float}

        Raises:
            ValueError: If fewer than 2 parameters are provided, resistance is <= 0,
                        voltage is < 0, or zero-division occurs.
        """
        params = [param for param in (v, i, r, p) if param is not None]
        if len(params) < 2:
            raise ValueError("At least two electrical parameters are required")

        if r is not None and r <= 0:
            raise ValueError("Resistance must be strictly positive to prevent short circuit")
        if v is not None and v < 0:
            raise ValueError("Voltage cannot be negative in basic DC calculation")
        if i is not None and i < 0:
            raise ValueError("Current cannot be negative in basic DC calculation")
        if p is not None and p < 0:
            raise ValueError("Power cannot be negative")

        if v is not None and i is not None:
            if i <= 0:
                raise ValueError("Current must be strictly positive to calculate resistance")
            r = v / i
            p = v * i
        elif v is not None and r is not None:
            i = v / r
            p = (v * v) / r
        elif i is not None and r is not None:
            v = i * r
            p = (i * i) * r
        elif p is not None and v is not None:
            if v <= 0:
                raise ValueError("Voltage must be strictly positive when dividing power by voltage")
            if p <= 0:
                raise ValueError("Power must be strictly positive when calculating resistance from power and voltage")
            i = p / v
            r = (v * v) / p
        elif p is not None and i is not None:
            if i <= 0:
                raise ValueError("Current must be strictly positive when dividing power by current")
            v = p / i
            r = p / (i * i)
        elif p is not None and r is not None:
            i = math.sqrt(p / r)
            v = i * r

        return {
            "voltage_v": round(v, 3),
            "current_a": round(i, 3),
            "resistance_ohm": round(r, 3),
            "power_w": round(p, 3),
        }

    @staticmethod
    def calculate_dc_voltage_drop(
        source_voltage: float,
        current_a: float,
        one_way_length_meters: float,
        wire_resistance_ohm_per_km: float,
    ) -> Dict[str, Any]:
        """Calculates DC voltage drop and percentage loss over a two-conductor loop.

        Args:
            source_voltage: Supply voltage at the source (V > 0).
            current_a: Circuit continuous current in Amperes (I >= 0).
            one_way_length_meters: One-way distance from source to load in meters (L >= 0).
            wire_resistance_ohm_per_km: Conductor DC resistance in Ohms per kilometer (R > 0).

        Returns:
            Dictionary matching authoritative ElectricalOhmOracle schema.

        Raises:
            ValueError: If source_voltage <= 0, or current/length/resistance are negative/zero.
        """
        if source_voltage <= 0:
            raise ValueError("Source voltage must be positive")
        if current_a < 0 or one_way_length_meters < 0 or wire_resistance_ohm_per_km <= 0:
            raise ValueError("Current, length, and wire resistance must be positive")

        # Two-way conductor loop length: 2 * L
        total_resistance = 2 * (one_way_length_meters / 1000.0) * wire_resistance_ohm_per_km
        v_drop = round(current_a * total_resistance, 3)
        pct_drop = round((v_drop / source_voltage) * 100.0, 2)
        load_voltage = round(source_voltage - v_drop, 3)

        return {
            "source_voltage": source_voltage,
            "voltage_drop": v_drop,
            "percentage_drop": pct_drop,
            "load_voltage": load_voltage,
            "is_critical_acceptable": pct_drop <= 3.0,
            "is_standard_acceptable": pct_drop <= 5.0,
        }

    @classmethod
    def calculate_voltage_drop_by_awg(
        cls,
        source_voltage: float,
        current_a: float,
        one_way_length_meters: float,
        wire_awg: str,
    ) -> Dict[str, Any]:
        """Convenience method calculating voltage drop using standard AWG wire gauge."""
        awg_key = str(wire_awg).strip()
        if awg_key not in AWG_RESISTANCE_OHM_PER_KM:
            available = ", ".join(AWG_RESISTANCE_OHM_PER_KM.keys())
            raise ValueError(f"Unknown AWG wire gauge '{wire_awg}'. Available gauges: {available}")

        r_km = AWG_RESISTANCE_OHM_PER_KM[awg_key]
        res = cls.calculate_dc_voltage_drop(source_voltage, current_a, one_way_length_meters, r_km)
        res["wire_awg"] = awg_key
        return res

    @classmethod
    def calculate(cls, params: Union[ElectricalParams, Dict[str, Any]]) -> Dict[str, Any]:
        """Unified entry point supporting ElectricalParams dataclass or dictionary."""
        if isinstance(params, dict):
            p = ElectricalParams(**params)
        else:
            p = params

        mode = p.mode.lower()
        if mode in ("ohms_law", "ohm"):
            return cls.solve_ohms_law(v=p.v, i=p.i, r=p.r, p=p.p)
        elif mode in ("voltage_drop", "drop"):
            if p.wire_awg:
                return cls.calculate_voltage_drop_by_awg(
                    source_voltage=p.source_voltage,
                    current_a=p.current_a,
                    one_way_length_meters=p.one_way_length_meters,
                    wire_awg=p.wire_awg,
                )
            else:
                return cls.calculate_dc_voltage_drop(
                    source_voltage=p.source_voltage,
                    current_a=p.current_a,
                    one_way_length_meters=p.one_way_length_meters,
                    wire_resistance_ohm_per_km=p.wire_resistance_ohm_per_km,
                )
        else:
            raise ValueError(f"Unknown electrical calculation mode: '{p.mode}'")

    @staticmethod
    def format_mesh_summary(result: Dict[str, Any]) -> str:
        """Formats calculation into a concise string for radio mesh (<= 200B)."""
        if "resistance_ohm" in result and "power_w" in result:
            return f"Ohm: Current {result['current_a']} A, Power {result['power_w']} W."
        elif "voltage_drop" in result:
            status = "OK" if result.get("is_standard_acceptable", True) else "HIGH_DROP"
            return (
                f"Drop: {result['voltage_drop']}V ({result['percentage_drop']}%), "
                f"Load: {result['load_voltage']}V [{status}]."
            )
        return str(result)

    # General Survival Unit Conversions
    @staticmethod
    def celsius_to_fahrenheit(celsius: float) -> float:
        """Converts Celsius to Fahrenheit."""
        return round((celsius * 9.0 / 5.0) + 32.0, 1)

    @staticmethod
    def fahrenheit_to_celsius(fahrenheit: float) -> float:
        """Converts Fahrenheit to Celsius."""
        return round((fahrenheit - 32.0) * 5.0 / 9.0, 1)

    @staticmethod
    def meters_to_feet(meters: float) -> float:
        """Converts meters to feet."""
        return round(meters * 3.28084, 2)

    @staticmethod
    def feet_to_meters(feet: float) -> float:
        """Converts feet to meters."""
        return round(feet / 3.28084, 2)
