import asyncio
from asyncio.log import logger
import time
from typing import Dict, Optional, TYPE_CHECKING
import os
import sys
import logging

if TYPE_CHECKING:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.types import *

# Import the agent factory for user wallet management
from trading_engine.agent_factory import AgentFactory

# Import strategy manager
from strategies.strategy_manager import PerUserStrategyManager

# Import examples for setup
examples_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'examples')
if examples_dir not in sys.path:
    sys.path.append(examples_dir)

# Add MultiUserTradingEngine implementation
class MultiUserTradingEngine:
    """
    Multi-user trading engine that maintains isolated user environments
    Each user has their own exchange connection and strategies
    """
    def __init__(self, master_private_key: str, base_url: str = None):
        """
        Initialize the multi-user trading engine
        
        Args:
            master_private_key: Private key for the master wallet used to create agent wallets
            base_url: API URL for Hyperliquid (defaults to constants.MAINNET_API_URL)
        """
        self.base_url = base_url or constants.MAINNET_API_URL
        self.agent_factory = AgentFactory(master_private_key, base_url=self.base_url)
        self.user_strategies = {}  # {user_id: {strategy_name: strategy_instance}}
        self.user_exchanges = {}   # {user_id: Exchange}
        self.user_info = {}        # {user_id: Info}
        self.user_tasks = {}       # {user_id: {strategy_name: asyncio.Task}}
        self.strategy_manager = PerUserStrategyManager()
        
        # Global Info client for market data (shared across users)
        self.global_info = Info(self.base_url)
        
        # Cache for market data
        self.mids_cache = {}
        self.mids_cache_time = 0
        self.mids_cache_ttl = 5  # 5 seconds TTL
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("MultiUserTradingEngine initialized")
        
        # Set the singleton instance
        MultiUserTradingEngine._instance = self

    @classmethod
    def get_instance(cls):
        if not hasattr(cls, '_instance') or cls._instance is None:
            return None
        return cls._instance

    async def initialize(self) -> bool:
        """Initialize the trading engine and its components"""
        try:
            # Initialize agent factory
            await self.agent_factory.initialize()
            
            # Test connection to API
            if await self.validate_connection():
                self.logger.info("Connection to Hyperliquid API validated")
                return True
            else:
                self.logger.error("Failed to validate connection to Hyperliquid API")
                return False
        except Exception as e:
            self.logger.error(f"Error initializing MultiUserTradingEngine: {e}")
            return False

    async def get_all_mids(self) -> Dict[str, float]:
        """
        Get market data (shared across all users)
        Uses caching to reduce API calls
        
        Returns:
            Dict mapping coin symbols to their current prices
        """
        current_time = time.time()
        
        # Return cached values if still valid
        if self.mids_cache and current_time - self.mids_cache_time < self.mids_cache_ttl:
            return self.mids_cache
        
        try:
            # Use global info client for market data
            mids_dict = self.global_info.all_mids()
            
            # Convert string values to float
            mids = {k: float(v) for k, v in mids_dict.items()}
            
            # Update cache
            self.mids_cache = mids
            self.mids_cache_time = current_time
            
            return mids
        except Exception as e:
            self.logger.error(f"Error getting all mids: {e}")
            # Return last cached data if available, otherwise empty dict
            return self.mids_cache if self.mids_cache else {}

    async def create_user_trader(self, user_id: int, main_address: str) -> Dict:
        """
        Create a dedicated trader for a user
        
        Args:
            user_id: User ID
            main_address: User's main Hyperliquid address
            
        Returns:
            Dict with status and details
        """
        try:
            # Create agent wallet via the agent factory
            create_result = await self.agent_factory.create_user_agent(user_id, main_address)
            
            if create_result["status"] != "success" and create_result["status"] != "exists":
                return create_result
                
            # Get exchange for user
            exchange = await self.agent_factory.get_user_exchange(user_id)
            if not exchange:
                return {
                    "status": "error",
                    "message": "Failed to initialize user exchange"
                }
                
            # Store exchange reference
            self.user_exchanges[user_id] = exchange
            
            # Create dedicated info client (could share global, but this allows customization)
            self.user_info[user_id] = Info(self.base_url)
            
            return {
                "status": "success",
                "message": "User trader created successfully",
                "agent_address": create_result.get("agent_address")
            }
            
        except Exception as e:
            self.logger.error(f"Error creating user trader: {e}")
            return {
                "status": "error",
                "message": f"Failed to create user trader: {str(e)}"
            }
            
    async def start_user_strategy(self, user_id: int, strategy_name: str, config: Dict) -> Dict:
        """
        Start a trading strategy for a specific user
        
        Args:
            user_id: User ID
            strategy_name: Name of the strategy to start
            config: Strategy configuration parameters
            
        Returns:
            Dict with status and details
        """
        try:
            # Check if user has exchange
            user_exchange = self.user_exchanges.get(user_id) or await self.agent_factory.get_user_exchange(user_id)
            
            if not user_exchange:
                return {
                    "status": "error",
                    "message": "User not authenticated or funded"
                }
            
            # Store exchange if not already stored
            if user_id not in self.user_exchanges:
                self.user_exchanges[user_id] = user_exchange
            
            # Verify user is funded
            funding_status = await self.agent_factory.fund_detection(user_id)
            if not funding_status.get("funded", False):
                return {
                    "status": "error",
                    "message": "User wallet not funded"
                }
            
            # Initialize user strategies dict if not exists
            if user_id not in self.user_strategies:
                self.user_strategies[user_id] = {}
                
            # Initialize user tasks dict if not exists
            if user_id not in self.user_tasks:
                self.user_tasks[user_id] = {}
            
            # Cancel existing strategy if running
            if strategy_name in self.user_strategies[user_id]:
                await self.stop_user_strategy(user_id, strategy_name)
            
            # Create strategy instance
            strategy_config = config.copy()
            strategy_config["user_id"] = user_id
            
            # Store strategy in user strategies mapping
            self.user_strategies[user_id][strategy_name] = {
                "name": strategy_name,
                "config": strategy_config,
                "started_at": time.time(),
                "status": "starting"
            }
            
            # Start background task based on strategy type
            if strategy_name == "grid":
                task = asyncio.create_task(
                    self.strategy_manager.execute_grid_trading(
                        user_id, user_exchange, strategy_config
                    )
                )
                self.user_tasks[user_id][strategy_name] = task
            elif strategy_name == "maker_rebate":
                task = asyncio.create_task(
                    self.strategy_manager.execute_profit_bot(
                        user_id, user_exchange, strategy_config
                    )
                )
                self.user_tasks[user_id][strategy_name] = task
            elif strategy_name == "hyperevm":
                task = asyncio.create_task(
                    self.strategy_manager.execute_hyperevm_strategy(
                        user_id, user_exchange, strategy_config
                    )
                )
                self.user_tasks[user_id][strategy_name] = task
            else:
                return {
                    "status": "error",
                    "message": f"Unknown strategy: {strategy_name}"
                }
            
            # Update strategy status
            self.user_strategies[user_id][strategy_name]["status"] = "running"
            
            self.logger.info(f"Started {strategy_name} strategy for user {user_id}")
            
            return {
                "status": "success",
                "message": f"Strategy {strategy_name} started successfully",
                "strategy_name": strategy_name,
                "user_id": user_id
            }
            
        except Exception as e:
            self.logger.error(f"Error starting strategy {strategy_name} for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to start strategy: {str(e)}"
            }
    
    async def stop_user_strategy(self, user_id: int, strategy_name: str) -> Dict:
        """
        Stop a specific strategy for a user
        
        Args:
            user_id: User ID
            strategy_name: Name of the strategy to stop
            
        Returns:
            Dict with status and details
        """
        try:
            # Check if user has this strategy running
            if (user_id not in self.user_strategies or 
                strategy_name not in self.user_strategies[user_id]):
                return {
                    "status": "error",
                    "message": f"Strategy {strategy_name} not running for user {user_id}"
                }
            
            # Cancel the task
            if user_id in self.user_tasks and strategy_name in self.user_tasks[user_id]:
                task = self.user_tasks[user_id][strategy_name]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass  # Expected when cancelling
                    
                # Remove task reference
                del self.user_tasks[user_id][strategy_name]
            
            # Update strategy status
            self.user_strategies[user_id][strategy_name]["status"] = "stopped"
            self.user_strategies[user_id][strategy_name]["stopped_at"] = time.time()
            
            # Get user exchange to cancel orders
            user_exchange = self.user_exchanges.get(user_id)
            if user_exchange:
                # Cancel any open orders for this strategy
                # Get top coins
                top_coins = ["BTC", "ETH", "SOL"]
                
                for coin in top_coins:
                    try:
                        await user_exchange.cancel_by_coin(coin)
                    except Exception as e:
                        self.logger.error(f"Error cancelling orders for {coin}: {e}")
            
            self.logger.info(f"Stopped {strategy_name} strategy for user {user_id}")
            
            return {
                "status": "success",
                "message": f"Strategy {strategy_name} stopped successfully"
            }
            
        except Exception as e:
            self.logger.error(f"Error stopping strategy {strategy_name} for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to stop strategy: {str(e)}"
            }
    
    async def get_user_strategies(self, user_id: int) -> Dict:
        """
        Get all strategies for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with status and list of strategies
        """
        try:
            if user_id not in self.user_strategies:
                return {
                    "status": "success",
                    "strategies": []
                }
            
            strategies = []
            for name, strategy in self.user_strategies[user_id].items():
                strategies.append({
                    "name": name,
                    "status": strategy.get("status", "unknown"),
                    "started_at": strategy.get("started_at"),
                    "config": {k: v for k, v in strategy.get("config", {}).items() 
                              if k != "user_id"}  # Remove user_id from config
                })
            
            return {
                "status": "success",
                "strategies": strategies
            }
            
        except Exception as e:
            self.logger.error(f"Error getting strategies for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to get strategies: {str(e)}",
                "strategies": []
            }
    
    async def place_order(self, user_id: int, coin: str, is_buy: bool, size: float, 
                        price: float, order_type: Dict = None) -> Dict:
        """
        Place an order for a specific user
        
        Args:
            user_id: User ID
            coin: Trading pair symbol
            is_buy: True for buy, False for sell
            size: Order size
            price: Order price
            order_type: Order type specification
            
        Returns:
            Dict with order result
        """
        try:
            # Get user's exchange
            user_exchange = self.user_exchanges.get(user_id)
            if not user_exchange:
                return {
                    "status": "error",
                    "message": "User not authenticated or exchange not initialized"
                }
            
            # Use default limit order type if not specified
            if not order_type:
                order_type = {"limit": {"tif": "Gtc"}}
            
            # ✅ CORRECT FORMAT - Method 1 (All positional)
            result = user_exchange.order(
                coin,         # coin
                is_buy,       # is_buy
                size,         # sz
                price,        # px
                order_type    # order_type
            )
            
            # Log the order
            side = "buy" if is_buy else "sell"
            self.logger.info(f"User {user_id} placed {side} order for {size} {coin} at ${price}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error placing order for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to place order: {str(e)}"
            }

    async def place_test_order(self, user_exchange: Exchange, coin: str = "BTC") -> Dict:
        """Place test order with correct format"""
        try:
            # Get realistic price
            mids = await self.get_all_mids()
            current_price = float(mids.get(coin, 30000))
            test_price = current_price * 0.95  # 5% below market
            
            # ✅ CORRECT FORMAT - Method 1
            result = user_exchange.order(
                coin,                           # coin name
                True,                          # is_buy
                0.001,                         # size
                test_price,                    # realistic price
                {"limit": {"tif": "Alo"}}      # order_type
            )
            
            self.logger.info(f"Test order result: {result}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error placing test order: {e}")
            return {"status": "error", "message": str(e)}

    async def place_maker_order(self, user_exchange: Exchange, coin: str, is_buy: bool, 
                               size: float, price: float) -> Dict:
        """Place maker order with correct format"""
        try:
            # ✅ CORRECT FORMAT - Method 1
            result = user_exchange.order(
                coin,                           # coin name
                is_buy,                        # is_buy boolean  
                size,                          # size
                price,                         # price
                {"limit": {"tif": "Alo"}}      # order_type (maker)
            )
            
            self.logger.info(f"Maker order placed: {coin} {size}@{price}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error placing maker order: {e}")
            return {"status": "error", "message": str(e)}

    async def get_user_positions(self, user_id: int) -> Dict:
        """
        Get positions for a specific user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with positions information
        """
        try:
            # Get agent address from agent factory
            agent_details = await self.agent_factory.get_agent_details(user_id)
            if not agent_details or not agent_details.get("address"):
                return {
                    "status": "error",
                    "message": "User not authenticated or agent wallet not found",
                    "positions": []
                }
            
            agent_address = agent_details["address"]
            
            # Use global info client to get positions
            user_state = self.global_info.user_state(agent_address)
            
            # Extract positions
            positions = []
            for pos_data in user_state.get("assetPositions", []):
                pos = pos_data.get("position", {})
                if pos:
                    positions.append({
                        "coin": pos.get("coin", "Unknown"),
                        "size": float(pos.get("szi", 0)),
                        "entry_price": float(pos.get("entryPx", 0)),
                        "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                        "liquidation_price": float(pos.get("liquidationPx", 0)) if "liquidationPx" in pos else None
                    })
            
            return {
                "status": "success",
                "positions": positions,
                "account_value": float(user_state.get("marginSummary", {}).get("accountValue", 0))
            }
            
        except Exception as e:
            self.logger.error(f"Error getting positions for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to get positions: {str(e)}",
                "positions": []
            }
    
    async def validate_connection(self) -> bool:
        """
        Validate connection to Hyperliquid API
        
        Returns:
            bool: True if connection is valid
        """
        try:
            # Simple check - get all mids
            mids = await self.get_all_mids()
            return bool(mids)
        except Exception as e:
            self.logger.error(f"Error validating connection: {e}")
            return False
    
    async def stop_all_user_strategies(self, user_id: int) -> Dict:
        """
        Stop all strategies for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with status and details
        """
        try:
            if user_id not in self.user_strategies:
                return {
                    "status": "info",
                    "message": "No active strategies for user"
                }
            
            strategies_stopped = []
            
            # Get list of strategy names
            strategy_names = list(self.user_strategies[user_id].keys())
            
            # Stop each strategy
            for strategy_name in strategy_names:
                result = await self.stop_user_strategy(user_id, strategy_name)
                if result["status"] == "success":
                    strategies_stopped.append(strategy_name)
            
            return {
                "status": "success",
                "message": f"Stopped {len(strategies_stopped)} strategies",
                "strategies_stopped": strategies_stopped
            }
            
        except Exception as e:
            self.logger.error(f"Error stopping all strategies for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to stop all strategies: {str(e)}"
            }
    
    async def cancel_all_orders(self, user_id: int) -> Dict:
        """
        Cancel all orders for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with status and details
        """
        try:
            # Get user's exchange
            user_exchange = self.user_exchanges.get(user_id)
            if not user_exchange:
                return {
                    "status": "error",
                    "message": "User not authenticated or exchange not initialized"
                }
            
            # Get agent details to find address
            agent_details = await self.agent_factory.get_agent_details(user_id)
            if not agent_details or not agent_details.get("address"):
                return {
                    "status": "error",
                    "message": "Agent wallet details not found"
                }
            
            agent_address = agent_details["address"]
            
            # Get open orders from API
            open_orders = self.global_info.open_orders(agent_address)
            
            # Extract unique coins
            coins = set()
            for order in open_orders:
                if order.get("coin"):
                    coins.add(order.get("coin"))
            
            # Cancel orders for each coin
            orders_cancelled = 0
            for coin in coins:
                try:
                    result = user_exchange.cancel_by_coin(coin)
                    if result.get("status") == "ok":
                        # Count cancelled orders from response
                        cancel_data = result.get("response", {}).get("data", {})
                        statuses = cancel_data.get("statuses", [])
                        orders_cancelled += len([s for s in statuses if s.get("status") == "cancelled"])
                except Exception as e:
                    self.logger.error(f"Error cancelling orders for coin {coin}: {e}")
            
            return {
                "status": "success",
                "message": f"Cancelled {orders_cancelled} orders",
                "orders_cancelled": orders_cancelled
            }
            
        except Exception as e:
            self.logger.error(f"Error cancelling orders for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Failed to cancel orders: {str(e)}"
            }
    
    async def get_user_exchange(self, user_id: int) -> Optional[Exchange]:
        """
        Get Exchange instance for a user's agent wallet
        
        Args:
            user_id: User ID
            
        Returns:
            Exchange: Exchange instance for user's agent wallet
        """
        try:
            # Get agent wallet details from agent factory
            agent_details = await self.agent_factory.get_agent_details(user_id)
            
            if not agent_details:
                self.logger.error(f"No agent wallet found for user {user_id}")
                return None
            
            # Create Exchange instance using agent factory
            exchange = await self.agent_factory.get_user_exchange(user_id)
            
            # Store in cache for later use
            self.user_exchanges[user_id] = exchange
            
            return exchange
            
        except Exception as e:
            self.logger.error(f"Error getting user exchange for user {user_id}: {e}")
            return None
    
    async def fund_detection(self, user_id: int) -> Dict:
        """
        Check if a user's agent wallet is funded
        FIXED: Check main address balance, not agent address
        """
        try:
            # Get agent details first
            agent_details = await self.agent_factory.get_agent_details(user_id)
            if not agent_details or not agent_details.get("main_address"):
                return {
                    "status": "error",
                    "message": "Agent wallet not found or missing main address",
                    "funded": False
                }
                
            # ✅ FIX: Use main address for balance check (where funds actually are)
            main_address = agent_details.get("main_address")
            agent_address = agent_details.get("address")
            
            logger.info(f"Fund detection for user {user_id}: checking main_address={main_address}")
            
            # Query account state using MAIN address (where funds are stored)
            user_state = self.global_info.user_state(main_address)
            
            # Get account value from margin summary
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            logger.info(f"User {user_id} fund detection: main_address={main_address}, balance=${account_value}")
            
            # Consider funded if account value > minimum threshold
            min_funding = 5.0  # $5 minimum funding (lowered threshold)
            funded = account_value >= min_funding
            
            return {
                "status": "success",
                "message": f"Main account {'is' if funded else 'is not'} funded (${account_value:.2f})",
                "funded": funded,
                "balance": account_value,
                "main_address": main_address,
                "agent_address": agent_address
            }
            
        except Exception as e:
            logger.error(f"Error detecting funding for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error checking wallet funding: {str(e)}",
                "funded": False
            }
    
    async def get_agent_details(self, user_id: int) -> Dict:
        """
        Get agent wallet details for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with agent wallet details
        """
        try:
            # Get details from agent factory
            return await self.agent_factory.get_agent_details(user_id)
        except Exception as e:
            self.logger.error(f"Error getting agent details for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error getting agent details: {str(e)}"
            }
    
    async def update_agent_approval(self, user_id: int, approved: bool = True) -> Dict:
        """
        Update agent wallet approval status
        
        Args:
            user_id: User ID
            approved: True if approved, False otherwise
            
        Returns:
            Dict with update status
        """
        try:
            # Update approval in agent factory
            result = await self.agent_factory.update_agent_approval(user_id, approved)
            return result
        except Exception as e:
            self.logger.error(f"Error updating agent approval for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error updating approval: {str(e)}"
            }
    
    async def enable_trading(self, user_id: int) -> Dict:
        """
        Enable trading for a user's agent wallet
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with status
        """
        try:
            # Check if agent wallet exists
            agent_details = await self.get_agent_details(user_id)
            if not agent_details or agent_details.get("status") == "error":
                return {
                    "status": "error",
                    "message": "Agent wallet not found"
                }
            
            # Check if wallet is funded
            funding_status = await self.fund_detection(user_id)
            if not funding_status.get("funded", False):
                return {
                    "status": "error",
                    "message": "Agent wallet must be funded before enabling trading",
                    "balance": funding_status.get("balance", 0)
                }
            
            # Get user's exchange
            user_exchange = await self.get_user_exchange(user_id)
            if not user_exchange:
                return {
                    "status": "error",
                    "message": "Failed to create exchange connection"
                }
            
            # Enable trading in agent factory first
            result = await self.agent_factory.enable_trading(user_id)
            
            # Place initial grid orders - ENSURE THIS ACTUALLY HAPPENS
            orders_placed = 0
            orders_details = []
            
            try:
                # Get market data
                all_mids = await self.get_all_mids()
                meta = self.global_info.meta()
                
                # Get universe info for price formatting
                universe_data = {}
                for asset in meta.get('universe', []):
                    name = asset.get('name')
                    if name:
                        universe_data[name] = asset
                
                # Focus on the most liquid pairs for initial orders
                pairs = ['BTC', 'ETH', 'SOL']
                
                for coin in pairs:
                    if coin in all_mids and coin in universe_data:
                        try:
                            current_price = float(all_mids[coin])
                            tick_size = float(universe_data[coin].get('szDecimals', 0.01))
                            position_size = 0.001  # Small size to minimize risk
                            
                            # Function to ensure price conforms to tick size
                            def round_to_tick(price, tick):
                                return round(round(price / tick) * tick, 8)
                            
                            # Place buy order 1% below current price
                            buy_price = round_to_tick(current_price * 0.99, tick_size)
                            
                            # Use the synchronous order method directly on the exchange
                            buy_result = user_exchange.order(
                                coin,         # coin
                                True,         # is_buy
                                position_size, # sz
                                buy_price,    # px
                                {"limit": {"tif": "Gtc"}}  # order_type
                            )
                            
                            if buy_result and buy_result.get('status') == 'ok':
                                orders_placed += 1
                                orders_details.append(f"{coin} BUY @ ${buy_price:.2f}")
                                self.logger.info(f"✅ Placed {coin} buy order @ ${buy_price:.2f} for user {user_id}")
                            else:
                                self.logger.warning(f"Buy order failed for {coin}: {buy_result}")
                            
                            # Place sell order 1% above current price
                            sell_price = round_to_tick(current_price * 1.01, tick_size)
                            
                            sell_result = user_exchange.order(
                                coin,         # coin
                                False,        # is_buy
                                position_size, # sz
                                sell_price,   # px
                                {"limit": {"tif": "Gtc"}}  # order_type
                            )
                            
                            if sell_result and sell_result.get('status') == 'ok':
                                orders_placed += 1
                                orders_details.append(f"{coin} SELL @ ${sell_price:.2f}")
                                self.logger.info(f"✅ Placed {coin} sell order @ ${sell_price:.2f} for user {user_id}")
                            else:
                                self.logger.warning(f"Sell order failed for {coin}: {sell_result}")
                                
                        except Exception as e:
                            self.logger.error(f"Error placing initial orders for {coin}: {e}")
                            
            except Exception as e:
                self.logger.error(f"Error placing initial orders for user {user_id}: {e}")
            
            # Always return success if agent factory enabled trading, even if no orders placed
            if result.get("status") == "success":
                self.logger.info(f"Trading enabled for user {user_id}, placed {orders_placed} initial orders")
                return {
                    "status": "success" if orders_placed > 0 else "partial_success",
                    "message": f"Trading enabled, placed {orders_placed} initial orders",
                    "orders_placed": orders_placed,
                    "orders": orders_details
                }
            else:
                return {
                    "status": "error",
                    "message": result.get("message", "Failed to enable trading"),
                    "orders_placed": orders_placed,
                    "orders": orders_details
                }
        
        except Exception as e:
            self.logger.error(f"Error enabling trading for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error enabling trading: {str(e)}"
            }
    
    async def disable_trading(self, user_id: int) -> Dict:
        """
        Disable trading for a user's agent wallet
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with status
        """
        try:
            # Check if agent wallet exists
            agent_details = await self.get_agent_details(user_id)
            if not agent_details or agent_details.get("status") == "error":
                return {
                    "status": "error",
                    "message": "Agent wallet not found"
                }
            
            # First, stop all strategies
            stop_result = await self.stop_all_user_strategies(user_id)
            
            # Disable trading in agent factory
            result = await self.agent_factory.disable_trading(user_id)
            
            if result.get("status") == "success":
                self.logger.info(f"Trading disabled for user {user_id}")
                result["strategies_stopped"] = stop_result.get("strategies_stopped", [])
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error disabling trading for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error disabling trading: {str(e)}"
            }
    
    async def emergency_stop(self, user_id: int) -> Dict:
        """
        Emergency stop for a user: cancel all orders, close all positions
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with operation result
        """
        try:
            # Check if agent wallet exists
            agent_details = await self.get_agent_details(user_id)
            if not agent_details or agent_details.get("status") == "error":
                return {
                    "status": "error",
                    "message": "Agent wallet not found"
                }
            
            # Stop all strategies
            await self.stop_all_user_strategies(user_id)
            
            # Cancel all orders
            await self.cancel_all_orders(user_id)
            
            # Get user's exchange
            exchange = self.user_exchanges.get(user_id)
            if not exchange:
                exchange = await self.get_user_exchange(user_id)
                
            if not exchange:
                return {
                    "status": "error",
                    "message": "Failed to get user exchange"
                }
            
            # Close all positions
            # First, get positions
            positions_result = await self.get_user_positions(user_id)
            
            if positions_result.get("status") != "success":
                return {
                    "status": "partial",
                    "message": "Stopped strategies and cancelled orders but failed to get positions",
                    "details": positions_result
                }
            
            positions = positions_result.get("positions", [])
            positions_closed = 0
            
            # Close each position with market order
            for position in positions:
                coin = position.get("coin")
                size = position.get("size", 0)
                
                if not coin or abs(size) < 1e-8:
                    continue
                    
                # Create market order to close
                is_buy = size < 0  # If short, buy to close
                close_size = abs(size)
                
                try:
                    # Market order with reduceOnly
                    order_type = {"market": {"reduceOnly": True}}
                    result = exchange.order(coin, is_buy, close_size, 0, order_type)
                    
                    if result.get("status") == "ok":
                        positions_closed += 1
                        self.logger.info(f"Closed {coin} position for user {user_id}")
                except Exception as e:
                    self.logger.error(f"Error closing {coin} position for user {user_id}: {e}")
            
            # Disable trading in agent factory
            disable_result = await self.agent_factory.disable_trading(user_id)
            
            return {
                "status": "success",
                "message": "Emergency stop completed successfully",
                "positions_closed": positions_closed,
                "total_positions": len(positions)
            }
            
        except Exception as e:
            self.logger.error(f"Error in emergency stop for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error in emergency stop: {str(e)}"
            }

    async def check_agent_approval(self, user_id: int) -> Dict:
        """
        Check if an agent wallet is approved
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with approval status
        """
        try:
            # Check approval in agent factory
            return await self.agent_factory.check_agent_approval(user_id)
        except Exception as e:
            self.logger.error(f"Error checking agent approval for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error checking approval: {str(e)}",
                "approved": False
            }
    
    async def get_agent_stats(self, user_id: int) -> Dict:
        """
        Get agent wallet statistics
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with agent wallet statistics
        """
        try:
            # Get agent details
            agent_details = await self.get_agent_details(user_id)
            if not agent_details or agent_details.get("status") == "error":
                return {
                    "status": "error",
                    "message": "Agent wallet not found",
                    "stats": {}
                }
            
            # Get funding status
            funding_status = await self.fund_detection(user_id)
            
            # Get positions
            positions_result = await self.get_user_positions(user_id)
            
            # Get strategies
            strategies_result = await self.get_user_strategies(user_id)
            
            # Check approval status
            approval_result = await self.check_agent_approval(user_id)
            
            # Compile stats
            stats = {
                "agent_address": agent_details.get("address"),
                "main_address": agent_details.get("main_address"),
                "created_at": agent_details.get("created_at"),
                "balance": funding_status.get("balance", 0),
                "funded": funding_status.get("funded", False),
                "approved": approval_result.get("approved", False),
                "positions_count": len(positions_result.get("positions", [])),
                "account_value": positions_result.get("account_value", 0),
                "active_strategies": len(strategies_result.get("strategies", [])),
                "trading_enabled": agent_details.get("trading_enabled", False)
            }
            
            return {
                "status": "success",
                "stats": stats
            }
            
        except Exception as e:
            self.logger.error(f"Error getting agent stats for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error getting agent stats: {str(e)}",
                "stats": {}
            }
