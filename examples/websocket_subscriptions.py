"""
Example demonstrating comprehensive WebSocket subscriptions with Hyperliquid API
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

class WebSocketExample:
    """Comprehensive WebSocket usage example"""
    
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
        
        logger.info(f"WebSocket example initialized with address: {self.address}")
        
    async def start(self):
        """Start WebSocket connections and subscriptions"""
        logger.info("Starting WebSocket example")
        
        # Connect to WebSocket
        await self.ws_manager.connect()
        
        # Subscribe to various data streams
        logger.info("Subscribing to data streams...")
        
        # 1. All mids (prices)
        await self.ws_manager.subscribe_all_mids(self.handle_all_mids)
        logger.info("Subscribed to all mids")
        
        # 2. Candles for BTC - 1 minute intervals
        await self.ws_manager.subscribe_candles("BTC", "1m", self.handle_candles)
        logger.info("Subscribed to BTC candles")
        
        # 3. Order book for ETH
        await self.ws_manager.subscribe_l2_book("ETH", self.handle_orderbook)
        logger.info("Subscribed to ETH order book")
        
        # 4. Trades for SOL
        await self.ws_manager.subscribe_trades("SOL", self.handle_trades)
        logger.info("Subscribed to SOL trades")
        
        # 5. BBO (Best Bid/Offer) for BTC
        await self.ws_manager.subscribe_bbo("BTC", self.handle_bbo)
        logger.info("Subscribed to BTC BBO")
        
        # 6. Active Asset Context for ETH
        await self.ws_manager.subscribe_active_asset_ctx("ETH", self.handle_asset_ctx)
        logger.info("Subscribed to ETH asset context")
        
        # 7. Active Asset Data for ETH (user-specific)
        await self.ws_manager.subscribe_active_asset_data("ETH", self.handle_active_asset_data)
        logger.info("Subscribed to ETH active asset data")
        
        # 8. User-specific subscriptions
        await self.ws_manager.subscribe_user_events(self.handle_user_events)
        logger.info("Subscribed to user events")
        
        await self.ws_manager.subscribe_user_fills(self.handle_user_fills)
        logger.info("Subscribed to user fills")
        
        await self.ws_manager.subscribe_order_updates(self.handle_order_updates)
        logger.info("Subscribed to order updates")
        
        # 9. TWAP subscriptions
        await self.ws_manager.subscribe_user_twap_slice_fills(self.handle_twap_slice_fills)
        logger.info("Subscribed to TWAP slice fills")
        
        await self.ws_manager.subscribe_user_twap_history(self.handle_twap_history)
        logger.info("Subscribed to TWAP history")
        
        # Demo WebSocket post request
        logger.info("Sending WebSocket post request for L2 book...")
        response = await self.ws_manager.post_info_request({
            "type": "l2Book",
            "coin": "BTC",
            "nSigFigs": 5,
            "mantissa": None
        })
        logger.info(f"Received L2 book post response: {response.get('type', 'unknown')}")
        
        # Wait a bit before unsubscribing from one channel as a demo
        await asyncio.sleep(30)
        logger.info("Demonstrating unsubscribe from BBO...")
        await self.ws_manager.unsubscribe("bbo_BTC")
        logger.info("Unsubscribed from BTC BBO")
        
        # Keep connection open
        try:
            while True:
                logger.info("WebSocket connections active...")
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            # Clean up
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up WebSocket connections"""
        logger.info("Unsubscribing from all channels...")
        await self.ws_manager.unsubscribe_all()
        
        logger.info("Closing WebSocket connection...")
        await self.ws_manager.close()
    
    # Handler functions for different data types
    async def handle_all_mids(self, data: Dict[str, Any]):
        """Handle all mids updates"""
        if "data" in data and "mids" in data["data"]:
            mids = data["data"]["mids"]
            logger.info(f"Received {len(mids)} mid prices")
            
            # Print a few examples
            for coin, price in list(mids.items())[:3]:
                logger.info(f"{coin}: {price}")
    
    async def handle_candles(self, data: Dict[str, Any]):
        """Handle candle data"""
        if "data" in data:
            candles = data["data"]
            logger.info(f"Received {len(candles)} BTC candles")
            
            # Print latest candle
            if candles:
                latest = candles[-1]
                logger.info(f"Latest candle: O:{latest.get('o')} H:{latest.get('h')} L:{latest.get('l')} C:{latest.get('c')} V:{latest.get('v')}")
    
    async def handle_orderbook(self, data: Dict[str, Any]):
        """Handle order book data"""
        if "data" in data and "levels" in data["data"]:
            levels = data["data"]["levels"]
            
            if len(levels) >= 2:
                bids = levels[0]
                asks = levels[1]
                
                logger.info(f"Order book: {len(bids)} bids, {len(asks)} asks")
                
                # Print best bid and ask
                if bids and asks:
                    logger.info(f"Best bid: {bids[0][0]} ({bids[0][1]}), Best ask: {asks[0][0]} ({asks[0][1]})")
                    
                    # Calculate spread
                    bid = float(bids[0][0])
                    ask = float(asks[0][0])
                    spread = ask - bid
                    spread_bps = (spread / bid) * 10000
                    
                    logger.info(f"Spread: {spread:.4f} ({spread_bps:.2f} bps)")
    
    async def handle_trades(self, data: Dict[str, Any]):
        """Handle trade data"""
        if "data" in data:
            trades = data["data"]
            
            if trades:
                logger.info(f"Received {len(trades)} trades")
                
                # Print latest trade
                latest = trades[-1]
                logger.info(f"Latest trade: {latest.get('side')} {latest.get('size')} @ {latest.get('px')}")
    
    async def handle_user_events(self, data: Dict[str, Any]):
        """Handle user events"""
        if "data" in data:
            event = data["data"]
            logger.info(f"User event: {json.dumps(event)}")
    
    async def handle_user_fills(self, data: Dict[str, Any]):
        """Handle user fills"""
        if "data" in data:
            fills = data["data"]
            
            if "isSnapshot" in data and data["isSnapshot"]:
                logger.info(f"Received user fills snapshot: {len(fills)} fills")
            else:
                logger.info(f"New user fill: {json.dumps(fills)}")
    
    async def handle_order_updates(self, data: Dict[str, Any]):
        """Handle order updates"""
        if "data" in data:
            updates = data["data"]
            logger.info(f"Order update: {json.dumps(updates)}")
    
    async def handle_bbo(self, data: Dict[str, Any]):
        """Handle BBO (Best Bid/Offer) data"""
        if "data" in data and "bbo" in data["data"]:
            bbo = data["data"]["bbo"]
            coin = data["data"].get("coin", "")
            timestamp = data["data"].get("time", 0)
            
            best_bid = bbo[0]  # Could be None
            best_ask = bbo[1]  # Could be None
            
            logger.info(f"BBO update for {coin} at {datetime.fromtimestamp(timestamp/1000).strftime('%H:%M:%S')}:")
            
            if best_bid:
                bid_price = best_bid[0]
                bid_size = best_bid[1]
                logger.info(f"  Best bid: {bid_price} ({bid_size})")
            else:
                logger.info("  No bids available")
                
            if best_ask:
                ask_price = best_ask[0]
                ask_size = best_ask[1]
                logger.info(f"  Best ask: {ask_price} ({ask_size})")
            else:
                logger.info("  No asks available")
                
            # Calculate spread if both bid and ask are available
            if best_bid and best_ask:
                bid = float(best_bid[0])
                ask = float(best_ask[0])
                spread = ask - bid
                spread_bps = (spread / bid) * 10000
                logger.info(f"  Spread: {spread:.6f} ({spread_bps:.1f} bps)")
    
    async def handle_asset_ctx(self, data: Dict[str, Any]):
        """Handle active asset context data"""
        if "data" in data and "ctx" in data["data"]:
            coin = data["data"].get("coin", "")
            ctx = data["data"]["ctx"]
            
            logger.info(f"Asset context for {coin}:")
            logger.info(f"  Mark price: {ctx.get('markPx', 'N/A')}")
            logger.info(f"  Oracle price: {ctx.get('oraclePx', 'N/A')}")
            
            if "midPx" in ctx:
                logger.info(f"  Mid price: {ctx['midPx']}")
                
            if "funding" in ctx:
                funding_rate = ctx["funding"]
                funding_pct = funding_rate * 100
                logger.info(f"  Funding rate: {funding_pct:+.6f}%")
                
            if "openInterest" in ctx:
                logger.info(f"  Open interest: {ctx['openInterest']}")
                
            if "dayNtlVlm" in ctx:
                logger.info(f"  24h volume: ${ctx['dayNtlVlm']:,.0f}")
    
    async def handle_active_asset_data(self, data: Dict[str, Any]):
        """Handle active asset data"""
        if "data" in data:
            asset_data = data["data"]
            user = asset_data.get("user", "unknown")
            coin = asset_data.get("coin", "unknown")
            
            logger.info(f"Active asset data for {user} on {coin}:")
            
            if "leverage" in asset_data:
                leverage = asset_data["leverage"]
                logger.info(f"  Leverage: {leverage}")
            
            if "maxTradeSzs" in asset_data:
                max_sizes = asset_data["maxTradeSzs"]
                logger.info(f"  Max trade sizes: Buy={max_sizes[0]}, Sell={max_sizes[1]}")
            
            if "availableToTrade" in asset_data:
                available = asset_data["availableToTrade"]
                logger.info(f"  Available to trade: Buy={available[0]}, Sell={available[1]}")
    
    async def handle_twap_slice_fills(self, data: Dict[str, Any]):
        """Handle TWAP slice fills data"""
        if "data" in data:
            twap_slice_fills = data.get("data", {}).get("twapSliceFills", [])
            
            if "isSnapshot" in data and data["isSnapshot"]:
                logger.info(f"TWAP slice fills snapshot: {len(twap_slice_fills)} fills")
            else:
                logger.info("TWAP slice fill update:")
                
                for fill in twap_slice_fills:
                    if "fill" in fill and "twapId" in fill:
                        logger.info(f"  TWAP ID: {fill['twapId']}")
                        
                        fill_data = fill["fill"]
                        logger.info(f"  Coin: {fill_data.get('coin', 'N/A')}")
                        logger.info(f"  Size: {fill_data.get('sz', 'N/A')}")
                        logger.info(f"  Price: {fill_data.get('px', 'N/A')}")
                        logger.info(f"  Side: {fill_data.get('side', 'N/A')}")
    
    async def handle_twap_history(self, data: Dict[str, Any]):
        """Handle TWAP history data"""
        if "data" in data:
            history = data.get("data", {}).get("history", [])
            
            if "isSnapshot" in data and data["isSnapshot"]:
                logger.info(f"TWAP history snapshot: {len(history)} items")
                
                if history:
                    # Show details of the first few items in the snapshot
                    for item in history[:3]:
                        if "state" in item and "status" in item:
                            state = item["state"]
                            status = item["status"]
                            
                            logger.info(f"TWAP order:")
                            logger.info(f"  Coin: {state.get('coin', 'N/A')}")
                            logger.info(f"  User: {state.get('user', 'N/A')}")
                            logger.info(f"  Side: {state.get('side', 'N/A')}")
                            logger.info(f"  Size: {state.get('sz', 'N/A')}")
                            logger.info(f"  Executed: {state.get('executedSz', 'N/A')}/{state.get('sz', 'N/A')}")
                            logger.info(f"  Minutes: {state.get('minutes', 'N/A')}")
                            logger.info(f"  Status: {status.get('status', 'N/A')}")
                            logger.info(f"  Description: {status.get('description', 'N/A')}")
            else:
                logger.info("TWAP history update:")
                
                for item in history:
                    if "state" in item and "status" in item:
                        state = item["state"]
                        status = item["status"]
                        
                        logger.info(f"  Coin: {state.get('coin', 'N/A')}")
                        logger.info(f"  Status update: {status.get('status', 'N/A')}")
                        logger.info(f"  Description: {status.get('description', 'N/A')}")
                        logger.info(f"  Executed: {state.get('executedSz', 'N/A')}/{state.get('sz', 'N/A')}")


async def reserve_request_weight_example():
    """Example showing how to reserve request weight"""
    logger.info("Running reserve request weight example")
    
    # Set up connection
    address, info, exchange = example_utils.setup(
        base_url=constants.TESTNET_API_URL,
        skip_ws=True
    )
    
    logger.info(f"Connected with address: {address}")
    
    # Current timestamp
    timestamp = int(time.time() * 1000)
    
    # Construct request weight action
    action = {
        "type": "reserveRequestWeight",
        "weight": 10  # Reserve 10 units of weight
    }
    
    # Generate nonce
    nonce = timestamp
    
    # Execute the weight reservation
    logger.info("Reserving request weight (10 units)...")
    response = exchange._post_exchange(action, nonce)
    
    logger.info(f"Reservation result: {json.dumps(response)}")
    
    return response


async def websocket_post_examples():
    """Examples showing WebSocket post requests"""
    logger.info("Running WebSocket POST request examples")
    
    # Set up connection
    address, info, exchange = example_utils.setup(
        base_url=constants.TESTNET_API_URL,
        skip_ws=True
    )
    
    # Import WebSocket manager
    from trading_engine.websocket_manager import HyperliquidWebSocketManager
    ws_manager = HyperliquidWebSocketManager(
        base_url=constants.TESTNET_API_URL,
        address=address,
        info=info,
        exchange=exchange
    )
    
    # Connect to WebSocket
    await ws_manager.connect()
    
    logger.info(f"Connected with address: {address}")
    
    # Example 1: Info request for L2 book
    logger.info("Sending POST info request for L2 book...")
    l2_response = await ws_manager.post_info_request({
        "type": "l2Book",
        "coin": "ETH",
        "nSigFigs": 5,
        "mantissa": None
    })
    
    if "payload" in l2_response and "data" in l2_response["payload"]:
        data = l2_response["payload"]["data"]
        logger.info(f"L2 book response received: {data.get('coin')} at {data.get('time')}")
        
        if "levels" in data and len(data["levels"]) >= 2:
            bids = data["levels"][0]
            asks = data["levels"][1]
            logger.info(f"Book depth: {len(bids)} bids, {len(asks)} asks")
    
    # Example 2: Info request for user state
    logger.info("Sending POST info request for user state...")
    user_state_response = await ws_manager.post_info_request({
        "type": "userState",
        "user": address
    })
    
    if "payload" in user_state_response and "data" in user_state_response["payload"]:
        data = user_state_response["payload"]["data"]
        account_value = data.get("marginSummary", {}).get("accountValue", "0")
        logger.info(f"User state response received: Account value = {account_value}")
    
    # Close the connection
    await ws_manager.close()
    
    return True


async def main():
    """Run the WebSocket examples"""
    logger.info("Starting Hyperliquid WebSocket examples")
    
    # First demonstrate request weight reservation
    await reserve_request_weight_example()
    
    # Demonstrate WebSocket POST requests
    logger.info("\n=== WebSocket POST Requests ===")
    await websocket_post_examples()
    
    # Then demonstrate WebSocket subscriptions
    logger.info("\n=== WebSocket Subscriptions ===")
    ws_example = WebSocketExample()
    await ws_example.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Example stopped by user")
    except Exception as e:
        logger.error(f"Error in example: {e}")
