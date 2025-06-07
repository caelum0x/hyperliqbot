import asyncio
import json
import threading
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass
import logging
from datetime import datetime

# Real Hyperliquid WebSocket imports
from hyperliquid.info import Info
from hyperliquid.utils import constants
import example_utils

@dataclass
class RealMarketData:
    """Real market data structure from Hyperliquid"""
    coin: str
    timestamp: float
    best_bid: float
    best_ask: float
    bid_size: float
    ask_size: float
    last_price: float
    volume_24h: float
    spread_bps: float

class HyperliquidWebSocketManager:
    """
    Real-time WebSocket manager using actual Hyperliquid WebSocket API
    Following the pattern from basic_ws.py example
    """
    
    def __init__(self, base_url: str = None, address: str = None, info: Info = None, exchange = None):
        # Use provided components or set up new ones
        if info and address:
            self.address = address
            self.info = info
            self.exchange = exchange
        else:
            self.base_url = base_url or constants.TESTNET_API_URL
            self.address, self.info, self.exchange = example_utils.setup(self.base_url)
        
        self.subscriptions = {}
        self.callbacks = {}
        self.market_data = {}
        self.logger = logging.getLogger(__name__)
        
        # The Info class handles WebSocket connections internally when subscribe() is called
        self.logger.info(f"WebSocket manager initialized for address: {self.address}")
        
    def subscribe_all_mids(self, callback: Callable[[Dict], None]):
        """Subscribe to all mid prices using real Hyperliquid WebSocket via Info.subscribe()"""
        def wrapper(data):
            self._process_all_mids(data)
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "allMids"}, wrapper)
        self.callbacks["allMids"] = callback
        self.logger.info("Subscribed to all mids via Info.subscribe()")
    
    def subscribe_l2_book(self, coin: str, callback: Callable[[Dict], None]):
        """Subscribe to L2 order book for a specific coin"""
        def wrapper(data):
            self._process_l2_book(coin, data)
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "l2Book", "coin": coin}, wrapper)
        self.callbacks[f"l2Book_{coin}"] = callback
        self.logger.info(f"Subscribed to L2 book for {coin} via Info.subscribe()")
    
    def subscribe_trades(self, coin: str, callback: Callable[[Dict], None]):
        """Subscribe to trades for a specific coin"""
        def wrapper(data):
            self._process_trades(coin, data)
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "trades", "coin": coin}, wrapper)
        self.callbacks[f"trades_{coin}"] = callback
        self.logger.info(f"Subscribed to trades for {coin} via Info.subscribe()")
    
    def subscribe_user_events(self, callback: Callable[[Dict], None]):
        """Subscribe to user events using authenticated address"""
        def wrapper(data):
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "userEvents", "user": self.address}, wrapper)
        self.callbacks["userEvents"] = callback
        self.logger.info(f"Subscribed to user events for {self.address} via Info.subscribe()")
    
    def subscribe_user_fills(self, callback: Callable[[Dict], None]):
        """Subscribe to user fills"""
        def wrapper(data):
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "userFills", "user": self.address}, wrapper)
        self.callbacks["userFills"] = callback
        self.logger.info(f"Subscribed to user fills for {self.address} via Info.subscribe()")
    
    def subscribe_order_updates(self, callback: Callable[[Dict], None]):
        """Subscribe to order updates"""
        def wrapper(data):
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "orderUpdates", "user": self.address}, wrapper)
        self.callbacks["orderUpdates"] = callback
        self.logger.info(f"Subscribed to order updates for {self.address} via Info.subscribe()")
    
    def subscribe_candles(self, coin: str, interval: str, callback: Callable[[Dict], None]):
        """Subscribe to candle data"""
        def wrapper(data):
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "candle", "coin": coin, "interval": interval}, wrapper)
        self.callbacks[f"candle_{coin}_{interval}"] = callback
        self.logger.info(f"Subscribed to {interval} candles for {coin} via Info.subscribe()")
    
    def subscribe_bbo(self, coin: str, callback: Callable[[Dict], None]):
        """Subscribe to best bid/offer data"""
        def wrapper(data):
            self._process_bbo(coin, data)
            callback(data)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "bbo", "coin": coin}, wrapper)
        self.callbacks[f"bbo_{coin}"] = callback
        self.logger.info(f"Subscribed to BBO for {coin} via Info.subscribe()")

    def subscribe_user_fundings(self, callback: Callable[[Dict], None]):
        """Subscribe to user funding payments"""
        def wrapper(data):
            callback(data)
        
        # Additional subscription type from basic_ws.py
        self.info.subscribe({"type": "userFundings", "user": self.address}, wrapper)
        self.callbacks["userFundings"] = callback
        self.logger.info(f"Subscribed to user fundings for {self.address} via Info.subscribe()")

    def subscribe_user_non_funding_ledger_updates(self, callback: Callable[[Dict], None]):
        """Subscribe to user non-funding ledger updates"""
        def wrapper(data):
            callback(data)
        
        # Additional subscription type from basic_ws.py
        self.info.subscribe({"type": "userNonFundingLedgerUpdates", "user": self.address}, wrapper)
        self.callbacks["userNonFundingLedgerUpdates"] = callback
        self.logger.info(f"Subscribed to user non-funding ledger updates for {self.address} via Info.subscribe()")

    def subscribe_web_data2(self, callback: Callable[[Dict], None]):
        """Subscribe to web data2"""
        def wrapper(data):
            callback(data)
        
        # Additional subscription type from basic_ws.py
        self.info.subscribe({"type": "webData2", "user": self.address}, wrapper)
        self.callbacks["webData2"] = callback
        self.logger.info(f"Subscribed to webData2 for {self.address} via Info.subscribe()")
    
    def _process_all_mids(self, data: Dict):
        """Process all mids data"""
        try:
            # The Info WebSocket sends data in different formats, check the actual structure
            if isinstance(data, dict):
                # Handle direct mids data or nested structure
                mids = data.get("mids") or data
                if isinstance(mids, dict):
                    for coin, price_str in mids.items():
                        try:
                            price = float(price_str)
                            self._update_market_data(coin, {"last_price": price})
                        except (ValueError, TypeError):
                            continue
        except Exception as e:
            self.logger.error(f"Error processing all mids: {e}")
    
    def _process_l2_book(self, coin: str, data: Dict):
        """Process L2 book data"""
        try:
            if "levels" in data:
                levels = data["levels"]
                if len(levels) >= 2:
                    bids = levels[0]  # Bid levels
                    asks = levels[1]  # Ask levels
                    
                    if bids and asks:
                        best_bid = float(bids[0][0])
                        best_ask = float(asks[0][0])
                        bid_size = float(bids[0][1])
                        ask_size = float(asks[0][1])
                        
                        spread_bps = ((best_ask - best_bid) / best_bid) * 10000
                        
                        self._update_market_data(coin, {
                            "best_bid": best_bid,
                            "best_ask": best_ask,
                            "bid_size": bid_size,
                            "ask_size": ask_size,
                            "spread_bps": spread_bps,
                            "last_price": (best_bid + best_ask) / 2
                        })
        except Exception as e:
            self.logger.error(f"Error processing L2 book for {coin}: {e}")
    
    def _process_trades(self, coin: str, data: List[Dict]):
        """Process trade data"""
        try:
            if isinstance(data, list) and data:
                latest_trade = data[-1]
                price = float(latest_trade.get("px", 0))
                size = float(latest_trade.get("sz", 0))
                
                self._update_market_data(coin, {
                    "last_price": price,
                    "last_trade_size": size
                })
        except Exception as e:
            self.logger.error(f"Error processing trades for {coin}: {e}")
    
    def _process_bbo(self, coin: str, data: Dict):
        """Process best bid/offer data"""
        try:
            if "bid" in data and "ask" in data:
                bid = float(data["bid"])
                ask = float(data["ask"])
                
                self._update_market_data(coin, {
                    "best_bid": bid,
                    "best_ask": ask,
                    "last_price": (bid + ask) / 2,
                    "spread_bps": ((ask - bid) / bid) * 10000
                })
        except Exception as e:
            self.logger.error(f"Error processing BBO for {coin}: {e}")
    
    def _update_market_data(self, coin: str, updates: Dict):
        """Update market data for a coin"""
        if coin not in self.market_data:
            self.market_data[coin] = RealMarketData(
                coin=coin,
                timestamp=datetime.now().timestamp(),
                best_bid=0,
                best_ask=0,
                bid_size=0,
                ask_size=0,
                last_price=0,
                volume_24h=0,
                spread_bps=0
            )
        
        # Update fields
        for field, value in updates.items():
            if hasattr(self.market_data[coin], field):
                setattr(self.market_data[coin], field, value)
        
        # Update timestamp
        self.market_data[coin].timestamp = datetime.now().timestamp()
    
    def get_market_data(self, coin: str) -> Optional[RealMarketData]:
        """Get current market data for a coin"""
        return self.market_data.get(coin)
    
    def get_all_market_data(self) -> Dict[str, RealMarketData]:
        """Get all current market data"""
        return self.market_data.copy()

class TradingSignalProcessor:
    """
    Process real-time Hyperliquid data to generate trading signals
    """
    
    def __init__(self, ws_manager: HyperliquidWebSocketManager):
        self.ws_manager = ws_manager
        self.signal_callbacks = []
        self.price_history = {}
        self.logger = logging.getLogger(__name__)
        
    def add_signal_callback(self, callback: Callable[[Dict], None]):
        """Add callback for trading signals"""
        self.signal_callbacks.append(callback)
    
    def start_monitoring(self, coins: List[str]):
        """Start monitoring coins for trading signals"""
        # Subscribe to all mids for general price tracking
        self.ws_manager.subscribe_all_mids(self._process_price_update)
        
        for coin in coins:
            # Subscribe to L2 book for spread analysis
            self.ws_manager.subscribe_l2_book(coin, self._analyze_orderbook)
            
            # Subscribe to trades for volume analysis
            self.ws_manager.subscribe_trades(coin, self._analyze_trades)
            
            # Subscribe to BBO for tight spread detection
            self.ws_manager.subscribe_bbo(coin, self._detect_tight_spreads)
            
            # Initialize price history
            self.price_history[coin] = []
        
        # Subscribe to user events for portfolio tracking
        self.ws_manager.subscribe_user_fills(self._track_fills)
        
        self.logger.info(f"Started monitoring {len(coins)} coins for signals")
    
    def _process_price_update(self, data: Dict):
        """Process price updates for momentum detection"""
        try:
            if isinstance(data, dict) and "mids" in data:
                for coin, price_str in data["mids"].items():
                    price = float(price_str)
                    
                    if coin in self.price_history:
                        self.price_history[coin].append({
                            "price": price,
                            "timestamp": datetime.now().timestamp()
                        })
                        
                        # Keep only last 100 prices
                        if len(self.price_history[coin]) > 100:
                            self.price_history[coin] = self.price_history[coin][-100:]
                        
                        # Check for momentum
                        self._check_momentum(coin)
        except Exception as e:
            self.logger.error(f"Error processing price update: {e}")
    
    def _analyze_orderbook(self, data: Dict):
        """Analyze orderbook for imbalance signals"""
        try:
            market_data = self.ws_manager.get_market_data(data.get("coin", ""))
            if not market_data:
                return
            
            # Check for orderbook imbalance
            if market_data.ask_size > 0:
                ratio = market_data.bid_size / market_data.ask_size
                
                if ratio > 3:  # Strong buying pressure
                    self._emit_signal({
                        "type": "orderbook_imbalance",
                        "coin": market_data.coin,
                        "signal": "bullish",
                        "ratio": ratio,
                        "confidence": min(ratio / 3, 1.0)
                    })
                elif ratio < 0.33:  # Strong selling pressure
                    self._emit_signal({
                        "type": "orderbook_imbalance",
                        "coin": market_data.coin,
                        "signal": "bearish",
                        "ratio": ratio,
                        "confidence": min(3 / ratio if ratio > 0 else 3, 1.0)
                    })
        except Exception as e:
            self.logger.error(f"Error analyzing orderbook: {e}")
    
    def _analyze_trades(self, data: List[Dict]):
        """Analyze trades for volume signals"""
        try:
            if not isinstance(data, list) or not data:
                return
            
            coin = data[0].get("coin")
            if not coin:
                return
            
            # Analyze large trades
            for trade in data:
                price = float(trade.get("px", 0))
                size = float(trade.get("sz", 0))
                value = price * size
                
                if value > 50000:  # Large trade >$50k
                    self._emit_signal({
                        "type": "large_trade",
                        "coin": coin,
                        "signal": "bullish" if trade.get("side") == "buy" else "bearish",
                        "value": value,
                        "price": price,
                        "confidence": min(value / 100000, 0.9)
                    })
        except Exception as e:
            self.logger.error(f"Error analyzing trades: {e}")
    
    def _detect_tight_spreads(self, data: Dict):
        """Detect tight spreads for market making opportunities"""
        try:
            coin = data.get("coin")
            if not coin:
                return
            
            market_data = self.ws_manager.get_market_data(coin)
            if market_data and market_data.spread_bps < 5:  # <0.5 bps spread
                self._emit_signal({
                    "type": "tight_spread",
                    "coin": coin,
                    "signal": "market_make",
                    "spread_bps": market_data.spread_bps,
                    "mid_price": market_data.last_price,
                    "confidence": 0.9
                })
        except Exception as e:
            self.logger.error(f"Error detecting tight spreads: {e}")
    
    def _track_fills(self, data: Dict):
        """Track user fills for performance analysis"""
        try:
            # Process fill data for portfolio tracking
            if isinstance(data, list):
                for fill in data:
                    self._emit_signal({
                        "type": "user_fill",
                        "data": fill,
                        "confidence": 1.0
                    })
        except Exception as e:
            self.logger.error(f"Error tracking fills: {e}")
    
    def _check_momentum(self, coin: str):
        """Check for price momentum"""
        try:
            history = self.price_history.get(coin, [])
            if len(history) < 20:
                return
            
            recent = history[-20:]
            prices = [h["price"] for h in recent]
            
            # Simple momentum: compare current vs 20-period average
            avg_price = sum(prices) / len(prices)
            current_price = prices[-1]
            momentum = (current_price - avg_price) / avg_price
            
            if abs(momentum) > 0.005:  # >0.5% momentum
                self._emit_signal({
                    "type": "momentum",
                    "coin": coin,
                    "signal": "bullish" if momentum > 0 else "bearish",
                    "momentum": abs(momentum),
                    "confidence": min(abs(momentum) * 100, 0.9)
                })
        except Exception as e:
            self.logger.error(f"Error checking momentum for {coin}: {e}")
    
    def _emit_signal(self, signal: Dict):
        """Emit trading signal to all callbacks"""
        signal["timestamp"] = datetime.now().timestamp()
        
        for callback in self.signal_callbacks:
            try:
                callback(signal)
            except Exception as e:
                self.logger.error(f"Error in signal callback: {e}")

# Legacy aliases for compatibility
RealHyperliquidWebSocketManager = HyperliquidWebSocketManager
RealTradingSignalProcessor = TradingSignalProcessor
MarketData = RealMarketData
