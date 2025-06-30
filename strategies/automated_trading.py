"""
Automated Trading Engine for Hyperliquid
Implements various automated trading strategies with real market analysis
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import sys
import os
import math
from collections import deque

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
        
        # Advanced tracking for momentum strategies
        self.momentum_indicators = {}
        self.counter_trend_levels = {}
        self.market_regime = {}
        
        # Performance tracking
        self.strategy_performance = {}
        self.logger = logging.getLogger(__name__)
        
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

    async def adaptive_market_making(self, coin: str, position_size: float = 0.1, 
                                   target_spread_bps: float = 5.0):
        """
        Adaptive market making strategy with optimal spread positioning
        Places orders at optimal positions in the spread based on order book imbalance
        """
        try:
            # Get L2 book data
            l2_book = self.info.l2_snapshot(coin)
            if not l2_book or 'levels' not in l2_book or len(l2_book['levels']) < 2:
                return {'status': 'error', 'message': f'No L2 data for {coin}'}
            
            # Get best bid/ask
            best_bid = float(l2_book['levels'][0][0]['px'])
            best_ask = float(l2_book['levels'][1][0]['px'])
            mid_price = (best_bid + best_ask) / 2
            spread_bps = ((best_ask - best_bid) / mid_price) * 10000
            
            # Calculate order book imbalance
            bid_depth = sum(float(lvl['sz']) * float(lvl['px']) for lvl in l2_book['levels'][0][:5])
            ask_depth = sum(float(lvl['sz']) * float(lvl['px']) for lvl in l2_book['levels'][1][:5])
            
            if bid_depth + ask_depth == 0:
                return {'status': 'error', 'message': f'No liquidity for {coin}'}
            
            # Calculate imbalance (-1 to 1)
            imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
            
            # Adaptive pricing based on imbalance
            # More negative imbalance (sell pressure) = place bid higher in spread
            # More positive imbalance (buy pressure) = place ask higher in spread
            
            # Calculate optimal price points
            spread = best_ask - best_bid
            
            # Bid placement: higher when sell pressure, lower when buy pressure
            bid_position = 0.3 - (imbalance * 0.3)  # 0-60% of spread from bid
            bid_position = max(0.01, min(0.6, bid_position))  # Limit to 1-60% range
            
            # Ask placement: lower when buy pressure, higher when sell pressure
            ask_position = 0.3 + (imbalance * 0.3)  # 0-60% of spread from ask
            ask_position = max(0.01, min(0.6, ask_position))
            
            # Calculate actual prices
            bid_price = best_bid + (spread * bid_position)
            ask_price = best_ask - (spread * ask_position)
            
            # Place orders
            bid_result = await self.place_adding_liquidity_order(
                coin=coin,
                is_buy=True,
                size=position_size,
                price=bid_price
            )
            
            ask_result = await self.place_adding_liquidity_order(
                coin=coin,
                is_buy=False,
                size=position_size,
                price=ask_price
            )
            
            return {
                'status': 'success',
                'strategy': 'adaptive_market_making',
                'coin': coin,
                'imbalance': imbalance,
                'spread_bps': spread_bps,
                'bid': {'price': bid_price, 'position': bid_position, 'result': bid_result},
                'ask': {'price': ask_price, 'position': ask_position, 'result': ask_result}
            }
            
        except Exception as e:
            self.logger.error(f"Error in adaptive market making for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def place_adding_liquidity_order(self, coin: str, is_buy: bool, size: float, price: float) -> Dict:
        """Place order with Add Liquidity Only flag for guaranteed maker rebates"""
        try:
            # Use real Hyperliquid order execution with ALO flag
            order_result = self.exchange.order(
                coin, is_buy, size, price,
                {"limit": {"tif": "Alo"}},  # Add Liquidity Only
                reduce_only=False
            )
            
            # Extract order status and OID for tracking
            if order_result.get("status") == "ok":
                status = order_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    oid = status["resting"]["oid"]
                    
                    # Log order placement
                    logger.info(f"Placed {'BUY' if is_buy else 'SELL'} ALO order: {coin} {size}@{price}")
                    return {
                        'status': 'success',
                        'side': 'buy' if is_buy else 'sell',
                        'price': price,
                        'size': size,
                        'oid': oid,
                        'execution': order_result
                    }
            
            logger.warning(f"Failed to place ALO order: {order_result}")
            return {
                'status': 'error',
                'message': 'Order failed to rest',
                'execution': order_result
            }
            
        except Exception as e:
            logger.error(f"Error placing ALO order: {e}")
            return {'status': 'error', 'message': str(e)}

    async def advanced_momentum_detection(self, coin: str, lookback_periods: int = 24) -> Dict:
        """
        Advanced momentum detection using multiple indicators and time frames
        Combines price action, volume, and order book signals
        """
        try:
            # Get historical candle data (hourly)
            candles = self.info.candles_snapshot(coin, "1h", lookback_periods + 10)  # Extra candles for calculation
            
            if len(candles) < lookback_periods:
                return {'status': 'error', 'message': f'Insufficient candle data for {coin}'}
            
            # Calculate technical indicators
            prices = [float(candle['c']) for candle in candles]  # Close prices
            volumes = [float(candle['v']) for candle in candles]  # Volumes
            
            # 1. Calculate momentum oscillators
            # RSI - Relative Strength Index
            rsi = self._calculate_rsi(prices, period=14)
            
            # MACD - Moving Average Convergence Divergence
            macd_line, signal_line, macd_histogram = self._calculate_macd(prices)
            
            # 2. Calculate trend strength
            # ADX - Average Directional Index (simplified)
            adx = self._calculate_adx_simplified(candles)
            
            # 3. Calculate volume profile
            volume_sma = sum(volumes[-5:]) / 5
            relative_volume = volumes[-1] / volume_sma if volume_sma > 0 else 1.0
            
            # 4. Get orderbook imbalance
            l2_book = self.info.l2_snapshot(coin)
            imbalance = 0
            
            if l2_book and 'levels' in l2_book and len(l2_book['levels']) >= 2:
                bid_depth = sum(float(lvl['sz']) * float(lvl['px']) for lvl in l2_book['levels'][0][:5])
                ask_depth = sum(float(lvl['sz']) * float(lvl['px']) for lvl in l2_book['levels'][1][:5])
                
                if bid_depth + ask_depth > 0:
                    imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
            
            # 5. Price breakout detection
            recent_high = max(float(c['h']) for c in candles[-10:])
            recent_low = min(float(c['l']) for c in candles[-10:])
            latest_close = prices[-1]
            
            # Calculate overall momentum score (-100 to +100)
            momentum_score = self._calculate_momentum_score(
                rsi=rsi,
                macd_histogram=macd_histogram,
                adx=adx,
                relative_volume=relative_volume,
                imbalance=imbalance,
                price_position=(latest_close - recent_low) / (recent_high - recent_low) if recent_high > recent_low else 0.5
            )
            
            # Determine trend direction and strength
            trend_strength = abs(momentum_score) / 100
            trend_direction = "bullish" if momentum_score > 0 else "bearish"
            
            # Store momentum indicators for this coin
            self.momentum_indicators[coin] = {
                'score': momentum_score,
                'rsi': rsi,
                'macd': macd_histogram,
                'adx': adx,
                'imbalance': imbalance,
                'updated_at': datetime.now()
            }
            
            # Generate signal based on momentum score
            signal = "hold"
            confidence = trend_strength
            
            if momentum_score > 30 and macd_histogram > 0:
                signal = "buy"
                entry_price = latest_close * 1.001  # Slight premium
                stop_loss = max(latest_close * 0.99, recent_low * 0.995)  # 1% or recent low
            elif momentum_score < -30 and macd_histogram < 0:
                signal = "sell"
                entry_price = latest_close * 0.999  # Slight discount
                stop_loss = min(latest_close * 1.01, recent_high * 1.005)  # 1% or recent high
            else:
                entry_price = latest_close
                stop_loss = latest_close
            
            # Create trading signal with detailed analysis
            return {
                'status': 'success',
                'coin': coin,
                'signal': signal,
                'confidence': confidence,
                'momentum_score': momentum_score,
                'trend': {
                    'direction': trend_direction,
                    'strength': trend_strength
                },
                'indicators': {
                    'rsi': rsi,
                    'macd': macd_histogram,
                    'adx': adx,
                    'relative_volume': relative_volume,
                    'imbalance': imbalance
                },
                'prices': {
                    'current': latest_close,
                    'recent_high': recent_high,
                    'recent_low': recent_low,
                    'entry': entry_price,
                    'stop_loss': stop_loss
                }
            }
            
        except Exception as e:
            logger.error(f"Error in advanced momentum detection for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI - Relative Strength Index"""
        if len(prices) <= period:
            return 50.0  # Not enough data
            
        # Calculate price changes
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separate gains and losses
        gains = [delta if delta > 0 else 0 for delta in deltas]
        losses = [-delta if delta < 0 else 0 for delta in deltas]
        
        # Calculate average gains and losses
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0  # No losses = RSI 100
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi

    def _calculate_macd(self, prices: List[float]) -> Tuple[float, float, float]:
        """Calculate MACD - Moving Average Convergence Divergence"""
        if len(prices) < 26:
            return 0.0, 0.0, 0.0  # Not enough data
            
        # Calculate EMAs
        ema12 = self._calculate_ema(prices, 12)
        ema26 = self._calculate_ema(prices, 26)
        
        # MACD line = 12-period EMA - 26-period EMA
        macd_line = ema12 - ema26
        
        # Signal line = 9-period EMA of MACD line
        macd_history = []
        for i in range(len(prices) - 26 + 1):
            short_ema = self._calculate_ema(prices[i:i+26], 12)
            long_ema = self._calculate_ema(prices[i:i+26], 26)
            macd_history.append(short_ema - long_ema)
            
        signal_line = self._calculate_ema(macd_history, 9) if len(macd_history) >= 9 else macd_line
        
        # Histogram = MACD line - Signal line
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram

    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate EMA - Exponential Moving Average"""
        if len(prices) < period:
            return sum(prices) / len(prices)  # Simple average if not enough data
            
        multiplier = 2 / (period + 1)
        initial_sma = sum(prices[:period]) / period
        
        ema = initial_sma
        for i in range(period, len(prices)):
            ema = (prices[i] * multiplier) + (ema * (1 - multiplier))
            
        return ema

    def _calculate_adx_simplified(self, candles: List[Dict]) -> float:
        """Calculate simplified ADX (Average Directional Index)"""
        if len(candles) < 14:
            return 25.0  # Not enough data, return neutral value
            
        # Extract price data
        highs = [float(c['h']) for c in candles]
        lows = [float(c['l']) for c in candles]
        closes = [float(c['c']) for c in candles]
        
        # Calculate True Range
        tr_sum = 0
        for i in range(1, len(candles)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i-1]
            
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            
            tr = max(tr1, tr2, tr3)
            tr_sum += tr
            
        atr = tr_sum / (len(candles) - 1)
        
        # Calculate price movement directional strength (simplified)
        up_moves = 0
        down_moves = 0
        for i in range(1, len(candles)):
            if closes[i] > closes[i-1]:
                up_moves += closes[i] - closes[i-1]
            else:
                down_moves += closes[i-1] - closes[i]
                
        # Calculate simplified ADX
        di_diff = abs(up_moves - down_moves)
        di_sum = up_moves + down_moves
        
        adx = 100 * di_diff / di_sum if di_sum > 0 else 25.0
        return adx

    def _calculate_momentum_score(self, rsi: float, macd_histogram: float, 
                                adx: float, relative_volume: float,
                                imbalance: float, price_position: float) -> float:
        """
        Calculate comprehensive momentum score (-100 to +100)
        Higher positive = stronger bullish momentum
        Lower negative = stronger bearish momentum
        """
        # RSI component: -30 to +30
        # 70+ = overbought, 30- = oversold
        rsi_score = (rsi - 50) * 0.6
        
        # MACD component: -25 to +25
        # Normalize MACD histogram
        macd_score = min(25, max(-25, macd_histogram * 1000))
        
        # ADX component: 0 to 20 (trend strength)
        adx_score = (adx / 100) * 20
        
        # Volume component: -10 to +10
        volume_score = (relative_volume - 1) * 10
        
        # Order book imbalance: -15 to +15
        imbalance_score = imbalance * 15
        
        # Price position component: -20 to +20
        position_score = (price_position - 0.5) * 40
        
        # Total score
        total_score = rsi_score + macd_score + adx_score + volume_score + imbalance_score + position_score
        
        # Limit to -100 to +100 range
        return max(-100, min(100, total_score))

    async def counter_trend_strategy(self, coin: str, position_size: float = 0.1, 
                                  lookback_periods: int = 48) -> Dict:
        """
        Counter-trend strategy that identifies overbought/oversold conditions
        and potential trend reversals
        """
        try:
            # Get historical candles
            candles = self.info.candles_snapshot(coin, "1h", lookback_periods)
            
            if len(candles) < lookback_periods:
                return {'status': 'error', 'message': f'Insufficient candle data for {coin}'}
            
            # Extract price data
            closes = [float(c['c']) for c in candles]
            highs = [float(c['h']) for c in candles]
            lows = [float(c['l']) for c in candles]
            
            # Calculate technical indicators
            rsi = self._calculate_rsi(closes)
            macd_line, signal_line, macd_histogram = self._calculate_macd(closes)
            
            # Calculate Bollinger Bands
            sma20 = sum(closes[-20:]) / 20
            std_dev = np.std(closes[-20:])
            upper_band = sma20 + (2 * std_dev)
            lower_band = sma20 - (2 * std_dev)
            
            # Calculate Stochastic
            stoch_k = self._calculate_stochastic_k(closes, highs, lows, 14)
            
            # Get latest price
            latest_close = closes[-1]
            
            # Determine if we're in extreme territory
            is_overbought = (rsi > 75 or stoch_k > 85) and latest_close > upper_band
            is_oversold = (rsi < 25 or stoch_k < 15) and latest_close < lower_band
            
            # Check for divergence signals
            price_making_higher_highs = highs[-1] > max(highs[-10:-1])
            price_making_lower_lows = lows[-1] < min(lows[-10:-1])
            
            # Get recent momentum direction
            recent_momentum = self.momentum_indicators.get(coin, {}).get('score', 0)
            
            # Store key levels for this coin
            self.counter_trend_levels[coin] = {
                'upper_band': upper_band,
                'lower_band': lower_band,
                'sma20': sma20,
                'updated_at': datetime.now()
            }
            
            # Generate counter-trend signals
            signal = "hold"
            confidence = 0.0
            signal_type = "none"
            reasoning = ""
            
            # Bearish counter-trend signal (sell when overbought)
            if is_overbought and recent_momentum > 0:
                signal = "sell"
                confidence = min(0.3 + (rsi - 70) / 100 + (stoch_k - 80) / 100, 0.9)
                signal_type = "bearish_reversal"
                reasoning = f"Overbought conditions: RSI={rsi:.1f}, Stoch={stoch_k:.1f}, price above upper band"
                
                # Extra confidence if divergence present
                if price_making_higher_highs and macd_line < macd_line[-2]:
                    confidence += 0.1
                    reasoning += " with bearish divergence"
            
            # Bullish counter-trend signal (buy when oversold)
            elif is_oversold and recent_momentum < 0:
                signal = "buy"
                confidence = min(0.3 + (30 - rsi) / 100 + (20 - stoch_k) / 100, 0.9)
                signal_type = "bullish_reversal"
                reasoning = f"Oversold conditions: RSI={rsi:.1f}, Stoch={stoch_k:.1f}, price below lower band"
                
                # Extra confidence if divergence present
                if price_making_lower_lows and macd_line > macd_line[-2]:
                    confidence += 0.1
                    reasoning += " with bullish divergence"
            
            # Calculate entry, target and stop prices
            if signal == "buy":
                entry_price = latest_close * 1.001  # Small buffer above current
                target_price = sma20  # Target the mean
                stop_price = latest_close * 0.99  # 1% stop
            elif signal == "sell":
                entry_price = latest_close * 0.999  # Small buffer below current
                target_price = sma20  # Target the mean
                stop_price = latest_close * 1.01  # 1% stop
            else:
                entry_price = latest_close
                target_price = latest_close
                stop_price = latest_close
            
            # Determine risk/reward
            if signal != "hold":
                risk = abs(entry_price - stop_price)
                reward = abs(target_price - entry_price)
                risk_reward_ratio = reward / risk if risk > 0 else 0
            else:
                risk_reward_ratio = 0
            
            # Execute trade if signal is strong enough
            result = None
            if signal != "hold" and confidence >= 0.7 and risk_reward_ratio >= 2:
                # Calculate position size based on risk
                adjusted_size = position_size * confidence
                
                if signal == "buy":
                    result = await self._execute_counter_trend_buy(
                        coin=coin,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        size=adjusted_size
                    )
                else:
                    result = await self._execute_counter_trend_sell(
                        coin=coin, 
                        entry_price=entry_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        size=adjusted_size
                    )
            
            return {
                'status': 'success',
                'coin': coin,
                'signal': signal,
                'signal_type': signal_type,
                'confidence': confidence,
                'reasoning': reasoning,
                'indicators': {
                    'rsi': rsi,
                    'stoch_k': stoch_k,
                    'macd': macd_histogram
                },
                'levels': {
                    'upper_band': upper_band,
                    'sma20': sma20,
                    'lower_band': lower_band,
                    'current_price': latest_close
                },
                'trade_setup': {
                    'entry': entry_price,
                    'target': target_price,
                    'stop': stop_price,
                    'risk_reward': risk_reward_ratio
                },
                'execution': result
            }
            
        except Exception as e:
            logger.error(f"Error in counter-trend strategy for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _calculate_stochastic_k(self, closes: List[float], highs: List[float], 
                             lows: List[float], period: int = 14) -> float:
        """Calculate Stochastic oscillator %K value"""
        if len(closes) < period:
            return 50.0  # Not enough data
            
        recent_range = min(period, len(closes))
        recent_low = min(lows[-recent_range:])
        recent_high = max(highs[-recent_range:])
        
        if recent_high == recent_low:
            return 50.0  # Avoid division by zero
            
        latest_close = closes[-1]
        k_value = 100 * (latest_close - recent_low) / (recent_high - recent_low)
        
        return k_value
    
    async def _execute_counter_trend_buy(self, coin: str, entry_price: float, 
                                     stop_price: float, target_price: float, 
                                     size: float) -> Dict:
        """Execute counter-trend buy order with TP/SL"""
        try:
            # Place main entry order with Add Liquidity Only
            entry_result = self.exchange.order(
                coin, True, size, entry_price,
                {"limit": {"tif": "Alo"}},
                reduce_only=False
            )
            
            if entry_result.get('status') != 'ok':
                return {'status': 'error', 'message': f'Failed to place entry order: {entry_result}'}
            
            # Get order ID
            status = entry_result["response"]["data"]["statuses"][0]
            if "resting" not in status:
                return {'status': 'error', 'message': 'Entry order did not rest on book'}
            
            entry_oid = status["resting"]["oid"]
            
            # Place stop loss order
            sl_result = self.exchange.order(
                coin, False, size, stop_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": stop_price, "isMarket": True, "sz": size},
                        "condition": "sl"
                    }]
                },
                reduce_only=True
            )
            
            # Place take profit order
            tp_result = self.exchange.order(
                coin, False, size, target_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": target_price, "isMarket": True, "sz": size},
                        "condition": "tp"
                    }]
                },
                reduce_only=True
            )
            
            return {
                'status': 'success',
                'action': 'counter_trend_buy',
                'entry_oid': entry_oid,
                'entry_price': entry_price,
                'stop_price': stop_price,
                'target_price': target_price,
                'size': size,
                'risk_reward': (target_price - entry_price) / (entry_price - stop_price) if entry_price != stop_price else 0,
                'orders': {
                    'entry': entry_result,
                    'stop_loss': sl_result,
                    'take_profit': tp_result
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing counter-trend buy: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def _execute_counter_trend_sell(self, coin: str, entry_price: float, 
                                      stop_price: float, target_price: float, 
                                      size: float) -> Dict:
        """Execute counter-trend sell order with TP/SL"""
        try:
            # Place main entry order with Add Liquidity Only
            entry_result = self.exchange.order(
                coin, False, size, entry_price,
                {"limit": {"tif": "Alo"}},
                reduce_only=False
            )
            
            if entry_result.get('status') != 'ok':
                return {'status': 'error', 'message': f'Failed to place entry order: {entry_result}'}
            
            # Get order ID
            status = entry_result["response"]["data"]["statuses"][0]
            if "resting" not in status:
                return {'status': 'error', 'message': 'Entry order did not rest on book'}
            
            entry_oid = status["resting"]["oid"]
            
            # Place stop loss order (buy back higher)
            sl_result = self.exchange.order(
                coin, True, size, stop_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": stop_price, "isMarket": True, "sz": size},
                        "condition": "sl"
                    }]
                },
                reduce_only=True
            )
            
            # Place take profit order (buy back lower)
            tp_result = self.exchange.order(
                coin, True, size, target_price,
                {
                    "limit": {"tif": "Gtc"},
                    "tpsl": [{
                        "trigger": {"px": target_price, "isMarket": True, "sz": size},
                        "condition": "tp"
                    }]
                },
                reduce_only=True
            )
            
            return {
                'status': 'success',
                'action': 'counter_trend_sell',
                'entry_oid': entry_oid,
                'entry_price': entry_price,
                'stop_price': stop_price,
                'target_price': target_price,
                'size': size,
                'risk_reward': (entry_price - target_price) / (stop_price - entry_price) if stop_price != entry_price else 0,
                'orders': {
                    'entry': entry_result,
                    'stop_loss': sl_result,
                    'take_profit': tp_result
                }
            }
            
        except Exception as e:
            logger.error(f"Error executing counter-trend sell: {e}")
            return {'status': 'error', 'message': str(e)}

    async def market_regime_analysis(self, coin: str) -> Dict:
        """
        Analyze market regime to determine optimal strategy
        Returns key information about current market conditions
        """
        try:
            # Get historical candles for different timeframes
            hourly_candles = self.info.candles_snapshot(coin, "1h", 48)  # 2 days of hourly
            daily_candles = self.info.candles_snapshot(coin, "1d", 30)   # 30 days of daily
            
            if len(hourly_candles) < 24 or len(daily_candles) < 7:
                return {'status': 'error', 'message': f'Insufficient historical data for {coin}'}
            
            # Extract prices
            hourly_closes = [float(c['c']) for c in hourly_candles]
            daily_closes = [float(c['c']) for c in daily_candles]
            
            # Calculate short-term volatility (hourly)
            short_term_returns = [hourly_closes[i]/hourly_closes[i-1]-1 for i in range(1, len(hourly_closes))]
            short_term_volatility = np.std(short_term_returns) * np.sqrt(24)  # Annualize
            
            # Calculate long-term volatility (daily)
            long_term_returns = [daily_closes[i]/daily_closes[i-1]-1 for i in range(1, len(daily_candles))]
            long_term_volatility = np.std(long_term_returns) * np.sqrt(365)  # Annualize
            
            # Calculate moving averages
            sma20 = sum(daily_closes[-20:]) / 20 if len(daily_closes) >= 20 else sum(daily_closes) / len(daily_closes)
            sma50 = sum(daily_closes[-50:]) / 50 if len(daily_closes) >= 50 else sma20
            
            current_price = hourly_closes[-1]
            
            # Determine trend
            trend = "neutral"
            if current_price > sma20 and sma20 > sma50:
                trend = "bullish"
            elif current_price < sma20 and sma20 < sma50:
                trend = "bearish"
                
            # Calculate volatility ratio (short-term vs long-term)
            volatility_ratio = short_term_volatility / long_term_volatility if long_term_volatility > 0 else 1.0
            
            # Determine market regime
            regime = "normal"
            
            if volatility_ratio > 1.5:
                regime = "high_volatility"
            elif volatility_ratio < 0.5:
                regime = "low_volatility"
                
            if short_term_volatility > 0.8:  # 80% annualized volatility
                regime = "crisis"
                
            # Store market regime
            self.market_regime[coin] = {
                'regime': regime,
                'trend': trend,
                'short_volatility': short_term_volatility,
                'long_volatility': long_term_volatility,
                'volatility_ratio': volatility_ratio,
                'updated_at': datetime.now()
            }
            
            # Determine optimal strategy for current regime
            optimal_strategy = "market_making"  # Default
            
            if regime == "high_volatility":
                if trend == "bullish":
                    optimal_strategy = "momentum_trading"
                else:
                    optimal_strategy = "counter_trend"
            elif regime == "low_volatility":
                optimal_strategy = "market_making"
            elif regime == "crisis":
                optimal_strategy = "counter_trend"
            else:  # normal
                if trend == "bullish" or trend == "bearish":
                    optimal_strategy = "momentum_trading"
                else:
                    optimal_strategy = "market_making"
            
            return {
                'status': 'success',
                'coin': coin,
                'regime': regime,
                'trend': trend,
                'volatility': {
                    'short_term': short_term_volatility,
                    'long_term': long_term_volatility,
                    'ratio': volatility_ratio
                },
                'levels': {
                    'current_price': current_price,
                    'sma20': sma20,
                    'sma50': sma50,
                    'price_to_sma20': current_price / sma20 - 1,
                    'sma20_to_sma50': sma20 / sma50 - 1
                },
                'recommended_strategy': optimal_strategy
            }
            
        except Exception as e:
            logger.error(f"Error in market regime analysis for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def validate_connection(self) -> bool:
        """Validate connection to exchange"""
        try:
            # Simple validation by getting price data
            all_mids = self.info.all_mids()
            return len(all_mids) > 0
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False

    async def risk_managed_trading(self, coin: str, risk_percentage: float = 0.02, 
                             strategy: str = 'momentum') -> Dict:
        """
        Implement position sizing based on account value and market conditions
        
        Args:
            coin: The coin to trade
            risk_percentage: Maximum percentage of account to risk
            strategy: Trading strategy to use ('momentum', 'counter_trend', etc)
        """
        try:
            # Get account value
            user_state = self.info.user_state(self.address)
            account_value = float(user_state['marginSummary']['accountValue'])
            
            if account_value <= 0:
                return {'status': 'error', 'message': 'Could not determine account value'}
            
            # Calculate optimal position size based on risk
            position_size = await self.calculate_optimal_position_size(coin, risk_percentage)
            
            # Execute selected strategy with risk-optimized size
            result = None
            if strategy == 'momentum':
                result = await self.momentum_strategy(coin, position_size)
            elif strategy == 'counter_trend':
                result = await self.counter_trend_strategy(coin, position_size)
            elif strategy == 'scalping':
                result = await self.scalping_strategy(coin)
            else:
                return {'status': 'error', 'message': f'Unknown strategy: {strategy}'}
            
            if result and result.get('status') == 'success':
                # Add risk management information to result
                result['risk_management'] = {
                    'account_value': account_value,
                    'risk_percentage': risk_percentage,
                    'position_size': position_size,
                }
                
            return result
            
        except Exception as e:
            self.logger.error(f"Risk managed trading error: {e}")
            return {'status': 'error', 'message': str(e)}

    async def calculate_optimal_position_size(self, coin: str, risk_percentage: float = 0.02) -> float:
        """
        Calculate optimal position size based on account value, volatility, and risk tolerance
        
        Args:
            coin: The trading pair
            risk_percentage: Maximum percentage of account to risk
        
        Returns:
            Optimal position size in coin units
        """
        try:
            # Get account value
            user_state = self.info.user_state(self.address)
            account_value = float(user_state['marginSummary']['accountValue'])
            
            # Get current exposure to calculate remaining risk capacity
            current_exposure = 0
            for pos in user_state.get('assetPositions', []):
                if float(pos['position'].get('szi', 0)) != 0:
                    entry_px = float(pos['position'].get('entryPx', 0))
                    size = float(pos['position'].get('szi', 0))
                    current_exposure += abs(size * entry_px)
            
            remaining_capacity = max(0, account_value - current_exposure)
            
            # Calculate volatility
            volatility = await self._calculate_coin_volatility(coin)
            
            # Get current price
            all_mids = self.info.all_mids()
            current_price = float(all_mids.get(coin, 0))
            
            if current_price <= 0:
                return 0
            
            # Calculate position size in dollars
            # - Lower volatility = larger position
            # - Higher volatility = smaller position
            volatility_factor = max(0.5, min(2.0, 0.2 / volatility)) if volatility > 0 else 1.0
            
            # Calculate optimal position size in dollars
            position_dollars = min(
                account_value * risk_percentage * volatility_factor,
                remaining_capacity * 0.5  # At most 50% of remaining capacity
            )
            
            # Convert to coin units
            position_size = position_dollars / current_price
            
            # Round to 4 decimal places for most coins
            return round(position_size, 4)
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0.01  # Safe minimal size
        
    async def _calculate_coin_volatility(self, coin: str, lookback_hours: int = 24) -> float:
        """Calculate coin volatility based on recent price history"""
        try:
            # Get hourly candles
            candles = self.info.candles_snapshot(coin, "1h", lookback_hours)
            
            if len(candles) < 6:  # Need at least 6 hours of data
                return 0.02  # Default 2% if insufficient data
            
            # Calculate returns
            prices = [float(c['c']) for c in candles]
            returns = [prices[i]/prices[i-1]-1 for i in range(1, len(prices))]
            
            # Calculate annualized volatility
            hourly_vol = np.std(returns)
            annualized_vol = hourly_vol * np.sqrt(24 * 365)
            
            return annualized_vol
            
        except Exception as e:
            self.logger.error(f"Volatility calculation error: {e}")
            return 0.02  # Default 2%

    async def integrated_risk_management(self) -> Dict:
        """
        Get comprehensive risk analysis across all positions
        """
        try:
            # Get user state
            user_state = self.info.user_state(self.address)
            account_value = float(user_state['marginSummary']['accountValue'])
            
            # Calculate current exposure and risk metrics
            positions = []
            total_exposure = 0
            weighted_volatility = 0
            
            for pos in user_state.get('assetPositions', []):
                if float(pos['position'].get('szi', 0)) != 0:
                    coin = pos['position'].get('coin', '')
                    size = float(pos['position'].get('szi', 0))
                    entry_px = float(pos['position'].get('entryPx', 0))
                    
                    # Calculate position exposure
                    exposure = abs(size * entry_px)
                    total_exposure += exposure
                    
                    # Calculate coin volatility
                    volatility = await self._calculate_coin_volatility(coin)
                    
                    # Calculate position risk
                    position_risk = exposure * volatility
                    weighted_volatility += position_risk
                    
                    positions.append({
                        'coin': coin,
                        'size': size,
                        'exposure_usd': exposure,
                        'volatility': volatility,
                        'position_risk': position_risk
                    })
            
            # Calculate portfolio risk metrics
            if total_exposure > 0:
                portfolio_volatility = weighted_volatility / total_exposure
            else:
                portfolio_volatility = 0
                
            leverage = total_exposure / account_value if account_value > 0 else 0
            
            # Calculate maximum drawdown risk
            max_drawdown_risk = total_exposure * portfolio_volatility * 2  # 2-sigma event
            max_drawdown_percentage = max_drawdown_risk / account_value if account_value > 0 else 0
            
            # Calculate risk per strategy
            strategy_exposure = {}
            for strategy, alloc in self.active_strategies.items():
                strategy_exposure[strategy] = alloc.get('allocation', 0) * account_value
            
            return {
                'status': 'success',
                'account_value': account_value,
                'total_exposure': total_exposure,
                'leverage': leverage,
                'portfolio_volatility': portfolio_volatility,
                'max_drawdown_risk': {
                    'usd': max_drawdown_risk,
                    'percentage': max_drawdown_percentage
                },
                'position_risk': positions,
                'strategy_exposure': strategy_exposure,
                'risk_rating': 'high' if leverage > 3 else 'medium' if leverage > 1 else 'low'
            }
            
        except Exception as e:
            self.logger.error(f"Risk management error: {e}")
            return {'status': 'error', 'message': str(e)}

    async def start_user_automation(self, user_id: int, exchange, config: Dict = None) -> Dict:
        """Start automated trading for a specific user"""
        try:
            if config is None:
                config = {
                    'strategy': 'momentum_with_maker',
                    'pairs': ['BTC', 'ETH', 'SOL'],
                    'position_size': 15,  # $15 per trade
                    'spread_percentage': 0.002  # 0.2% spread
                }
            from hyperliquid.info import Info
            info = Info(exchange.base_url if hasattr(exchange, 'base_url') else constants.MAINNET_API_URL)
            mids = info.all_mids()
            if not mids:
                return {'status': 'error', 'message': 'No market data available'}
            orders_placed = 0
            strategies_started = []
            # Momentum
            for pair in config['pairs'][:2]:
                if pair not in mids:
                    continue
                try:
                    current_price = float(mids[pair])
                    size = config['position_size'] / current_price
                    breakout_price = current_price * 1.008
                    result = exchange.order(
                        pair, True, size, breakout_price,
                        {"limit": {"tif": "Gtc"}}
                    )
                    if result and result.get('status') == 'ok':
                        orders_placed += 1
                        strategies_started.append('momentum')
                except Exception:
                    continue
            # Maker rebate
            spread = config['spread_percentage']
            for pair in config['pairs'][:3]:
                if pair not in mids:
                    continue
                try:
                    current_price = float(mids[pair])
                    size = config['position_size'] / current_price
                    bid_price = current_price * (1 - spread)
                    ask_price = current_price * (1 + spread)
                    bid_result = exchange.order(
                        pair, True, size, bid_price,
                        {"limit": {"tif": "Alo"}}
                    )
                    if bid_result and bid_result.get('status') == 'ok':
                        orders_placed += 1
                    ask_result = exchange.order(
                        pair, False, size, ask_price,
                        {"limit": {"tif": "Alo"}}
                    )
                    if ask_result and ask_result.get('status') == 'ok':
                        orders_placed += 1
                    strategies_started.append('maker_rebate')
                except Exception:
                    continue
            self.user_strategies = getattr(self, 'user_strategies', {})
            self.user_strategies[user_id] = {
                'config': config,
                'strategies': strategies_started,
                'started_at': time.time(),
                'orders_placed': orders_placed
            }
            return {
                'status': 'success',
                'orders_placed': orders_placed,
                'strategies': strategies_started,
                'pairs_count': len(config['pairs'])
            }
        except Exception as e:
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
