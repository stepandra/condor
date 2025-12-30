"""
Basis Trade controller configuration.

Defines defaults and validation for a basis trade between spot and perp connectors.
"""

from typing import Any, Dict, List, Optional, Tuple

from .._base import ControllerField


DEFAULTS: Dict[str, Any] = {
    "controller_name": "basis_trade",
    "controller_type": "generic",
    "id": "",
    "total_amount_quote": 100,
    "manual_kill_switch": False,
    "connector_pair_spot": {
        "connector_name": "dedust/router",
        "trading_pair": "TON-USDT",
    },
    "connector_pair_perp": {
        "connector_name": "hyperliquid_perpetual",
        "trading_pair": "TON-USD",
    },
    "entry_threshold": 0.01,
    "exit_threshold": 0.002,
    "take_profit": None,
    "stop_loss": None,
    "tp_global": None,
    "sl_global": None,
    "tp_multiplier": 2,
    "use_full_perp_balance": True,
    "limit_spot_to_balance": True,
    "min_amount_quote": 10,
    "pos_hedge_ratio": 1.0,
    "leverage": 10,
    "position_mode": "ONEWAY",
    "min_gas_balance": 0,
    "candles_config": [],
}


FIELDS: Dict[str, ControllerField] = {
    "id": ControllerField(
        name="id",
        label="Config ID",
        type="str",
        required=True,
        hint="Auto-generated with sequence number",
    ),
    "connector_pair_spot": ControllerField(
        name="connector_pair_spot",
        label="Spot Connector + Pair",
        type="dict",
        required=True,
        hint="Gateway connector and trading pair",
    ),
    "connector_pair_perp": ControllerField(
        name="connector_pair_perp",
        label="Perp Connector + Pair",
        type="dict",
        required=True,
        hint="Perpetual connector and trading pair",
    ),
    "entry_threshold": ControllerField(
        name="entry_threshold",
        label="Entry Threshold",
        type="float",
        required=True,
        hint="Basis entry threshold (e.g. 0.01 = 1%)",
        default=0.01,
    ),
    "exit_threshold": ControllerField(
        name="exit_threshold",
        label="Exit Threshold",
        type="float",
        required=True,
        hint="Basis exit threshold (e.g. 0.002 = 0.2%)",
        default=0.002,
    ),
    "tp_multiplier": ControllerField(
        name="tp_multiplier",
        label="TP Multiplier",
        type="float",
        required=False,
        hint="Take profit multiplier on margin (e.g. 2 = 2x)",
        default=2,
    ),
    "use_full_perp_balance": ControllerField(
        name="use_full_perp_balance",
        label="Use Full Perp Balance",
        type="bool",
        required=False,
        hint="Use full perp collateral balance",
        default=True,
    ),
    "limit_spot_to_balance": ControllerField(
        name="limit_spot_to_balance",
        label="Limit Spot to Balance",
        type="bool",
        required=False,
        hint="Cap spot quote amount to available balance",
        default=True,
    ),
    "min_amount_quote": ControllerField(
        name="min_amount_quote",
        label="Min Amount (Quote)",
        type="float",
        required=False,
        hint="Minimum order size in quote",
        default=10,
    ),
    "pos_hedge_ratio": ControllerField(
        name="pos_hedge_ratio",
        label="Hedge Ratio",
        type="float",
        required=False,
        hint="Spot/perp notional ratio",
        default=1.0,
    ),
    "leverage": ControllerField(
        name="leverage",
        label="Leverage",
        type="int",
        required=True,
        hint="Perp leverage (e.g. 10)",
        default=10,
    ),
    "position_mode": ControllerField(
        name="position_mode",
        label="Position Mode",
        type="str",
        required=False,
        hint="ONEWAY or HEDGE",
        default="ONEWAY",
    ),
    "min_gas_balance": ControllerField(
        name="min_gas_balance",
        label="Min Gas Balance",
        type="float",
        required=False,
        hint="Minimum gas token balance",
        default=0,
    ),
}


FIELD_ORDER: List[str] = [
    "id",
    "connector_pair_spot",
    "connector_pair_perp",
    "entry_threshold",
    "exit_threshold",
    "tp_multiplier",
    "use_full_perp_balance",
    "limit_spot_to_balance",
    "min_amount_quote",
    "pos_hedge_ratio",
    "leverage",
    "position_mode",
    "min_gas_balance",
]


WIZARD_STEPS: List[str] = [
    "spot_connector",
    "spot_pair",
    "perp_connector",
    "perp_pair",
    "entry_threshold",
    "exit_threshold",
    "review",
]


def _get_connector_pair(config: Dict[str, Any], key: str) -> Dict[str, str]:
    value = config.get(key)
    if isinstance(value, dict):
        return value
    return {}


def validate_config(config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Validate basis trade configuration.

    Checks:
    - Spot and perp connector pairs are provided
    - Entry threshold > exit threshold
    - Leverage and ratios are positive
    """
    spot = _get_connector_pair(config, "connector_pair_spot")
    perp = _get_connector_pair(config, "connector_pair_perp")

    if not spot.get("connector_name") or not spot.get("trading_pair"):
        return False, "Missing spot connector or trading pair"
    if not perp.get("connector_name") or not perp.get("trading_pair"):
        return False, "Missing perp connector or trading pair"

    try:
        entry = float(config.get("entry_threshold", 0))
        exit_thr = float(config.get("exit_threshold", 0))
    except (ValueError, TypeError):
        return False, "Invalid entry/exit threshold"

    if entry <= 0:
        return False, "Entry threshold must be positive"
    if exit_thr < 0:
        return False, "Exit threshold must be non-negative"
    if entry <= exit_thr:
        return False, "Entry threshold must be greater than exit threshold"

    try:
        leverage = int(config.get("leverage", 0))
    except (ValueError, TypeError):
        return False, "Invalid leverage"
    if leverage <= 0:
        return False, "Leverage must be positive"

    try:
        tp_multiplier = float(config.get("tp_multiplier", 1))
    except (ValueError, TypeError):
        return False, "Invalid TP multiplier"
    if tp_multiplier < 1:
        return False, "TP multiplier must be >= 1"

    try:
        min_amount_quote = float(config.get("min_amount_quote", 0))
    except (ValueError, TypeError):
        return False, "Invalid min_amount_quote"
    if min_amount_quote <= 0:
        return False, "min_amount_quote must be positive"

    try:
        hedge_ratio = float(config.get("pos_hedge_ratio", 0))
    except (ValueError, TypeError):
        return False, "Invalid pos_hedge_ratio"
    if hedge_ratio <= 0:
        return False, "pos_hedge_ratio must be positive"

    if not config.get("use_full_perp_balance", True):
        try:
            total_amount = float(config.get("total_amount_quote", 0))
        except (ValueError, TypeError):
            return False, "Invalid total_amount_quote"
        if total_amount <= 0:
            return False, "total_amount_quote must be positive"

    return True, None


def _clean_connector_name(name: str) -> str:
    cleaned = name.replace("_perpetual", "").replace("_spot", "")
    cleaned = cleaned.replace("/", "-")
    return cleaned


def generate_id(
    config: Dict[str, Any],
    existing_configs: List[Dict[str, Any]]
) -> str:
    """
    Generate a unique config ID with sequential numbering.

    Format: NNN_basis_spotConnector_spotPair_perpConnector_perpPair
    Example: 001_basis_dedust-router_TON-USDT_hyperliquid_TON-USD
    """
    max_num = 0
    for cfg in existing_configs:
        config_id = cfg.get("id", "")
        if not config_id:
            continue
        parts = config_id.split("_", 1)
        if parts and parts[0].isdigit():
            max_num = max(max_num, int(parts[0]))

    seq = str(max_num + 1).zfill(3)

    spot = _get_connector_pair(config, "connector_pair_spot")
    perp = _get_connector_pair(config, "connector_pair_perp")

    spot_connector = _clean_connector_name(spot.get("connector_name", "spot"))
    perp_connector = _clean_connector_name(perp.get("connector_name", "perp"))
    spot_pair = spot.get("trading_pair", "SPOT").upper()
    perp_pair = perp.get("trading_pair", "PERP").upper()

    return f"{seq}_basis_{spot_connector}_{spot_pair}_{perp_connector}_{perp_pair}"
