"""
Simple trading strategy module with direct trade execution
"""
import logging
import time
import asyncio
from typing import Dict, Optional, Any
from datetime import datetime

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger(__name__)

class SimpleTrader:
    """
    Simple trading strategy for basic order execution and testing
    Provides fundamental trading operations for users
    """
    
    def __init__(self, exchange: Exchange = None, info: Info = None, base_url: str = None):
        self.exchange = exchange
        self.info = info or Info(base_url or constants.MAINNET_API_URL)
        self.base_url = base_url or constants.MAINNET_API_URL
        self.user_manager = None
        
        logger.info("SimpleTrader initialized")
    
    async def validate_connection(self) -> bool:
        """Validate connection to Hyperliquid API"""
        try:
            if not self.info:
                return False
            
            # Test connection
            mids = self.info.all_mids()
            return len(mids) > 0
            
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False
    
    async def place_market_order(self, coin: str, is_buy: bool, size: float) -> Dict:
        """
        Place a market order
        
        Args:
            coin: Asset symbol
            is_buy: True for buy, False for sell
            size: Order size
            
        Returns:
            Dict with order result
        """
        try:
            if not self.exchange:
                return {'status': 'error', 'message': 'No exchange connection'}
            
            # ✅ CORRECT FORMAT - Method 1 (All positional)
            result = self.exchange.order(
                coin,              # coin
                is_buy,           # is_buy
                size,             # sz
                0,                # px (0 for market order)
                {"market": {}}    # order_type
            )
            
            return {
                'status': 'success' if result.get('status') == 'ok' else 'error',
                'result': result,
                'coin': coin,
                'side': 'buy' if is_buy else 'sell',
                'size': size,
                'type': 'market'
            }
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def place_limit_order(self, coin: str, is_buy: bool, size: float, price: float, post_only: bool = False) -> Dict:
        """
        Place a limit order
        
        Args:
            coin: Asset symbol
            is_buy: True for buy, False for sell
            size: Order size
            price: Order price
            post_only: True for post-only (maker) orders
            
        Returns:
            Dict with order result
        """
        try:
            if not self.exchange:
                return {'status': 'error', 'message': 'No exchange connection'}
            
            # Choose order type
            if post_only:
                order_type = {"limit": {"tif": "Alo"}}  # Add Liquidity Only
            else:
                order_type = {"limit": {"tif": "Gtc"}}  # Good Till Cancelled
            
            # ✅ CORRECT FORMAT - Method 1 (All positional)
            result = self.exchange.order(
                coin,         # coin
                is_buy,       # is_buy
                size,         # sz
                price,        # px
                order_type    # order_type
            )
            
            return {
                'status': 'success' if result.get('status') == 'ok' else 'error',
                'result': result,
                'coin': coin,
                'side': 'buy' if is_buy else 'sell',
                'size': size,
                'price': price,
                'type': 'limit',
                'post_only': post_only
            }
            
        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def place_test_order(self, coin: str = "BTC") -> Dict:
        """Place test order with correct format"""
        try:
            # Get realistic price
            try:
                mids = self.info.all_mids()
                current_price = float(mids.get(coin, 30000))
                test_price = current_price * 0.9  # 10% below market
            except:
                test_price = 25000  # Fallback price
            
            # ✅ CORRECT FORMAT - Method 1
            result = self.exchange.order(
                coin,                           # coin name
                True,                          # is_buy
                0.001,                         # size
                test_price,                    # realistic price
                {"limit": {"tif": "Alo"}}      # order_type
            )
            
            logger.info(f"Test order result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error placing test order: {e}")
            return {"status": "error", "message": str(e)}

    async def place_grid_order(self, coin: str, is_buy: bool, size: float, 
                              price: float) -> Dict:
        """Place grid order with correct format"""
        try:
            # ✅ CORRECT FORMAT - Method 1
            result = self.exchange.order(
                coin,                           # coin name
                is_buy,                        # is_buy boolean
                size,                          # size  
                price,                         # price
                {"limit": {"tif": "Alo"}}      # ALO for maker rebates
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error placing grid order: {e}")
            return {"status": "error", "message": str(e)}

    async def cancel_order(self, coin: str, order_id: int) -> Dict:
        """
        Cancel a specific order
        
        Args:
            coin: Asset symbol
            order_id: Order ID to cancel
            
        Returns:
            Dict with cancellation result
        """
        try:
            if not self.exchange:
                return {'status': 'error', 'message': 'No exchange connection'}
            
            result = self.exchange.cancel(coin, order_id)
            
            return {
                'status': 'success' if result.get('status') == 'ok' else 'error',
                'result': result,
                'coin': coin,
                'order_id': order_id
            }
            
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def cancel_all_orders(self, coin: str) -> Dict:
        """
        Cancel all orders for a specific coin
        
        Args:
            coin: Asset symbol
            
        Returns:
            Dict with cancellation result
        """
        try:
            if not self.exchange:
                return {'status': 'error', 'message': 'No exchange connection'}
            
            result = self.exchange.cancel_by_coin(coin)
            
            return {
                'status': 'success' if result.get('status') == 'ok' else 'error',
                'result': result,
                'coin': coin
            }
            
        except Exception as e:
            logger.error(f"Error cancelling all orders: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def get_current_price(self, coin: str) -> Optional[float]:
        """
        Get current market price for a coin
        
        Args:
            coin: Asset symbol
            
        Returns:
            Current price or None if error
        """
        try:
            mids = self.info.all_mids()
            return float(mids.get(coin, 0)) if coin in mids else None
            
        except Exception as e:
            logger.error(f"Error getting current price for {coin}: {e}")
            return None
    
    async def get_order_book(self, coin: str) -> Optional[Dict]:
        """
        Get order book for a coin
        
        Args:
            coin: Asset symbol
            
        Returns:
            Order book data or None if error
        """
        try:
            return self.info.l2_snapshot(coin)
            
        except Exception as e:
            logger.error(f"Error getting order book for {coin}: {e}")
            return None
    
    def set_user_manager(self, user_manager):
        """Set user manager for multi-user support"""
        self.user_manager = user_manager
        logger.info("User manager set for SimpleTrader")
