"""
Vehicle Configuration Validator
Prevents hallucinations by validating vehicle configs against known database
"""

from typing import Optional
from models.vehicle import Vehicle

# Hardcoded valid configurations for now
# TODO: Load from Supabase vehicle table or vehicles.json when available
VALID_CONFIGS = {
    # Ford F-150 (comprehensive list)
    ("2011", "ford", "f-150", "5.0l"),
    ("2011", "ford", "f-150", "50l"),  # Normalized version
    ("2011", "ford", "f150", "50l"),  # No dash version
    ("2013", "ford", "f-150", "3.5lecoboost"),
    ("2013", "ford", "f150", "35lecoboost"),
    ("2013", "ford", "f-150", "5.0l"),
    ("2013", "ford", "f150", "50l"),
    ("2015", "ford", "f-150", "5.0l"),
    ("2015", "ford", "f150", "50l"),
    ("2015", "ford", "f-150", "2.7lecoboost"),
    ("2015", "ford", "f-150", "3.5lecoboost"),
    ("2016", "chevrolet", "silverado", "5.3l"),
    ("2016", "chevrolet", "silverado", "53l"),
    # Honda Civic
    ("2018", "honda", "civic", "1.5t"),
    ("2018", "honda", "civic", "15t"),
    ("2019", "honda", "accord", "1.5t"),
    # Toyota Camry
    ("2007", "toyota", "camry", "2.4l"),
    ("2007", "toyota", "camry", "24l"),
    ("2020", "toyota", "camry", "2.5l"),
    # Ram 1500
    ("2014", "ram", "1500", "5.7lhemi"),
    ("2014", "ram", "1500", "57lhemi"),
}


class VehicleValidator:
    """Validates vehicle configurations against known database"""

    @staticmethod
    def normalize_config(year: str, make: str, model: str, engine: str) -> tuple:
        """Normalize to canonical format for lookup"""
        return (
            str(year),
            make.lower().strip(),
            model.lower().strip().replace("_", "-"),
            engine.lower()
            .strip()
            .replace(" ", "")
            .replace("l", "l"),  # Keep 'L' lowercase
        )

    @staticmethod
    def is_valid(vehicle: Vehicle) -> tuple[bool, Optional[str]]:
        """
        Check if vehicle configuration is valid
        Returns: (is_valid, error_message)
        """
        config = VehicleValidator.normalize_config(
            vehicle.year, vehicle.make, vehicle.model, vehicle.engine
        )

        # Check against known configs
        if config in VALID_CONFIGS:
            return True, None

        # Check for obvious red flags
        year_int = int(vehicle.year)

        # 2019 F-150 never had 3.0L Powerstroke (that's F-250+)
        if (
            vehicle.year == "2019"
            and vehicle.make.lower() == "ford"
            and vehicle.model.lower() == "f-150"
            and "powerstroke" in vehicle.engine.lower()
        ):
            return (
                False,
                "INVALID: 2019 F-150 never offered 3.0L Powerstroke diesel (F-250/350 only)",
            )

        # Generic red flags
        if year_int < 1996:
            return False, f"INVALID: Pre-1996 vehicles not supported (OBD-II required)"

        if year_int > 2026:
            return False, f"INVALID: Future model year {year_int} not yet released"

        # Configuration not in database
        return (
            False,
            f"UNVERIFIED VEHICLE CONFIGURATION: {vehicle.year} {vehicle.make} {vehicle.model} {vehicle.engine} not in verified database. Cannot generate chunks for unverified configurations.",
        )


vehicle_validator = VehicleValidator()
