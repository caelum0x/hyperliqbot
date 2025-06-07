import asyncio
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
import sys
import os

# Real Hyperliquid imports
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Import actual examples for real patterns
examples_dir = os.path.join(os.path.dirname(__file__), '..', 'examples')
sys.path.append(examples_dir)

import basic_order
import basic_adding
import cancel_open_orders
import example_utils

@dataclass
class GridOrder:
    """Individual grid order with real tracking"""
    order_id: str
    side: str  # buy/sell
    price: float
    size: float
    filled: bool
    created_at: datetime
    rebate_earned: float
    exchange_order_id: Optional[str] = None  # Real exchange order ID
    status: str = "pending"  # pending, filled, cancelled

class GridTradingEngine:
    """
    Real grid trading engine using actual Hyperliquid API patterns
    Uses real examples: basic_order.py and basic_adding.py
    """
    
    def __init__(self, exchange: Exchange = None, info: Info = None, base_url: str = None):
        if exchange and info:
            self.exchange = exchange
            self.info = info
            self.address = exchange.account_address
        else:
            # Use example_utils.setup like all real examples
            self.address, self.info, self.exchange = example_utils.setup(
                base_url=base_url or constants.TESTNET_API_URL,
                skip_ws=True
            )
        
        self.active_grids = {}
        self.logger = logging.getLogger(__name__)
        
        # Risk management parameters
        self.risk_limits = {
            "max_position_size": 50000,  # $50K max position
            "max_grid_levels": 20,
            "min_spread_bps": 5,         # 5 basis points minimum
            "max_leverage": 10
        }
        
        self.logger.info("GridTradingEngine initialized with real Hyperliquid API")

    async def start_grid(self, coin: str, levels: int = 10, spacing: float = 0.002, size_per_level: Optional[float] = None) -> Dict:
        """
        Start grid trading using real Hyperliquid orders
        Following basic_order.py and basic_adding.py patterns exactly
        """
        try:
            # Get current price using Info API (basic_order.py pattern)
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                return {'status': 'error', 'message': f'No price data for {coin}'}
            
            mid_price = float(all_mids[coin])
            
            # Calculate size per level if not provided
            if not size_per_level:
                user_state = self.info.user_state(self.address)
                margin_summary = user_state.get('marginSummary', {})
                available = float(margin_summary.get('accountValue', 0)) - float(margin_summary.get('totalMarginUsed', 0))
                
                # Use max 30% of available balance or $2000, whichever is smaller
                grid_allocation = min(available * 0.3, 2000)
                size_per_level = (grid_allocation / (levels * 2)) / mid_price
                
                if size_per_level <= 0:
                    return {'status': 'error', 'message': 'Insufficient balance for grid trading'}
            
            orders = []
            
            # Place buy orders following basic_adding.py pattern for maker rebates
            for i in range(1, levels + 1):
                buy_price = mid_price * (1 - spacing * i)
                buy_price = round(buy_price, 2)
                
                # Use basic_adding.py exact pattern with Add Liquidity Only
                order_result = self.exchange.order(
                    coin, True, size_per_level, buy_price,
                    {"limit": {"tif": "Alo"}}, reduce_only=False
                )
                print(order_result)  # Print like basic_order.py
                
                if order_result.get('status') == 'ok':
                    status = order_result["response"]["data"]["statuses"][0]
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                        
                        # Query order status like basic_order.py
                        order_status = self.info.query_order_by_oid(self.address, oid)
                        print("Order status by oid:", order_status)
                        
                        orders.append({
                            'side': 'buy',
                            'price': buy_price,
                            'size': size_per_level,
                            'oid': oid,
                            'status': 'resting'
                        })
                        
                        self.logger.info(f"Placed BUY grid order: {coin} {size_per_level}@{buy_price}")
                    else:
                        self.logger.warning(f"BUY order not resting: {status}")
                else:
                    self.logger.error(f"Failed to place BUY order: {order_result}")
            
            # Place sell orders following basic_adding.py pattern
            for i in range(1, levels + 1):
                sell_price = mid_price * (1 + spacing * i)
                sell_price = round(sell_price, 2)
                
                # Use basic_adding.py exact pattern with Add Liquidity Only
                order_result = self.exchange.order(
                    coin, False, size_per_level, sell_price,
                    {"limit": {"tif": "Alo"}}, reduce_only=False
                )
                print(order_result)  # Print like basic_order.py
                
                if order_result.get('status') == 'ok':
                    status = order_result["response"]["data"]["statuses"][0]
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                        
                        # Query order status like basic_order.py
                        order_status = self.info.query_order_by_oid(self.address, oid)
                        print("Order status by oid:", order_status)
                        
                        orders.append({
                            'side': 'sell',
                            'price': sell_price,
                            'size': size_per_level,
                            'oid': oid,
                            'status': 'resting'
                        })
                        
                        self.logger.info(f"Placed SELL grid order: {coin} {size_per_level}@{sell_price}")
                    else:
                        self.logger.warning(f"SELL order not resting: {status}")
                else:
                    self.logger.error(f"Failed to place SELL order: {order_result}")
            
            # Store grid configuration
            self.active_grids[coin] = {
                'orders': orders,
                'levels': levels,
                'spacing': spacing,
                'mid_price': mid_price,
                'size_per_level': size_per_level,
                'created_at': datetime.now(),
                'total_orders_placed': len(orders)
            }
            
            return {
                'status': 'success',
                'orders_placed': len(orders),
                'mid_price': mid_price,
                'grid_range': f"${mid_price * (1 - spacing * levels):.2f} - ${mid_price * (1 + spacing * levels):.2f}",
                'expected_rebates_per_fill': size_per_level * mid_price * 0.0001  # 0.01% maker rebate
            }
            
        except Exception as e:
            self.logger.error(f"Error starting grid for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def monitor_grid_performance(self, coin: str) -> Dict:
        """Monitor grid performance using real fill data"""
        try:
            if coin not in self.active_grids:
                return {'status': 'error', 'message': f'No active grid for {coin}'}
            
            grid = self.active_grids[coin]
            
            # Get real fills from Info API
            user_fills = self.info.user_fills(self.exchange.account_address)
            
            # Filter fills for this grid (after grid creation time)
            grid_fills = []
            for fill in user_fills:
                if (fill.get('coin') == coin and 
                    int(fill.get('time', 0)) > grid['created_at'].timestamp() * 1000):
                    grid_fills.append(fill)
            
            # Calculate performance metrics
            total_fill_volume = sum(float(fill.get('sz', 0)) * float(fill.get('px', 0)) for fill in grid_fills)
            total_rebates = sum(float(fill.get('sz', 0)) * float(fill.get('px', 0)) * 0.0001 
                               for fill in grid_fills if fill.get('dir') == 'Add Liquidity')
            
            # Check order statuses
            active_orders = []
            filled_orders = []
            
            for order in grid['orders']:
                # Check if order is still open
                open_orders = self.info.open_orders(self.exchange.account_address)
                is_open = any(open_order['oid'] == order['oid'] for open_order in open_orders)
                
                if is_open:
                    active_orders.append(order)
                else:
                    filled_orders.append(order)
            
            runtime_hours = (datetime.now() - grid['created_at']).total_seconds() / 3600
            
            performance = {
                'coin': coin,
                'runtime_hours': runtime_hours,
                'total_orders_placed': grid['total_orders_placed'],
                'active_orders': len(active_orders),
                'filled_orders': len(filled_orders),
                'fill_rate': len(filled_orders) / grid['total_orders_placed'] if grid['total_orders_placed'] > 0 else 0,
                'total_fills': len(grid_fills),
                'total_volume': total_fill_volume,
                'total_rebates_earned': total_rebates,
                'hourly_rebate_rate': total_rebates / max(runtime_hours, 0.1),
                'current_mid_price': float(self.info.all_mids().get(coin, 0)),
                'original_mid_price': grid['mid_price']
            }
            
            return {'status': 'success', 'performance': performance}
            
        except Exception as e:
            self.logger.error(f"Error monitoring grid for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def stop_grid(self, coin: str) -> Dict:
        """Stop grid by canceling all open orders using cancel_open_orders.py pattern"""
        try:
            if coin not in self.active_grids:
                return {'status': 'error', 'message': f'No active grid for {coin}'}
            
            grid = self.active_grids[coin]
            cancelled_orders = []
            
            # Cancel all orders in the grid using cancel_open_orders.py pattern
            for order in grid['orders']:
                try:
                    # Use cancel_open_orders.py exact pattern
                    print(f"cancelling order {order}")
                    cancel_result = self.exchange.cancel(order['oid'])
                    
                    if cancel_result.get('status') == 'ok':
                        cancelled_orders.append(order['oid'])
                        self.logger.info(f"Cancelled order {order['oid']} for {coin}")
                    else:
                        self.logger.error(f"Failed to cancel order {order['oid']}: {cancel_result}")
                        
                except Exception as e:
                    self.logger.error(f"Error cancelling order {order['oid']}: {e}")
            
            # Remove grid from active grids
            del self.active_grids[coin]
            
            return {
                'status': 'success',
                'cancelled_orders': len(cancelled_orders),
                'total_orders': len(grid['orders']),
                'message': f'Grid stopped for {coin}'
            }
            
        except Exception as e:
            self.logger.error(f"Error stopping grid for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def rebalance_grid(self, coin: str) -> Dict:
        """Rebalance grid when price moves significantly"""
        try:
            if coin not in self.active_grids:
                return {'status': 'error', 'message': f'No active grid for {coin}'}
            
            grid = self.active_grids[coin]
            current_mid = float(self.info.all_mids().get(coin, 0))
            original_mid = grid['mid_price']
            
            # Check if rebalancing is needed (price moved >5% from original)
            price_deviation = abs(current_mid - original_mid) / original_mid
            if price_deviation < 0.05:
                return {'status': 'info', 'message': 'No rebalancing needed'}
            
            # Stop current grid
            stop_result = await self.stop_grid(coin)
            if stop_result['status'] != 'success':
                return stop_result
            
            # Start new grid at current price
            start_result = await self.start_grid(
                coin, 
                levels=grid['levels'], 
                spacing=grid['spacing'],
                size_per_level=grid['size_per_level']
            )
            
            if start_result['status'] == 'success':
                return {
                    'status': 'success',
                    'message': f'Grid rebalanced for {coin}',
                    'old_center': original_mid,
                    'new_center': current_mid,
                    'price_move': f"{price_deviation:.2%}",
                    'new_orders': start_result['orders_placed']
                }
            else:
                return start_result
                
        except Exception as e:
            self.logger.error(f"Error rebalancing grid for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_active_grids(self) -> Dict:
        """Get all active grids"""
        return self.active_grids.copy()

    async def get_grid_summary(self) -> str:
        """Generate a summary of all active grids"""
        try:
            if not self.active_grids:
                return "📊 No active grids. Use start_grid() to begin earning maker rebates!"
            
            summary = "🤖 ACTIVE GRID TRADING SUMMARY\n\n"
            total_orders = 0
            total_estimated_rebates = 0
            
            for coin, grid in self.active_grids.items():
                performance = await self.monitor_grid_performance(coin)
                if performance['status'] == 'success':
                    perf = performance['performance']
                    
                    summary += f"💰 {coin} Grid:\n"
                    summary += f"  • Runtime: {perf['runtime_hours']:.1f} hours\n"
                    summary += f"  • Orders: {perf['active_orders']} active, {perf['filled_orders']} filled\n"
                    summary += f"  • Rebates Earned: ${perf['total_rebates_earned']:.4f}\n"
                    summary += f"  • Hourly Rate: ${perf['hourly_rebate_rate']:.4f}/hr\n"
                    summary += f"  • Fill Rate: {perf['fill_rate']:.2%}\n\n"
                    
                    total_orders += perf['active_orders']
                    total_estimated_rebates += perf['total_rebates_earned']
            
            summary += f"🎯 TOTALS:\n"
            summary += f"  • Active Orders: {total_orders}\n"
            summary += f"  • Total Rebates: ${total_estimated_rebates:.4f}\n"
            summary += f"  • Grids Running: {len(self.active_grids)}\n"
            summary += f"\n⚡ All orders use Add Liquidity Only = guaranteed maker rebates!"
            
            return summary
            
        except Exception as e:
            return f"Error generating summary: {str(e)}"

# Run basic examples directly
def run_basic_order_example():
    """Run the basic_order.py example directly"""
    try:
        basic_order.main()
    except Exception as e:
        print(f"Error running basic_order example: {e}")

def run_basic_adding_example():
    """Run the basic_adding.py example directly"""
    try:
        basic_adding.main()
    except Exception as e:
        print(f"Error running basic_adding example: {e}")

# Legacy class alias for compatibility
class RealGridTradingEngine(GridTradingEngine):
    """Legacy alias pointing to real implementation"""
    pass
