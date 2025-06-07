import asyncio
import json
import threading
import random
import time
from typing import Dict, List, Callable, Optional, Any, Deque
from dataclasses import dataclass
import logging
from datetime import datetime
from collections import deque

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
        
        # Connection health monitoring
        self.last_heartbeat = time.time()
        self.heartbeat_task = None
        self.connection_active = False
        self.reconnect_attempts = 0
        
        # Message queues for high-frequency operations
        self.message_queues = {}
        self.processing_tasks = {}
        self.queue_processors = {}
        
        # Rate limiting
        self.rate_limits = {
            "default": {"max_per_second": 10, "window_size": 1.0},
            "order_updates": {"max_per_second": 20, "window_size": 1.0},
            "l2_book": {"max_per_second": 5, "window_size": 1.0}
        }
        
        # Connection setup
        self.logger.info(f"WebSocket manager initialized for address: {self.address}")
        
    async def initialize(self):
        """Initialize connection with backoff and start heartbeat"""
        await self.connect_with_backoff()
        
    async def connect_with_backoff(self, max_retries: int = 10):
        """Connect to WebSocket with exponential backoff"""
        retry = 0
        delay = 1  # Start with 1 second delay
        
        while retry < max_retries:
            try:
                # Attempt connection
                # Note: The actual connection is handled by the Info.subscribe method
                # This is just to handle reconnection logic
                
                # Set up heartbeat monitoring
                self._setup_heartbeat()
                
                # Mark as connected
                self.connection_active = True
                self.reconnect_attempts = 0
                
                self.logger.info(f"WebSocket connected after {retry} retries")
                return True
            except Exception as e:
                self.logger.error(f"WebSocket connection attempt {retry+1} failed: {e}")
                retry += 1
                self.reconnect_attempts += 1
                
                # Exponential backoff with jitter
                delay = min(30, delay * 2)  # Cap at 30 seconds
                jitter = random.uniform(0, 0.3 * delay)  # 0-30% jitter
                await asyncio.sleep(delay + jitter)
        
        self.logger.critical(f"Failed to connect after {max_retries} attempts")
        return False

    def _setup_heartbeat(self):
        """Setup heartbeat monitoring for connection health"""
        self.last_heartbeat = time.time()
        
        # Cancel existing heartbeat task if any
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
        
        # Create heartbeat checker task
        async def check_heartbeat():
            while True:
                try:
                    if time.time() - self.last_heartbeat > 30:  # No heartbeat for 30 seconds
                        self.logger.warning("WebSocket heartbeat timeout, reconnecting...")
                        self.connection_active = False
                        await self.connect_with_backoff()
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    self.logger.info("Heartbeat monitor cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"Error in heartbeat check: {e}")
        
        self.heartbeat_task = asyncio.create_task(check_heartbeat())
    
    def _update_heartbeat(self):
        """Update heartbeat timestamp when message received"""
        self.last_heartbeat = time.time()
    
    def _create_message_queue(self, queue_name: str):
        """Create a message queue for a specific subscription type"""
        if queue_name in self.message_queues:
            return
        
        self.message_queues[queue_name] = deque(maxlen=1000)  # Limit queue size
        self.queue_processors[queue_name] = True  # Flag to control processor
        
        # Start queue processor
        async def process_queue():
            rate_limit = self.rate_limits.get(queue_name, self.rate_limits["default"])
            max_per_second = rate_limit["max_per_second"]
            window_size = rate_limit["window_size"]
            
            tokens = max_per_second
            last_refill = time.time()
            
            while self.queue_processors.get(queue_name, False):
                try:
                    # Token bucket rate limiting
                    now = time.time()
                    elapsed = now - last_refill
                    tokens = min(max_per_second, tokens + elapsed * (max_per_second / window_size))
                    last_refill = now
                    
                    if self.message_queues[queue_name] and tokens >= 1:
                        # Process a message
                        message, callback = self.message_queues[queue_name].popleft()
                        tokens -= 1
                        
                        try:
                            callback(message)
                        except Exception as e:
                            self.logger.error(f"Error in {queue_name} callback: {e}")
                    else:
                        # Either queue is empty or we hit rate limit
                        await asyncio.sleep(0.01)
                    
                except asyncio.CancelledError:
                    self.logger.info(f"Queue processor for {queue_name} cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"Error in queue processor for {queue_name}: {e}")
                    await asyncio.sleep(1)  # Avoid tight loop on error
        
        # Start processing task
        self.processing_tasks[queue_name] = asyncio.create_task(process_queue())
    
    def _enqueue_message(self, queue_name: str, message: Any, callback: Callable):
        """Add message to queue for rate-limited processing"""
        if queue_name not in self.message_queues:
            self._create_message_queue(queue_name)
        
        self.message_queues[queue_name].append((message, callback))
    
    def subscribe_all_mids(self, callback: Callable[[Dict], None]):
        """Subscribe to all mid prices using real Hyperliquid WebSocket via Info.subscribe()"""
        def wrapper(data):
            self._update_heartbeat()  # Update connection health
            self._process_all_mids(data)
            self._enqueue_message("all_mids", data, callback)
        
        # Use Info.subscribe() exactly like basic_ws.py
        self.info.subscribe({"type": "allMids"}, wrapper)
        self.callbacks["allMids"] = callback
        self.logger.info("Subscribed to all mids via Info.subscribe()")
    
    def subscribe_l2_book(self, coin: str, callback: Callable[[Dict], None]):
        """Subscribe to L2 order book for a specific coin"""
        def wrapper(data):
            self._update_heartbeat()  # Update connection health
            self._process_l2_book(coin, data)
            self._enqueue_message("l2_book", data, callback)
        
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

class ConnectionHealthMonitor:
    """
    Monitor WebSocket connection health for reliability
    """
    
    def __init__(self, ws_manager: HyperliquidWebSocketManager):
        self.ws_manager = ws_manager
        self.health_status = {
            "is_healthy": True,
            "last_heartbeat": time.time(),
            "reconnect_count": 0,
            "latency_ms": 0,
            "message_rates": {}
        }
        self.logger = logging.getLogger(__name__)
        self.monitoring_task = None
    
    async def start_monitoring(self):
        """Start monitoring WebSocket connection health"""
        async def monitor_loop():
            while True:
                try:
                    # Check connection status
                    connection_active = await self._check_connection()
                    
                    # Update health status
                    self.health_status["is_healthy"] = connection_active
                    self.health_status["last_heartbeat"] = self.ws_manager.last_heartbeat
                    self.health_status["reconnect_count"] = self.ws_manager.reconnect_attempts
                    
                    # Measure latency
                    latency = await self._measure_latency()
                    self.health_status["latency_ms"] = latency
                    
                    # Calculate message rates
                    self._update_message_rates()
                    
                    # Log status periodically
                    self.logger.debug(f"WebSocket health: {self.health_status}")
                    
                    await asyncio.sleep(30)  # Check every 30 seconds
                    
                except asyncio.CancelledError:
                    self.logger.info("Connection health monitor cancelled")
                    break
                except Exception as e:
                    self.logger.error(f"Error in connection health monitor: {e}")
                    await asyncio.sleep(10)  # Back off on error
        
        self.monitoring_task = asyncio.create_task(monitor_loop())
    
    async def _check_connection(self) -> bool:
        """Check if connection is active"""
        return await self.ws_manager.test_connection()
    
    async def _measure_latency(self) -> int:
        """Measure WebSocket latency in milliseconds"""
        try:
            start_time = time.time()
            if await self.ws_manager.test_connection():
                end_time = time.time()
                return int((end_time - start_time) * 1000)
            return -1  # Connection failed
        except Exception:
            return -1
    
    def _update_message_rates(self):
        """Calculate message processing rates for each queue"""
        for queue_name, queue in self.ws_manager.message_queues.items():
            self.health_status["message_rates"][queue_name] = len(queue)
    
    async def stop_monitoring(self):
        """Stop monitoring task"""
        if self.monitoring_task and not self.monitoring_task.done():
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

    def get_health_report(self) -> Dict:
        """Get comprehensive health report"""
        return {
            **self.health_status,
            "report_time": time.time(),
            "uptime_seconds": time.time() - self.ws_manager.last_heartbeat + 30 
                if not self.health_status["is_healthy"] else 
                time.time() - self.ws_manager.last_heartbeat
        }
