"""
Trade alerts for Hummingbot trades.

Polls trade history and sends a Telegram message for each new fill.
"""

import logging
from datetime import datetime
from collections.abc import MutableMapping
from typing import Any, Dict, Iterable, List, Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from utils.telegram_formatters import escape_markdown_v2, format_amount, format_price
from ._shared import get_bots_client

logger = logging.getLogger(__name__)

_ALERTS_KEY = "trade_alerts"
_JOB_PREFIX = "trade_alerts"
_DEFAULT_INTERVAL_SEC = 10
_MAX_TRADES_PER_POLL = 100

_ORDERS_KEY = "order_alerts"
_ORDERS_JOB_PREFIX = "order_alerts"
_DEFAULT_ORDERS_INTERVAL_SEC = 5
_MAX_ORDERS_PER_POLL = 200


def _job_name(chat_id: int) -> str:
    return f"{_JOB_PREFIX}:{chat_id}"


def _orders_job_name(chat_id: int) -> str:
    return f"{_ORDERS_JOB_PREFIX}:{chat_id}"


def _get_chat_state(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> Dict[str, Any]:
    """Return a per-chat mutable state dict.

    NOTE: In python-telegram-bot v20+, Application.chat_data is exposed as a
    MappingProxyType (read-only). Mutations must go through Context.chat_data.
    """

    chat_data = getattr(context, "chat_data", None)
    if isinstance(chat_data, MutableMapping):
        return chat_data.setdefault(_ALERTS_KEY, {})

    # Fallback for contexts without chat_data (should be rare). Keep state in bot_data.
    bot_data = getattr(getattr(context, "application", None), "bot_data", None)
    if isinstance(bot_data, MutableMapping):
        all_chats = bot_data.setdefault(_ALERTS_KEY, {})
        if isinstance(all_chats, MutableMapping):
            return all_chats.setdefault(str(chat_id), {})

    return {}


def _get_orders_state(
    context: ContextTypes.DEFAULT_TYPE, chat_id: int
) -> Dict[str, Any]:
    chat_data = getattr(context, "chat_data", None)
    if isinstance(chat_data, MutableMapping):
        return chat_data.setdefault(_ORDERS_KEY, {})

    bot_data = getattr(getattr(context, "application", None), "bot_data", None)
    if isinstance(bot_data, MutableMapping):
        all_chats = bot_data.setdefault(_ORDERS_KEY, {})
        if isinstance(all_chats, MutableMapping):
            return all_chats.setdefault(str(chat_id), {})

    return {}


def _normalize_list(value: Optional[Iterable[str]]) -> Optional[List[str]]:
    if not value:
        return None
    items = [v for v in value if v]
    return items or None


def _merge_filters(
    existing: Optional[Dict[str, List[str]]], new: Optional[Dict[str, List[str]]]
) -> Dict[str, List[str]]:
    existing = existing or {}
    new = new or {}
    merged: Dict[str, List[str]] = {}
    for key in ("account_names", "connector_names", "trading_pairs"):
        merged_values = set(existing.get(key, [])) | set(new.get(key, []))
        if merged_values:
            merged[key] = sorted(merged_values)
    return merged


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_trade_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except (TypeError, ValueError):
            return None
    try:
        ts = str(value)
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _format_trade_alert(trade: Dict[str, Any], ts: Optional[datetime]) -> str:
    connector = trade.get("connector_name", "unknown")
    pair = trade.get("trading_pair", "unknown")
    side = str(trade.get("trade_type", "unknown")).upper()
    account = trade.get("account_name")

    amount = _safe_float(trade.get("amount"))
    price = _safe_float(trade.get("price"))
    fee_paid = _safe_float(trade.get("fee_paid"))
    fee_currency = trade.get("fee_currency") or ""

    amount_str = (
        format_amount(amount) if amount is not None else str(trade.get("amount", ""))
    )
    price_str = (
        format_price(price) if price is not None else str(trade.get("price", ""))
    )

    lines = ["🔔 *Trade Filled*"]
    if account:
        lines.append(f"Account: {escape_markdown_v2(account)}")
    lines.append(f"Connector: {escape_markdown_v2(connector)}")
    lines.append(f"Pair: {escape_markdown_v2(pair)}")
    lines.append(f"Side: {escape_markdown_v2(side)}")
    lines.append(f"Amount: {escape_markdown_v2(amount_str)}")
    lines.append(f"Price: {escape_markdown_v2(price_str)}")
    if fee_paid is not None:
        fee_str = format_amount(fee_paid)
        fee_line = f"Fee: {escape_markdown_v2(fee_str)}"
        if fee_currency:
            fee_line += f" {escape_markdown_v2(fee_currency)}"
        lines.append(fee_line)
    if ts:
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"Time: {escape_markdown_v2(time_str)}")
    return "\n".join(lines)


def build_trade_filters(
    configs: List[Dict[str, Any]],
    controller_ids: List[str],
    credentials_profile: Optional[str] = None,
) -> Dict[str, List[str]]:
    target_ids = set(controller_ids or [])
    connectors: set[str] = set()
    trading_pairs: set[str] = set()

    def add_pair(connector: Optional[str], pair: Optional[str]) -> None:
        if connector:
            connectors.add(connector)
        if pair:
            trading_pairs.add(pair)

    for cfg in configs:
        cfg_id = cfg.get("id") or cfg.get("config_name")
        if target_ids and cfg_id not in target_ids:
            continue

        add_pair(cfg.get("connector_name"), cfg.get("trading_pair"))

        spot = cfg.get("connector_pair_spot")
        if isinstance(spot, dict):
            add_pair(spot.get("connector_name"), spot.get("trading_pair"))

        perp = cfg.get("connector_pair_perp")
        if isinstance(perp, dict):
            add_pair(perp.get("connector_name"), perp.get("trading_pair"))

    filters: Dict[str, List[str]] = {}
    if credentials_profile:
        filters["account_names"] = [credentials_profile]
    if connectors:
        filters["connector_names"] = sorted(connectors)
    if trading_pairs:
        filters["trading_pairs"] = sorted(trading_pairs)
    return filters


def is_trade_alerts_enabled(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    job_name = _job_name(chat_id)
    if context.job_queue.get_jobs_by_name(job_name):
        return True
    state = _get_chat_state(context, chat_id)
    return bool(state.get("enabled", False))


async def start_trade_alerts(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    filters: Optional[Dict[str, List[str]]] = None,
    interval: int = _DEFAULT_INTERVAL_SEC,
) -> bool:
    state = _get_chat_state(context, chat_id)
    if filters:
        state["filters"] = _merge_filters(state.get("filters"), filters)

    job_name = _job_name(chat_id)
    if context.job_queue.get_jobs_by_name(job_name):
        state["enabled"] = True
        return False

    context.job_queue.run_repeating(
        _poll_trades,
        interval=interval,
        first=1.0,
        data={"chat_id": chat_id},
        name=job_name,
        chat_id=chat_id,
    )
    state["enabled"] = True
    return True


def stop_trade_alerts(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    job_name = _job_name(chat_id)
    jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in jobs:
        job.schedule_removal()
    state = _get_chat_state(context, chat_id)
    state["enabled"] = False
    return bool(jobs)


async def handle_toggle_trade_alerts(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    chat_id = update.effective_chat.id

    if is_trade_alerts_enabled(context, chat_id):
        stop_trade_alerts(context, chat_id)
    else:
        state = _get_chat_state(context, chat_id)
        filters = state.get("filters")
        await start_trade_alerts(context, chat_id, filters=filters)


async def _poll_trades(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.data.get("chat_id") if job and job.data else None
    if not chat_id:
        return

    state = _get_chat_state(context, chat_id)
    filters = state.get("filters", {})

    account_names = _normalize_list(filters.get("account_names"))
    connector_names = _normalize_list(filters.get("connector_names"))
    trading_pairs = _normalize_list(filters.get("trading_pairs"))

    start_time = state.get("last_seen_ts")
    if start_time is not None:
        try:
            start_time = max(0, int(float(start_time) * 1000) - 1000)
        except (TypeError, ValueError):
            start_time = None

    try:
        client = await get_bots_client(chat_id)
        result = await client.trading.get_trades(
            account_names=account_names,
            connector_names=connector_names,
            trading_pairs=trading_pairs,
            start_time=start_time,
            limit=_MAX_TRADES_PER_POLL,
        )
        trades = result.get("data", []) if isinstance(result, dict) else []
    except Exception as e:
        logger.warning(f"Trade alerts poll failed: {e}")
        return

    if not trades:
        return

    parsed: List[Tuple[Tuple[float, str], Dict[str, Any], Optional[datetime]]] = []
    for trade in trades:
        ts = _parse_trade_timestamp(trade.get("timestamp"))
        if not ts:
            continue
        ts_value = ts.timestamp()
        trade_id = str(trade.get("trade_id", ""))
        parsed.append(((ts_value, trade_id), trade, ts))

    if not parsed:
        return

    parsed.sort(key=lambda item: item[0])
    last_ts = state.get("last_seen_ts")
    last_id = state.get("last_seen_trade_id", "")

    if last_ts is None:
        latest_key = parsed[-1][0]
        state["last_seen_ts"] = latest_key[0]
        state["last_seen_trade_id"] = latest_key[1]
        return

    last_key = (float(last_ts), str(last_id))
    new_trades = [item for item in parsed if item[0] > last_key]

    if not new_trades:
        latest_key = parsed[-1][0]
        if latest_key > last_key:
            state["last_seen_ts"] = latest_key[0]
            state["last_seen_trade_id"] = latest_key[1]
        return

    for _, trade, ts in new_trades:
        message = _format_trade_alert(trade, ts)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send trade alert: {e}")

    latest_key = new_trades[-1][0]
    state["last_seen_ts"] = latest_key[0]
    state["last_seen_trade_id"] = latest_key[1]


def is_order_alerts_enabled(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    job_name = _orders_job_name(chat_id)
    if context.job_queue.get_jobs_by_name(job_name):
        return True
    state = _get_orders_state(context, chat_id)
    return bool(state.get("enabled", False))


async def start_order_alerts(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    filters: Optional[Dict[str, List[str]]] = None,
    interval: int = _DEFAULT_ORDERS_INTERVAL_SEC,
) -> bool:
    state = _get_orders_state(context, chat_id)
    if filters:
        state["filters"] = _merge_filters(state.get("filters"), filters)

    job_name = _orders_job_name(chat_id)
    if context.job_queue.get_jobs_by_name(job_name):
        state["enabled"] = True
        return False

    context.job_queue.run_repeating(
        _poll_orders,
        interval=interval,
        first=1.0,
        data={"chat_id": chat_id},
        name=job_name,
        chat_id=chat_id,
    )
    state["enabled"] = True
    return True


def stop_order_alerts(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> bool:
    job_name = _orders_job_name(chat_id)
    jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in jobs:
        job.schedule_removal()
    state = _get_orders_state(context, chat_id)
    state["enabled"] = False
    return bool(jobs)


def _parse_order_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except (TypeError, ValueError):
            return None
    try:
        ts = str(value)
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _format_order_alert(order: Dict[str, Any], ts: Optional[datetime]) -> str:
    connector = order.get("connector_name", "unknown")
    pair = order.get("trading_pair", "unknown")
    side = str(order.get("trade_type", "unknown")).upper()
    account = order.get("account_name")

    order_type = str(order.get("order_type", "unknown")).upper()
    status = str(order.get("status", "SUBMITTED")).upper()

    amount = _safe_float(order.get("amount"))
    price = _safe_float(order.get("price"))

    amount_str = (
        format_amount(amount) if amount is not None else str(order.get("amount", ""))
    )
    price_str = (
        format_price(price) if price is not None else str(order.get("price", ""))
    )

    lines = ["🚀 *Order Submitted*"]
    if account:
        lines.append(f"Account: {escape_markdown_v2(account)}")
    lines.append(f"Connector: {escape_markdown_v2(connector)}")
    lines.append(f"Pair: {escape_markdown_v2(pair)}")
    lines.append(f"Side: {escape_markdown_v2(side)}")
    lines.append(f"Type: {escape_markdown_v2(order_type)}")
    lines.append(f"Amount: {escape_markdown_v2(amount_str)}")
    if price_str:
        lines.append(f"Price: {escape_markdown_v2(price_str)}")
    lines.append(f"Status: {escape_markdown_v2(status)}")
    if ts:
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"Time: {escape_markdown_v2(time_str)}")

    order_id = order.get("order_id") or order.get("client_order_id")
    if order_id:
        lines.append(f"Order ID: {escape_markdown_v2(str(order_id))}")

    return "\n".join(lines)


def _order_key(order: Dict[str, Any]) -> str:
    account = str(order.get("account_name") or "")
    connector = str(order.get("connector_name") or "")
    order_id = str(order.get("order_id") or order.get("client_order_id") or "")
    if not order_id:
        pair = str(order.get("trading_pair") or "")
        side = str(order.get("trade_type") or "")
        amount = str(order.get("amount") or "")
        return f"{account}:{connector}:{pair}:{side}:{amount}"
    return f"{account}:{connector}:{order_id}"


async def _poll_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.data.get("chat_id") if job and job.data else None
    if not chat_id:
        return

    state = _get_orders_state(context, chat_id)
    filters = state.get("filters", {})

    account_names = _normalize_list(filters.get("account_names"))
    connector_names = _normalize_list(filters.get("connector_names"))
    trading_pairs = _normalize_list(filters.get("trading_pairs"))

    try:
        client = await get_bots_client(chat_id)
        result = await client.trading.get_active_orders(
            account_names=account_names,
            connector_names=connector_names,
            trading_pairs=trading_pairs,
            limit=_MAX_ORDERS_PER_POLL,
        )
        orders = result.get("data", []) if isinstance(result, dict) else []
    except Exception as e:
        logger.warning(f"Order alerts poll failed: {e}")
        return

    if not orders:
        return

    if not state.get("initialized", False):
        state["initialized"] = True
        state["seen_order_keys"] = sorted({_order_key(o) for o in orders})
        return

    seen_keys = set(state.get("seen_order_keys") or [])
    current_keys = set()

    new_orders: List[Tuple[Tuple[float, str], Dict[str, Any], Optional[datetime]]] = []
    for order in orders:
        key = _order_key(order)
        current_keys.add(key)
        if key in seen_keys:
            continue

        ts = _parse_order_timestamp(order.get("created_at") or order.get("timestamp"))
        sort_key = (ts.timestamp() if ts else 0.0, key)
        new_orders.append((sort_key, order, ts))

    if not new_orders:
        state["seen_order_keys"] = sorted(current_keys)
        return

    new_orders.sort(key=lambda item: item[0])

    for _, order, ts in new_orders:
        message = _format_order_alert(order, ts)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send order alert: {e}")

    for _, order, _ in new_orders:
        current_keys.add(_order_key(order))
    state["seen_order_keys"] = sorted(current_keys)
