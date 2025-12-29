"""Check TON basis between DeDust spot and Hyperliquid perp."""

from decimal import Decimal
from pydantic import BaseModel, Field
from telegram.ext import ContextTypes

from servers import get_client


class Config(BaseModel):
    """TON basis check: buy on DeDust, short on Hyperliquid."""

    amount: float = Field(default=1.0, description="Base amount in TON to quote")
    dex_connector: str = Field(default="dedust", description="Gateway DEX connector")
    dex_network: str = Field(default="mainnet", description="Gateway network")
    dex_trading_pair: str = Field(default="TON-USDT", description="DEX trading pair")
    cex_connector: str = Field(default="hyperliquid", description="CEX connector")
    cex_trading_pair: str = Field(default="TON-USD", description="CEX trading pair")
    slippage_pct: float = Field(default=1.0, description="Slippage for DEX quotes")


def _is_ton_pair(trading_pair: str) -> bool:
    return trading_pair.upper().startswith("TON-")


async def run(config: Config, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Check TON basis: buy spot on DeDust, short on Hyperliquid."""
    chat_id = context._chat_id if hasattr(context, "_chat_id") else None
    client = await get_client(chat_id)

    if not client:
        return "No server available. Configure servers in /config."

    if not _is_ton_pair(config.dex_trading_pair) or not _is_ton_pair(config.cex_trading_pair):
        return "This routine is TON-only. Use TON-* trading pairs."

    results = []

    dex_buy = None
    dex_sell = None
    cex_buy = None
    cex_sell = None

    # --- DEX Quotes (DeDust) ---
    try:
        if hasattr(client, "gateway_swap"):
            async def get_dex_quote(side: str):
                result = await client.gateway_swap.get_swap_quote(
                    connector=config.dex_connector,
                    network=config.dex_network,
                    trading_pair=config.dex_trading_pair,
                    side=side,
                    amount=Decimal(str(config.amount)),
                    slippage_pct=Decimal(str(config.slippage_pct)),
                )
                if isinstance(result, dict):
                    return result.get("price")
                return None

            import asyncio
            dex_buy, dex_sell = await asyncio.gather(
                get_dex_quote("BUY"),
                get_dex_quote("SELL"),
            )
        else:
            results.append("DEX: Gateway not available")
    except Exception as e:
        results.append(f"DEX Error: {str(e)}")

    # --- CEX Quotes (Hyperliquid) ---
    try:
        async def get_cex_quote(is_buy: bool):
            result = await client.market_data.get_price_for_volume(
                connector_name=config.cex_connector,
                trading_pair=config.cex_trading_pair,
                volume=config.amount,
                is_buy=is_buy,
            )
            if isinstance(result, dict):
                return (
                    result.get("result_price")
                    or result.get("price")
                    or result.get("average_price")
                )
            return None

        import asyncio
        cex_buy, cex_sell = await asyncio.gather(
            get_cex_quote(True),
            get_cex_quote(False),
        )
    except Exception as e:
        results.append(f"CEX Error: {str(e)}")

    # Display quotes
    if dex_buy:
        results.append(f"DEX BUY:  {float(dex_buy):.6f}")
    if dex_sell:
        results.append(f"DEX SELL: {float(dex_sell):.6f}")
    if cex_buy:
        results.append(f"CEX BUY:  {float(cex_buy):.6f}")
    if cex_sell:
        results.append(f"CEX SELL: {float(cex_sell):.6f}")

    if not dex_buy and not dex_sell:
        results.append("DEX: No quotes")
    if not cex_buy and not cex_sell:
        results.append("CEX: No quotes")

    # --- Basis Analysis ---
    results.append("")
    results.append("--- Basis ---")

    opportunities = []

    # Buy spot on DeDust, short on Hyperliquid
    if dex_buy and cex_sell:
        dex_buy_f = float(dex_buy)
        cex_sell_f = float(cex_sell)
        spread_pct = ((cex_sell_f - dex_buy_f) / dex_buy_f) * 100
        basis = cex_sell_f - dex_buy_f
        if spread_pct > 0:
            opportunities.append(
                f"LONG DEX / SHORT CEX: +{spread_pct:.2f}% (basis {basis:.6f})"
            )
        else:
            results.append(f"LONG DEX / SHORT CEX: {spread_pct:.2f}%")

    # Reverse: sell spot, buy back short
    if dex_sell and cex_buy:
        dex_sell_f = float(dex_sell)
        cex_buy_f = float(cex_buy)
        spread_pct = ((dex_sell_f - cex_buy_f) / cex_buy_f) * 100
        basis = dex_sell_f - cex_buy_f
        if spread_pct > 0:
            opportunities.append(
                f"SHORT CEX CLOSE / SELL DEX: +{spread_pct:.2f}% (basis {basis:.6f})"
            )
        else:
            results.append(f"SHORT CEX CLOSE / SELL DEX: {spread_pct:.2f}%")

    if opportunities:
        results.append("")
        results.append("OPPORTUNITIES FOUND:")
        results.extend(opportunities)
    else:
        results.append("No profitable basis found.")

    return "\n".join(results)
