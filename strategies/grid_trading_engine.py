import asyncio
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import logging
import sys
import os
import numpy as np

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

    async def calculate_dynamic_grid_spacing(self, coin: str) -> float:
        """Calculate optimal grid spacing based on volatility"""
        try:
            # Get coin volatility
            volatility = await self._calculate_volatility(coin)
            
            # Base spacing on volatility
            # Higher volatility = wider grid spacing
            base_spacing = 0.002  # 0.2% default
            
            if volatility > 0:
                # Scale spacing with volatility
                # Typical volatility is around 1-5%
                optimal_spacing = base_spacing * (volatility / 0.02)  # Normalize to 2% volatility
                
                # Limit to reasonable range
                return max(0.001, min(0.01, optimal_spacing))
            
            return base_spacing
        except Exception as e:
            self.logger.error(f"Error calculating dynamic spacing: {e}")
            return 0.002  # Default to 0.2%
            
    async def _calculate_volatility(self, coin: str) -> float:
        """Calculate 24h volatility for a coin"""
        try:
            # Get candle data
            candles = self.info.candles_snapshot(coin, "1h", 24)
            
            if not candles or len(candles) < 12:
                return 0.02  # Default 2% if no data
                
            # Calculate returns
            prices = [float(candle['c']) for candle in candles]
            returns = [prices[i]/prices[i-1]-1 for i in range(1, len(prices))]
            
            # Calculate volatility (standard deviation of returns)
            if returns:
                volatility = np.std(returns)
                # Annualize
                volatility_24h = volatility * np.sqrt(24)
                return volatility_24h
                
            return 0.02  # Default 2% if calculation fails
        except Exception as e:
            self.logger.error(f"Error calculating volatility: {e}")
            return 0.02  # Default 2%
    
    async def start_dynamic_grid(self, coin: str, levels: int = 10, size_per_level: Optional[float] = None) -> Dict:
        """Start grid with dynamic spacing based on volatility"""
        try:
            # Calculate optimal grid spacing
            optimal_spacing = await self.calculate_dynamic_grid_spacing(coin)
            
            self.logger.info(f"Using dynamic grid spacing of {optimal_spacing:.4f} for {coin}")
            
            # Start grid with calculated spacing
            return await self.start_grid(coin, levels, optimal_spacing, size_per_level)
            
        except Exception as e:
            self.logger.error(f"Error starting dynamic grid: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def auto_compound_grid_profits(self, coin: str, compound_percentage: float = 0.5) -> Dict:
        """
        Auto-compound profits from filled grid orders into larger grid orders
        """
        try:
            if coin not in self.active_grids:
                return {'status': 'error', 'message': f'No active grid for {coin}'}
            
            # Get grid performance to calculate profits
            performance = await self.monitor_grid_performance(coin)
            if performance['status'] != 'success':
                return {'status': 'error', 'message': 'Could not calculate grid performance'}
                
            perf = performance['performance']
            
            # Calculate rebates earned (actual profits)
            rebates_earned = perf['total_rebates_earned']
            
            if rebates_earned < 0.1:  # Less than $0.10 in rebates
                return {'status': 'info', 'message': 'Insufficient profits for compounding'}
            
            # Calculate amount to compound
            compound_amount = rebates_earned * compound_percentage
            
            # Get current grid configuration
            grid = self.active_grids[coin]
            current_size_per_level = grid['size_per_level']
            levels = grid['levels']
            spacing = grid['spacing']
            
            # Calculate size increase
            mid_price = float(self.info.all_mids().get(coin, 0))
            if mid_price <= 0:
                return {'status': 'error', 'message': 'Invalid price data'}
            
            # Calculate additional size per level
            additional_coin_size = compound_amount / mid_price / (2 * levels)  # Divide by 2*levels (buy+sell sides)
            new_size_per_level = current_size_per_level + additional_coin_size
            
            # Stop current grid
            await self.stop_grid(coin)
            
            # Start new grid with increased size
            result = await self.start_grid(coin, levels, spacing, new_size_per_level)
            
            if result['status'] == 'success':
                return {
                    'status': 'success',
                    'message': 'Grid profits compounded successfully',
                    'original_size_per_level': current_size_per_level,
                    'new_size_per_level': new_size_per_level,
                    'rebates_compounded': compound_amount,
                    'orders_placed': result['orders_placed']
                }
            else:
                return result
                
        except Exception as e:
            self.logger.error(f"Error compounding grid profits: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def start_liquidity_scaled_grid(self, coin: str, levels: int = 10, max_size: float = 1000) -> Dict:
        """
        Start grid with order sizes scaled based on market liquidity
        """
        try:
            # Get orderbook to analyze liquidity
            orderbook = self.info.l2_snapshot(coin)
            if not orderbook or 'levels' not in orderbook:
                return {'status': 'error', 'message': 'Could not get orderbook data'}
            
            # Calculate liquidity factor
            liquidity_factor = await self._calculate_liquidity_factor(coin, orderbook)
            
            # Get current price
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                return {'status': 'error', 'message': f'No price data for {coin}'}
            
            mid_price = float(all_mids[coin])
            
            # Calculate base size and spacing
            base_size = max_size / levels / 2  # Divide by 2 for buy/sell sides
            optimal_spacing = await self.calculate_dynamic_grid_spacing(coin)
            
            # Scale size by liquidity (more liquidity = larger orders)
            size_per_level = base_size * liquidity_factor
            
            # Place orders with variable sizes at different price levels
            orders = []
            total_buy_size = 0
            total_sell_size = 0
            
            # Place buy orders with size scaled by distance from midpoint
            for i in range(1, levels + 1):
                # Scale size by distance from mid price (further = larger)
                # This creates a more natural liquidity curve
                distance_factor = 1 + ((i - 1) / levels)  # 1.0 to 2.0
                level_size = size_per_level * distance_factor
                
                buy_price = mid_price * (1 - optimal_spacing * i)
                buy_price = round(buy_price, 2)
                
                # Use basic_adding.py exact pattern with Add Liquidity Only
                order_result = self.exchange.order(
                    coin, True, level_size, buy_price,
                    {"limit": {"tif": "Alo"}}, reduce_only=False
                )
                
                if order_result.get('status') == 'ok':
                    status = order_result["response"]["data"]["statuses"][0]
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                        orders.append({
                            'side': 'buy',
                            'price': buy_price,
                            'size': level_size,
                            'oid': oid,
                            'status': 'resting'
                        })
                        total_buy_size += level_size
                        self.logger.info(f"Placed BUY grid order: {coin} {level_size}@{buy_price}")
            
            # Place sell orders with size scaled by distance from midpoint
            for i in range(1, levels + 1):
                # Scale size by distance from mid price (further = larger)
                distance_factor = 1 + ((i - 1) / levels)  # 1.0 to 2.0
                level_size = size_per_level * distance_factor
                
                sell_price = mid_price * (1 + optimal_spacing * i)
                sell_price = round(sell_price, 2)
                
                # Use basic_adding.py exact pattern with Add Liquidity Only
                order_result = self.exchange.order(
                    coin, False, level_size, sell_price,
                    {"limit": {"tif": "Alo"}}, reduce_only=False
                )
                
                if order_result.get('status') == 'ok':
                    status = order_result["response"]["data"]["statuses"][0]
                    if "resting" in status:
                        oid = status["resting"]["oid"]
                        orders.append({
                            'side': 'sell',
                            'price': sell_price,
                            'size': level_size,
                            'oid': oid,
                            'status': 'resting'
                        })
                        total_sell_size += level_size
                        self.logger.info(f"Placed SELL grid order: {coin} {level_size}@{sell_price}")
            
            # Store grid configuration with liquidity scaling info
            self.active_grids[coin] = {
                'orders': orders,
                'levels': levels,
                'spacing': optimal_spacing,
                'mid_price': mid_price,
                'size_per_level': size_per_level,
                'created_at': datetime.now(),
                'total_orders_placed': len(orders),
                'liquidity_factor': liquidity_factor,
                'total_buy_size': total_buy_size,
                'total_sell_size': total_sell_size,
                'liquidity_scaled': True
            }
            
            return {
                'status': 'success',
                'orders_placed': len(orders),
                'mid_price': mid_price,
                'grid_range': f"${mid_price * (1 - optimal_spacing * levels):.2f} - ${mid_price * (1 + optimal_spacing * levels):.2f}",
                'liquidity_factor': liquidity_factor,
                'total_buy_size': total_buy_size,
                'total_sell_size': total_sell_size
            }
            
        except Exception as e:
            self.logger.error(f"Error starting liquidity scaled grid: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def _calculate_liquidity_factor(self, coin: str, orderbook: Dict) -> float:
        """
        Calculate liquidity factor based on orderbook depth
        Returns a number between 0.5 and 2.0 to scale order sizes
        """
        try:
            # Extract orderbook data
            bid_levels = orderbook['levels'][0] if len(orderbook['levels']) > 0 else []
            ask_levels = orderbook['levels'][1] if len(orderbook['levels']) > 1 else []
            
            # Calculate 2% depth for buy and sell sides
            mid_price = float(self.info.all_mids().get(coin, 0))
            if mid_price <= 0:
                return 1.0  # Default factor
            
            lower_bound = mid_price * 0.98  # 2% down
            upper_bound = mid_price * 1.02  # 2% up
            
            bid_depth = 0
            for bid in bid_levels:
                bid_price = float(bid[0])
                bid_size = float(bid[1])
                if bid_price >= lower_bound:
                    bid_depth += bid_size * bid_price
            
            ask_depth = 0
            for ask in ask_levels:
                ask_price = float(ask[0])
                ask_size = float(ask[1])
                if ask_price <= upper_bound:
                    ask_depth += ask_size * ask_price
            
            total_depth = bid_depth + ask_depth
            
            # Scale factor based on depth
            # More depth = more liquidity = can place larger orders
            base_liquidity = 100000  # $100K is considered average liquidity within 2% of mid
            
            # Calculate liquidity factor (0.5 to 2.0)
            liquidity_factor = (total_depth / base_liquidity)
            liquidity_factor = max(0.5, min(2.0, liquidity_factor))
            
            self.logger.info(f"Liquidity factor for {coin}: {liquidity_factor:.2f} (depth: ${total_depth:,.2f})")
            return liquidity_factor
            
        except Exception as e:
            self.logger.error(f"Error calculating liquidity factor: {e}")
            return 1.0  # Default factor
    
    async def auto_adjust_grid(self, coin: str) -> Dict:
        """
        Auto-adjust grid based on market conditions:
        - Recenter if price moved significantly
        - Adjust spacing based on volatility
        - Scale sizes based on liquidity
        """
        try:
            if coin not in self.active_grids:
                return {'status': 'error', 'message': f'No active grid for {coin}'}
            
            grid = self.active_grids[coin]
            current_mid = float(self.info.all_mids().get(coin, 0))
            original_mid = grid['mid_price']
            
            # Check if recentering is needed
            price_deviation = abs(current_mid - original_mid) / original_mid
            need_recenter = price_deviation > 0.05  # 5% move
            
            # Check if volatility changed
            current_spacing = grid['spacing']
            optimal_spacing = await self.calculate_dynamic_grid_spacing(coin)
            spacing_change = abs(optimal_spacing - current_spacing) / current_spacing
            need_spacing_update = spacing_change > 0.3  # 30% change in optimal spacing
            
            # Check liquidity change
            orderbook = self.info.l2_snapshot(coin)
            current_liquidity = await self._calculate_liquidity_factor(coin, orderbook)
            original_liquidity = grid.get('liquidity_factor', 1.0)
            liquidity_change = abs(current_liquidity - original_liquidity) / original_liquidity
            need_liquidity_update = liquidity_change > 0.3  # 30% change in liquidity
            
            # If any adjustments needed, rebuild grid
            if need_recenter or need_spacing_update or need_liquidity_update:
                self.logger.info(f"Auto-adjusting grid for {coin}. "
                               f"Recenter: {need_recenter}, "
                               f"Spacing: {need_spacing_update}, "
                               f"Liquidity: {need_liquidity_update}")
                
                # Get accumulated profits for compounding
                performance = await self.monitor_grid_performance(coin)
                if performance['status'] == 'success':
                    rebates_earned = performance['performance']['total_rebates_earned']
                else:
                    rebates_earned = 0
                
                # Stop current grid
                await self.stop_grid(coin)
                
                # Calculate new size accounting for profits
                levels = grid['levels']
                size_per_level = grid['size_per_level']
                
                # Compound profits if available
                if rebates_earned > 0.1:  # Only if we have at least $0.1 in profits
                    compound_amount = rebates_earned * 0.5  # Compound 50% of profits
                    additional_coin_size = compound_amount / current_mid / (2 * levels)
                    size_per_level += additional_coin_size
                
                # Start new optimized grid
                result = await self.start_liquidity_scaled_grid(coin, levels)
                
                if result['status'] == 'success':
                    return {
                        'status': 'success',
                        'message': 'Grid auto-adjusted successfully',
                        'price_deviation': f"{price_deviation:.2%}",
                        'spacing_change': f"{spacing_change:.2%}",
                        'liquidity_change': f"{liquidity_change:.2%}",
                        'profits_compounded': rebates_earned * 0.5 if rebates_earned > 0.1 else 0,
                        'new_grid': result
                    }
                else:
                    return result
            else:
                return {
                    'status': 'info',
                    'message': 'No grid adjustment needed',
                    'price_deviation': f"{price_deviation:.2%}",
                    'spacing_change': f"{spacing_change:.2%}",
                    'liquidity_change': f"{liquidity_change:.2%}"
                }
                
        except Exception as e:
            self.logger.error(f"Error auto-adjusting grid: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def start_auto_managed_grid(self, coin: str, levels: int = 10, max_size: float = 1000) -> Dict:
        """
        Start a fully automated grid that self-optimizes over time
        """
        try:
            # First, start a liquidity-scaled grid with dynamic spacing
            result = await self.start_liquidity_scaled_grid(coin, levels, max_size)
            
            if result['status'] != 'success':
                return result
            
            # Set up monitoring task if not already running
            if not hasattr(self, 'monitoring_tasks'):
                self.monitoring_tasks = {}
            
            # Cancel existing monitoring task if present
            if coin in self.monitoring_tasks and not self.monitoring_tasks[coin].done():
                self.monitoring_tasks[coin].cancel()
            
            # Start new monitoring task
            self.monitoring_tasks[coin] = asyncio.create_task(self._auto_manage_grid(coin))
            
            return {
                'status': 'success',
                'message': f'Auto-managed grid started for {coin}',
                'grid_info': result,
                'auto_management': 'enabled',
                'monitoring_interval': '15 minutes',
                'features': [
                    'Dynamic spacing based on volatility',
                    'Order sizes scaled by liquidity',
                    'Auto-recentering when price moves >5%',
                    'Profit compounding',
                    'Periodic optimization'
                ]
            }
            
        except Exception as e:
            self.logger.error(f"Error starting auto-managed grid: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def _auto_manage_grid(self, coin: str):
        """Background task to automatically manage grid"""
        try:
            while coin in self.active_grids:
                # Check and adjust grid if needed
                adjust_result = await self.auto_adjust_grid(coin)
                
                if adjust_result['status'] == 'success':
                    self.logger.info(f"Auto-adjusted grid for {coin}: {adjust_result['message']}")
                
                # Check for profit compounding opportunity
                compound_result = await self.auto_compound_grid_profits(coin, 0.5)
                
                if compound_result['status'] == 'success':
                    self.logger.info(f"Compounded grid profits for {coin}: {compound_result['rebates_compounded']}")
                
                # Wait before next check (15 minutes)
                await asyncio.sleep(900)
                
        except asyncio.CancelledError:
            self.logger.info(f"Auto-management task for {coin} cancelled")
        except Exception as e:
            self.logger.error(f"Error in auto grid management for {coin}: {e}")
    
    async def validate_connection(self) -> bool:
        """Validate connection to exchange"""
        try:
            # Simple validation by getting price data
            all_mids = self.info.all_mids()
            return len(all_mids) > 0
        except Exception as e:
            self.logger.error(f"Connection validation failed: {e}")
            return False

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

async def start_multi_asset_grid(self, coins: List[str], total_capital: float, base_levels: int = 10) -> Dict:
    """
    Start grid strategies across multiple assets with capital allocation based on volatility
    
    Args:
        coins: List of coins to create grids for
        total_capital: Total capital to allocate across all grids
        base_levels: Base number of grid levels (will be adjusted by volatility)
    """
    try:
        # Analyze volatility for each coin
        volatility_data = {}
        for coin in coins:
            volatility = await self._calculate_volatility(coin)
            volatility_data[coin] = volatility
        
        if not volatility_data:
            return {"status": "error", "message": "Could not calculate volatility for any coins"}
        
        # Allocate capital inversely proportional to volatility
        # Higher volatility = lower allocation
        total_inverse_vol = sum(1/v for v in volatility_data.values() if v > 0)
        
        if total_inverse_vol <= 0:
            return {"status": "error", "message": "Invalid volatility calculations"}
        
        allocations = {
            coin: (1/vol) / total_inverse_vol * total_capital
            for coin, vol in volatility_data.items()
            if vol > 0
        }
        
        # Start grids for each coin with appropriate allocation
        results = {}
        for coin, allocation in allocations.items():
            # Adjust grid levels based on volatility - more volatile coins get more levels
            adjusted_levels = int(base_levels * (1 + (volatility_data[coin] / 0.02)))
            adjusted_levels = min(max(5, adjusted_levels), 20)  # Keep between 5-20 levels
            
            # Calculate optimal spacing based on volatility
            spacing = await self.calculate_dynamic_grid_spacing(coin)
            
            # Calculate size per level from allocation
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                continue
                
            mid_price = float(all_mids[coin])
            size_per_level = allocation / (adjusted_levels * mid_price * 2)  # Divide by 2 for buy+sell
            
            # Start grid for this coin
            grid_result = await self.start_grid(
                coin=coin,
                levels=adjusted_levels,
                spacing=spacing,
                size_per_level=size_per_level
            )
            
            results[coin] = {
                'allocation': allocation,
                'levels': adjusted_levels,
                'spacing': spacing,
                'size_per_level': size_per_level,
                'result': grid_result
            }
        
        successful_grids = sum(1 for r in results.values() if r['result']['status'] == 'success')
        
        return {
            'status': 'success' if successful_grids > 0 else 'error',
            'message': f'Started {successful_grids}/{len(coins)} grid strategies',
            'volatility_data': volatility_data,
            'allocations': allocations,
            'results': results
        }
        
    except Exception as e:
        self.logger.error(f"Error in multi-asset grid: {e}")
        return {"status": "error", "message": str(e)}
