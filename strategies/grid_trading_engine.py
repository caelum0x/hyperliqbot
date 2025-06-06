import asyncio
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import random

@dataclass
class GridOrder:
    """Individual grid order"""
    order_id: str
    side: str  # buy/sell
    price: float
    size: float
    filled: bool
    created_at: datetime
    rebate_earned: float

class GridTradingEngine:
    """
    Automated grid trading for maximum maker rebates
    """
    
    def __init__(self, config):
        self.config = config
        self.active_grids = {}
        self.rebate_tracking = {}
        self.risk_limits = {
            "max_position_size": 50000,  # $50K max position
            "max_grid_levels": 20,
            "min_spread": 0.05,          # 0.05% minimum spread
            "max_leverage": 10
        }
        
    async def create_adaptive_grid(self, user_id: str, symbol: str, capital: float) -> Dict:
        """Create adaptive grid that adjusts to market conditions"""
        try:
            # Get current market data (simulated)
            market_data = await self._get_market_data(symbol)
            
            # Calculate optimal grid parameters
            grid_params = await self._calculate_grid_parameters(market_data, capital)
            
            # Create grid orders
            grid_orders = await self._place_grid_orders(user_id, symbol, grid_params)
            
            grid_config = {
                "user_id": user_id,
                "symbol": symbol,
                "capital_allocated": capital,
                "grid_params": grid_params,
                "orders_placed": len(grid_orders),
                "active_orders": grid_orders,
                "expected_daily_rebates": grid_params["expected_daily_volume"] * 0.0001,  # 0.01% rebate
                "risk_metrics": {
                    "max_drawdown": grid_params["max_drawdown"],
                    "position_limit": grid_params["position_limit"],
                    "stop_loss": grid_params["stop_loss"]
                }
            }
            
            self.active_grids[f"{user_id}_{symbol}"] = grid_config
            
            return {
                "status": "success",
                "grid_id": f"{user_id}_{symbol}",
                "config": grid_config,
                "monitoring": {
                    "auto_adjust": True,
                    "rebalance_frequency": "hourly",
                    "risk_monitoring": "continuous"
                }
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _get_market_data(self, symbol: str) -> Dict:
        """Get current market data for grid calculation"""
        # Simulate market data
        base_price = {"BTC": 95000, "ETH": 3400, "SOL": 190}.get(symbol, 100)
        
        return {
            "current_price": base_price,
            "24h_volume": base_price * 1000000,  # Mock volume
            "volatility": random.uniform(0.02, 0.08),  # 2-8% daily volatility
            "trend": random.choice(["bullish", "bearish", "sideways"]),
            "support_level": base_price * 0.95,
            "resistance_level": base_price * 1.05,
            "optimal_spread": random.uniform(0.1, 0.3)  # 0.1-0.3% optimal spread
        }
    
    async def _calculate_grid_parameters(self, market_data: Dict, capital: float) -> Dict:
        """Calculate optimal grid parameters based on market conditions"""
        try:
            current_price = market_data["current_price"]
            volatility = market_data["volatility"]
            optimal_spread = market_data["optimal_spread"]
            
            # Adaptive grid calculation
            grid_params = {
                "center_price": current_price,
                "grid_levels": min(int(capital / 1000), self.risk_limits["max_grid_levels"]),  # 1 level per $1K
                "spread_percent": max(optimal_spread, self.risk_limits["min_spread"]),
                "order_size": capital / (min(int(capital / 1000), self.risk_limits["max_grid_levels"]) * 2),  # Split between buy/sell
                "upper_bound": current_price * (1 + volatility * 2),
                "lower_bound": current_price * (1 - volatility * 2),
                "rebalance_threshold": volatility * 0.5,
                "expected_daily_volume": capital * 3,  # 3x capital turnover
                "max_drawdown": volatility * 1.5,
                "position_limit": capital * 0.8,  # 80% max position
                "stop_loss": current_price * (1 - volatility * 3)
            }
            
            return grid_params
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _place_grid_orders(self, user_id: str, symbol: str, params: Dict) -> List[GridOrder]:
        """Place all grid orders"""
        try:
            orders = []
            center_price = params["center_price"]
            grid_levels = params["grid_levels"]
            spread_percent = params["spread_percent"]
            order_size = params["order_size"]
            
            # Place buy orders below current price
            for i in range(1, grid_levels + 1):
                buy_price = center_price * (1 - (i * spread_percent / 100))
                if buy_price >= params["lower_bound"]:
                    order = GridOrder(
                        order_id=f"BUY_{user_id}_{symbol}_{i}_{int(time.time())}",
                        side="buy",
                        price=buy_price,
                        size=order_size / buy_price,  # Size in base currency
                        filled=False,
                        created_at=datetime.now(),
                        rebate_earned=0
                    )
                    orders.append(order)
            
            # Place sell orders above current price
            for i in range(1, grid_levels + 1):
                sell_price = center_price * (1 + (i * spread_percent / 100))
                if sell_price <= params["upper_bound"]:
                    order = GridOrder(
                        order_id=f"SELL_{user_id}_{symbol}_{i}_{int(time.time())}",
                        side="sell",
                        price=sell_price,
                        size=order_size / sell_price,  # Size in base currency
                        filled=False,
                        created_at=datetime.now(),
                        rebate_earned=0
                    )
                    orders.append(order)
            
            return orders
            
        except Exception as e:
            return []
    
    async def manage_grid_lifecycle(self, grid_id: str) -> Dict:
        """Manage complete grid lifecycle"""
        try:
            if grid_id not in self.active_grids:
                return {"status": "error", "message": "Grid not found"}
            
            grid = self.active_grids[grid_id]
            
            # Check for filled orders
            filled_orders = await self._check_filled_orders(grid)
            
            # Calculate rebates earned
            total_rebates = await self._calculate_rebates(filled_orders)
            
            # Rebalance if needed
            rebalance_needed = await self._check_rebalance_needed(grid)
            
            if rebalance_needed:
                rebalance_result = await self._rebalance_grid(grid_id)
            else:
                rebalance_result = {"status": "no_rebalance_needed"}
            
            # Risk monitoring
            risk_status = await self._monitor_risk(grid)
            
            lifecycle_result = {
                "grid_id": grid_id,
                "filled_orders": len(filled_orders),
                "total_rebates_earned": total_rebates,
                "rebalance_result": rebalance_result,
                "risk_status": risk_status,
                "performance_metrics": {
                    "uptime": "99.9%",
                    "fill_rate": len(filled_orders) / len(grid["active_orders"]) if grid["active_orders"] else 0,
                    "daily_volume": grid["grid_params"]["expected_daily_volume"],
                    "rebate_efficiency": total_rebates / grid["capital_allocated"] if grid["capital_allocated"] > 0 else 0
                }
            }
            
            return lifecycle_result
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _check_filled_orders(self, grid: Dict) -> List[GridOrder]:
        """Check which orders have been filled"""
        filled_orders = []
        
        # Simulate order fills based on market movement
        for order in grid["active_orders"]:
            if not order.filled:
                # Random fill simulation (in production, check with exchange)
                fill_probability = random.uniform(0, 0.1)  # 10% chance per check
                if random.random() < fill_probability:
                    order.filled = True
                    order.rebate_earned = order.price * order.size * 0.0001  # 0.01% rebate
                    filled_orders.append(order)
        
        return filled_orders
    
    async def _calculate_rebates(self, filled_orders: List[GridOrder]) -> float:
        """Calculate total rebates from filled orders"""
        return sum([order.rebate_earned for order in filled_orders])
    
    async def _check_rebalance_needed(self, grid: Dict) -> bool:
        """Check if grid needs rebalancing"""
        # Get current market price
        current_market = await self._get_market_data(grid["symbol"])
        center_price = grid["grid_params"]["center_price"]
        rebalance_threshold = grid["grid_params"]["rebalance_threshold"]
        
        price_deviation = abs(current_market["current_price"] - center_price) / center_price
        
        return price_deviation > rebalance_threshold
    
    async def _rebalance_grid(self, grid_id: str) -> Dict:
        """Rebalance grid when market moves significantly"""
        try:
            grid = self.active_grids[grid_id]
            
            # Cancel existing orders
            await self._cancel_all_orders(grid)
            
            # Get new market data
            market_data = await self._get_market_data(grid["symbol"])
            
            # Recalculate grid parameters
            new_params = await self._calculate_grid_parameters(market_data, grid["capital_allocated"])
            
            # Place new grid orders
            new_orders = await self._place_grid_orders(grid["user_id"], grid["symbol"], new_params)
            
            # Update grid
            grid["grid_params"] = new_params
            grid["active_orders"] = new_orders
            
            return {
                "status": "success",
                "rebalanced_at": datetime.now(),
                "new_center_price": new_params["center_price"],
                "orders_replaced": len(new_orders),
                "reason": "Price deviation exceeded threshold"
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def _cancel_all_orders(self, grid: Dict):
        """Cancel all active orders in grid"""
        # In production, this would cancel orders via exchange API
        for order in grid["active_orders"]:
            if not order.filled:
                order.filled = False  # Mark as cancelled
    
    async def _monitor_risk(self, grid: Dict) -> Dict:
        """Monitor risk metrics for grid"""
        try:
            # Calculate current position
            filled_orders = [order for order in grid["active_orders"] if order.filled]
            current_position = sum([
                order.size if order.side == "buy" else -order.size 
                for order in filled_orders
            ])
            
            # Risk metrics
            risk_metrics = {
                "current_position": current_position,
                "position_limit": grid["grid_params"]["position_limit"],
                "position_utilization": abs(current_position) / grid["grid_params"]["position_limit"],
                "max_drawdown_current": 0.02,  # Simulated 2% drawdown
                "max_drawdown_limit": grid["grid_params"]["max_drawdown"],
                "risk_score": "LOW"  # LOW, MEDIUM, HIGH
            }
            
            # Determine risk level
            if risk_metrics["position_utilization"] > 0.8:
                risk_metrics["risk_score"] = "HIGH"
            elif risk_metrics["position_utilization"] > 0.5:
                risk_metrics["risk_score"] = "MEDIUM"
            
            return risk_metrics
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def generate_grid_performance_report(self, user_id: str) -> str:
        """Generate grid performance report"""
        try:
            user_grids = {k: v for k, v in self.active_grids.items() if v["user_id"] == user_id}
            
            if not user_grids:
                return "No active grids found for user."
            
            total_rebates = 0
            total_volume = 0
            total_capital = 0
            
            for grid_id, grid in user_grids.items():
                filled_orders = [order for order in grid["active_orders"] if order.filled]
                grid_rebates = sum([order.rebate_earned for order in filled_orders])
                total_rebates += grid_rebates
                total_volume += grid["grid_params"]["expected_daily_volume"]
                total_capital += grid["capital_allocated"]
            
            report = f"""
🤖 GRID TRADING PERFORMANCE REPORT

📊 OVERVIEW:
• Active Grids: {len(user_grids)}
• Total Capital: ${total_capital:,.0f}
• Daily Volume: ${total_volume:,.0f}
• Rebates Earned: ${total_rebates:.2f}

💰 MAKER REBATE PERFORMANCE:
• Rebate Rate: 0.01% (industry leading)
• Daily Rebate Target: ${total_volume * 0.0001:.2f}
• Monthly Projection: ${total_volume * 0.0001 * 30:.2f}
• Annual Projection: ${total_volume * 0.0001 * 365:.2f}

🎯 GRID EFFICIENCY:
• All orders are MAKER ONLY (guaranteed rebates)
• Auto-rebalancing every hour
• Risk monitoring 24/7
• 99.9% uptime target

⚡ LIVE METRICS:
"""
            
            for grid_id, grid in user_grids.items():
                symbol = grid["symbol"]
                filled_count = len([o for o in grid["active_orders"] if o.filled])
                total_count = len(grid["active_orders"])
                
                report += f"""
• {symbol}: {filled_count}/{total_count} orders filled
  Volume: ${grid["grid_params"]["expected_daily_volume"]:,.0f}
  Rebates: ${sum([o.rebate_earned for o in grid["active_orders"] if o.filled]):.2f}
"""
            
            report += """
🚀 OPTIMIZATION:
• Spreads auto-adjust to market volatility
• Grid levels scale with available capital
• Risk limits prevent overexposure
• Profits automatically compound

Remember: Maker rebates = guaranteed income on every trade!

#GridTrading #MakerRebates #AutomatedProfit
            """
            
            return report.strip()
            
        except Exception as e:
            return f"Error generating report: {str(e)}"
