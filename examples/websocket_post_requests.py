"""
Example demonstrating WebSocket POST requests with Hyperliquid API
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any
from datetime import datetime

import example_utils
from hyperliquid.utils import constants

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebSocketPostExample:
    """WebSocket POST requests example"""
    
    def __init__(self, base_url=None):
        # Set up connection using standard pattern
        self.address, self.info, self.exchange = example_utils.setup(
            base_url=base_url or constants.TESTNET_API_URL,
            skip_ws=True
        )
        
        # Import WebSocket manager
        from trading_engine.websocket_manager import HyperliquidWebSocketManager
        self.ws_manager = HyperliquidWebSocketManager(
            base_url=base_url or constants.TESTNET_API_URL,
            address=self.address,
            info=self.info,
            exchange=self.exchange
        )
        
        logger.info(f"WebSocket POST example initialized with address: {self.address}")
        
    async def run_examples(self):
        """Run WebSocket POST request examples"""
        logger.info("Starting WebSocket POST examples")
        
        # Connect to WebSocket
        await self.ws_manager.connect()
        logger.info("Connected to WebSocket")
        
        # Example 1: L2 Book Info Request
        logger.info("\n=== Example 1: L2 Book Info Request ===")
        l2_response = await self.ws_manager.post_info_request({
            "type": "l2Book",
            "coin": "BTC",
            "nSigFigs": 5,
            "mantissa": None
        })
        
        self._process_l2_response(l2_response)
        
        # Example 2: Candles Info Request
        logger.info("\n=== Example 2: Candles Info Request ===")
        candles_response = await self.ws_manager.post_info_request({
            "type": "candles",
            "coin": "ETH",
            "interval": "15m",
            "lookback": 10
        })
        
        self._process_candles_response(candles_response)
        
        # Example 3: User State Info Request
        logger.info("\n=== Example 3: User State Info Request ===")
        user_state_response = await self.ws_manager.post_info_request({
            "type": "userState",
            "user": self.address
        })
        
        self._process_user_state_response(user_state_response)
        
        # Example 4: User Fills Info Request
        logger.info("\n=== Example 4: User Fills Info Request ===")
        fills_response = await self.ws_manager.post_info_request({
            "type": "userFills",
            "user": self.address
        })
        
        self._process_fills_response(fills_response)
        
        # Example 5: Funding Rate Info Request
        logger.info("\n=== Example 5: Funding Rate Info Request ===")
        funding_response = await self.ws_manager.post_info_request({
            "type": "fundingHistory",
            "coin": "BTC"
        })
        
        self._process_funding_response(funding_response)
        
        # Example 6: Using POST for action request (requires signing)
        logger.info("\n=== Example 6: Action Request (Cancel All) ===")
        # Note: This is just a demonstration - actual execution is commented out
        logger.info("Demonstrating action request format (not executing)")
        
        # Clean up
        await self.ws_manager.close()
        logger.info("WebSocket connection closed")
    
    def _process_l2_response(self, response):
        """Process L2 book response"""
        try:
            if "payload" in response and "data" in response["payload"]:
                data = response["payload"]["data"]
                logger.info(f"L2 book response for {data.get('coin')} at timestamp {data.get('time')}")
                
                if "levels" in data and len(data["levels"]) >= 2:
                    bids = data["levels"][0]
                    asks = data["levels"][1]
                    logger.info(f"Book depth: {len(bids)} bids, {len(asks)} asks")
                    
                    # Display top 3 levels on each side
                    logger.info("Top 3 bids:")
                    for i, bid in enumerate(bids[:3]):
                        logger.info(f"  {i+1}. Price: {bid.get('px')}, Size: {bid.get('sz')}, Orders: {bid.get('n')}")
                        
                    logger.info("Top 3 asks:")
                    for i, ask in enumerate(asks[:3]):
                        logger.info(f"  {i+1}. Price: {ask.get('px')}, Size: {ask.get('sz')}, Orders: {ask.get('n')}")
            else:
                logger.warning(f"Unexpected L2 book response format: {response}")
        except Exception as e:
            logger.error(f"Error processing L2 book response: {e}")
    
    def _process_candles_response(self, response):
        """Process candles response"""
        try:
            if "payload" in response and "data" in response["payload"]:
                candles = response["payload"]["data"]
                logger.info(f"Received {len(candles)} candles")
                
                if candles:
                    # Display the most recent candles
                    logger.info("Most recent candles:")
                    for i, candle in enumerate(candles[-3:]):
                        open_time = datetime.fromtimestamp(candle.get('t') / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        logger.info(f"  {i+1}. Time: {open_time}, Open: {candle.get('o')}, High: {candle.get('h')}, "
                                  f"Low: {candle.get('l')}, Close: {candle.get('c')}, Volume: {candle.get('v')}")
            else:
                logger.warning(f"Unexpected candles response format: {response}")
        except Exception as e:
            logger.error(f"Error processing candles response: {e}")
    
    def _process_user_state_response(self, response):
        """Process user state response"""
        try:
            if "payload" in response and "data" in response["payload"]:
                user_state = response["payload"]["data"]
                
                # Extract key account information
                margin_summary = user_state.get("marginSummary", {})
                account_value = margin_summary.get("accountValue", "0")
                total_margin_used = margin_summary.get("totalMarginUsed", "0")
                
                logger.info(f"User state summary:")
                logger.info(f"  Account value: {account_value}")
                logger.info(f"  Margin used: {total_margin_used}")
                
                # Display positions if any
                positions = user_state.get("assetPositions", [])
                if positions:
                    logger.info(f"  Number of positions: {len(positions)}")
                    for i, position in enumerate(positions[:3]):  # Show up to 3 positions
                        pos = position.get("position", {})
                        coin = pos.get("coin", "unknown")
                        size = pos.get("szi", "0")
                        entry_price = pos.get("entryPx", "0")
                        logger.info(f"  Position {i+1}: {coin} - Size: {size}, Entry price: {entry_price}")
                else:
                    logger.info("  No active positions")
            else:
                logger.warning(f"Unexpected user state response format: {response}")
        except Exception as e:
            logger.error(f"Error processing user state response: {e}")
    
    def _process_fills_response(self, response):
        """Process user fills response"""
        try:
            if "payload" in response and "data" in response["payload"]:
                fills = response["payload"]["data"]
                logger.info(f"Received {len(fills)} user fills")
                
                if fills:
                    # Display the most recent fills
                    logger.info("Most recent fills:")
                    for i, fill in enumerate(fills[-3:]):
                        fill_time = datetime.fromtimestamp(fill.get('time') / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        logger.info(f"  {i+1}. Time: {fill_time}, Coin: {fill.get('coin')}, "
                                  f"Side: {fill.get('dir')}, Size: {fill.get('sz')}, "
                                  f"Price: {fill.get('px')}, Fee: {fill.get('fee')}")
                else:
                    logger.info("  No fills found")
            else:
                logger.warning(f"Unexpected fills response format: {response}")
        except Exception as e:
            logger.error(f"Error processing fills response: {e}")
    
    def _process_funding_response(self, response):
        """Process funding rate response"""
        try:
            if "payload" in response and "data" in response["payload"]:
                funding_history = response["payload"]["data"]
                logger.info(f"Received {len(funding_history)} funding rate entries")
                
                if funding_history:
                    # Display the most recent funding rates
                    logger.info("Most recent funding rates:")
                    for i, entry in enumerate(funding_history[-3:]):
                        funding_time = datetime.fromtimestamp(entry.get('time') / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        funding_rate = float(entry.get('funding', 0)) * 100  # Convert to percentage
                        logger.info(f"  {i+1}. Time: {funding_time}, Rate: {funding_rate:+.6f}%")
                else:
                    logger.info("  No funding history found")
            else:
                logger.warning(f"Unexpected funding response format: {response}")
        except Exception as e:
            logger.error(f"Error processing funding response: {e}")


async def main():
    """Run the WebSocket POST example"""
    logger.info("Starting Hyperliquid WebSocket POST examples")
    
    example = WebSocketPostExample()
    await example.run_examples()
    
    logger.info("WebSocket POST examples completed")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Example stopped by user")
    except Exception as e:
        logger.error(f"Error in example: {e}")
