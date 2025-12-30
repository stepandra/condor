"""
Basis Trade Controller Module

Provides configuration, validation, and ID generation for basis trade controllers.
"""

import io
from typing import Any, Dict, List, Optional, Tuple

from .._base import BaseController, ControllerField
from .config import (
    DEFAULTS,
    FIELDS,
    FIELD_ORDER,
    WIZARD_STEPS,
    validate_config,
    generate_id,
)


class BasisTradeController(BaseController):
    """Basis trade controller implementation."""

    controller_type = "basis_trade"
    display_name = "Basis Trade"
    description = "Spot/perp basis trade with delta-neutral exposure"

    @classmethod
    def get_defaults(cls) -> Dict[str, Any]:
        defaults = DEFAULTS.copy()
        defaults["connector_pair_spot"] = DEFAULTS["connector_pair_spot"].copy()
        defaults["connector_pair_perp"] = DEFAULTS["connector_pair_perp"].copy()
        defaults["candles_config"] = list(DEFAULTS.get("candles_config", []))
        return defaults

    @classmethod
    def get_fields(cls) -> Dict[str, ControllerField]:
        return FIELDS

    @classmethod
    def get_field_order(cls) -> List[str]:
        return FIELD_ORDER

    @classmethod
    def validate_config(cls, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        return validate_config(config)

    @classmethod
    def generate_chart(
        cls,
        config: Dict[str, Any],
        candles_data: List[Dict[str, Any]],
        current_price: Optional[float] = None,
    ) -> io.BytesIO:
        return io.BytesIO()

    @classmethod
    def generate_id(
        cls,
        config: Dict[str, Any],
        existing_configs: List[Dict[str, Any]],
    ) -> str:
        return generate_id(config, existing_configs)


__all__ = [
    "BasisTradeController",
    "DEFAULTS",
    "FIELDS",
    "FIELD_ORDER",
    "WIZARD_STEPS",
    "validate_config",
    "generate_id",
]
