import asyncio
import json
import websocket
import threading
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass
import logging

@dataclass
class MarketData:
    """Market data structure"""
    coin: str
    timestamp: float
    best_bid: float
    best_ask: float
    bid_size: float
    ask_size: float
    last_price: float
    volume_24h: float

class HyperliquidWebSocketManager:
    """
    Real-time WebSocket manager for Hyperliquid data streams
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.ws_url = base_url.replace("https://", "wss://") + "/ws"
        self.ws = None
        self.subscriptions = {}
        self.callbacks = {}
        self.running = False
        self.logger = logging.getLogger(__name__)
        self.market_data = {}
        
    def subscribe_l2_book(self, coin: str, callback: Callable[[Dict], None]):
        """Subscribe to L2 order book for a coin"""
        subscription = {"type": "l2Book", "coin": coin}
        self.subscriptions[f"l2Book_{coin}"] = subscription
        self.callbacks[f"l2Book_{coin}"] = callback
        
        if self.ws:
            self._send_subscription(subscription)
    
    def subscribe_all_mids(self, callback: Callable[[Dict], None]):
        """Subscribe to all mid prices"""
        subscription = {"type": "allMids"}
        self.subscriptions["allMids"] = subscription
        self.callbacks["allMids"] = callback
        
        if self.ws:
            self._send_subscription(subscription)
    
    def subscribe_trades(self, coin: str, callback: Callable[[Dict], None]):
        """Subscribe to trade feed for a coin"""
        subscription = {"type": "trades", "coin": coin}
        self.subscriptions[f"trades_{coin}"] = subscription
        self.callbacks[f"trades_{coin}"] = callback
        
        if self.ws:
            self._send_subscription(subscription)
    
    def subscribe_user_events(self, user: str, callback: Callable[[Dict], None]):
        """Subscribe to user events (fills, liquidations, etc.)"""
        subscription = {"type": "userEvents", "user": user}
        self.subscriptions[f"userEvents_{user}"] = subscription
        self.callbacks[f"userEvents_{user}"] = callback
        
        if self.ws:
            self._send_subscription(subscription)
    
    def subscribe_user_fills(self, user: str, callback: Callable[[Dict], None]):
        """Subscribe to user fills"""
        subscription = {"type": "userFills", "user": user}
        self.subscriptions[f"userFills_{user}"] = subscription
        self.callbacks[f"userFills_{user}"] = callback
        
        if self.ws:
            self._send_subscription(subscription)
    
    def subscribe_order_updates(self, user: str, callback: Callable[[Dict], None]):
        """Subscribe to order updates"""
        subscription = {"type": "orderUpdates", "user": user}
        self.subscriptions[f"orderUpdates_{user}"] = subscription
        self.callbacks[f"orderUpdates_{user}"] = callback
        
        if self.ws:
            self._send_subscription(subscription)
    
    def start(self):
        """Start WebSocket connection"""
        self.running = True
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                self._handle_message(data)
            except Exception as e:
                self.logger.error(f"Error processing WebSocket message: {e}")
        
        def on_error(ws, error):
            self.logger.error(f"WebSocket error: {error}")
        
        def on_close(ws, close_status_code, close_msg):
            self.logger.info("WebSocket connection closed")
            if self.running:
                # Attempt to reconnect
                threading.Timer(5.0, self._reconnect).start()
        
        def on_open(ws):
            self.logger.info("WebSocket connection opened")
            # Subscribe to all pending subscriptions
            for subscription in self.subscriptions.values():
                self._send_subscription(subscription)
        
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # Run in separate thread
        threading.Thread(
            target=self.ws.run_forever,
            daemon=True
        ).start()
    
    def stop(self):
        """Stop WebSocket connection"""
        self.running = False
        if self.ws:
            self.ws.close()
    
    def _reconnect(self):
        """Reconnect WebSocket"""
        if self.running:
            self.logger.info("Attempting to reconnect WebSocket...")
            self.start()
    
    def _send_subscription(self, subscription: Dict):
        """Send subscription message"""
        try:
            message = {
                "method": "subscribe",
                "subscription": subscription
            }
            self.ws.send(json.dumps(message))
            self.logger.info(f"Subscribed to: {subscription}")
        except Exception as e:
            self.logger.error(f"Error sending subscription: {e}")
    
    def _handle_message(self, data: Dict):
        """Handle incoming WebSocket message"""
        try:
            channel = data.get("channel")
            msg_data = data.get("data", {})
            
            if channel == "l2Book":
                coin = msg_data.get("coin")
                if coin:
                    # Update market data
                    self._update_market_data(coin, msg_data)
                    
                    # Call callback
                    callback_key = f"l2Book_{coin}"
                    if callback_key in self.callbacks:
                        self.callbacks[callback_key](data)
            
            elif channel == "allMids":
                # Update all mid prices
                mids = msg_data.get("mids", {})
                for coin, price in mids.items():
                    if coin not in self.market_data:
                        self.market_data[coin] = MarketData(
                            coin=coin,
                            timestamp=0,
                            best_bid=0,
                            best_ask=0,
                            bid_size=0,
                            ask_size=0,
                            last_price=float(price),
                            volume_24h=0
                        )
                    else:
                        self.market_data[coin].last_price = float(price)
                
                # Call callback
                if "allMids" in self.callbacks:
                    self.callbacks["allMids"](data)
            
            elif channel == "trades":
                coin = msg_data[0].get("coin") if msg_data and len(msg_data) > 0 else None
                if coin:
                    callback_key = f"trades_{coin}"
                    if callback_key in self.callbacks:
                        self.callbacks[callback_key](data)
            
            elif channel in ["userEvents", "userFills", "orderUpdates"]:
                # Find matching callback
                for callback_key, callback in self.callbacks.items():
                    if channel in callback_key:
                        callback(data)
                        break
            
        except Exception as e:
            self.logger.error(f"Error handling WebSocket message: {e}")
    
    def _update_market_data(self, coin: str, l2_data: Dict):
        """Update market data from L2 book"""
        try:
            levels = l2_data.get("levels", [[], []])
            bids = levels[0] if len(levels) > 0 else []
            asks = levels[1] if len(levels) > 1 else []
            
            best_bid = float(bids[0][0]) if bids else 0
            best_ask = float(asks[0][0]) if asks else 0
            bid_size = float(bids[0][1]) if bids else 0
            ask_size = float(asks[0][1]) if asks else 0
            
            import time
            self.market_data[coin] = MarketData(
                coin=coin,
                timestamp=time.time(),
                best_bid=best_bid,
                best_ask=best_ask,
                bid_size=bid_size,
                ask_size=ask_size,
                last_price=(best_bid + best_ask) / 2 if best_bid and best_ask else 0,
                volume_24h=0  # Would need separate endpoint for volume
            )
            
        except Exception as e:
            self.logger.error(f"Error updating market data: {e}")
    
    def get_market_data(self, coin: str) -> Optional[MarketData]:
        """Get current market data for a coin"""
        return self.market_data.get(coin)
    
    def get_all_market_data(self) -> Dict[str, MarketData]:
        """Get all current market data"""
        return self.market_data.copy()

class TradingSignalProcessor:
    """
    Process real-time data to generate trading signals
    """
    
    def __init__(self, ws_manager: HyperliquidWebSocketManager):
        self.ws_manager = ws_manager
        self.signal_callbacks = []
        self.price_history = {}
        self.volume_history = {}
        
    def add_signal_callback(self, callback: Callable[[Dict], None]):
        """Add callback for trading signals"""
        self.signal_callbacks.append(callback)
    
    def start_signal_processing(self, coins: List[str]):
        """Start processing signals for specified coins"""
        for coin in coins:
            # Subscribe to order book updates
            self.ws_manager.subscribe_l2_book(coin, self._process_l2_book)
            
            # Subscribe to trades
            self.ws_manager.subscribe_trades(coin, self._process_trades)
    
    def _process_l2_book(self, data: Dict):
        """Process L2 book data for signals"""
        try:
            msg_data = data.get("data", {})
            coin = msg_data.get("coin")
            
            if not coin:
                return
            
            market_data = self.ws_manager.get_market_data(coin)
            if not market_data:
                return
            
            # Check for order book imbalance
            bid_ask_ratio = market_data.bid_size / market_data.ask_size if market_data.ask_size > 0 else 0
            
            if bid_ask_ratio > 3:  # Strong buying pressure
                signal = {
                    "type": "orderbook_imbalance",
                    "coin": coin,
                    "signal": "bullish",
                    "strength": min(bid_ask_ratio / 3, 2),  # Cap at 2x
                    "best_bid": market_data.best_bid,
                    "best_ask": market_data.best_ask,
                    "timestamp": market_data.timestamp
                }
                self._emit_signal(signal)
            
            elif bid_ask_ratio < 0.33:  # Strong selling pressure
                signal = {
                    "type": "orderbook_imbalance",
                    "coin": coin,
                    "signal": "bearish",
                    "strength": min(3 / bid_ask_ratio, 2) if bid_ask_ratio > 0 else 2,
                    "best_bid": market_data.best_bid,
                    "best_ask": market_data.best_ask,
                    "timestamp": market_data.timestamp
                }
                self._emit_signal(signal)
            
        except Exception as e:
            logging.error(f"Error processing L2 book: {e}")
    
    def _process_trades(self, data: Dict):
        """Process trade data for signals"""
        try:
            trades = data.get("data", [])
            
            for trade in trades:
                coin = trade.get("coin")
                price = float(trade.get("px", 0))
                size = float(trade.get("sz", 0))
                side = trade.get("side")
                
                # Track large trades
                trade_value = price * size
                if trade_value > 10000:  # $10k+ trades
                    signal = {
                        "type": "large_trade",
                        "coin": coin,
                        "signal": "bullish" if side == "B" else "bearish",
                        "price": price,
                        "size": size,
                        "value": trade_value,
                        "timestamp": trade.get("time", 0)
                    }
                    self._emit_signal(signal)
                
                # Update price history
                if coin not in self.price_history:
                    self.price_history[coin] = []
                
                self.price_history[coin].append(price)
                
                # Keep only last 100 prices
                if len(self.price_history[coin]) > 100:
                    self.price_history[coin] = self.price_history[coin][-100:]
                
                # Check for price momentum
                if len(self.price_history[coin]) >= 10:
                    recent_prices = self.price_history[coin][-10:]
                    price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                    
                    if abs(price_change) > 0.002:  # 0.2% momentum
                        signal = {
                            "type": "price_momentum",
                            "coin": coin,
                            "signal": "bullish" if price_change > 0 else "bearish",
                            "momentum": abs(price_change),
                            "price": price,
                            "timestamp": trade.get("time", 0)
                        }
                        self._emit_signal(signal)
                
        except Exception as e:
            logging.error(f"Error processing trades: {e}")
    
    def _emit_signal(self, signal: Dict):
        """Emit trading signal to all callbacks"""
        for callback in self.signal_callbacks:
            try:
                callback(signal)
            except Exception as e:
                logging.error(f"Error in signal callback: {e}")
