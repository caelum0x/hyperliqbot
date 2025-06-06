import asyncio
import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.types import *

@dataclass
class TradingConfig:
    """Trading configuration based on actual Hyperliquid fee structure"""
    # Real Hyperliquid fee rates from knowledge doc
    base_taker_fee: float = 0.00035      # 0.035% for <$5M volume
    base_maker_fee: float = 0.0001       # 0.01% for <$5M volume
    
    # Maker rebate rates (negative = rebate)
    rebate_tier_1: float = -0.00001      # -0.001% for >0.5% maker volume
    rebate_tier_2: float = -0.00002      # -0.002% for >1.5% maker volume  
    rebate_tier_3: float = -0.00003      # -0.003% for >3% maker volume
    
    # Volume thresholds for fee tiers (14-day volume)
    tier_1_volume: float = 5000000       # $5M
    tier_2_volume: float = 25000000      # $25M
    tier_3_volume: float = 125000000     # $125M
    
    # Risk management
    max_position_size: float = 10000     # $10k max position
    min_profit_threshold: float = 0.001  # 0.1% minimum profit
    
    # Vault settings
    vault_profit_share: float = 0.10     # 10% profit share (actual rate)
    vault_minimum_capital: float = 100   # 100 USDC minimum
    vault_leader_min_ownership: float = 0.05  # 5% minimum ownership
    
    # Referral settings
    referral_commission_rate: float = 0.10    # 10% of referee fees
    referral_user_discount: float = 0.004    # 4% fee discount
    referral_volume_limit: float = 25000000  # $25M per referee

class ProfitOptimizedTrader:
    """
    Core trading engine optimized based on actual Hyperliquid features
    """
    
    def __init__(self, exchange: Exchange, info: Info, config: TradingConfig):
        self.exchange = exchange
        self.info = info
        self.config = config
        self.active_orders = {}
        self.profit_tracker = {}
        self.user_stats = {"14d_volume": 0, "14d_maker_volume": 0}
        self.logger = logging.getLogger(__name__)
        
    async def get_current_fee_tier(self) -> Dict:
        """Get current fee tier based on 14-day volume"""
        try:
            volume_14d = self.user_stats["14d_volume"]
            maker_volume_14d = self.user_stats["14d_maker_volume"]
            maker_percentage = maker_volume_14d / volume_14d if volume_14d > 0 else 0
            
            # Determine fee tier
            if volume_14d < self.config.tier_1_volume:
                taker_fee = 0.00035
                maker_fee = 0.0001
            elif volume_14d < self.config.tier_2_volume:
                taker_fee = 0.000325
                maker_fee = 0.00005
            elif volume_14d < self.config.tier_3_volume:
                taker_fee = 0.0003
                maker_fee = 0.0
            else:
                taker_fee = 0.000275 if volume_14d < 500000000 else 0.00019
                maker_fee = 0.0
            
            # Check for maker rebates
            rebate = 0.0
            if maker_percentage > 0.03:
                rebate = self.config.rebate_tier_3
            elif maker_percentage > 0.015:
                rebate = self.config.rebate_tier_2
            elif maker_percentage > 0.005:
                rebate = self.config.rebate_tier_1
            
            effective_maker_fee = maker_fee + rebate  # rebate is negative
            
            return {
                "volume_14d": volume_14d,
                "maker_volume_14d": maker_volume_14d,
                "maker_percentage": maker_percentage,
                "taker_fee": taker_fee,
                "maker_fee": maker_fee,
                "rebate": rebate,
                "effective_maker_fee": effective_maker_fee,
                "tier": self._get_tier_name(volume_14d)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting fee tier: {e}")
            return {"error": str(e)}
    
    def _get_tier_name(self, volume: float) -> str:
        """Get tier name based on volume"""
        if volume < 5000000:
            return "Bronze"
        elif volume < 25000000:
            return "Silver" 
        elif volume < 125000000:
            return "Gold"
        elif volume < 500000000:
            return "Platinum"
        else:
            return "Diamond"

    async def place_maker_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,  # Use proper notation: sz = size
        px: float,  # Use proper notation: px = price  
        reduce_only: bool = False,
        vault_address: str = None
    ) -> Dict:
        """
        Place maker order to earn rebates - updated for actual Hyperliquid API
        """
        try:
            # Get asset index for proper notation
            meta_response = self.info.meta()
            universe = meta_response.get('universe', [])
            asset = next((i for i, c in enumerate(universe) if c['name'] == coin), None)
            
            if asset is None:
                return {'status': 'error', 'message': f'Asset {coin} not found'}
            
            # Build order using actual Hyperliquid order structure with proper notation
            # a=asset, b=isBuy, p=price, s=size, r=reduceOnly, t=type
            order_request = {
                "a": asset,
                "b": is_buy,
                "p": str(px),  # price as string
                "s": str(sz),  # size as string
                "r": reduce_only,
                "t": {"limit": {"tif": "Alo"}}  # Add Liquidity Only
            }
            
            # Place order using exchange
            if vault_address:
                order_result = self.exchange.order(
                    coin, is_buy, sz, px, 
                    {"limit": {"tif": "Alo"}},
                    reduce_only=reduce_only,
                    vaultAddress=vault_address
                )
            else:
                order_result = self.exchange.order(
                    coin, is_buy, sz, px,
                    {"limit": {"tif": "Alo"}},
                    reduce_only=reduce_only
                )
            
            if order_result.get("status") == "ok":
                # Calculate expected rebate based on current tier
                fee_info = await self.get_current_fee_tier()
                expected_fee = sz * px * fee_info.get("effective_maker_fee", 0)
                
                # Track order using proper oid (order id) notation
                order_data = order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0]
                if "resting" in order_data:
                    oid = order_data["resting"]["oid"]
                    
                    self.active_orders[oid] = {
                        "coin": coin,
                        "side": "buy" if is_buy else "sell",
                        "sz": sz,    # size
                        "px": px,    # price
                        "timestamp": time.time(),
                        "expected_fee": expected_fee,
                        "vault_address": vault_address
                    }
                    
                    rebate_msg = f"rebate: ${abs(expected_fee):.4f}" if expected_fee < 0 else f"fee: ${expected_fee:.4f}"
                    self.logger.info(f"Maker order placed: {coin} {sz}@{px} ({rebate_msg})")
            
            return order_result
            
        except Exception as e:
            self.logger.error(f"Error placing maker order: {e}")
            return {"status": "error", "message": str(e)}
    
    async def smart_market_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,  # Use proper notation
        max_slippage: float = 0.005
    ) -> Dict:
        """
        Smart market order that minimizes fees and slippage
        """
        try:
            # Get current orderbook
            l2_book = self.info.l2_snapshot(coin)
            
            if not l2_book or not l2_book.get("levels"):
                return {"status": "error", "message": "No orderbook data"}
            
            bids = l2_book["levels"][0]
            asks = l2_book["levels"][1]
            
            if is_buy and asks:
                # Use proper notation: px = price
                best_ask_px = float(asks[0]["px"])
                limit_px = best_ask_px * (1 + max_slippage)
            elif not is_buy and bids:
                best_bid_px = float(bids[0]["px"])
                limit_px = best_bid_px * (1 - max_slippage)
            else:
                return {"status": "error", "message": "No liquidity"}
            
            # Use IOC (Immediate or Cancel) with proper TIF notation
            order_result = self.exchange.order(
                coin, is_buy, sz, limit_px,
                {"limit": {"tif": "Ioc"}}  # Immediate or Cancel
            )
            
            return order_result
            
        except Exception as e:
            self.logger.error(f"Error placing smart market order: {e}")
            return {"status": "error", "message": str(e)}
    
    async def calculate_optimal_spread(self, coin: str, base_spread_bps: int = 20) -> Tuple[float, float]:
        """
        Calculate optimal bid/ask spread for market making
        """
        try:
            # Get recent volatility using proper candle format
            candles = self.info.candles_snapshot(coin, "1m", 60)
            if len(candles) < 10:
                # Fallback to base spread
                all_mids = self.info.all_mids()
                mid_px = float(all_mids.get(coin, 0))  # Use px notation
                spread = mid_px * (base_spread_bps / 10000)
                return mid_px - spread/2, mid_px + spread/2
            
            # Calculate volatility-adjusted spread using proper candle notation
            # c = close price in candle format
            prices = [float(c['c']) for c in candles]
            volatility = self._calculate_volatility(prices)
            
            # Adjust spread based on volatility
            vol_multiplier = max(1.0, min(3.0, volatility * 100))  # 1x to 3x based on volatility
            adjusted_spread_bps = base_spread_bps * vol_multiplier
            
            mid_px = prices[-1]
            spread = mid_px * (adjusted_spread_bps / 10000)
            
            return mid_px - spread/2, mid_px + spread/2
            
        except Exception as e:
            self.logger.error(f"Error calculating optimal spread: {e}")
            return 0, 0
    
    def _calculate_volatility(self, prices: List[float]) -> float:
        """Calculate price volatility"""
        if len(prices) < 2:
            return 0.01  # 1% default
        
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        return variance ** 0.5
    
    async def profit_taking_strategy(
        self,
        coin: str,
        target_profit_pct: float = 0.02,  # 2% profit target
        stop_loss_pct: float = 0.01       # 1% stop loss
    ) -> Dict:
        """
        Automated profit taking and stop loss using proper notation
        """
        try:
            user_state = self.info.user_state(self.exchange.account_address)
            positions = user_state.get("assetPositions", [])
            
            for asset_pos in positions:
                position = asset_pos["position"]
                if position["coin"] != coin or float(position["szi"]) == 0:  # szi = signed size
                    continue
                
                szi = float(position["szi"])  # Use proper notation
                entry_px = float(position["entryPx"])  # entryPx = entry price
                
                # Get current mid price
                all_mids = self.info.all_mids()
                current_px = float(all_mids.get(coin, entry_px))
                
                # Calculate P&L
                if szi > 0:  # Long position (positive signed size)
                    pnl_pct = (current_px - entry_px) / entry_px
                    
                    if pnl_pct >= target_profit_pct:
                        # Take profit - close long position (sell)
                        result = await self.smart_market_order(coin, False, abs(szi))
                        self.logger.info(f"Profit taken on {coin}: {pnl_pct:.2%}")
                        return {"action": "profit_taken", "pnl_pct": pnl_pct, "result": result}
                    
                    elif pnl_pct <= -stop_loss_pct:
                        # Stop loss - close long position (sell)
                        result = await self.smart_market_order(coin, False, abs(szi))
                        self.logger.info(f"Stop loss triggered on {coin}: {pnl_pct:.2%}")
                        return {"action": "stop_loss", "pnl_pct": pnl_pct, "result": result}
                
                else:  # Short position (negative signed size)
                    pnl_pct = (entry_px - current_px) / entry_px
                    
                    if pnl_pct >= target_profit_pct:
                        # Take profit - close short position (buy)
                        result = await self.smart_market_order(coin, True, abs(szi))
                        self.logger.info(f"Profit taken on {coin}: {pnl_pct:.2%}")
                        return {"action": "profit_taken", "pnl_pct": pnl_pct, "result": result}
                    
                    elif pnl_pct <= -stop_loss_pct:
                        # Stop loss - close short position (buy)
                        result = await self.smart_market_order(coin, True, abs(szi))
                        self.logger.info(f"Stop loss triggered on {coin}: {pnl_pct:.2%}")
                        return {"action": "stop_loss", "pnl_pct": pnl_pct, "result": result}
            
            return {"action": "monitoring", "message": "No action needed"}
            
        except Exception as e:
            self.logger.error(f"Error in profit taking strategy: {e}")
            return {"action": "error", "message": str(e)}
    
    async def track_performance(self) -> Dict:
        """
        Track trading performance with actual Hyperliquid data using proper notation
        """
        try:
            user_state = self.info.user_state(self.exchange.account_address)
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Get recent fills for accurate profit calculation
            recent_fills = self.info.user_fills(self.exchange.account_address)
            
            total_pnl = 0
            total_fees_paid = 0
            total_rebates_earned = 0
            trade_count = 0
            volume_14d = 0
            maker_volume_14d = 0
            
            # Process fills using proper notation
            for fill in recent_fills:
                pnl = float(fill.get("closedPnl", 0))
                fee = float(fill.get("fee", 0))
                # Use proper notation: px=price, sz=size
                notional = float(fill.get("px", 0)) * float(fill.get("sz", 0))
                
                total_pnl += pnl
                trade_count += 1
                
                # Track fees vs rebates
                if fee < 0:
                    total_rebates_earned += abs(fee)
                else:
                    total_fees_paid += fee
                
                # Track volume (last 14 days would need timestamp filtering)
                volume_14d += notional
                
                # Maker orders have negative fees
                if fee <= 0:
                    maker_volume_14d += notional
            
            # Update user stats
            self.user_stats["14d_volume"] = volume_14d
            self.user_stats["14d_maker_volume"] = maker_volume_14d
            
            net_profit = total_pnl + total_rebates_earned - total_fees_paid
            maker_percentage = maker_volume_14d / volume_14d if volume_14d > 0 else 0
            
            return {
                "account_value": account_value,
                "total_pnl": total_pnl,
                "total_fees_paid": total_fees_paid,
                "total_rebates_earned": total_rebates_earned,
                "net_profit": net_profit,
                "trade_count": trade_count,
                "volume_14d": volume_14d,
                "maker_volume_14d": maker_volume_14d,
                "maker_percentage": maker_percentage,
                "avg_profit_per_trade": net_profit / trade_count if trade_count > 0 else 0,
                "fee_efficiency": total_rebates_earned / (total_fees_paid + total_rebates_earned) if (total_fees_paid + total_rebates_earned) > 0 else 0,
                "current_tier": await self.get_current_fee_tier()
            }
            
        except Exception as e:
            self.logger.error(f"Error tracking performance: {e}")
            return {"error": str(e)}

    async def optimize_for_rebates(self, coin: str, target_volume: float) -> Dict:
        """
        Optimize trading strategy to maximize maker rebates
        """
        try:
            fee_info = await self.get_current_fee_tier()
            current_maker_pct = fee_info.get("maker_percentage", 0)
            
            # Calculate required maker volume for next rebate tier
            total_volume = fee_info.get("volume_14d", 0)
            required_maker_volume_tier1 = total_volume * 0.005  # 0.5%
            required_maker_volume_tier2 = total_volume * 0.015  # 1.5%
            required_maker_volume_tier3 = total_volume * 0.03   # 3%
            
            current_maker_volume = fee_info.get("maker_volume_14d", 0)
            
            recommendations = []
            
            if current_maker_pct < 0.005:
                needed = required_maker_volume_tier1 - current_maker_volume
                recommendations.append(f"Need ${needed:,.0f} more maker volume for -0.001% rebate")
            elif current_maker_pct < 0.015:
                needed = required_maker_volume_tier2 - current_maker_volume
                recommendations.append(f"Need ${needed:,.0f} more maker volume for -0.002% rebate")
            elif current_maker_pct < 0.03:
                needed = required_maker_volume_tier3 - current_maker_volume
                recommendations.append(f"Need ${needed:,.0f} more maker volume for -0.003% rebate")
            else:
                recommendations.append("Maximum rebate tier achieved!")
            
            return {
                "status": "success",
                "current_stats": fee_info,
                "recommendations": recommendations,
                "strategy": "Focus on maker-only orders with tight spreads"
            }
            
        except Exception as e:
            self.logger.error(f"Error optimizing for rebates: {e}")
            return {"status": "error", "message": str(e)}
