import asyncio
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import json

@dataclass
class StrategyConfig:
    """Configuration for trading strategies"""
    name: str
    enabled: bool = True
    max_position_size: float = 1000  # USD
    profit_target: float = 0.02  # 2%
    stop_loss: float = 0.01  # 1%
    max_daily_trades: int = 50
    maker_only: bool = True  # Use maker orders for rebates
    
@dataclass
class TradeSignal:
    """Trading signal data"""
    coin: str
    action: str  # "buy", "sell", "hold"
    confidence: float  # 0-1
    price: float
    size: float
    reason: str

class ProfitMaximizingStrategies:
    """
    Collection of automated trading strategies optimized for profit
    """
    
    def __init__(self, trader, config: Dict):
        self.trader = trader
        self.config = config
        self.active_strategies = {}
        self.trade_history = []
        self.logger = logging.getLogger(__name__)
        
    async def dca_strategy(self, coin: str, amount: float, interval_hours: int = 4) -> Dict:
        """
        Dollar Cost Averaging strategy with maker rebates
        """
        try:
            strategy_id = f"dca_{coin}_{int(time.time())}"
            
            # Get current price for reference
            current_price = (await self.trader.info.all_mids()).get(coin, 0)
            
            # Calculate order placement below market for maker rebates
            buy_price = current_price * 0.9995  # 0.05% below market
            
            # Place maker buy order
            result = await self.trader.place_maker_order(
                coin=coin,
                is_buy=True,
                size=amount / buy_price,
                price=buy_price
            )
            
            if result.get("status") == "ok":
                self.active_strategies[strategy_id] = {
                    "type": "dca",
                    "coin": coin,
                    "amount": amount,
                    "interval_hours": interval_hours,
                    "last_order": time.time(),
                    "total_invested": amount,
                    "orders_placed": 1,
                    "expected_rebate": amount * 0.0002  # 0.02% rebate
                }
                
                return {
                    "status": "success",
                    "strategy_id": strategy_id,
                    "message": f"DCA strategy started for {coin}",
                    "next_order_in": f"{interval_hours} hours",
                    "expected_rebate": f"${amount * 0.0002:.4f}"
                }
        
        except Exception as e:
            self.logger.error(f"DCA strategy error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def grid_trading_strategy(
        self, 
        coin: str, 
        base_price: float, 
        grid_spacing: float = 0.005,  # 0.5%
        grid_levels: int = 10,
        order_size: float = 100
    ) -> Dict:
        """
        Grid trading strategy for market making profits
        """
        try:
            strategy_id = f"grid_{coin}_{int(time.time())}"
            orders_placed = []
            
            # Calculate grid levels
            for i in range(-grid_levels//2, grid_levels//2 + 1):
                if i == 0:
                    continue  # Skip center price
                
                grid_price = base_price * (1 + i * grid_spacing)
                is_buy = i < 0  # Buy orders below, sell orders above
                
                # Place maker order
                result = await self.trader.place_maker_order(
                    coin=coin,
                    is_buy=is_buy,
                    size=order_size / grid_price,
                    price=grid_price
                )
                
                if result.get("status") == "ok":
                    orders_placed.append({
                        "price": grid_price,
                        "side": "buy" if is_buy else "sell",
                        "size": order_size / grid_price,
                        "expected_rebate": (order_size / grid_price) * grid_price * 0.0002
                    })
            
            if orders_placed:
                total_rebate_potential = sum(order["expected_rebate"] for order in orders_placed)
                
                self.active_strategies[strategy_id] = {
                    "type": "grid",
                    "coin": coin,
                    "base_price": base_price,
                    "grid_spacing": grid_spacing,
                    "orders": orders_placed,
                    "total_orders": len(orders_placed),
                    "rebate_potential": total_rebate_potential
                }
                
                return {
                    "status": "success",
                    "strategy_id": strategy_id,
                    "orders_placed": len(orders_placed),
                    "total_rebate_potential": f"${total_rebate_potential:.4f}",
                    "price_range": f"${min(o['price'] for o in orders_placed):.2f} - ${max(o['price'] for o in orders_placed):.2f}"
                }
        
        except Exception as e:
            self.logger.error(f"Grid strategy error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def momentum_scalping(
        self,
        coin: str,
        momentum_threshold: float = 0.002,  # 0.2% price movement
        profit_target: float = 0.001,  # 0.1% profit
        max_hold_time: int = 300  # 5 minutes
    ) -> Dict:
        """
        Momentum scalping strategy
        """
        try:
            # Get recent price data
            candles = await self.trader.info.candles_snapshot(coin, "1m", 10)
            if len(candles) < 5:
                return {"status": "error", "message": "Insufficient price data"}
            
            # Calculate momentum
            recent_prices = [float(c['c']) for c in candles[-5:]]
            price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
            
            if abs(price_change) < momentum_threshold:
                return {"status": "no_signal", "message": "No momentum detected"}
            
            # Determine trade direction
            is_buy = price_change > 0
            current_price = recent_prices[-1]
            
            # Calculate entry and exit prices
            if is_buy:
                entry_price = current_price * 0.9998  # Slightly below market
                exit_price = entry_price * (1 + profit_target)
            else:
                entry_price = current_price * 1.0002  # Slightly above market  
                exit_price = entry_price * (1 - profit_target)
            
            # Place entry order
            entry_result = await self.trader.place_maker_order(
                coin=coin,
                is_buy=is_buy,
                size=100 / entry_price,  # $100 position
                price=entry_price
            )
            
            if entry_result.get("status") == "ok":
                strategy_id = f"scalp_{coin}_{int(time.time())}"
                
                self.active_strategies[strategy_id] = {
                    "type": "scalping",
                    "coin": coin,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "is_buy": is_buy,
                    "entry_time": time.time(),
                    "max_hold_time": max_hold_time,
                    "profit_target": profit_target
                }
                
                return {
                    "status": "success",
                    "strategy_id": strategy_id,
                    "direction": "LONG" if is_buy else "SHORT",
                    "entry_price": f"${entry_price:.4f}",
                    "target_price": f"${exit_price:.4f}",
                    "momentum": f"{price_change*100:+.2f}%"
                }
        
        except Exception as e:
            self.logger.error(f"Scalping strategy error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def arbitrage_scanner(self) -> List[Dict]:
        """
        Scan for arbitrage opportunities between different assets
        """
        opportunities = []
        
        try:
            # Get all available mids
            all_mids = await self.trader.info.all_mids()
            
            # Look for triangular arbitrage opportunities
            # Example: BTC -> ETH -> USDC -> BTC
            btc_price = all_mids.get("BTC", 0)
            eth_price = all_mids.get("ETH", 0)
            
            if btc_price > 0 and eth_price > 0:
                # Calculate cross rates and look for discrepancies
                btc_eth_rate = btc_price / eth_price
                
                # Check if there's an arbitrage opportunity
                # This is simplified - real arbitrage would need orderbook depth analysis
                theoretical_rate = 15.5  # Example theoretical BTC/ETH rate
                rate_difference = abs(btc_eth_rate - theoretical_rate) / theoretical_rate
                
                if rate_difference > 0.001:  # 0.1% arbitrage opportunity
                    opportunities.append({
                        "type": "triangular_arbitrage",
                        "assets": ["BTC", "ETH"],
                        "profit_potential": f"{rate_difference*100:.2f}%",
                        "current_rate": btc_eth_rate,
                        "theoretical_rate": theoretical_rate,
                        "action": "Execute arbitrage cycle"
                    })
        
        except Exception as e:
            self.logger.error(f"Arbitrage scanner error: {e}")
        
        return opportunities
    
    async def trend_following_strategy(
        self,
        coin: str,
        lookback_periods: int = 20,
        trend_threshold: float = 0.01  # 1% trend
    ) -> Dict:
        """
        Trend following strategy using moving averages
        """
        try:
            # Get historical data
            candles = await self.trader.info.candles_snapshot(coin, "1h", lookback_periods + 5)
            if len(candles) < lookback_periods:
                return {"status": "error", "message": "Insufficient data"}
            
            # Calculate moving averages
            prices = [float(c['c']) for c in candles]
            short_ma = sum(prices[-10:]) / 10  # 10-period MA
            long_ma = sum(prices[-20:]) / 20   # 20-period MA
            current_price = prices[-1]
            
            # Determine trend
            trend_strength = (short_ma - long_ma) / long_ma
            
            if abs(trend_strength) < trend_threshold:
                return {"status": "no_signal", "message": "No clear trend"}
            
            # Generate signal
            is_uptrend = trend_strength > 0
            
            if is_uptrend:
                # Enter long position
                entry_price = current_price * 0.9995
                target_price = entry_price * 1.02  # 2% target
                stop_price = entry_price * 0.99   # 1% stop
            else:
                # Enter short position
                entry_price = current_price * 1.0005
                target_price = entry_price * 0.98  # 2% target
                stop_price = entry_price * 1.01   # 1% stop
            
            # Place entry order
            result = await self.trader.place_maker_order(
                coin=coin,
                is_buy=is_uptrend,
                size=200 / entry_price,  # $200 position
                price=entry_price
            )
            
            if result.get("status") == "ok":
                strategy_id = f"trend_{coin}_{int(time.time())}"
                
                self.active_strategies[strategy_id] = {
                    "type": "trend_following",
                    "coin": coin,
                    "trend_direction": "up" if is_uptrend else "down",
                    "trend_strength": trend_strength,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "entry_time": time.time()
                }
                
                return {
                    "status": "success",
                    "strategy_id": strategy_id,
                    "trend": "UPTREND" if is_uptrend else "DOWNTREND",
                    "strength": f"{abs(trend_strength)*100:.2f}%",
                    "entry": f"${entry_price:.4f}",
                    "target": f"${target_price:.4f}"
                }
                
        except Exception as e:
            self.logger.error(f"Trend following error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def manage_active_strategies(self) -> Dict:
        """
        Monitor and manage all active strategies
        """
        management_results = {
            "total_strategies": len(self.active_strategies),
            "actions_taken": [],
            "total_profit": 0,
            "total_rebates": 0
        }
        
        try:
            current_time = time.time()
            
            for strategy_id, strategy in list(self.active_strategies.items()):
                coin = strategy["coin"]
                strategy_type = strategy["type"]
                
                # Get current price
                current_price = (await self.trader.info.all_mids()).get(coin, 0)
                
                if strategy_type == "scalping":
                    # Check if position should be closed
                    entry_time = strategy["entry_time"]
                    max_hold_time = strategy["max_hold_time"]
                    
                    if current_time - entry_time > max_hold_time:
                        # Force close position
                        close_result = await self.trader.smart_market_order(
                            coin=coin,
                            is_buy=not strategy["is_buy"],  # Opposite direction
                            size=100 / current_price  # Close position
                        )
                        
                        if close_result.get("status") == "ok":
                            profit = self._calculate_profit(strategy, current_price)
                            management_results["actions_taken"].append({
                                "strategy_id": strategy_id,
                                "action": "force_close",
                                "profit": profit
                            })
                            management_results["total_profit"] += profit
                            del self.active_strategies[strategy_id]
                
                elif strategy_type == "trend_following":
                    # Check stop loss and take profit
                    entry_price = strategy["entry_price"]
                    target_price = strategy["target_price"]
                    stop_price = strategy["stop_price"]
                    is_long = strategy["trend_direction"] == "up"
                    
                    should_close = False
                    close_reason = ""
                    
                    if is_long:
                        if current_price >= target_price:
                            should_close = True
                            close_reason = "take_profit"
                        elif current_price <= stop_price:
                            should_close = True
                            close_reason = "stop_loss"
                    else:
                        if current_price <= target_price:
                            should_close = True
                            close_reason = "take_profit"
                        elif current_price >= stop_price:
                            should_close = True
                            close_reason = "stop_loss"
                    
                    if should_close:
                        close_result = await self.trader.smart_market_order(
                            coin=coin,
                            is_buy=not is_long,
                            size=200 / current_price
                        )
                        
                        if close_result.get("status") == "ok":
                            profit = self._calculate_profit(strategy, current_price)
                            management_results["actions_taken"].append({
                                "strategy_id": strategy_id,
                                "action": close_reason,
                                "profit": profit
                            })
                            management_results["total_profit"] += profit
                            del self.active_strategies[strategy_id]
            
            return management_results
            
        except Exception as e:
            self.logger.error(f"Strategy management error: {e}")
            return {"status": "error", "message": str(e)}
    
    def _calculate_profit(self, strategy: Dict, current_price: float) -> float:
        """Calculate profit for a strategy"""
        try:
            entry_price = strategy["entry_price"]
            
            if strategy["type"] == "scalping":
                is_long = strategy["is_buy"]
                if is_long:
                    return (current_price - entry_price) / entry_price * 100  # $100 position
                else:
                    return (entry_price - current_price) / entry_price * 100
            
            elif strategy["type"] == "trend_following":
                is_long = strategy["trend_direction"] == "up"
                if is_long:
                    return (current_price - entry_price) / entry_price * 200  # $200 position
                else:
                    return (entry_price - current_price) / entry_price * 200
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Profit calculation error: {e}")
            return 0
    
    async def get_strategy_performance(self) -> Dict:
        """Get performance statistics for all strategies"""
        try:
            performance = {
                "active_strategies": len(self.active_strategies),
                "total_trades": len(self.trade_history),
                "strategy_breakdown": {},
                "profitability": {
                    "total_profit": 0,
                    "total_rebates": 0,
                    "win_rate": 0,
                    "average_trade": 0
                }
            }
            
            # Analyze trade history
            profitable_trades = [t for t in self.trade_history if t.get("profit", 0) > 0]
            total_profit = sum(t.get("profit", 0) for t in self.trade_history)
            total_rebates = sum(t.get("rebate", 0) for t in self.trade_history)
            
            performance["profitability"] = {
                "total_profit": total_profit,
                "total_rebates": total_rebates,
                "win_rate": len(profitable_trades) / max(len(self.trade_history), 1) * 100,
                "average_trade": total_profit / max(len(self.trade_history), 1)
            }
            
            # Strategy breakdown
            for strategy_id, strategy in self.active_strategies.items():
                strategy_type = strategy["type"]
                if strategy_type not in performance["strategy_breakdown"]:
                    performance["strategy_breakdown"][strategy_type] = {
                        "count": 0,
                        "total_capital": 0
                    }
                
                performance["strategy_breakdown"][strategy_type]["count"] += 1
                
                # Estimate capital deployed
                if strategy_type == "dca":
                    performance["strategy_breakdown"][strategy_type]["total_capital"] += strategy.get("total_invested", 0)
                elif strategy_type == "grid":
                    performance["strategy_breakdown"][strategy_type]["total_capital"] += len(strategy.get("orders", [])) * 100
            
            return performance
            
        except Exception as e:
            self.logger.error(f"Performance calculation error: {e}")
            return {"status": "error", "message": str(e)}

class RiskManager:
    """
    Risk management for automated strategies
    """
    
    def __init__(self, max_account_risk: float = 0.02):  # 2% max account risk
        self.max_account_risk = max_account_risk
        self.daily_loss_limit = 0.05  # 5% daily loss limit
        self.max_open_positions = 10
        
    async def check_risk_limits(self, trader, new_trade_size: float) -> Dict:
        """Check if new trade passes risk management rules"""
        try:
            # Get account information
            performance = await trader.track_performance()
            account_value = performance.get("account_value", 0)
            
            # Check daily loss limit
            daily_pnl = performance.get("total_pnl", 0)  # Simplified
            if daily_pnl < -account_value * self.daily_loss_limit:
                return {
                    "approved": False,
                    "reason": "Daily loss limit exceeded",
                    "limit": f"{self.daily_loss_limit*100}%"
                }
            
            # Check position size limit
            max_position_size = account_value * self.max_account_risk
            if new_trade_size > max_position_size:
                return {
                    "approved": False,
                    "reason": "Position size too large",
                    "max_size": max_position_size,
                    "requested": new_trade_size
                }
            
            return {"approved": True, "message": "Risk checks passed"}
            
        except Exception as e:
            return {"approved": False, "reason": f"Risk check error: {str(e)}"}
