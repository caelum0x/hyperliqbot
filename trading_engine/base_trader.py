"""
Base trader class to avoid circular imports between modules
"""

from typing import Dict, List, Optional, Any
import logging
import time
import asyncio

class BaseTrader:
    """
    Base trader class that ProfitOptimizedTrader will inherit from
    Provides common functionality without circular imports
    """
    
    def __init__(self, address=None, info=None, exchange=None):
        self.address = address
        self.info = info
        self.exchange = exchange
        self.logger = logging.getLogger(__name__)
    
    async def get_all_mids(self) -> Dict[str, float]:
        """Get mid prices for all assets"""
        if not self.info:
            return {}
        
        try:
            mids_dict = self.info.all_mids()
            # Convert string values to float
            return {k: float(v) for k, v in mids_dict.items()}
        except Exception as e:
            self.logger.error(f"Error getting all mids: {e}")
            return {}
    
    async def get_user_state(self) -> Dict:
        """Get user state including balances and positions"""
        if not self.info or not self.address:
            return {}
        
        try:
            return self.info.user_state(self.address)
        except Exception as e:
            self.logger.error(f"Error getting user state: {e}")
            return {}
    
    async def place_order(self, coin: str, is_buy: bool, size: float, price: float, 
                        reduce_only: bool = False, post_only: bool = False) -> Dict:
        """
        Base method to place orders
        """
        if not self.exchange or not self.info:
            return {"status": "error", "message": "Exchange not initialized"}
            
        try:
            # Implementation will be in derived classes
            return {"status": "not_implemented"}
        except Exception as e:
            self.logger.error(f"Error placing order: {e}")
            return {"status": "error", "message": str(e)}
    
    # Additional common methods can be added here

class ProfitOptimizedTrader(BaseTrader):
    """
    Advanced trader with profit optimization strategies
    Inherits from BaseTrader to avoid circular imports
    """
    
    def __init__(self, address=None, info=None, exchange=None):
        super().__init__(address, info, exchange)
        self.profit_history = []
        self.performance_stats = {}
    
    async def place_order(self, coin: str, is_buy: bool, size: float, price: float, 
                        reduce_only: bool = False, post_only: bool = False) -> Dict:
        """
        Place order with profit optimization
        """
        if not self.exchange or not self.info:
            self.logger.error("Exchange or Info client not initialized. Cannot place order.")
            return {"status": "error", "message": "Exchange not initialized"}
            
        try:
            # Get asset ID according to Hyperliquid standards
            meta = self.info.meta() # This should be an API call if info is an Info client
            # If self.info.meta() is not async, and self.info is the SDK's Info client, it's a direct call.
            # If it needs to be async, it should be: meta = await self.info.meta() (depends on SDK version/wrapper)
            # Assuming self.info.meta() is synchronous as per typical SDK usage.

            asset_id = None
            target_name = coin.upper() 
            
            universe = meta.get("universe", [])
            for i, asset_data in enumerate(universe):
                if asset_data.get("name", "").upper() == target_name:
                    asset_id = i 
                    break 
            
            if asset_id is None:
                self.logger.error(f"Coin '{coin}' (target: '{target_name}') not found in metadata universe.")
                return {"status": "error", "message": f"Coin {coin} not found in metadata"}
            
            # Format order following Hyperliquid notation standards
            order_type_details = {"limit": {"tif": "Alo" if post_only else "Gtc"}}
            
            order = {
                "a": asset_id,      # asset index
                "b": is_buy,        # isBuy
                "p": str(price),    # price
                "s": str(size),     # size
                "r": reduce_only,   # reduceOnly
                "t": order_type_details
            }
            
            self.logger.debug(f"Placing order: {order}")
            # Place the order with proper format
            order_result = self.exchange.order(
                orders=[order], 
                grouping="na"   # No atomicity for a single order
            )
            self.logger.debug(f"Order result: {order_result}")
            
            if order_result.get("status") == "ok":
                response_data = order_result.get("response", {}).get("data", {})
                statuses = response_data.get("statuses", [])
                if statuses and isinstance(statuses[0], dict):
                    if "resting" in statuses[0]:
                        order_id = statuses[0]["resting"]["oid"]
                        self.logger.info(f"Order placed successfully for {coin}. Order ID: {order_id}")
                        return {"status": "ok", "type": "resting", "order_id": order_id, "details": statuses[0]}
                    elif "filled" in statuses[0]:
                        fill_details = statuses[0]["filled"]
                        self.logger.info(f"Order filled immediately for {coin}. Avg Px: {fill_details.get('avgPx')}, Total Sz: {fill_details.get('totalSz')}")
                        return {"status": "ok", "type": "filled", "details": statuses[0]}
                    elif "error" in statuses[0]:
                        error_msg = statuses[0]["error"]
                        self.logger.error(f"Order placement failed for {coin} with error: {error_msg}")
                        return {"status": "error", "message": error_msg, "details": statuses[0]}
                    else:
                        self.logger.warning(f"Order status unclear for {coin}: {statuses[0]}")
                        return {"status": "ok_unknown_sub_status", "details": statuses[0]}
                else: # Should not happen if status is "ok"
                    self.logger.error(f"Order status 'ok' but no valid status in response for {coin}: {order_result}")
                    return {"status": "error", "message": "Order status 'ok' but no valid status in response", "details": order_result}
            else:
                error_message = order_result.get("response", {}).get("error", "Unknown error from exchange")
                self.logger.error(f"Failed to place order for {coin}: {error_message}. Full response: {order_result}")
                return {"status": "error", "message": error_message, "details": order_result}

        except Exception as e:
            self.logger.error(f"Exception placing order for {coin}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
    
    async def cancel_order(self, coin: str, oid: int) -> Dict:
        """Cancel order with error handling"""
        try:
            result = self.exchange.cancel(coin, oid)
            return result
        except Exception as e:
            self.logger.error(f"Error cancelling order: {e}")
            return {"status": "error", "message": str(e)}
    
    async def update_leverage(self, coin: str, leverage: int, is_cross: bool = True) -> Dict:
        """Update leverage for a position"""
        try:
            result = self.exchange.update_leverage(leverage, coin, is_cross)
            return result
        except Exception as e:
            self.logger.error(f"Error updating leverage: {e}")
            return {"status": "error", "message": str(e)}
    
    async def optimize_trading_params(self, coin: str) -> Dict:
        """Optimize trading parameters based on historical performance"""
        try:
            # Calculate optimal parameters based on profit history
            # This would implement sophisticated algorithms in a real system
            return {
                "optimal_size": 0.1,
                "optimal_leverage": 5,
                "optimal_entry_timing": "immediate"
            }
        except Exception as e:
            self.logger.error(f"Error optimizing trading parameters: {e}")
            return {}
