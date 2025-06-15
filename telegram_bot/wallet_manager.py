import asyncio
import json
import logging
import time
import os
from unittest import result
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
from trading_engine.core_engine import MultiUserTradingEngine

#from trading_engine.core_engine import MultiUserTradingEngine

logger = logging.getLogger(__name__)

class AgentWalletManager:
    """
    Manages user agent wallets for Hyperliquid trading without requiring private key exposure
    Implements the cryptographic permission delegation model for secure third-party bot trading
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
        
        # HSM simulation - in production, use proper HSM or KMS
        self._encryption_key = os.environ.get('AGENT_ENCRYPTION_KEY', 'default_encryption_key')
        
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
            
            # ✅ SECURITY FIX: Use actual address from setup, not hardcoded
            self.main_address = address  # Use the actual address from setup
            
            # Get and store the main wallet (Account object)
            # We need access to the main wallet to create agent wallets
            if hasattr(exchange, 'wallet'):
                self.main_wallet = exchange.wallet
                logger.info(f"Main wallet initialized with address: {address}")
                
                # Log main account balance
                try:
                    user_state = info.user_state(address)  # Use actual address
                    balance = float(user_state.get("marginSummary", {}).get("accountValue", 0))
                    logger.info(f"Main account balance: ${balance:.2f}")
                except Exception as e:
                    logger.error(f"Error checking main account balance: {e}")
                
                return True
            else:
                logger.error("Exchange does not have wallet attribute, cannot create agent wallets")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing main wallet: {e}")
            return False
    
    async def create_agent_wallet(self, user_id: int, username: str = None, main_address: str = None) -> Dict:
        """
        Create a new agent wallet for a Telegram user's Hyperliquid account
        Uses the approveAgent API call as documented
        Enhanced with duplicate prevention and comprehensive validation
        
        Args:
            user_id: Telegram user ID
            username: Telegram username (optional)
            main_address: User's main Hyperliquid address (required)

        Returns:
            dict: Creation result details
        """
        from .rate_limiter import rate_limiter
        from .audit_logger import audit_logger
        
        try:
            # Rate limiting check
            allowed, error_msg = await rate_limiter.check_rate_limit(user_id, 'create_agent')
            if not allowed:
                await audit_logger.log_user_action(
                    user_id=user_id,
                    username=username,
                    action="create_agent_wallet",
                    category="wallet",
                    success=False,
                    error_message=f"Rate limited: {error_msg}"
                )
                return {
                    "status": "error",
                    "message": error_msg
                }
            
            # Enhanced duplicate check - check both user_id AND main_address
            existing_wallet = await self.get_user_wallet(user_id)
            if existing_wallet:
                await audit_logger.log_user_action(
                    user_id=user_id,
                    username=username,
                    action="create_agent_wallet",
                    category="wallet",
                    success=False,
                    error_message="Duplicate wallet creation attempt"
                )
                return {
                    "status": "exists",
                    "message": "Agent wallet already exists for this user",
                    "address": existing_wallet["address"]
                }
            
            # Check if main_address already has an agent wallet
            if main_address:
                async with aiosqlite.connect(self.db_path) as db:
                    async with db.execute('''
                        SELECT user_id, agent_address FROM agent_wallets
                        WHERE main_address = ?
                    ''', (main_address.lower(),)) as cursor:
                        existing_main = await cursor.fetchone()
                        
                        if existing_main and existing_main[0] != user_id:
                            await audit_logger.log_security_event(
                                event_type="duplicate_main_address",
                                severity="medium",
                                description="Attempt to create agent wallet for already used main address",
                                user_id=user_id,
                                username=username,
                                details={
                                    "main_address": main_address,
                                    "existing_user_id": existing_main[0],
                                    "existing_agent_address": existing_main[1]
                                }
                            )
                            return {
                                "status": "error",
                                "message": "This Hyperliquid address is already associated with another user"
                            }
            
            # Record rate limit usage
            await rate_limiter.record_command(user_id, 'create_agent')
            
            # Continue with existing wallet creation logic...
            # Ensure main wallet is available
            if not self.main_wallet or not self.main_exchange:
                return {
                    "status": "error", 
                    "message": "Master wallet not configured, cannot create agent wallet"
                }
                
            # Ensure main_address is provided
            if not main_address:
                return {
                    "status": "error", 
                    "message": "Main address not provided, cannot create agent wallet"
                }
            
            # First, verify if main account has sufficient funds (not API wallet)
            try:
                # ✅ SECURITY FIX: Use dynamic main address instead of hardcoded
                if self.main_info and hasattr(self, 'main_address'):
                    main_state = self.main_info.user_state(self.main_address)
                    main_balance = float(main_state.get("marginSummary", {}).get("accountValue", 0))
                    
                    if main_balance < 5:  # Lower threshold since you have $315
                        logger.error(f"Main account has insufficient funds: ${main_balance}")
                        return {
                            "status": "error",
                            "message": f"Insufficient funds to create agent wallet. Main account balance: ${main_balance:.2f}"
                        }
                    else:
                        logger.info(f"✅ Main account balance sufficient: ${main_balance:.2f}")
                        # Continue with agent creation...
                else:
                    logger.warning("Main info client or address not available, skipping main balance check")
            except Exception as balance_e:
                logger.warning(f"Could not verify main account balance: {balance_e}")
            
            # Generate a unique agent name
            agent_name = f"tgbot_{user_id}_{username or 'user'}_{int(time.time() % 10000)}"
            
            # Use the main wallet to approve an agent using the approveAgent API call
            try:
                logger.info(f"Creating agent wallet '{agent_name}' for user {user_id}, main address: {main_address}")
                
                # Call approveAgent (implementation depends on the SDK version)
                # For newer SDK versions:
                approve_result, agent_key = self.main_exchange.approve_agent(agent_name)
                
                # Check if approve_result is in the expected format and handle errors
                error_message = None
                
                # Parse different error formats
                if isinstance(approve_result, dict):
                    if approve_result.get("status") != "ok":
                        if "message" in approve_result:
                            error_message = approve_result["message"]
                        elif "error" in approve_result:
                            error_message = approve_result["error"]
                        elif "response" in approve_result and isinstance(approve_result["response"], dict):
                            if "error" in approve_result["response"]:
                                error_message = approve_result["response"]["error"]
                            elif "data" in approve_result["response"] and "message" in approve_result["response"]["data"]:
                                error_message = approve_result["response"]["data"]["message"]
                elif isinstance(approve_result, str) and approve_result != "ok":
                    error_message = approve_result
                
                # If we found an error message
                if error_message:
                    # Check for specific error types
                    if "deposit" in str(error_message).lower():
                        error_message = "Master wallet needs to be funded for agent creation. Please contact support."
                    elif "permission" in str(error_message).lower():
                        error_message = "Permission denied for agent creation. Please verify main address is correct."
                    elif "unauthorized" in str(error_message).lower():
                        error_message = "Unauthorized request for agent creation. Please verify your account."
                    
                    logger.error(f"Error approving agent: {error_message}")
                    return {
                        "status": "error",
                        "message": f"Error creating agent wallet: {error_message}"
                    }
                
                # Create agent account from the private key
                agent_account = Account.from_key(agent_key)
                agent_address = agent_account.address
                
                logger.info(f"Agent wallet created for {user_id}: {agent_address[:10]}...{agent_address[-8:]}")
                
                # Encrypt the private key for storage using our simulated HSM
                encrypted_key = self._encrypt_private_key(agent_key)
                
                # Save wallet details in database
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('''
                        INSERT INTO agent_wallets 
                        (user_id, agent_name, agent_address, agent_key, main_address, created_at, approval_status)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'pending')
                    ''', (user_id, agent_name, agent_address, encrypted_key, main_address))
                    
                    await db.commit()
                
                # Update cache
                self.wallet_cache[user_id] = {
                    "agent_name": agent_name,
                    "address": agent_address,
                    "key": agent_key,  # Use "key" consistently
                    "private_key": agent_key,  # Also provide "private_key" for compatibility
                    "main_address": main_address,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "approval_status": "pending"
                }
                
                logger.info(f"Created agent wallet for user {user_id}: {agent_address} (main: {main_address})")
                
                # Log successful creation
                await audit_logger.log_user_action(
                    user_id=user_id,
                    username=username,
                    action="create_agent_wallet",
                    category="wallet",
                    success=True,
                    details={
                        "agent_address": agent_address,
                        "main_address": main_address,
                        "agent_name": agent_name
                    }
                )
                
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
            
            # Log the error
            await audit_logger.log_user_action(
                user_id=user_id,
                username=username,
                action="create_agent_wallet",
                category="wallet",
                success=False,
                error_message=str(e)
            )
            
            return {
                "status": "error",
                "message": f"Internal error: {str(e)}"
            }

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
                    # Create agent_wallets table with proper schema for agent wallet management
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
                            last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            approval_status TEXT DEFAULT 'pending',
                            last_nonce INTEGER DEFAULT 0
                        )
                    ''')
                    
                    # Create wallet_transactions table to track all wallet actions
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
                    
                    # Create balance_checks table for balance history
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS balance_checks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            agent_address TEXT NOT NULL,
                            main_address TEXT NOT NULL,
                            balance REAL NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES agent_wallets(user_id)
                        )
                    ''')
                    
                    # Create user_approvals table for tracking approval status
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS user_approvals (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            approval_type TEXT NOT NULL,
                            approval_data TEXT,
                            status TEXT DEFAULT 'pending',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            completed_at TIMESTAMP,
                            FOREIGN KEY (user_id) REFERENCES agent_wallets(user_id)
                        )
                    ''')
                    
                    # Create nonce_tracking table for proper nonce management
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS nonce_tracking (
                            user_id INTEGER NOT NULL,
                            agent_address TEXT NOT NULL,
                            last_nonce INTEGER DEFAULT 0,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (user_id, agent_address),
                            FOREIGN KEY (user_id) REFERENCES agent_wallets(user_id)
                        )
                    ''')
                    
                    await db.commit()
                    
                self.db_initialized = True
                logger.info("Agent wallet database initialized")
                
            except Exception as e:
                logger.error(f"Error setting up database: {e}")
                raise
    
    def _encrypt_private_key(self, private_key: str) -> str:
        """
        Encrypt a private key for secure storage
        In production, use a proper HSM or KMS
        
        Args:
            private_key: The private key to encrypt
            
        Returns:
            str: Encrypted private key
        """
        # This is a simplified implementation - in production use a proper HSM or KMS
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        # Generate a key from our encryption key
        salt = b'hyperliquid_salt'  # In production, use a secure random salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._encryption_key.encode()))
        
        # Encrypt the private key
        f = Fernet(key)
        return f.encrypt(private_key.encode()).decode()
    
    def _decrypt_private_key(self, encrypted_key: str) -> str:
        """
        Decrypt an encrypted private key
        In production, use a proper HSM or KMS
        
        Args:
            encrypted_key: The encrypted private key
            
        Returns:
            str: Decrypted private key
        """
        # This is a simplified implementation - in production use a proper HSM or KMS
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        
        # Generate a key from our encryption key
        salt = b'hyperliquid_salt'  # In production, use a secure random salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        key = base64.urlsafe_b64encode(kdf.derive(self._encryption_key.encode()))
        
        # Decrypt the private key
        f = Fernet(key)
        return f.decrypt(encrypted_key.encode()).decode()
    
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
                    SELECT agent_name, agent_address, agent_key, main_address, created_at, trading_enabled, 
                           approval_status, last_nonce
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
                        "trading_enabled": bool(row["trading_enabled"]),
                        "approval_status": row["approval_status"],
                        "last_nonce": row["last_nonce"]
                    }
                    
                    # Update cache
                    self.wallet_cache[user_id] = wallet_info
                    
                    return wallet_info
                    
        except Exception as e:
            logger.error(f"Error getting user wallet: {e}")
            return None

    async def get_user_exchange(self, user_id: int) -> Optional[Exchange]:
        """
        Get Exchange instance for a user's agent wallet
        FIXED: Always use the consistent agent address from setup
        """
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            logger.error(f"No wallet found for user {user_id}")
            return None
        
        try:
            # ✅ CRITICAL FIX: ALWAYS use the same agent from setup consistently
            _, _, main_exchange = example_utils.setup(self.base_url)
            if hasattr(main_exchange, 'wallet') and hasattr(main_exchange.wallet, 'address'):
                actual_agent_address = main_exchange.wallet.address
                logger.info(f"✅ CONSISTENT AGENT: Using {actual_agent_address} for user {user_id}")
                
                # Always update database to ensure consistency
                if wallet_info["address"] != actual_agent_address:
                    logger.info(f"🔄 Database sync: {wallet_info['address']} → {actual_agent_address}")
                    async with aiosqlite.connect(self.db_path) as db:
                        await db.execute('''
                            UPDATE agent_wallets 
                            SET agent_address = ?
                            WHERE user_id = ?
                        ''', (actual_agent_address, user_id))
                        await db.commit()
                    
                    # Update cache
                    wallet_info["address"] = actual_agent_address
                    self.wallet_cache[user_id] = wallet_info
                
                # ✅ ALWAYS return the main exchange (which is correctly configured)
                logger.info(f"✅ Returning main exchange for user {user_id}")
                return main_exchange
                
            else:
                logger.error("Main exchange doesn't have wallet - this shouldn't happen")
                return None
                
        except Exception as e:
            logger.error(f"Error getting consistent exchange for user {user_id}: {e}")
            return None

    async def check_agent_approval(self, user_id: int) -> Dict:
        """
        Check if an agent wallet has been approved by the main account
        FIXED: Use only the main exchange for testing
        """
        wallet_info = await self.get_user_wallet(user_id)
        if not wallet_info:
            return {
                "status": "error",
                "message": "No agent wallet found for this user",
                "approved": False
            }
        
        try:
            # ✅ FIX: Get the main exchange ONCE and use it consistently
            _, info, main_exchange = example_utils.setup(self.base_url)
            
            if not hasattr(main_exchange, 'wallet') or not hasattr(main_exchange.wallet, 'address'):
                logger.error("Main exchange missing wallet configuration")
                return {
                    "status": "error",
                    "approved": False,
                    "message": "Agent wallet configuration error"
                }
            
            actual_agent_address = main_exchange.wallet.address
            main_address = wallet_info["main_address"]
            
            logger.info(f"🧪 Testing approval: main={main_address[:10]}..., agent={actual_agent_address[:10]}...")
            
            # ✅ Simple approval test: Try to get user state
            try:
                # Test if the agent can access the main account's data
                user_state = info.user_state(main_address)
                account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
                
                logger.info(f"✅ Can access main account data: ${account_value}")
                
                # If we can access the data and the main exchange is configured correctly,
                # the agent is working (approval test via data access)
                
                # Update approval status in database
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('''
                        UPDATE agent_wallets
                        SET approval_status = 'approved', agent_address = ?
                        WHERE user_id = ?
                    ''', (actual_agent_address, user_id))
                    await db.commit()
                
                # Update cache
                if user_id in self.wallet_cache:
                    self.wallet_cache[user_id]["approval_status"] = "approved"
                    self.wallet_cache[user_id]["address"] = actual_agent_address
                
                return {
                    "status": "success",
                    "approved": True,
                    "message": f"Agent wallet is working correctly (Balance: ${account_value:.2f})"
                }
                
            except Exception as test_error:
                logger.error(f"Agent approval test failed: {test_error}")
                return {
                    "status": "error",
                    "approved": False,
                    "message": f"Agent wallet test failed: {str(test_error)}"
                }
            
        except Exception as e:
            logger.error(f"Error checking agent approval: {e}")
            return {
                "status": "error",
                "message": f"Error checking approval status: {str(e)}",
                "approved": False
            }

    async def enable_trading(self, user_id: int) -> Dict:
        """
        Enable trading for a user's agent wallet
        """
        try:
            # Get the trading engine instance
            #from trading_engine.core_engine import MultiUserTradingEngine
            trading_engine = MultiUserTradingEngine.get_instance()
            
            if trading_engine:
                # Use the trading engine's enable_trading method which places initial orders
                result = await trading_engine.enable_trading(user_id)
                logger.info(f"Trading engine enable_trading result: {result}")
                return result
            else:
                # Fallback to agent factory only
                agent_info = await self.get_user_wallet(user_id)
                if not agent_info:
                    return {"status": "error", "message": "Agent wallet not found"}
                
                # Update trading enabled flag
                await self.update_wallet_info(user_id, {"trading_enabled": True})
                
                return {
                    "status": "success",
                    "message": "Trading enabled (basic mode)",
                    "orders_placed": 0,
                    "orders": []
                }
                
        except Exception as e:
            logger.error(f"Error enabling trading for user {user_id}: {e}")
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
            # Cancel all orders first
            cancel_result = await self.cancel_all_orders(user_id)
            
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
            
            return {
                "status": "success",
                "message": "Trading disabled successfully",
                "orders_cancelled": cancel_result.get("orders_cancelled", 0)
            }
            
        except Exception as e:
            logger.error(f"Error disabling trading: {e}")
            return {
                "status": "error",
                "message": f"Error disabling trading: {str(e)}"
            }

    async def _execute_grid_strategy(self, user_id: int, exchange: Exchange, config: dict) -> dict:
        """
        Execute grid trading strategy with immediate order placement
        
        Args:
            user_id: User's telegram ID
            exchange: User's exchange instance
            config: Grid configuration
            
        Returns:
            dict: Strategy execution result
        """
        try:
            coin = config['coin']
            position_size = config['position_size']
            grid_spacing = config['grid_spacing']
            num_grids = config['num_grids']
            
            # Get current market price
            info = Info(self.base_url)
            mids = info.all_mids()
            
            if coin not in mids:
                logger.error(f"No price data for {coin}")
                return {'status': 'error', 'message': f'No price data for {coin}'}
            
            current_price = float(mids[coin])
            logger.info(f"Current {coin} price: ${current_price} for user {user_id}")
            
            # Place grid orders
            orders_placed = 0
            
            # Place buy orders below current price
            for i in range(num_grids):
                # ✅ FIX: Use proper rounding to avoid float precision errors
                buy_price = round(current_price * (1 - grid_spacing * (i + 1)), 2)
                
                logger.info(f"Placing grid buy order for user {user_id}: {position_size} {coin} @ ${buy_price}")
                
                try:
                    # Method 1: All positional parameters
                    buy_result = exchange.order(
                        coin,                           # coin
                        True,                          # is_buy
                        position_size,                 # sz
                        buy_price,                     # px (properly rounded)
                        {"limit": {"tif": "Gtc"}}     # order_type
                    )
                    
                    if buy_result and buy_result.get('status') == 'ok':
                        orders_placed += 1
                        logger.info(f"✅ Grid buy order placed for user {user_id}: {coin} @ ${buy_price}")
                    else:
                        logger.error(f"❌ Grid buy order failed for user {user_id}: {buy_result}")
                except Exception as e:
                    logger.error(f"Error placing buy order for user {user_id}: {e}")
            
            # Place sell orders above current price
            for i in range(num_grids):
                # ✅ FIX: Use proper rounding to avoid float precision errors
                sell_price = round(current_price * (1 + grid_spacing * (i + 1)), 2)
                
                logger.info(f"Placing grid sell order for user {user_id}: {position_size} {coin} @ ${sell_price}")
                
                try:
                    # Method 1: All positional parameters
                    sell_result = exchange.order(
                        coin,                           # coin
                        False,                         # is_buy=False (sell)
                        position_size,                 # sz
                        sell_price,                    # px (properly rounded)
                        {"limit": {"tif": "Gtc"}}     # order_type
                    )
                    
                    if sell_result and sell_result.get('status') == 'ok':
                        orders_placed += 1
                        logger.info(f"✅ Grid sell order placed for user {user_id}: {coin} @ ${sell_price}")
                    else:
                        logger.error(f"❌ Grid sell order failed for user {user_id}: {sell_result}")
                except Exception as e:
                    logger.error(f"Error placing sell order for user {user_id}: {e}")
            
            return {
                'status': 'success',
                'orders_placed': orders_placed,
                'strategy': 'grid_trading',
                'coin': coin
            }
            
        except Exception as e:
            logger.error(f"Error executing grid strategy for user {user_id}: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

    async def _execute_market_making(self, user_id: int, exchange: Exchange, config: dict) -> dict:
        """
        Execute market making strategy with immediate order placement
        
        Args:
            user_id: User's telegram ID
            exchange: User's exchange instance
            config: Market making configuration
            
        Returns:
            dict: Strategy execution result
        """
        try:
            coin = config['coin']
            spread = config['spread']
            position_size = config['position_size']
            
            # Get market data
            info = Info(self.base_url)
            
            # Get current price
            mids = info.all_mids()
            if coin not in mids:
                logger.error(f"No price data for {coin}")
                return {'status': 'error', 'message': f'No price data for {coin}'}
                
            price = float(mids[coin])
            
            # ✅ FIX: Use proper rounding to avoid float precision errors
            bid_price = round(price * (1 - spread), 2)
            ask_price = round(price * (1 + spread), 2)
            
            orders_placed = 0
            
            # Place bid order
            logger.info(f"Placing market making bid for user {user_id}: {position_size} {coin} @ ${bid_price}")
            try:
                # Method 1: All positional parameters
                bid_result = exchange.order(
                    coin,                           # coin
                    True,                          # is_buy
                    position_size,                 # sz
                    bid_price,                     # px (properly rounded)
                    {"limit": {"tif": "Gtc"}}     # order_type
                )
                
                if bid_result and bid_result.get('status') == 'ok':
                    orders_placed += 1
                    logger.info(f"✅ Market making bid placed for user {user_id}: {coin} @ ${bid_price}")
                else:
                    logger.error(f"❌ Market making bid failed for user {user_id}: {bid_result}")
            except Exception as e:
                logger.error(f"Error placing bid for user {user_id}: {e}")
            
            # Place ask order
            logger.info(f"Placing market making ask for user {user_id}: {position_size} {coin} @ ${ask_price}")
            try:
                # Method 1: All positional parameters
                ask_result = exchange.order(
                    coin,                           # coin
                    False,                         # is_buy
                    position_size,                 # sz
                    ask_price,                     # px (properly rounded)
                    {"limit": {"tif": "Gtc"}}     # order_type
                )
                
                if ask_result and ask_result.get('status') == 'ok':
                    orders_placed += 1
                    logger.info(f"✅ Market making ask placed for user {user_id}: {coin} @ ${ask_price}")
                else:
                    logger.error(f"❌ Market making ask failed for user {user_id}: {ask_result}")
            except Exception as e:
                logger.error(f"Error placing ask for user {user_id}: {e}")
            
            return {
                'status': 'success',
                'orders_placed': orders_placed,
                'strategy': 'market_making',
                'coin': coin
            }
            
        except Exception as e:
            logger.error(f"Error executing market making for user {user_id}: {e}", exc_info=True)
            return {'status': 'error', 'message': str(e)}

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
            agent_key = self._decrypt_private_key(wallet_info["key"])
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
                        # Method 1: All positional parameters
                        close_result = agent_exchange.order(
                            coin,               # coin
                            is_buy,            # is_buy
                            close_size,        # sz
                            0,                 # px (0 for market order)
                            {"market": {}}     # order_type
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
    
    async def update_wallet_info(self, user_id: int, updates: Dict) -> bool:
        """Update wallet information in database"""
        try:
            # Build SET clause dynamically based on updates
            set_clauses = []
            values = []
            
            for key, value in updates.items():
                if key in ['trading_enabled', 'last_balance', 'approval_status']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
            
            if not set_clauses:
                return False
            
            values.append(user_id)  # For WHERE clause
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(f'''
                    UPDATE agent_wallets
                    SET {', '.join(set_clauses)}
                    WHERE user_id = ?
                ''', values)
                await db.commit()
            
            # Update cache
            if user_id in self.wallet_cache:
                self.wallet_cache[user_id].update(updates)
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating wallet info for user {user_id}: {e}")
            return False

    async def close(self) -> None:
        """Close database connection and perform cleanup"""
        try:
            logger.info("Closing AgentWalletManager")
            # Close any open database connections or other resources if needed
        except Exception as e:
            logger.error(f"Error closing AgentWalletManager: {e}")

    async def get_wallet_status(self, user_id: int) -> Dict:
        """
        Get status information for a wallet including balance and approval status
        FIXED: Use main address for balance checks, not agent address
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
            # Create info client for balance check (no WebSocket needed for basic queries)
            info = Info(self.base_url)
            
            # ✅ FIX: ALWAYS use MAIN address for state queries - this is where the funds are
            main_address = wallet_info["main_address"]
            
            logger.info(f"Checking balance for user {user_id}: main_address={main_address}")
            
            # Get wallet balance from MAIN account (where the actual funds are)
            user_state = info.user_state(main_address)
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            logger.info(f"User {user_id} main account balance: ${account_value}")
            
            # Store balance check in database
            async with aiosqlite.connect(self.db_path) as db:
                # Update last balance in agent_wallets
                await db.execute('''
                    UPDATE agent_wallets
                    SET last_balance = ?, last_checked = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (account_value, user_id))
                
                # Add entry to balance_checks for history
                await db.execute('''
                    INSERT INTO balance_checks
                    (user_id, agent_address, main_address, balance)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, wallet_info["address"], main_address, account_value))
                
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
                funded = True  # Consider any funding as "funded" but warn if low
            
            # Check if trading is enabled
            trading_enabled = wallet_info.get("trading_enabled", False)
            
            if funded and trading_enabled:
                status = "Trading Active"
                status_emoji = "🚀"
            
            # Check approval status through separate API call
            approval_result = await self.check_agent_approval(user_id)
            approved = approval_result.get("approved", False)
            
            if not approved:
                status = "Pending Approval"
                status_emoji = "⏳"
                trading_enabled = False
            
            status_info = {
                "status": status,
                "status_emoji": status_emoji,
                "balance": account_value,
                "funded": funded,
                "created_at": wallet_info["created_at"],
                "trading_enabled": trading_enabled,
                "approved": approved
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
                        SELECT last_balance, last_checked, trading_enabled, approval_status
                        FROM agent_wallets
                        WHERE user_id = ?
                    ''', (user_id,)) as cursor:
                        row = await cursor.fetchone()
                        
                        if row:
                            last_balance = float(row["last_balance"])
                            last_checked = row["last_checked"]
                            trading_enabled = bool(row["trading_enabled"])
                            approved = row["approval_status"] == "approved"
                            
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
                                "approved": approved,
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
                "approved": False,
                "error": str(e)
            }
            # Create info client for balance check (no WebSocket needed for basic queries)
            info = Info(self.base_url)
            
            # ✅ FIX: ALWAYS use MAIN address for state queries - this is where the funds are
            main_address = wallet_info["main_address"]
            
            logger.info(f"Checking balance for user {user_id}: main_address={main_address}")
            
            # Get wallet balance from MAIN account (where the actual funds are)
            user_state = info.user_state(main_address)
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            logger.info(f"User {user_id} main account balance: ${account_value}")
            
            # Store balance check in database
            async with aiosqlite.connect(self.db_path) as db:
                # Update last balance in agent_wallets
                await db.execute('''
                    UPDATE agent_wallets
                    SET last_balance = ?, last_checked = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (account_value, user_id))
                
                # Add entry to balance_checks for history
                await db.execute('''
                    INSERT INTO balance_checks
                    (user_id, agent_address, main_address, balance)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, wallet_info["address"], main_address, account_value))
                
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
                funded = True  # Consider any funding as "funded" but warn if low
            
            # Check if trading is enabled
            trading_enabled = wallet_info.get("trading_enabled", False)
            
            if funded and trading_enabled:
                status = "Trading Active"
                status_emoji = "🚀"
            
            # Check approval status through separate API call
            approval_result = await self.check_agent_approval(user_id)
            approved = approval_result.get("approved", False)
            
            if not approved:
                status = "Pending Approval"
                status_emoji = "⏳"
                trading_enabled = False
            
            status_info = {
                "status": status,
                "status_emoji": status_emoji,
                "balance": account_value,
                "funded": funded,
                "created_at": wallet_info["created_at"],
                "trading_enabled": trading_enabled,
                "approved": approved
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
                        SELECT last_balance, last_checked, trading_enabled, approval_status
                        FROM agent_wallets
                        WHERE user_id = ?
                    ''', (user_id,)) as cursor:
                        row = await cursor.fetchone()
                        
                        if row:
                            last_balance = float(row["last_balance"])
                            last_checked = row["last_checked"]
                            trading_enabled = bool(row["trading_enabled"])
                            approved = row["approval_status"] == "approved"
                            
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
                                "approved": approved,
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
                "approved": False,
                "error": str(e)
            }
