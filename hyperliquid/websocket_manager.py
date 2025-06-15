"""
WebSocket manager for Hyperliquid API
Implements proper connection handling and subscription management
"""
import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable, Union, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    try:
        from websockets import WebSocketServerProtocol
        from websockets.exceptions import ConnectionClosed
    except ImportError:
        pass

logger = logging.getLogger(__name__)

class WebsocketManager:
    """
    WebSocket manager for Hyperliquid API
    Handles subscriptions, reconnections, and message dispatching
    """
    
    def __init__(self, base_url: str, address: Optional[str] = None, 
                 info=None, exchange=None):
        """
        Initialize WebSocket manager
        
        Args:
            base_url: Hyperliquid API base URL
            address: User address for subscriptions
            info: Info client instance
            exchange: Exchange client instance
        """
        self.base_url = base_url
        self.ws_url = base_url.replace('https://', 'wss://').replace('http://', 'ws://')
        self.address = address
        self.info = info
        self.exchange = exchange
        
        # WebSocket connection
        self.websocket: Optional[Any] = None
        self.connected = False
        self.reconnecting = False
        
        # Subscription management
        self.subscriptions: Dict[str, Dict[str, Any]] = {}
        self.message_handlers: Dict[str, Callable] = {}
        
        # Connection monitoring
        self.last_ping = 0
        self.ping_interval = 30  # 30 seconds
        self.connection_timeout = 60  # 60 seconds
        
        # Message queue for when disconnected
        self.message_queue: List[Dict[str, Any]] = []
        self.max_queue_size = 1000
        
        logger.info(f"WebSocket manager initialized for {self.ws_url}")
    
    async def connect(self) -> bool:
        """
        Establish WebSocket connection
        
        Returns:
            bool: True if connection successful
        """
        try:
            # Try to import websockets
            try:
                import websockets
            except ImportError:
                logger.warning("websockets package not installed, WebSocket functionality disabled")
                return False
            
            self.websocket = await websockets.connect(
                f"{self.ws_url}/ws",
                ping_interval=self.ping_interval,
                ping_timeout=10,
                close_timeout=10
            )
            
            self.connected = True
            self.last_ping = time.time()
            
            logger.info("WebSocket connection established")
            
            # Start background tasks
            asyncio.create_task(self._message_listener())
            asyncio.create_task(self._connection_monitor())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect WebSocket: {e}")
            self.connected = False
            return False
    
    async def disconnect(self) -> None:
        """Close WebSocket connection"""
        try:
            if self.websocket and not self.websocket.closed:
                await self.websocket.close()
            
            self.connected = False
            self.websocket = None
            
            logger.info("WebSocket disconnected")
            
        except Exception as e:
            logger.error(f"Error disconnecting WebSocket: {e}")
    
    async def subscribe(self, subscription_type: str, **kwargs) -> bool:
        """
        Subscribe to a WebSocket channel
        
        Args:
            subscription_type: Type of subscription
            **kwargs: Additional subscription parameters
            
        Returns:
            bool: True if subscription successful
        """
        try:
            subscription_id = f"{subscription_type}_{int(time.time())}"
            
            # Build subscription message based on type
            if subscription_type == "allMids":
                message = {
                    "method": "subscribe",
                    "subscription": {"type": "allMids"}
                }
            elif subscription_type == "l2Book":
                coin = kwargs.get("coin", "BTC")
                message = {
                    "method": "subscribe", 
                    "subscription": {"type": "l2Book", "coin": coin}
                }
            elif subscription_type == "trades":
                coin = kwargs.get("coin", "BTC")
                message = {
                    "method": "subscribe",
                    "subscription": {"type": "trades", "coin": coin}
                }
            elif subscription_type == "userEvents" and self.address:
                message = {
                    "method": "subscribe",
                    "subscription": {"type": "userEvents", "user": self.address}
                }
            else:
                logger.error(f"Unknown subscription type: {subscription_type}")
                return False
            
            # Send subscription
            if await self._send_message(message):
                self.subscriptions[subscription_id] = {
                    "type": subscription_type,
                    "message": message,
                    "kwargs": kwargs,
                    "created_at": time.time()
                }
                
                logger.info(f"Subscribed to {subscription_type} with ID {subscription_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error subscribing to {subscription_type}: {e}")
            return False
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from a channel
        
        Args:
            subscription_id: ID of subscription to remove
            
        Returns:
            bool: True if unsubscription successful
        """
        try:
            if subscription_id not in self.subscriptions:
                logger.warning(f"Subscription {subscription_id} not found")
                return False
            
            subscription = self.subscriptions[subscription_id]
            
            # Build unsubscribe message
            message = {
                "method": "unsubscribe",
                "subscription": subscription["message"]["subscription"]
            }
            
            if await self._send_message(message):
                del self.subscriptions[subscription_id]
                logger.info(f"Unsubscribed from {subscription_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error unsubscribing from {subscription_id}: {e}")
            return False
    
    def add_message_handler(self, message_type: str, handler: Callable) -> None:
        """
        Add a message handler for specific message types
        
        Args:
            message_type: Type of message to handle
            handler: Callback function to handle messages
        """
        self.message_handlers[message_type] = handler
        logger.info(f"Added handler for {message_type}")
    
    async def _send_message(self, message: Dict[str, Any]) -> bool:
        """
        Send message to WebSocket
        
        Args:
            message: Message to send
            
        Returns:
            bool: True if sent successfully
        """
        try:
            if not self.connected or not self.websocket:
                # Queue message for when reconnected
                if len(self.message_queue) < self.max_queue_size:
                    self.message_queue.append(message)
                return False
            
            await self.websocket.send(json.dumps(message))
            return True
            
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
            self.connected = False
            return False
    
    async def _message_listener(self) -> None:
        """Background task to listen for WebSocket messages"""
        try:
            while self.connected and self.websocket:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(), 
                        timeout=self.connection_timeout
                    )
                    
                    await self._handle_message(message)
                    
                except asyncio.TimeoutError:
                    logger.warning("WebSocket message timeout")
                    break
                except Exception as e:
                    logger.error(f"Error in message listener: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Message listener crashed: {e}")
        finally:
            self.connected = False
            if not self.reconnecting:
                asyncio.create_task(self._reconnect())
    
    async def _handle_message(self, raw_message: str) -> None:
        """
        Handle incoming WebSocket message
        
        Args:
            raw_message: Raw message string
        """
        try:
            message = json.loads(raw_message)
            message_type = message.get("channel", "unknown")
            
            # Update last ping time for any message
            self.last_ping = time.time()
            
            # Call appropriate handler
            if message_type in self.message_handlers:
                try:
                    await self.message_handlers[message_type](message)
                except Exception as e:
                    logger.error(f"Error in message handler for {message_type}: {e}")
            
            # Log message for debugging
            logger.debug(f"Received {message_type}: {message}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON message received: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _connection_monitor(self) -> None:
        """Monitor connection health and reconnect if needed"""
        while self.connected:
            try:
                current_time = time.time()
                
                # Check if we haven't received messages recently
                if current_time - self.last_ping > self.connection_timeout:
                    logger.warning("Connection timeout detected")
                    self.connected = False
                    break
                
                # Send ping to keep connection alive
                if current_time - self.last_ping > self.ping_interval:
                    await self._send_message({"method": "ping"})
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in connection monitor: {e}")
                break
        
        # Start reconnection if needed
        if not self.reconnecting:
            asyncio.create_task(self._reconnect())
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect WebSocket"""
        if self.reconnecting:
            return
            
        self.reconnecting = True
        reconnect_attempts = 0
        max_attempts = 5
        
        logger.info("Starting WebSocket reconnection...")
        
        while reconnect_attempts < max_attempts:
            try:
                await asyncio.sleep(2 ** reconnect_attempts)  # Exponential backoff
                
                if await self.connect():
                    logger.info("WebSocket reconnected successfully")
                    
                    # Resubscribe to all channels
                    await self._resubscribe_all()
                    
                    # Send queued messages
                    await self._send_queued_messages()
                    
                    self.reconnecting = False
                    return
                
                reconnect_attempts += 1
                logger.warning(f"Reconnection attempt {reconnect_attempts} failed")
                
            except Exception as e:
                logger.error(f"Error during reconnection attempt {reconnect_attempts}: {e}")
                reconnect_attempts += 1
        
        logger.error("Failed to reconnect after maximum attempts")
        self.reconnecting = False
    
    async def _resubscribe_all(self) -> None:
        """Resubscribe to all channels after reconnection"""
        try:
            for sub_id, subscription in list(self.subscriptions.items()):
                message = subscription["message"]
                if await self._send_message(message):
                    logger.info(f"Resubscribed to {subscription['type']}")
                else:
                    logger.error(f"Failed to resubscribe to {subscription['type']}")
                    
        except Exception as e:
            logger.error(f"Error resubscribing: {e}")
    
    async def _send_queued_messages(self) -> None:
        """Send queued messages after reconnection"""
        try:
            while self.message_queue:
                message = self.message_queue.pop(0)
                if not await self._send_message(message):
                    # Put it back if failed
                    self.message_queue.insert(0, message)
                    break
                    
        except Exception as e:
            logger.error(f"Error sending queued messages: {e}")
    
    async def test_connection(self) -> bool:
        """
        Test WebSocket connection
        
        Returns:
            bool: True if connection test successful
        """
        try:
            if await self.connect():
                await self.disconnect()
                return True
            return False
            
        except Exception as e:
            logger.error(f"WebSocket connection test failed: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get WebSocket manager status
        
        Returns:
            Dict with status information
        """
        return {
            "connected": self.connected,
            "reconnecting": self.reconnecting,
            "subscriptions": len(self.subscriptions),
            "queued_messages": len(self.message_queue),
            "last_ping": self.last_ping,
            "handlers": list(self.message_handlers.keys())
        }
    
    async def close(self) -> None:
        """Close WebSocket manager and cleanup"""
        try:
            await self.disconnect()
            self.subscriptions.clear()
            self.message_handlers.clear()
            self.message_queue.clear()
            
            logger.info("WebSocket manager closed")
            
        except Exception as e:
            logger.error(f"Error closing WebSocket manager: {e}")
    
    async def start(self):
        """Start the WebSocket manager - alias for connect()"""
        return await self.connect()
    
    async def stop(self):
        """Stop the WebSocket manager - alias for disconnect()"""
        await self.disconnect()


# Alias for compatibility with existing imports
WebsocketManager = WebsocketManager
