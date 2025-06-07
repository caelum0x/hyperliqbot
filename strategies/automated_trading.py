"""
Automated Trading Engine for Hyperliquid
Implements various automated trading strategies with real market analysis
"""

import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import sys
import os

# Real Hyperliquid imports
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

# Import actual examples for real patterns
examples_dir = os.path.join(os.path.dirname(__file__), '..', 'examples')
sys.path.append(examples_dir)

import basic_order
import basic_tpsl
import example_utils

logger = logging.getLogger(__name__)

@dataclass
class RealTradingSignal:
    """Real trading signal data structure based on actual market data"""
    symbol: str
    action: str  # 'buy', 'sell', 'hold'
    confidence: float
    price: float
    size: float
    timestamp: datetime
    strategy: str
    market_data: Dict  # Real market metrics
    reasoning: str

class AutomatedTrading:
    """
    Automated trading using actual Hyperliquid API patterns
    Uses real examples: basic_order.py and basic_tpsl.py
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
        
        self.active_strategies = {}
        self.signals = []
        self.running = False
        self.price_history = {}
        self.market_cache = {}
        
        logger.info("AutomatedTrading initialized with real Hyperliquid API")

    async def momentum_strategy(self, coin: str, position_size: float = 0.1) -> Dict:
        """
        Momentum strategy using real market data and basic_tpsl.py patterns
        """
        try:
            # Get real market data following basic_order.py pattern
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                return {'status': 'error', 'message': f'No price data for {coin}'}
            
            current_price = float(all_mids[coin])
            
            # Get order book imbalance using real L2 data
            l2_book = self.info.l2_snapshot(coin)
            if not l2_book or 'levels' not in l2_book or len(l2_book['levels']) < 2:
                return {'status': 'error', 'message': f'No L2 data for {coin}'}
            
            # Calculate real order book depth (top 10 levels)
            bid_depth = sum(float(lvl['sz']) * float(lvl['px']) for lvl in l2_book['levels'][0][:10])
            ask_depth = sum(float(lvl['sz']) * float(lvl['px']) for lvl in l2_book['levels'][1][:10])
            
            if bid_depth + ask_depth == 0:
                return {'status': 'error', 'message': f'No liquidity for {coin}'}
            
            # Calculate imbalance ratio
            imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
            
            logger.info(f"Market analysis for {coin}: price={current_price}, imbalance={imbalance:.3f}")
            
            # Generate signal based on imbalance
            if imbalance > 0.2:  # Strong buy pressure
                return await self._execute_momentum_buy(coin, current_price, position_size, imbalance)
            elif imbalance < -0.2:  # Strong sell pressure
                return await self._execute_momentum_sell(coin, current_price, position_size, imbalance)
            else:
                return {'status': 'neutral', 'imbalance': imbalance, 'message': 'No strong momentum signal'}
                
        except Exception as e:
            logger.error(f"Error in momentum strategy for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _execute_momentum_buy(self, coin: str, current_price: float, size: float, imbalance: float) -> Dict:
        """Execute momentum buy order with TP/SL using basic_tpsl.py pattern"""
        try:
            # Calculate entry, TP, and SL prices
            entry_price = current_price * 1.0001  # Slightly above mid for better fill
            tp_price = entry_price * 1.005  # 0.5% profit target
            sl_price = entry_price * 0.998  # 0.2% stop loss
            
            # Place main order following basic_order.py pattern with Add Liquidity Only
            order_result = self.exchange.order(
                coin, True, size, entry_price,
                {"limit": {"tif": "Alo"}},  # Add Liquidity Only for maker rebates
                reduce_only=False
            )
            print(order_result)  # Print like basic_order.py
            
            if order_result.get('status') != 'ok':
                return {'status': 'error', 'message': f'Failed to place entry order: {order_result}'}
            
            # Get order ID for tracking
            status = order_result["response"]["data"]["statuses"][0]
            if "resting" not in status:
                return {'status': 'error', 'message': 'Entry order did not rest on book'}
            
            entry_oid = status["resting"]["oid"]
            
            # Query order status like basic_order.py
            order_status = self.info.query_order_by_oid(self.address, entry_oid)
            print("Entry order status by oid:", order_status)
            
            # Place Take Profit order following basic_tpsl.py pattern
            tp_result = self.exchange.order(
                coin, False, size, tp_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": tp_price, "isMarket": True, "sz": size},
                        "condition": "tp"
                    }]
                },
                reduce_only=True
            )
            print("TP order result:", tp_result)
            
            # Place Stop Loss order following basic_tpsl.py pattern
            sl_result = self.exchange.order(
                coin, False, size, sl_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": sl_price, "isMarket": True, "sz": size},
                        "condition": "sl"
                    }]
                },
                reduce_only=True
            )
            print("SL order result:", sl_result)
            
            return {
                'status': 'success',
                'action': 'momentum_buy',
                'coin': coin,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'size': size,
                'imbalance': imbalance,
                'entry_oid': entry_oid,
                'orders': {
                    'entry': order_result,
                    'take_profit': tp_result,
                    'stop_loss': sl_result
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing momentum buy: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _execute_momentum_sell(self, coin: str, current_price: float, size: float, imbalance: float) -> Dict:
        """Execute momentum sell order with TP/SL using basic_tpsl.py pattern"""
        try:
            # Calculate entry, TP, and SL prices for short position
            entry_price = current_price * 0.9999  # Slightly below mid for better fill
            tp_price = entry_price * 0.995  # 0.5% profit target (price goes down)
            sl_price = entry_price * 1.002  # 0.2% stop loss (price goes up)
            
            # Place main short order following basic_order.py pattern
            order_result = self.exchange.order(
                coin, False, size, entry_price,
                {"limit": {"tif": "Alo"}},  # Add Liquidity Only for maker rebates
                reduce_only=False
            )
            print(order_result)  # Print like basic_order.py
            
            if order_result.get('status') != 'ok':
                return {'status': 'error', 'message': f'Failed to place entry order: {order_result}'}
            
            # Get order ID for tracking
            status = order_result["response"]["data"]["statuses"][0]
            if "resting" not in status:
                return {'status': 'error', 'message': 'Entry order did not rest on book'}
            
            entry_oid = status["resting"]["oid"]
            
            # Query order status like basic_order.py
            order_status = self.info.query_order_by_oid(self.address, entry_oid)
            print("Entry order status by oid:", order_status)
            
            # Place Take Profit order (buy back at lower price)
            tp_result = self.exchange.order(
                coin, True, size, tp_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": tp_price, "isMarket": True, "sz": size},
                        "condition": "tp"
                    }]
                },
                reduce_only=True
            )
            print("TP order result:", tp_result)
            
            # Place Stop Loss order (buy back at higher price)
            sl_result = self.exchange.order(
                coin, True, size, sl_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": sl_price, "isMarket": True, "sz": size},
                        "condition": "sl"
                    }]
                },
                reduce_only=True
            )
            print("SL order result:", sl_result)
            
            return {
                'status': 'success',
                'action': 'momentum_sell',
                'coin': coin,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'size': size,
                'imbalance': imbalance,
                'entry_oid': entry_oid,
                'orders': {
                    'entry': order_result,
                    'take_profit': tp_result,
                    'stop_loss': sl_result
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing momentum sell: {e}")
            return {'status': 'error', 'message': str(e)}

    async def scalping_strategy(self, coin: str, target_spread_bps: float = 5.0) -> Dict:
        """
        Scalping strategy targeting tight spreads for quick profits
        """
        try:
            # Get real L2 data
            l2_book = self.info.l2_snapshot(coin)
            if not l2_book or 'levels' not in l2_book or len(l2_book['levels']) < 2:
                return {'status': 'error', 'message': f'No L2 data for {coin}'}
            
            # Get best bid/ask
            best_bid = float(l2_book['levels'][0][0]['px'])
            best_ask = float(l2_book['levels'][1][0]['px'])
            mid_price = (best_bid + best_ask) / 2
            spread_bps = ((best_ask - best_bid) / mid_price) * 10000
            
            logger.info(f"Scalping analysis for {coin}: spread={spread_bps:.1f}bps, target={target_spread_bps}bps")
            
            # Only scalp when spread is tight enough
            if spread_bps > target_spread_bps:
                return {
                    'status': 'wait',
                    'message': f'Spread too wide: {spread_bps:.1f}bps > {target_spread_bps}bps'
                }
            
            # Place both bid and ask orders for market making
            bid_price = best_bid + 0.01  # One tick above best bid
            ask_price = best_ask - 0.01  # One tick below best ask
            size = 0.05  # Small size for scalping
            
            # Place bid order (buy)
            bid_result = self.exchange.order(
                coin, True, size, bid_price,
                {"limit": {"tif": "Alo"}},  # Add Liquidity Only
                reduce_only=False
            )
            print("Bid order result:", bid_result)
            
            # Place ask order (sell)
            ask_result = self.exchange.order(
                coin, False, size, ask_price,
                {"limit": {"tif": "Alo"}},  # Add Liquidity Only
                reduce_only=False
            )
            print("Ask order result:", ask_result)
            
            return {
                'status': 'success',
                'strategy': 'scalping',
                'coin': coin,
                'spread_bps': spread_bps,
                'bid_price': bid_price,
                'ask_price': ask_price,
                'size': size,
                'orders': {
                    'bid': bid_result,
                    'ask': ask_result
                }
            }
            
        except Exception as e:
            logger.error(f"Error in scalping strategy for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def dca_strategy(self, coin: str, usd_amount: float = 100) -> Dict:
        """
        Dollar Cost Averaging strategy using real market data
        """
        try:
            # Get current price
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                return {'status': 'error', 'message': f'No price data for {coin}'}
            
            current_price = float(all_mids[coin])
            size = usd_amount / current_price
            
            # Place DCA buy order slightly above mid for better fill probability
            entry_price = current_price * 1.0005
            
            # Use basic_order.py pattern for DCA execution
            order_result = self.exchange.order(
                coin, True, size, entry_price,
                {"limit": {"tif": "Gtc"}},  # Good Till Cancel
                reduce_only=False
            )
            print(order_result)  # Print like basic_order.py
            
            if order_result.get('status') == 'ok':
                status = order_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    order_status = self.info.query_order_by_oid(self.address, status["resting"]["oid"])
                    print("DCA order status by oid:", order_status)
            
            return {
                'status': 'success',
                'strategy': 'dca',
                'coin': coin,
                'usd_amount': usd_amount,
                'current_price': current_price,
                'entry_price': entry_price,
                'size': size,
                'order_result': order_result
            }
            
        except Exception as e:
            logger.error(f"Error in DCA strategy for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def get_strategy_performance(self, strategy_id: str) -> Dict:
        """Get performance metrics for a strategy"""
        try:
            # Get user fills for performance tracking
            user_fills = self.info.user_fills(self.address)
            
            # Calculate performance metrics
            total_pnl = sum(float(fill.get('closedPnl', 0)) for fill in user_fills)
            total_fees = sum(float(fill.get('fee', 0)) for fill in user_fills)
            net_pnl = total_pnl - total_fees
            
            return {
                'strategy_id': strategy_id,
                'total_pnl': total_pnl,
                'total_fees': total_fees,
                'net_pnl': net_pnl,
                'fill_count': len(user_fills),
                'performance': 'profitable' if net_pnl > 0 else 'unprofitable'
            }
            
        except Exception as e:
            logger.error(f"Error getting strategy performance: {e}")
            return {'status': 'error', 'message': str(e)}

# ...existing RealAutomatedTradingEngine code for compatibility...

# Legacy class alias for compatibility
class RealAutomatedTradingEngine(AutomatedTrading):
    """Legacy alias pointing to real implementation"""
    pass

# Helper functions to run examples directly
def run_basic_order_example():
    """Run the basic_order.py example directly"""
    try:
        basic_order.main()
    except Exception as e:
        print(f"Error running basic_order example: {e}")

def run_basic_tpsl_example():
    """Run the basic_tpsl.py example directly"""
    try:
        basic_tpsl.main()
    except Exception as e:
        print(f"Error running basic_tpsl example: {e}")
