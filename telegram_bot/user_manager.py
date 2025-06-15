"""
UserManager class for managing users in the multi-user architecture
Handles user registration, agent wallet creation, and status management
"""
import asyncio
import json
import logging
import time
import os
import sys
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from eth_account import Account
from eth_account.signers.local import LocalAccount
import re  # For address validation

# Hyperliquid imports
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Import database for user storage
from database import bot_db

logger = logging.getLogger(__name__)

class UserManager:
    """
    User management for the multi-user architecture
    Manages user registration, agent wallets, and user states
    """
    
    def __init__(self, vault_manager=None, exchange=None, info=None, base_url=None):
        """Initialize the UserManager"""
        self.vault_manager = vault_manager
        self.exchange = exchange
        self.info = info
        self.base_url = base_url or constants.MAINNET_API_URL
        
        # Use provided info client or create a new one
        if not self.info:
            self.info = Info(self.base_url)
            
        # Cache to reduce database hits
        self.user_cache = {}
        self.wallet_cache = {}
        
        # Status tracking for multi-user operations
        self.operations_in_progress = {}
        self.status_listeners = {}
        
        logger.info("UserManager initialized with API URL: %s", self.base_url)
    
    def set_vault_manager(self, vault_manager):
        """Set the vault manager after initialization"""
        self.vault_manager = vault_manager
    
    async def register_user(self, telegram_id: int, hyperliquid_address: str,
                           telegram_username: str = None) -> Dict:
        """
        Register new user with their Hyperliquid address
        
        Args:
            telegram_id: Telegram user ID
            hyperliquid_address: User's Hyperliquid address
            telegram_username: Optional Telegram username
            
        Returns:
            Dict with registration status
        """
        try:
            # Validate hyperliquid address format
            if not self._validate_address_format(hyperliquid_address):
                return {
                    "status": "error",
                    "message": "Invalid Hyperliquid address format. Address must start with 0x and have 42 characters."
                }
            
            # Normalize address format
            hyperliquid_address = hyperliquid_address.lower()
            
            # Check if address exists on Hyperliquid 
            try:
                # Try to fetch user state to see if address exists
                user_state = self.info.user_state(hyperliquid_address)
                if not user_state or not isinstance(user_state, dict):
                    return {
                        "status": "error",
                        "message": "Could not verify Hyperliquid address. Make sure it's a valid account."
                    }
            except Exception as e:
                logger.error(f"Error checking address on Hyperliquid: {e}")
                return {
                    "status": "error",
                    "message": f"Error verifying Hyperliquid address: {str(e)}"
                }
            
            # Check if user is already registered
            # Create user if not exists or update with Hyperliquid address
            user = await bot_db.add_user(telegram_id, telegram_username)
            
            # Update user with Hyperliquid address if needed
            if not user.get("hyperliquid_main_address"):
                # Address not set, update it
                async with bot_db.conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        UPDATE users SET
                            hyperliquid_main_address = ?,
                            status = 'registered',
                            last_active = CURRENT_TIMESTAMP
                        WHERE telegram_id = ?
                        """,
                        (hyperliquid_address, telegram_id)
                    )
                    await bot_db.conn.commit()
                    
                    # Retrieve updated user
                    await cursor.execute(
                        "SELECT * FROM users WHERE telegram_id = ?",
                        (telegram_id,)
                    )
                    user_data = await cursor.fetchone()
                    if user_data:
                        columns = [column[0] for column in cursor.description]
                        user = dict(zip(columns, user_data))
            
            # Update cache
            self.user_cache[telegram_id] = {
                "telegram_id": telegram_id,
                "main_address": hyperliquid_address,
                "status": user.get("status", "registered"),
                "last_active": datetime.now().isoformat()
            }
            
            return {
                "status": "success",
                "message": "User registered successfully",
                "user_id": user.get("id"),
                "telegram_id": telegram_id,
                "hyperliquid_address": hyperliquid_address
            }
            
        except Exception as e:
            logger.error(f"Error registering user: {e}")
            return {
                "status": "error",
                "message": f"Registration error: {str(e)}"
            }
    
    async def create_agent_wallet(self, telegram_id: int, main_address: str = None) -> Dict:
        """
        Create agent wallet for user's account
        
        Args:
            telegram_id: Telegram user ID
            main_address: Optional address override (default: use registered address)
            
        Returns:
            Dict with agent wallet creation status
        """
        try:
            # Track operation start
            op_id = str(uuid.uuid4())
            self.operations_in_progress[op_id] = {
                "type": "agent_wallet_creation",
                "user_id": telegram_id,
                "start_time": time.time(),
                "status": "starting"
            }
            
            # Get user's registered address if not provided
            if not main_address:
                user = await self._get_user(telegram_id)
                if not user:
                    return {
                        "status": "error",
                        "message": "User not found. Please register first with /start."
                    }
                    
                main_address = user.get("hyperliquid_main_address")
                
            if not main_address:
                return {
                    "status": "error",
                    "message": "No Hyperliquid address registered. Please provide your address first."
                }
            
            # Check if user already has an agent wallet
            existing_wallet = await self.get_user_wallet(telegram_id)
            if existing_wallet:
                return {
                    "status": "exists",
                    "message": "Agent wallet already exists for this user",
                    "agent_address": existing_wallet.get("agent_wallet_address")
                }
            
            # Generate new keypair for agent wallet
            self.operations_in_progress[op_id]["status"] = "generating_keypair"
            private_key = self._generate_private_key()
            agent_account = Account.from_key(private_key)
            agent_address = agent_account.address
            
            # Create agent name for better tracking
            agent_name = f"tg_{telegram_id}_{int(time.time() % 10000)}"
            
            # Store agent wallet in database
            self.operations_in_progress[op_id]["status"] = "storing_wallet"
            wallet_result = await bot_db.add_agent_wallet(
                telegram_id, 
                agent_address, 
                main_address,
                private_key
            )
            
            if not wallet_result:
                return {
                    "status": "error",
                    "message": "Failed to store agent wallet details"
                }
                
            # Update cache
            self.wallet_cache[telegram_id] = {
                "agent_address": agent_address,
                "main_address": main_address,
                "created_at": datetime.now().isoformat(),
                "status": "pending_approval"
            }
            
            # Track operation completion
            self.operations_in_progress[op_id]["status"] = "completed"
            self.operations_in_progress[op_id]["end_time"] = time.time()
            
            return {
                "status": "success",
                "message": "Agent wallet created successfully",
                "agent_address": agent_address,
                "agent_name": agent_name,
                "approval_required": True,
                "operation_id": op_id
            }
            
        except Exception as e:
            logger.error(f"Error creating agent wallet: {e}")
            if op_id in self.operations_in_progress:
                self.operations_in_progress[op_id]["status"] = "failed"
                self.operations_in_progress[op_id]["error"] = str(e)
                
            return {
                "status": "error",
                "message": f"Agent wallet creation failed: {str(e)}"
            }
    
    async def get_user_wallet(self, telegram_id: int) -> Optional[Dict]:
        """
        Get user's wallet info
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            Dict with wallet info or None if not found
        """
        try:
            # Check cache first
            if telegram_id in self.wallet_cache:
                cache_entry = self.wallet_cache[telegram_id]
                # Use cached data if recent (less than 5 minutes old)
                cache_time = datetime.fromisoformat(cache_entry.get("last_checked", "2000-01-01T00:00:00"))
                if (datetime.now() - cache_time).total_seconds() < 300:
                    return cache_entry
            
            # Get from database
            wallet_data = await bot_db.get_agent_wallet(telegram_id)
            if not wallet_data:
                return None
                
            # Get balance from Hyperliquid API
            agent_address = wallet_data.get("agent_wallet_address")
            if agent_address:
                try:
                    user_state = self.info.user_state(agent_address)
                    balance = float(user_state.get("marginSummary", {}).get("accountValue", 0))
                    
                    # Update balance in database
                    await bot_db.update_wallet_balance(telegram_id, balance)
                    
                    # Add balance to wallet data
                    wallet_data["balance"] = balance
                    wallet_data["funded"] = balance > 0
                    
                    # Update status if funded
                    if balance > 0 and wallet_data.get("status") == "approved":
                        await bot_db.update_agent_wallet_status(
                            telegram_id, agent_address, "funded"
                        )
                        wallet_data["status"] = "funded"
                except Exception as e:
                    logger.error(f"Error getting wallet balance: {e}")
                    wallet_data["balance"] = 0
                    wallet_data["funded"] = False
            
            # Update cache
            wallet_data["last_checked"] = datetime.now().isoformat()
            self.wallet_cache[telegram_id] = wallet_data
            
            return wallet_data
            
        except Exception as e:
            logger.error(f"Error getting user wallet: {e}")
            return None
    
    async def update_user_status(self, telegram_id: int, status: str) -> Dict:
        """
        Update user status in pipeline
        
        Args:
            telegram_id: Telegram user ID
            status: New status - one of 'pending_approval', 'approved', 'funded', 'trading'
            
        Returns:
            Dict with update status
        """
        try:
            # Validate status
            valid_statuses = ["pending_approval", "approved", "funded", "trading"]
            if status not in valid_statuses:
                return {
                    "status": "error",
                    "message": f"Invalid status: {status}. Must be one of {valid_statuses}"
                }
            
            # Get wallet info
            wallet = await self.get_user_wallet(telegram_id)
            if not wallet:
                return {
                    "status": "error",
                    "message": "No agent wallet found for this user"
                }
                
            agent_address = wallet.get("agent_wallet_address")
            if not agent_address:
                return {
                    "status": "error", 
                    "message": "Invalid agent wallet data"
                }
            
            # Check for valid status transitions
            current_status = wallet.get("status")
            if current_status == status:
                return {
                    "status": "info",
                    "message": f"User status is already {status}"
                }
                
            # Validate transitions
            valid_transitions = {
                "pending_approval": ["approved"],
                "approved": ["funded", "pending_approval"],
                "funded": ["trading", "approved"],
                "trading": ["funded"]
            }
            
            if current_status in valid_transitions and status not in valid_transitions[current_status]:
                return {
                    "status": "error",
                    "message": f"Invalid status transition from {current_status} to {status}"
                }
            
            # Update status
            result = await bot_db.update_agent_wallet_status(
                telegram_id, 
                agent_address, 
                status,
                status == "approved" # Set approved flag if status is approved
            )
            
            if not result:
                return {
                    "status": "error",
                    "message": "Failed to update user status"
                }
                
            # Update cache if it exists
            if telegram_id in self.wallet_cache:
                self.wallet_cache[telegram_id]["status"] = status
                self.wallet_cache[telegram_id]["last_checked"] = datetime.now().isoformat()
            
            # Clear user cache to force refresh
            if telegram_id in self.user_cache:
                del self.user_cache[telegram_id]
                
            return {
                "status": "success",
                "message": f"User status updated to {status}",
                "previous_status": current_status,
                "new_status": status
            }
            
        except Exception as e:
            logger.error(f"Error updating user status: {e}")
            return {
                "status": "error",
                "message": f"Error updating user status: {str(e)}"
            }
    
    async def approve_agent_wallet(self, telegram_id: int, 
                                by_admin_id: int = None) -> Dict:
        """
        Approve an agent wallet
        
        Args:
            telegram_id: User's Telegram ID
            by_admin_id: Admin who approved (for auditing)
            
        Returns:
            Dict with approval status
        """
        try:
            # Get wallet info
            wallet = await self.get_user_wallet(telegram_id)
            if not wallet:
                return {
                    "status": "error",
                    "message": "No agent wallet found for this user"
                }
                
            # Only pending wallets can be approved
            if wallet.get("status") != "pending_approval":
                return {
                    "status": "error",
                    "message": f"Cannot approve wallet with status {wallet.get('status')}"
                }
            
            # Update approval status in database
            result = await self.update_user_status(telegram_id, "approved")
            
            # Update approval record
            if result["status"] == "success" and by_admin_id:
                async with bot_db.conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        UPDATE approvals SET
                            status = 'approved',
                            processed_at = CURRENT_TIMESTAMP,
                            processed_by = (SELECT id FROM users WHERE telegram_id = ?)
                        WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?)
                        AND approval_type = 'agent_wallet'
                        AND status = 'pending'
                        """,
                        (by_admin_id, telegram_id)
                    )
                    await bot_db.conn.commit()
            
            return result
            
        except Exception as e:
            logger.error(f"Error approving agent wallet: {e}")
            return {
                "status": "error",
                "message": f"Error approving wallet: {str(e)}"
            }
    
    async def enable_trading(self, telegram_id: int) -> Dict:
        """
        Enable trading for a user
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            Dict with trading enablement status
        """
        try:
            # Get wallet info
            wallet = await self.get_user_wallet(telegram_id)
            if not wallet:
                return {
                    "status": "error",
                    "message": "No agent wallet found for this user"
                }
                
            # Wallet must be funded
            if wallet.get("status") not in ["funded", "trading"]:
                if wallet.get("status") == "approved" and wallet.get("funded", False):
                    # Status is approved but wallet is funded, update to funded first
                    await self.update_user_status(telegram_id, "funded")
                else:
                    return {
                        "status": "error",
                        "message": f"Wallet must be funded before enabling trading. Current status: {wallet.get('status')}"
                    }
            
            # If already trading, nothing to do
            if wallet.get("status") == "trading":
                return {
                    "status": "info",
                    "message": "Trading is already enabled"
                }
            
            # Enable trading
            result = await self.update_user_status(telegram_id, "trading")
            return result
            
        except Exception as e:
            logger.error(f"Error enabling trading: {e}")
            return {
                "status": "error",
                "message": f"Error enabling trading: {str(e)}"
            }
    
    async def disable_trading(self, telegram_id: int) -> Dict:
        """
        Disable trading for a user
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            Dict with trading disablement status
        """
        try:
            # Get wallet info
            wallet = await self.get_user_wallet(telegram_id)
            if not wallet:
                return {
                    "status": "error",
                    "message": "No agent wallet found for this user"
                }
                
            # Only trading wallets can be disabled
            if wallet.get("status") != "trading":
                return {
                    "status": "info",
                    "message": "Trading is already disabled"
                }
            
            # Disable trading
            result = await self.update_user_status(telegram_id, "funded")
            return result
            
        except Exception as e:
            logger.error(f"Error disabling trading: {e}")
            return {
                "status": "error",
                "message": f"Error disabling trading: {str(e)}"
            }
    
    async def get_user_trades(self, telegram_id: int, limit: int = 10) -> List[Dict]:
        """
        Get recent trades for a user
        
        Args:
            telegram_id: Telegram user ID
            limit: Maximum number of trades to return
            
        Returns:
            List of trades
        """
        try:
            # Get user ID
            user = await self._get_user(telegram_id)
            if not user:
                return []
                
            user_id = user.get("id")
            
            # Get trades from database
            async with bot_db.conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT * FROM user_trades
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (user_id, limit)
                )
                
                trades = []
                async for row in cursor:
                    columns = [column[0] for column in cursor.description]
                    trades.append(dict(zip(columns, row)))
                    
                return trades
                
        except Exception as e:
            logger.error(f"Error getting user trades: {e}")
            return []
    
    async def get_user_strategies(self, telegram_id: int) -> List[Dict]:
        """
        Get strategies for a user
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            List of strategies
        """
        try:
            # Get user ID
            user = await self._get_user(telegram_id)
            if not user:
                return []
                
            user_id = user.get("id")
            
            # Get strategies from database
            async with bot_db.conn.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT * FROM user_strategies
                    WHERE user_id = ?
                    """,
                    (user_id,)
                )
                
                strategies = []
                async for row in cursor:
                    columns = [column[0] for column in cursor.description]
                    strategy = dict(zip(columns, row))
                    
                    # Parse JSON fields
                    if strategy.get("config"):
                        strategy["config"] = json.loads(strategy["config"])
                    if strategy.get("performance"):
                        strategy["performance"] = json.loads(strategy["performance"])
                        
                    strategies.append(strategy)
                    
                return strategies
                
        except Exception as e:
            logger.error(f"Error getting user strategies: {e}")
            return []
    
    async def create_trading_session(self, telegram_id: int) -> Optional[Dict]:
        """
        Create a trading session for a user
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            Session data or None if creation failed
        """
        try:
            # Get wallet info
            wallet = await self.get_user_wallet(telegram_id)
            if not wallet:
                logger.error(f"No wallet found for user {telegram_id}")
                return None
                
            # Trading must be enabled
            if wallet.get("status") != "trading":
                logger.error(f"Trading not enabled for user {telegram_id}")
                return None
                
            # Get agent private key
            agent_address = wallet.get("agent_wallet_address")
            private_key = await bot_db.get_agent_private_key(
                telegram_id, 
                agent_address,
                access_reason="trading_session"
            )
            
            if not private_key:
                logger.error(f"Could not retrieve private key for user {telegram_id}")
                return None
            
            # Create session
            user_account = Account.from_key(private_key)
            
            # Create Exchange instance
            exchange = Exchange(
                wallet=user_account,
                base_url=self.base_url,
                account_address=agent_address
            )
            
            # Create Info instance (could share a common one)
            info = Info(self.base_url)
            
            # Return session data
            return {
                "telegram_id": telegram_id,
                "agent_address": agent_address,
                "exchange": exchange,
                "info": info,
                "created_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error creating trading session: {e}")
            return None
    
    async def _get_user(self, telegram_id: int) -> Optional[Dict]:
        """
        Get user data from database
        
        Args:
            telegram_id: Telegram user ID
            
        Returns:
            User data or None if not found
        """
        try:
            # Check cache first
            if telegram_id in self.user_cache:
                return self.user_cache[telegram_id]
                
            # Get from database
            async with bot_db.conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT * FROM users WHERE telegram_id = ?",
                    (telegram_id,)
                )
                
                user = await cursor.fetchone()
                if not user:
                    return None
                    
                columns = [column[0] for column in cursor.description]
                user_data = dict(zip(columns, user))
                
                # Update cache
                self.user_cache[telegram_id] = user_data
                
                return user_data
                
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def _validate_address_format(self, address: str) -> bool:
        """
        Validate Ethereum address format
        
        Args:
            address: Ethereum address to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not address:
            return False
            
        # Basic format check
        address_pattern = re.compile(r'^0x[a-fA-F0-9]{40}$')
        return bool(address_pattern.match(address))
    
    def _generate_private_key(self) -> str:
        """
        Generate a new private key
        
        Returns:
            New private key as hex string
        """
        account = Account.create()
        return account.key.hex()
    
    async def add_agent_wallet(self, telegram_id: int, agent_address: str,
                             main_address: str, private_key: str) -> Dict:
        """
        Add agent wallet to user
        Encrypts the private key before storage
        """
        if not bot_db.conn:
            await bot_db.initialize()
            
        # Encrypt private key
        encrypted_key = bot_db.encrypt_private_key(private_key)
        
        try:
            # First, check if users table has agent_wallet_address column
            async with bot_db.conn.cursor() as cursor:
                # Check if the column exists
                await cursor.execute("PRAGMA table_info(users)")
                columns = await cursor.fetchall()
                column_names = [col[1] for col in columns]
                
                # Add column if it doesn't exist
                if "agent_wallet_address" not in column_names:
                    await cursor.execute("ALTER TABLE users ADD COLUMN agent_wallet_address TEXT")
                    await bot_db.conn.commit()
                    logger.info("Added agent_wallet_address column to users table")
                
                if "agent_private_key" not in column_names:
                    await cursor.execute("ALTER TABLE users ADD COLUMN agent_private_key TEXT")
                    await bot_db.conn.commit()
                    logger.info("Added agent_private_key column to users table")
                
            # Now update the user with agent wallet info
            async with bot_db.conn.cursor() as cursor:
                # Update user with agent wallet info
                await cursor.execute(
                    """
                    UPDATE users SET
                        hyperliquid_main_address = ?,
                        agent_wallet_address = ?,
                        agent_private_key = ?,
                        status = ?,
                        last_active = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                    """,
                    (main_address, agent_address, encrypted_key, "pending_approval", telegram_id)
                )
                
                # Create approval record
                await cursor.execute(
                    """
                    INSERT INTO approvals (
                        user_id, approval_type, status, metadata
                    ) VALUES (
                        (SELECT id FROM users WHERE telegram_id = ?),
                        'agent_wallet', 'pending', ?
                    )
                    """,
                    (telegram_id, json.dumps({
                        "agent_address": agent_address,
                        "main_address": main_address,
                        "created_at": datetime.now().isoformat()
                    }))
                )
                
                await bot_db.conn.commit()
                
                # Return updated user data
                await cursor.execute(
                    """
                    SELECT id, telegram_id, hyperliquid_main_address, 
                           agent_wallet_address, status
                    FROM users WHERE telegram_id = ?
                    """, 
                    (telegram_id,)
                )
                user_data = await cursor.fetchone()
                if user_data:
                    columns = [column[0] for column in cursor.description]
                    return dict(zip(columns, user_data))
                
                return {
                    "status": "success", 
                    "message": "Agent wallet added successfully, but couldn't retrieve updated user data"
                }
                
        except Exception as e:
            logger.error(f"Error adding agent wallet: {e}")
            return {
                "status": "error",
                "message": f"Database error: {str(e)}"
            }
