import asyncio
import json
import logging
import time
import websockets
from typing import Dict, List, Optional, Callable, Any, Union

from hyperliquid.utils import constants

class HyperliquidWebSocketManager:
    """
    Advanced WebSocket manager for Hyperliquid API with comprehensive subscription support
    """
    
    def __init__(self, base_url=None, address=None, info=None, exchange=None):
        """Initialize the WebSocket manager"""
        self.base_url = base_url or constants.TESTNET_API_URL
        self.ws_url = "wss://api.hyperliquid.xyz/ws"
        self.address = address
        self.info = info
        self.exchange = exchange
        
        self.websockets = {}
        self.callbacks = {}
        self.subscriptions = {}
        self.connected = False
        self.logger = logging.getLogger(__name__)
        
        # Initialize post request tracking
        self.post_futures = {}
        
    async def connect(self):
        """Establish WebSocket connection"""
        try:
            if not self.connected:
                self.ws = await websockets.connect(self.ws_url)
                self.connected = True
                self.logger.info(f"Connected to WebSocket: {self.ws_url}")
                
                # Start message receiver
                asyncio.create_task(self._message_receiver())
                
                return True
        except Exception as e:
            self.logger.error(f"Error connecting to WebSocket: {e}")
            self.connected = False
            return False
            
    async def _message_receiver(self):
        """Background task to receive messages"""
        while self.connected:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                await self._process_message(data)
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("WebSocket connection closed")
                self.connected = False
                await self._reconnect()
                break
            except Exception as e:
                self.logger.error(f"Error receiving message: {e}")
    
    async def _reconnect(self):
        """Reconnect and resubscribe to streams"""
        retry_delay = 1
        max_retries = 10
        retries = 0
        
        while retries < max_retries and not self.connected:
            self.logger.info(f"Attempting to reconnect (retry {retries+1}/{max_retries})...")
            try:
                await self.connect()
                if self.connected:
                    # Resubscribe to all active subscriptions
                    for sub_id, subscription in self.subscriptions.items():
                        await self.send_subscription(subscription)
                    
                    self.logger.info("Successfully reconnected and resubscribed")
                    return True
            except Exception as e:
                self.logger.error(f"Reconnection error: {e}")
            
            retries += 1
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 30)  # Exponential backoff with max 30 seconds
        
        self.logger.error("Failed to reconnect after multiple attempts")
        return False
    
    async def send_subscription(self, subscription: Dict):
        """Send a subscription message"""
        if not self.connected:
            await self.connect()
            
        sub_message = {
            "method": "subscribe",
            "subscription": subscription
        }
        
        try:
            await self.ws.send(json.dumps(sub_message))
            return True
        except Exception as e:
            self.logger.error(f"Error sending subscription: {e}")
            return False

    async def unsubscribe(self, sub_id: str) -> bool:
        """Unsubscribe from a specific subscription"""
        if sub_id in self.subscriptions:
            # Get subscription details
            subscription = self.subscriptions[sub_id]
            
            try:
                # Send unsubscribe message
                unsubscribe_message = {
                    "method": "unsubscribe",
                    "subscription": subscription
                }
                
                await self.ws.send(json.dumps(unsubscribe_message))
                
                # Remove from tracked subscriptions
                subscription = self.subscriptions.pop(sub_id)
                
                # Identify channel and callback to remove
                channel_parts = sub_id.split('_')
                if len(channel_parts) > 0:
                    channel_type = channel_parts[0]
                    if channel_type in self.callbacks:
                        # For simplicity, remove all callbacks for this channel
                        # In a more advanced implementation, we would only remove specific callback
                        self.callbacks.pop(channel_type)
                        
                self.logger.info(f"Unsubscribed from {sub_id}")
                return True
            except Exception as e:
                self.logger.error(f"Error unsubscribing from {sub_id}: {e}")
                return False
                
        self.logger.warning(f"Subscription {sub_id} not found for unsubscribing")
        return False
    
    async def post_request(self, request: Dict, request_id: int = None) -> Dict:
        """
        Send a WebSocket POST request
        
        Args:
            request: The request payload (info or action)
            request_id: Optional request ID for tracking (auto-generated if None)
        """
        if not self.connected:
            await self.connect()
        
        # Generate request ID if not provided
        if request_id is None:
            request_id = int(time.time() * 1000)
            
        # Create post message
        post_message = {
            "method": "post",
            "id": request_id,
            "request": request
        }
        
        # Create future for response
        response_future = asyncio.Future()
        self.post_futures[request_id] = response_future
        
        try:
            # Send post request
            await self.ws.send(json.dumps(post_message))
            
            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=10.0)
            return response
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout waiting for response to request {request_id}")
            self.post_futures.pop(request_id, None)
            return {"status": "error", "message": "Timeout waiting for response"}
        except Exception as e:
            self.logger.error(f"Error sending post request: {e}")
            self.post_futures.pop(request_id, None)
            return {"status": "error", "message": str(e)}
    
    async def post_info_request(self, payload: Dict) -> Dict:
        """Send an info request via WebSocket"""
        request = {
            "type": "info",
            "payload": payload
        }
        return await self.post_request(request)
    
    async def post_action_request(self, payload: Dict) -> Dict:
        """Send a signed action request via WebSocket"""
        request = {
            "type": "action",
            "payload": payload
        }
        return await self.post_request(request)
    
    async def _process_message(self, data: Dict):
        """Process incoming WebSocket messages"""
        # Handle post responses
        if "channel" in data and data["channel"] == "post" and "data" in data:
            post_data = data["data"]
            if "id" in post_data and post_data["id"] in self.post_futures:
                request_id = post_data["id"]
                future = self.post_futures.pop(request_id)
                if not future.done():
                    future.set_result(post_data.get("response", {}))
                return
                
        # Handle subscription data
        if "channel" in data:
            channel = data["channel"]
            if channel in self.callbacks:
                for callback in self.callbacks[channel]:
                    try:
                        await self._execute_callback(callback, data)
                    except Exception as e:
                        self.logger.error(f"Error in callback for {channel}: {e}")
    
    async def subscribe_all_mids(self, callback: Callable, dex: str = None):
        """Subscribe to all mid prices"""
        subscription = {"type": "allMids"}
        if dex:
            subscription["dex"] = dex
            
        sub_id = f"allMids_{dex or 'default'}"
        self.subscriptions[sub_id] = subscription
        
        if "allMids" not in self.callbacks:
            self.callbacks["allMids"] = []
        self.callbacks["allMids"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_notification(self, callback: Callable):
        """Subscribe to notifications for the user"""
        if not self.address:
            self.logger.error("User address required for notification subscription")
            return False
            
        subscription = {
            "type": "notification",
            "user": self.address
        }
        
        sub_id = f"notification_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "notification" not in self.callbacks:
            self.callbacks["notification"] = []
        self.callbacks["notification"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_web_data(self, callback: Callable):
        """Subscribe to web data for the user"""
        if not self.address:
            self.logger.error("User address required for web data subscription")
            return False
            
        subscription = {
            "type": "webData2",
            "user": self.address
        }
        
        sub_id = f"webData2_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "webData2" not in self.callbacks:
            self.callbacks["webData2"] = []
        self.callbacks["webData2"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_candles(self, coin: str, interval: str, callback: Callable):
        """Subscribe to candle data for a coin"""
        subscription = {
            "type": "candle",
            "coin": coin,
            "interval": interval
        }
        
        sub_id = f"candle_{coin}_{interval}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"candle_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_l2_book(self, coin: str, callback: Callable, n_sig_figs: int = None, mantissa: int = None):
        """Subscribe to L2 order book for a coin"""
        subscription = {
            "type": "l2Book",
            "coin": coin
        }
        
        if n_sig_figs:
            subscription["nSigFigs"] = n_sig_figs
            
        if mantissa:
            subscription["mantissa"] = mantissa
        
        sub_id = f"l2Book_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"l2Book_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_trades(self, coin: str, callback: Callable):
        """Subscribe to trades for a coin"""
        subscription = {
            "type": "trades",
            "coin": coin
        }
        
        sub_id = f"trades_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"trades_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_order_updates(self, callback: Callable):
        """Subscribe to order updates for the user"""
        if not self.address:
            self.logger.error("User address required for order updates subscription")
            return False
            
        subscription = {
            "type": "orderUpdates",
            "user": self.address
        }
        
        sub_id = f"orderUpdates_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "orderUpdates" not in self.callbacks:
            self.callbacks["orderUpdates"] = []
        self.callbacks["orderUpdates"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_events(self, callback: Callable):
        """Subscribe to user events"""
        if not self.address:
            self.logger.error("User address required for user events subscription")
            return False
            
        subscription = {
            "type": "userEvents",
            "user": self.address
        }
        
        sub_id = f"userEvents_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userEvents" not in self.callbacks:
            self.callbacks["userEvents"] = []
        self.callbacks["userEvents"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_fills(self, callback: Callable, aggregate_by_time: bool = False):
        """Subscribe to user fills"""
        if not self.address:
            self.logger.error("User address required for user fills subscription")
            return False
            
        subscription = {
            "type": "userFills",
            "user": self.address
        }
        
        if aggregate_by_time:
            subscription["aggregateByTime"] = True
        
        sub_id = f"userFills_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userFills" not in self.callbacks:
            self.callbacks["userFills"] = []
        self.callbacks["userFills"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_fundings(self, callback: Callable):
        """Subscribe to user fundings"""
        if not self.address:
            self.logger.error("User address required for user fundings subscription")
            return False
            
        subscription = {
            "type": "userFundings",
            "user": self.address
        }
        
        sub_id = f"userFundings_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userFundings" not in self.callbacks:
            self.callbacks["userFundings"] = []
        self.callbacks["userFundings"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_non_funding_ledger_updates(self, callback: Callable):
        """Subscribe to user non-funding ledger updates"""
        if not self.address:
            self.logger.error("User address required for non-funding ledger updates subscription")
            return False
            
        subscription = {
            "type": "userNonFundingLedgerUpdates",
            "user": self.address
        }
        
        sub_id = f"userNonFundingLedgerUpdates_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userNonFundingLedgerUpdates" not in self.callbacks:
            self.callbacks["userNonFundingLedgerUpdates"] = []
        self.callbacks["userNonFundingLedgerUpdates"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_active_asset_ctx(self, coin: str, callback: Callable) -> bool:
        """Subscribe to active asset context for a coin"""
        subscription = {
            "type": "activeAssetCtx",
            "coin": coin
        }
        
        sub_id = f"activeAssetCtx_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"activeAssetCtx_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_active_asset_data(self, coin: str, callback: Callable) -> bool:
        """
        Subscribe to active asset data for a user and coin
        
        Args:
            coin: The coin symbol
            callback: Function to call when data is received
        """
        if not self.address:
            self.logger.error("User address required for active asset data subscription")
            return False
            
        subscription = {
            "type": "activeAssetData",
            "user": self.address,
            "coin": coin
        }
        
        sub_id = f"activeAssetData_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"activeAssetData_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_twap_slice_fills(self, callback: Callable) -> bool:
        """Subscribe to user's TWAP slice fills"""
        if not self.address:
            self.logger.error("User address required for TWAP slice fills subscription")
            return False
            
        subscription = {
            "type": "userTwapSliceFills",
            "user": self.address
        }
        
        sub_id = f"userTwapSliceFills_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        channel = "userTwapSliceFills"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_twap_history(self, callback: Callable) -> bool:
        """Subscribe to user's TWAP order history"""
        if not self.address:
            self.logger.error("User address required for TWAP history subscription")
            return False
            
        subscription = {
            "type": "userTwapHistory",
            "user": self.address
        }
        
        sub_id = f"userTwapHistory_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        channel = "userTwapHistory"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_bbo(self, coin: str, callback: Callable) -> bool:
        """
        Subscribe to best bid and offer (BBO) for a coin
        
        Args:
            coin: The coin symbol
            callback: Function to call when data is received
        """
        subscription = {
            "type": "bbo",
            "coin": coin
        }
        
        sub_id = f"bbo_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"bbo_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def unsubscribe(self, sub_id: str) -> bool:
        """Unsubscribe from a specific subscription"""
        if sub_id in self.subscriptions:
            # Get subscription details
            subscription = self.subscriptions[sub_id]
            
            try:
                # Send unsubscribe message
                unsubscribe_message = {
                    "method": "unsubscribe",
                    "subscription": subscription
                }
                
                await self.ws.send(json.dumps(unsubscribe_message))
                
                # Remove from tracked subscriptions
                subscription = self.subscriptions.pop(sub_id)
                
                # Identify channel and callback to remove
                channel_parts = sub_id.split('_')
                if len(channel_parts) > 0:
                    channel_type = channel_parts[0]
                    if channel_type in self.callbacks:
                        # For simplicity, remove all callbacks for this channel
                        # In a more advanced implementation, we would only remove specific callback
                        self.callbacks.pop(channel_type)
                        
                self.logger.info(f"Unsubscribed from {sub_id}")
                return True
            except Exception as e:
                self.logger.error(f"Error unsubscribing from {sub_id}: {e}")
                return False
                
        self.logger.warning(f"Subscription {sub_id} not found for unsubscribing")
        return False
    
    async def post_request(self, request: Dict, request_id: int = None) -> Dict:
        """
        Send a WebSocket POST request
        
        Args:
            request: The request payload (info or action)
            request_id: Optional request ID for tracking (auto-generated if None)
        """
        if not self.connected:
            await self.connect()
        
        # Generate request ID if not provided
        if request_id is None:
            request_id = int(time.time() * 1000)
            
        # Create post message
        post_message = {
            "method": "post",
            "id": request_id,
            "request": request
        }
        
        # Create future for response
        response_future = asyncio.Future()
        self.post_futures[request_id] = response_future
        
        try:
            # Send post request
            await self.ws.send(json.dumps(post_message))
            
            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=10.0)
            return response
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout waiting for response to request {request_id}")
            self.post_futures.pop(request_id, None)
            return {"status": "error", "message": "Timeout waiting for response"}
        except Exception as e:
            self.logger.error(f"Error sending post request: {e}")
            self.post_futures.pop(request_id, None)
            return {"status": "error", "message": str(e)}
    
    async def post_info_request(self, payload: Dict) -> Dict:
        """Send an info request via WebSocket"""
        request = {
            "type": "info",
            "payload": payload
        }
        return await self.post_request(request)
    
    async def post_action_request(self, payload: Dict) -> Dict:
        """Send a signed action request via WebSocket"""
        request = {
            "type": "action",
            "payload": payload
        }
        return await self.post_request(request)
    
    async def _process_message(self, data: Dict):
        """Process incoming WebSocket messages"""
        # Handle post responses
        if "channel" in data and data["channel"] == "post" and "data" in data:
            post_data = data["data"]
            if "id" in post_data and post_data["id"] in self.post_futures:
                request_id = post_data["id"]
                future = self.post_futures.pop(request_id)
                if not future.done():
                    future.set_result(post_data.get("response", {}))
                return
                
        # Handle subscription data
        if "channel" in data:
            channel = data["channel"]
            if channel in self.callbacks:
                for callback in self.callbacks[channel]:
                    try:
                        await self._execute_callback(callback, data)
                    except Exception as e:
                        self.logger.error(f"Error in callback for {channel}: {e}")
    
    async def subscribe_all_mids(self, callback: Callable, dex: str = None):
        """Subscribe to all mid prices"""
        subscription = {"type": "allMids"}
        if dex:
            subscription["dex"] = dex
            
        sub_id = f"allMids_{dex or 'default'}"
        self.subscriptions[sub_id] = subscription
        
        if "allMids" not in self.callbacks:
            self.callbacks["allMids"] = []
        self.callbacks["allMids"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_notification(self, callback: Callable):
        """Subscribe to notifications for the user"""
        if not self.address:
            self.logger.error("User address required for notification subscription")
            return False
            
        subscription = {
            "type": "notification",
            "user": self.address
        }
        
        sub_id = f"notification_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "notification" not in self.callbacks:
            self.callbacks["notification"] = []
        self.callbacks["notification"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_web_data(self, callback: Callable):
        """Subscribe to web data for the user"""
        if not self.address:
            self.logger.error("User address required for web data subscription")
            return False
            
        subscription = {
            "type": "webData2",
            "user": self.address
        }
        
        sub_id = f"webData2_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "webData2" not in self.callbacks:
            self.callbacks["webData2"] = []
        self.callbacks["webData2"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_candles(self, coin: str, interval: str, callback: Callable):
        """Subscribe to candle data for a coin"""
        subscription = {
            "type": "candle",
            "coin": coin,
            "interval": interval
        }
        
        sub_id = f"candle_{coin}_{interval}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"candle_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_l2_book(self, coin: str, callback: Callable, n_sig_figs: int = None, mantissa: int = None):
        """Subscribe to L2 order book for a coin"""
        subscription = {
            "type": "l2Book",
            "coin": coin
        }
        
        if n_sig_figs:
            subscription["nSigFigs"] = n_sig_figs
            
        if mantissa:
            subscription["mantissa"] = mantissa
        
        sub_id = f"l2Book_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"l2Book_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_trades(self, coin: str, callback: Callable):
        """Subscribe to trades for a coin"""
        subscription = {
            "type": "trades",
            "coin": coin
        }
        
        sub_id = f"trades_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"trades_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_order_updates(self, callback: Callable):
        """Subscribe to order updates for the user"""
        if not self.address:
            self.logger.error("User address required for order updates subscription")
            return False
            
        subscription = {
            "type": "orderUpdates",
            "user": self.address
        }
        
        sub_id = f"orderUpdates_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "orderUpdates" not in self.callbacks:
            self.callbacks["orderUpdates"] = []
        self.callbacks["orderUpdates"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_events(self, callback: Callable):
        """Subscribe to user events"""
        if not self.address:
            self.logger.error("User address required for user events subscription")
            return False
            
        subscription = {
            "type": "userEvents",
            "user": self.address
        }
        
        sub_id = f"userEvents_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userEvents" not in self.callbacks:
            self.callbacks["userEvents"] = []
        self.callbacks["userEvents"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_fills(self, callback: Callable, aggregate_by_time: bool = False):
        """Subscribe to user fills"""
        if not self.address:
            self.logger.error("User address required for user fills subscription")
            return False
            
        subscription = {
            "type": "userFills",
            "user": self.address
        }
        
        if aggregate_by_time:
            subscription["aggregateByTime"] = True
        
        sub_id = f"userFills_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userFills" not in self.callbacks:
            self.callbacks["userFills"] = []
        self.callbacks["userFills"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_fundings(self, callback: Callable):
        """Subscribe to user fundings"""
        if not self.address:
            self.logger.error("User address required for user fundings subscription")
            return False
            
        subscription = {
            "type": "userFundings",
            "user": self.address
        }
        
        sub_id = f"userFundings_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userFundings" not in self.callbacks:
            self.callbacks["userFundings"] = []
        self.callbacks["userFundings"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_non_funding_ledger_updates(self, callback: Callable):
        """Subscribe to user non-funding ledger updates"""
        if not self.address:
            self.logger.error("User address required for non-funding ledger updates subscription")
            return False
            
        subscription = {
            "type": "userNonFundingLedgerUpdates",
            "user": self.address
        }
        
        sub_id = f"userNonFundingLedgerUpdates_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        if "userNonFundingLedgerUpdates" not in self.callbacks:
            self.callbacks["userNonFundingLedgerUpdates"] = []
        self.callbacks["userNonFundingLedgerUpdates"].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_active_asset_ctx(self, coin: str, callback: Callable) -> bool:
        """Subscribe to active asset context for a coin"""
        subscription = {
            "type": "activeAssetCtx",
            "coin": coin
        }
        
        sub_id = f"activeAssetCtx_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"activeAssetCtx_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_active_asset_data(self, coin: str, callback: Callable) -> bool:
        """
        Subscribe to active asset data for a user and coin
        
        Args:
            coin: The coin symbol
            callback: Function to call when data is received
        """
        if not self.address:
            self.logger.error("User address required for active asset data subscription")
            return False
            
        subscription = {
            "type": "activeAssetData",
            "user": self.address,
            "coin": coin
        }
        
        sub_id = f"activeAssetData_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"activeAssetData_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_twap_slice_fills(self, callback: Callable) -> bool:
        """Subscribe to user's TWAP slice fills"""
        if not self.address:
            self.logger.error("User address required for TWAP slice fills subscription")
            return False
            
        subscription = {
            "type": "userTwapSliceFills",
            "user": self.address
        }
        
        sub_id = f"userTwapSliceFills_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        channel = "userTwapSliceFills"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_user_twap_history(self, callback: Callable) -> bool:
        """Subscribe to user's TWAP order history"""
        if not self.address:
            self.logger.error("User address required for TWAP history subscription")
            return False
            
        subscription = {
            "type": "userTwapHistory",
            "user": self.address
        }
        
        sub_id = f"userTwapHistory_{self.address}"
        self.subscriptions[sub_id] = subscription
        
        channel = "userTwapHistory"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def subscribe_bbo(self, coin: str, callback: Callable) -> bool:
        """
        Subscribe to best bid and offer (BBO) for a coin
        
        Args:
            coin: The coin symbol
            callback: Function to call when data is received
        """
        subscription = {
            "type": "bbo",
            "coin": coin
        }
        
        sub_id = f"bbo_{coin}"
        self.subscriptions[sub_id] = subscription
        
        channel = f"bbo_{coin}"
        if channel not in self.callbacks:
            self.callbacks[channel] = []
        self.callbacks[channel].append(callback)
        
        return await self.send_subscription(subscription)
    
    async def test_connection(self) -> bool:
        """Test WebSocket connection"""
        try:
            if self.ws and self.ws.open:
                return True
                
            # Connect if not already connected
            await self.connect()
            
            # Wait a bit to establish connection
            await asyncio.sleep(2)
            
            return self.ws and self.ws.open
        except Exception as e:
            self.logger.error(f"WebSocket connection test failed: {e}")
            return False
