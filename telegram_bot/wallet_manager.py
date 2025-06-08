import asyncio
import json
import logging
import time
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import aiosqlite
from eth_account import Account
from eth_account.signers.local import LocalAccount

# Hyperliquid imports
import example_utils
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger(__name__)

class AgentWalletManager:
    """
    Manages user agent wallets for Hyperliquid trading without requiring private key exposure
    """
    
    def __init__(self, db_path: str = "agent_wallets.db", 
                 base_url: str = None, 
                 main_wallet: Optional[LocalAccount] = None,
                 main_exchange: Optional[Exchange] = None):
        """
        Initialize the Agent Wallet Manager
        
        Args:
            db_path: Path to the SQLite database file
            base_url: Hyperliquid API base URL (defaults to TESTNET_API_URL if None)
            main_wallet: Pre-configured main wallet (optional)
            main_exchange: Pre-configured main exchange (optional)
        """
        self.db_path = db_path
        self.base_url = base_url or constants.TESTNET_API_URL
        self.main_wallet = main_wallet
        self.main_exchange = main_exchange
        
        self.setup_database_lock = asyncio.Lock()
        self.db_initialized = False
        
        # Cache for wallet info
        self.wallet_cache = {}
        self.wallet_status_cache = {}
        
        logger.info(f"AgentWalletManager initialized with DB path: {db_path}, API URL: {self.base_url}")
    
    async def initialize(self) -> bool:
        """
        Initialize the wallet manager, including database setup
        
        Returns:
            bool: True if initialization succeeded, False otherwise
        """
        try:
            # Set up database
            await self.setup_database()
            
            # If we don't have a main wallet yet, try to set up the main wallet
            if self.main_wallet is None or self.main_exchange is None:
                result = await self._initialize_main_wallet()
                if not result:
                    logger.warning("Failed to initialize main wallet, agent creation will not work")
            
            logger.info("AgentWalletManager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing AgentWalletManager: {e}")
            return False
    
    async def _initialize_main_wallet(self) -> bool:
        """
        Initialize the main wallet for agent creation
        
        Returns:
            bool: True if main wallet initialization succeeded, False otherwise
        """
        try:
            # Try to get main wallet from environment variable or examples/config.json
            address, info, exchange = example_utils.setup(self.base_url)
            
            # Store the exchange and info for future use
            self.main_exchange = exchange
            self.main_info = info
            
            # Get and store the main wallet (Account object)
            # We need access to the main wallet to create agent wallets
            if hasattr(exchange, 'wallet'):
                self.main_wallet = exchange.wallet
                logger.info(f"Main wallet initialized with address: {address}")
                return True
            else:
                logger.error("Exchange does not have wallet attribute, cannot create agent wallets")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing main wallet: {e}")
            return False
    
    async def setup_database(self) -> None:
        """Set up SQLite database for wallet management"""
        async with self.setup_database_lock:
            if self.db_initialized:
                return
                
            try:
                # Ensure the directory exists
                os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
                
                # Create database and tables
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS agent_wallets (
                            user_id INTEGER PRIMARY KEY,
                            agent_name TEXT NOT NULL,
                            agent_address TEXT NOT NULL,
                            agent_key TEXT NOT NULL,
                            main_address TEXT NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            trading_enabled INTEGER DEFAULT 0,
                            last_balance REAL DEFAULT 0.0,
                            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS wallet_transactions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            tx_hash TEXT,
                            tx_type TEXT NOT NULL,
                            amount REAL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            status TEXT DEFAULT 'pending',
                            FOREIGN KEY (user_id) REFERENCES agent_wallets(user_id)
                        )
                    ''')
                    
                    await db.commit()
                    
                self.db_initialized = True
                logger.info("Agent wallet database initialized")
                
            except Exception as e:
                logger.error(f"Error setting up database: {e}")
                raise
    
    async def create_agent_wallet(self, user_id: int, username: str = None) -> Dict:
        """
        Create a new agent wallet for a Telegram user
        
        Args:
            user_id: Telegram user ID
            username: Telegram username (optional)
        
        Returns:
            dict: Creation result details
        """
        try:
            # Check if wallet already exists for this user
            existing_wallet = await self.get_user_wallet(user_id)
            if existing_wallet:
                return {
                    "status": "exists",
                    "message": "Agent wallet already exists for this user",
                    "address": existing_wallet["address"]
                }
            
            # Ensure main wallet is available
            if not self.main_wallet or not self.main_exchange:
                return {
                    "status": "error", 
                    "message": "Main wallet not configured, cannot create agent wallet"
                }
            
            # Generate a unique agent name
            agent_name = f"tg_{user_id}_{username or 'user'}_{int(time.time() % 10000)}"
            
            # Use the main wallet to approve an agent
            try:
                approve_result, agent_key = self.main_exchange.approve_agent(agent_name)
                
                if not approve_result.get("status") == "ok":
                    logger.error(f"Error approving agent: {approve_result}")
                    return {
                        "status": "error",
                        "message": f"Error creating agent wallet: {approve_result.get('message', 'Unknown error')}"
                    }
                
                # Create agent account
                agent_account = Account.from_key(agent_key)
                agent_address = agent_account.address
                
                # Save wallet details in database
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('''
                        INSERT INTO agent_wallets 
                        (user_id, agent_name, agent_address, agent_key, main_address, created_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (user_id, agent_name, agent_address, agent_key, self.main_wallet.address))
                    
                    await db.commit()
                
                # Update cache
                self.wallet_cache[user_id] = {
                    "agent_name": agent_name,
                    "address": agent_address,
                    "key": agent_key,
                    "main_address": self.main_wallet.address,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                logger.info(f"Created agent wallet for user {user_id}: {agent_address}")
                
                return {
                    "status": "success",
                    "message": "Agent wallet created successfully",
                    "address": agent_address,
                    "agent_name": agent_name
                }
                
            except Exception as e:
                logger.error(f"Error creating agent wallet: {e}")
                return {
                    "status": "error",
                    "message": f"Error creating agent wallet: {str(e)}"
                }
                
        except Exception as e:
            logger.error(f"Error in create_agent_wallet: {e}")
            return {
                "status": "error",
                "message": f"Internal error: {str(e)}"
            }
    
    async def get_user_wallet(self, user_id: int) -> Optional[Dict]:
        """
        Get wallet information for a user
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            dict: Wallet information or None if not found
        """
        # Check cache first
        if user_id in self.wallet_cache:
            return self.wallet_cache[user_id]
            
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute('''
                    SELECT agent_name, agent_address, agent_key, main_address, created_at, trading_enabled
                    FROM agent_wallets
                    WHERE user_id = ?
                ''', (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    
                    if not row:
                        return None
                    
                    wallet_info = {
                        "agent_name": row["agent_name"],
                        "address": row["agent_address"],
                        "key": row["agent_key"],
                        "main_address": row["main_address"],
                        "created_at": row["created_at"],
                        "trading_enabled": bool(row["trading_enabled"])
                    }
                    
                    # Update cache
                    self.wallet_cache[user_id] = wallet_info
                    
                    return wallet_info
                    
        except Exception as e:
            logger.error(f"Error getting user wallet: {e}")
            return None
    
    async def get_wallet_status(self, user_id: int) -> Dict:
        """
        Get status information for a wallet
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            dict: Status information with balance, status message, etc.
        """
        # Check cache first if it's recent (less than 30 seconds old)
        current_time = time.time()
        if user_id in self.wallet_status_cache:
            cache_item = self.wallet_status_cache[user_id]
            if current_time - cache_item["timestamp"] < 30:
                return cache_item["status"]
        
        # Get wallet information
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            return {
                "status": "not_found",
                "status_emoji": "❌",
                "balance": 0.0,
                "funded": False,
                "created_at": "N/A",
                "trading_enabled": False
            }
        
        try:
            # Create info client for balance check
            info = Info(self.base_url)
            
            # Get wallet balance
            user_state = info.user_state(wallet_info["address"])
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Update balance in database
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE agent_wallets
                    SET last_balance = ?, last_checked = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (account_value, user_id))
                
                await db.commit()
            
            # Determine status based on balance
            status = "Not funded"
            status_emoji = "⚠️"
            funded = False
            
            if account_value >= 10.0:
                status = "Funded & Ready"
                status_emoji = "✅"
                funded = True
            elif account_value > 0:
                status = "Partially Funded"
                status_emoji = "⚠️"
                funded = False
            
            # Check if trading is enabled
            trading_enabled = wallet_info.get("trading_enabled", False)
            
            if funded and trading_enabled:
                status = "Trading Active"
                status_emoji = "🚀"
            
            status_info = {
                "status": status,
                "status_emoji": status_emoji,
                "balance": account_value,
                "funded": funded,
                "created_at": wallet_info["created_at"],
                "trading_enabled": trading_enabled
            }
            
            # Update cache
            self.wallet_status_cache[user_id] = {
                "timestamp": current_time,
                "status": status_info
            }
            
            return status_info
            
        except Exception as e:
            logger.error(f"Error getting wallet status: {e}")
            
            # Return last known balance from database
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    db.row_factory = aiosqlite.Row
                    
                    async with db.execute('''
                        SELECT last_balance, last_checked, trading_enabled
                        FROM agent_wallets
                        WHERE user_id = ?
                    ''', (user_id,)) as cursor:
                        row = await cursor.fetchone()
                        
                        if row:
                            last_balance = float(row["last_balance"])
                            last_checked = row["last_checked"]
                            trading_enabled = bool(row["trading_enabled"])
                            
                            status = "Error checking balance"
                            status_emoji = "⚠️"
                            funded = last_balance >= 10.0
                            
                            return {
                                "status": status,
                                "status_emoji": status_emoji,
                                "balance": last_balance,
                                "funded": funded,
                                "created_at": wallet_info["created_at"],
                                "last_checked": last_checked,
                                "trading_enabled": trading_enabled,
                                "error": str(e)
                            }
            except Exception as inner_e:
                logger.error(f"Error getting wallet data from database: {inner_e}")
            
            # Fallback if all else fails
            return {
                "status": "Error",
                "status_emoji": "❌",
                "balance": 0.0,
                "funded": False,
                "created_at": wallet_info["created_at"],
                "trading_enabled": False,
                "error": str(e)
            }
    
    async def refresh_wallet_status(self, user_id: int) -> Dict:
        """
        Force refresh wallet status by clearing cache
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            dict: Updated status information
        """
        # Remove from cache
        if user_id in self.wallet_status_cache:
            del self.wallet_status_cache[user_id]
            
        # Get fresh status
        return await self.get_wallet_status(user_id)
    
    async def get_balance_emoji(self, user_id: int) -> str:
        """
        Get emoji representing wallet balance status
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            str: Emoji representing balance status
        """
        status = await self.get_wallet_status(user_id)
        return status["status_emoji"]
    
    async def is_trading_enabled(self, user_id: int) -> bool:
        """
        Check if trading is enabled for a user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            bool: True if trading is enabled
        """
        status = await self.get_wallet_status(user_id)
        return status.get("trading_enabled", False)
    
    async def enable_trading(self, user_id: int) -> Dict:
        """
        Enable trading for a user's agent wallet
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            dict: Result of the operation
        """
        # Check if wallet exists
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            return {
                "status": "error", 
                "message": "No agent wallet found for this user"
            }
        
        # Check if wallet is funded
        status = await self.get_wallet_status(user_id)
        if not status["funded"]:
            return {
                "status": "error",
                "message": "Wallet needs to be funded before enabling trading"
            }
        
        try:
            # Update trading enabled flag in database
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE agent_wallets
                    SET trading_enabled = 1
                    WHERE user_id = ?
                ''', (user_id,))
                
                await db.commit()
            
            # Update cache
            if user_id in self.wallet_cache:
                self.wallet_cache[user_id]["trading_enabled"] = True
                
            if user_id in self.wallet_status_cache:
                self.wallet_status_cache[user_id]["status"]["trading_enabled"] = True
            
            logger.info(f"Trading enabled for user {user_id}")
            
            # Start trading strategies for this user
            # This would typically integrate with your trading engine
            # For now, we'll just return success
            
            return {
                "status": "success",
                "message": "Trading enabled successfully"
            }
            
        except Exception as e:
            logger.error(f"Error enabling trading: {e}")
            return {
                "status": "error",
                "message": f"Error enabling trading: {str(e)}"
            }
    
    async def disable_trading(self, user_id: int) -> Dict:
        """
        Disable trading for a user's agent wallet
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            dict: Result of the operation
        """
        # Check if wallet exists
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            return {
                "status": "error", 
                "message": "No agent wallet found for this user"
            }
        
        try:
            # Update trading enabled flag in database
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    UPDATE agent_wallets
                    SET trading_enabled = 0
                    WHERE user_id = ?
                ''', (user_id,))
                
                await db.commit()
            
            # Update cache
            if user_id in self.wallet_cache:
                self.wallet_cache[user_id]["trading_enabled"] = False
                
            if user_id in self.wallet_status_cache:
                self.wallet_status_cache[user_id]["status"]["trading_enabled"] = False
            
            logger.info(f"Trading disabled for user {user_id}")
            
            # Cancel all open orders
            result = await self.cancel_all_orders(user_id)
            
            return {
                "status": "success",
                "message": "Trading disabled successfully",
                "orders_cancelled": result.get("orders_cancelled", 0)
            }
            
        except Exception as e:
            logger.error(f"Error disabling trading: {e}")
            return {
                "status": "error",
                "message": f"Error disabling trading: {str(e)}"
            }
    
    async def emergency_stop(self, user_id: int) -> Dict:
        """
        Emergency stop: cancel all orders and close all positions
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            dict: Result of the operation
        """
        # Check if wallet exists
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            return {
                "status": "error", 
                "message": "No agent wallet found for this user"
            }
        
        try:
            # First, disable trading
            await self.disable_trading(user_id)
            
            # Get agent wallet info to create exchange object
            agent_address = wallet_info["address"]
            agent_key = wallet_info["key"]
            agent_account = Account.from_key(agent_key)
            
            # Create exchange instance for the agent
            agent_exchange = Exchange(
                wallet=agent_account,
                base_url=self.base_url
            )
            
            # Create info instance
            info = Info(self.base_url)
            
            # Get user state to find open positions
            user_state = info.user_state(agent_address)
            positions = user_state.get("assetPositions", [])
            
            positions_closed = 0
            for pos_data in positions:
                pos = pos_data.get("position", {})
                if not pos:
                    continue
                
                coin = pos.get("coin")
                size = float(pos.get("szi", 0))
                
                if abs(size) > 1e-10:  # Only close non-zero positions
                    # Market order to close position
                    is_buy = size < 0  # If size is negative, we need to buy to close
                    close_size = abs(size)
                    
                    # Place market order to close
                    try:
                        close_result = agent_exchange.order(
                            coin, 
                            is_buy, 
                            close_size, 
                            0,  # Price 0 for market order
                            {"market": {}}  # Market order type
                        )
                        
                        if close_result.get("status") == "ok":
                            positions_closed += 1
                            logger.info(f"Closed position for {user_id}: {coin} {size}")
                    except Exception as e:
                        logger.error(f"Error closing position for {user_id} ({coin}): {e}")
            
            # Get final balance
            final_state = info.user_state(agent_address)
            final_balance = float(final_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Update status to reflect positions closed
            return {
                "status": "success",
                "message": "Emergency stop completed",
                "positions_closed": positions_closed,
                "final_balance": final_balance
            }
            
        except Exception as e:
            logger.error(f"Error executing emergency stop for {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error executing emergency stop: {str(e)}"
            }
    
    async def cancel_all_orders(self, user_id: int) -> Dict:
        """
        Cancel all open orders for a user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            dict: Result of the operation
        """
        # Check if wallet exists
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            return {
                "status": "error", 
                "message": "No agent wallet found for this user"
            }
        
        try:
            # Get agent wallet info to create exchange object
            agent_key = wallet_info["key"]
            agent_account = Account.from_key(agent_key)
            
            # Create exchange instance for the agent
            agent_exchange = Exchange(
                wallet=agent_account,
                base_url=self.base_url
            )
            
            # Get all open orders (need to know coins)
            info = Info(self.base_url)
            user_state = info.user_state(wallet_info["address"])
            
            # Get unique coins from positions and open orders
            coins = set()
            
            # Add coins from positions
            for pos_data in user_state.get("assetPositions", []):
                pos = pos_data.get("position", {})
                if pos and pos.get("coin"):
                    coins.add(pos.get("coin"))
            
            # Add coins from open orders
            for order_data in user_state.get("crossMarginOrders", []):
                if order_data.get("coin"):
                    coins.add(order_data.get("coin"))
            
            # Cancel orders for each coin
            orders_cancelled = 0
            for coin in coins:
                try:
                    cancel_result = agent_exchange.cancel_all(coin)
                    
                    if cancel_result.get("status") == "ok":
                        # Count cancelled orders from response
                        cancel_data = cancel_result.get("response", {}).get("data", {})
                        statuses = cancel_data.get("statuses", [])
                        orders_cancelled += len([s for s in statuses if s.get("status") == "cancelled"])
                except Exception as e:
                    logger.error(f"Error cancelling orders for {user_id} ({coin}): {e}")
            
            return {
                "status": "success",
                "message": f"Cancelled {orders_cancelled} orders",
                "orders_cancelled": orders_cancelled
            }
            
        except Exception as e:
            logger.error(f"Error cancelling all orders for {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error cancelling orders: {str(e)}"
            }
    
    async def get_user_portfolio(self, user_id: int) -> Dict:
        """
        Get portfolio information for a user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            dict: Portfolio information
        """
        # Check if wallet exists
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            return {
                "status": "error", 
                "message": "No agent wallet found for this user",
                "account_value": 0.0,
                "available_balance": 0.0,
                "unrealized_pnl": 0.0,
                "positions": [],
                "recent_trades": []
            }
        
        try:
            # Get user state
            info = Info(self.base_url)
            user_state = info.user_state(wallet_info["address"])
            
            # Extract account value
            margin_summary = user_state.get("marginSummary", {})
            account_value = float(margin_summary.get("accountValue", 0))
            available_balance = account_value - float(margin_summary.get("totalMarginUsed", 0))
            unrealized_pnl = float(margin_summary.get("totalUnrealizedPnl", 0))
            
            # Get positions
            positions = []
            for pos_data in user_state.get("assetPositions", []):
                pos = pos_data.get("position", {})
                if not pos:
                    continue
                    
                coin = pos.get("coin", "Unknown")
                size = float(pos.get("szi", 0))
                entry_price = float(pos.get("entryPx", 0))
                unrealized_pnl_pos = float(pos.get("unrealizedPnl", 0))
                
                if abs(size) > 1e-10:  # Only include non-zero positions
                    positions.append({
                        "coin": coin,
                        "size": size,
                        "entry_price": entry_price,
                        "unrealized_pnl": unrealized_pnl_pos
                    })
            
            # Get recent trades (if available)
            recent_trades = []
            try:
                fills = info.user_fills(wallet_info["address"])
                
                for fill in fills[:10]:  # Get last 10 fills
                    recent_trades.append({
                        "coin": fill.get("coin", "Unknown"),
                        "side": fill.get("dir", "Unknown"),
                        "size": float(fill.get("sz", 0)),
                        "price": float(fill.get("px", 0)),
                        "time": datetime.fromtimestamp(fill.get("time", 0) / 1000).strftime("%Y-%m-%d %H:%M:%S"),
                        "fee": float(fill.get("fee", 0))
                    })
            except Exception as e:
                logger.error(f"Error getting fills for {user_id}: {e}")
            
            return {
                "status": "success",
                "account_value": account_value,
                "available_balance": available_balance,
                "unrealized_pnl": unrealized_pnl,
                "positions": positions,
                "recent_trades": recent_trades
            }
            
        except Exception as e:
            logger.error(f"Error getting portfolio for {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error getting portfolio: {str(e)}",
                "account_value": 0.0,
                "available_balance": 0.0,
                "unrealized_pnl": 0.0,
                "positions": [],
                "recent_trades": []
            }
    
    async def record_transaction(self, user_id: int, tx_hash: str, tx_type: str, amount: float) -> bool:
        """
        Record a transaction in the database
        
        Args:
            user_id: Telegram user ID
            tx_hash: Transaction hash
            tx_type: Transaction type (deposit, withdrawal, etc.)
            amount: Transaction amount
            
        Returns:
            bool: True if successful
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO wallet_transactions
                    (user_id, tx_hash, tx_type, amount, timestamp, status)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'completed')
                ''', (user_id, tx_hash, tx_type, amount))
                
                await db.commit()
                
            return True
            
        except Exception as e:
            logger.error(f"Error recording transaction for {user_id}: {e}")
            return False
    
    async def get_user_transactions(self, user_id: int) -> List[Dict]:
        """
        Get transaction history for a user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            list: List of transactions
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute('''
                    SELECT * FROM wallet_transactions
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                ''', (user_id,)) as cursor:
                    rows = await cursor.fetchall()
                    
                    transactions = []
                    for row in rows:
                        transactions.append({
                            "id": row["id"],
                            "tx_hash": row["tx_hash"],
                            "tx_type": row["tx_type"],
                            "amount": row["amount"],
                            "timestamp": row["timestamp"],
                            "status": row["status"]
                        })
                    
                    return transactions
                    
        except Exception as e:
            logger.error(f"Error getting transactions for {user_id}: {e}")
            return []
    
    async def close(self) -> None:
        """
        Close database connection and perform cleanup
        """
        logger.info("Closing AgentWalletManager")
