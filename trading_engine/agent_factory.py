"""
Agent Factory for creating and managing agent wallets
"""
import asyncio
import json
import logging
import os
import time
from typing import Dict, Optional, List
from eth_account import Account
from eth_account.signers.local import LocalAccount
from datetime import datetime

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Import database conditionally to handle the undefined bot_db
try:
    from database import bot_db
except ImportError:
    bot_db = None
    
logger = logging.getLogger(__name__)

class AgentFactory:
    """
    Factory for creating and managing agent wallets
    Provides secure agent wallet creation and management without exposing private keys
    """
    
    def __init__(self, master_private_key: str = None, base_url: str = None):
        """
        Initialize the Agent Factory
        
        Args:
            master_private_key: Master private key for creating agent wallets
            base_url: Base URL for Hyperliquid API
        """
        self.base_url = base_url or constants.MAINNET_API_URL
        self.master_private_key = master_private_key
        self.master_account = None
        self.master_exchange = None
        
        # Cache of agent wallets and exchanges
        self.agent_wallets = {}
        self.agent_exchanges = {}
        
        if master_private_key:
            try:
                self.master_account = Account.from_key(master_private_key)
                self.master_exchange = Exchange(
                    wallet=self.master_account,
                    base_url=self.base_url
                )
            except Exception as e:
                logger.error(f"Error initializing master account: {e}")
                
        self.user_agents = {}  # {user_id: Exchange instance}
        self.agent_details = {}  # {user_id: {address, key, etc}}
        self.last_balance_check = {}  # {user_id: timestamp}
        
        # Define storage path
        self.storage_path = os.path.join(os.path.dirname(__file__), "agent_wallets.json")
        
        # Set up master wallet for approvals
        try:
            if master_private_key:
                # Handle private key with or without 0x prefix
                if master_private_key.startswith('0x'):
                    self.master_wallet = Account.from_key(master_private_key)
                else:
                    self.master_wallet = Account.from_key(f"0x{master_private_key}")
                    
                # Create exchange instance for master wallet
                self.master_exchange = Exchange(
                    wallet=self.master_wallet,
                    base_url=self.base_url
                )
                
                logger.info(f"AgentFactory initialized with master wallet: {self.master_wallet.address}")
                
                # Create info client for market data queries
                self.info = Info(self.base_url)
                
                # Load existing agent details from storage
                self._load_agent_details()
            else:
                logger.warning("No master private key provided, agent creation will be limited")
                self.master_wallet = None
                self.info = Info(self.base_url)
                
        except Exception as e:
            logger.error(f"Error initializing AgentFactory: {e}")
            # Create placeholder but non-functional values to avoid errors
            self.master_wallet = None
            self.master_exchange = None
            self.info = Info(self.base_url)
    
    async def initialize(self) -> bool:
        """Initialize the agent factory"""
        try:
            # Test connection to info API
            if self.info:
                _ = self.info.meta()
                
            # Test master wallet if available
            if self.master_wallet and self.master_exchange:
                logger.info(f"Testing master wallet connection: {self.master_wallet.address}")
                
            return True
        except Exception as e:
            logger.error(f"Error initializing AgentFactory: {e}")
            return False
    
    def _load_agent_details(self) -> None:
        """Load agent details from storage file"""
        if not os.path.exists(self.storage_path):
            # Create empty storage file if it doesn't exist
            with open(self.storage_path, 'w') as f:
                json.dump({}, f)
            return
            
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
                
            # Convert string user_ids to integers
            self.agent_details = {int(user_id): details for user_id, details in data.items()}
            
            agent_count = len(self.agent_details)
            if agent_count > 0:
                logger.info(f"Loaded {agent_count} agent wallet details from storage")
                
        except Exception as e:
            logger.error(f"Error loading agent details: {e}")
            self.agent_details = {}
    
    def _save_agent_details(self) -> None:
        """Save agent details to storage file"""
        try:
            with open(self.storage_path, 'w') as f:
                # Convert user_ids to strings for JSON serialization
                data = {str(user_id): details for user_id, details in self.agent_details.items()}
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving agent details: {e}")
    
    async def create_user_agent(self, user_id: int, user_main_address: str) -> Dict:
        """
        Create agent wallet for specific user
        
        Args:
            user_id: User ID (e.g., Telegram ID)
            user_main_address: User's main Hyperliquid address
            
        Returns:
            Dict with agent details
        """
        # Check if agent already exists for this user
        if user_id in self.agent_details:
            return {
                "status": "exists",
                "message": "Agent wallet already exists for this user",
                "agent_address": self.agent_details[user_id].get("address")
            }
            
        # Check if master wallet is properly initialized
        if not self.master_wallet or not self.master_exchange:
            return {
                "status": "error",
                "message": "Master wallet not properly initialized"
            }
        
        try:
            # First, verify if master wallet has sufficient funds
            try:
                if self.info:
                    master_state = self.info.user_state(self.master_wallet.address)
                    master_balance = float(master_state.get("marginSummary", {}).get("accountValue", 0))
                    
                    if master_balance < 1.0:  # Require at least $1 USDC for agent creation fees
                        logger.error(f"Master wallet has insufficient funds: ${master_balance}")
                        return {
                            "status": "error",
                            "message": "Master wallet has insufficient funds to create agent. Please fund the master wallet."
                        }
            except Exception as balance_e:
                logger.warning(f"Could not verify master wallet balance: {balance_e}")
            
            # Generate agent name for better tracking
            agent_name = f"tg_{user_id}_{int(time.time() % 10000)}"
            
            # Create approval transaction for agent wallet
            logger.info(f"Creating agent wallet for user {user_id} with name {agent_name}")
            approve_result, agent_key = self.master_exchange.approve_agent(agent_name)
            
            # Check if agent creation was successful
            if not isinstance(approve_result, dict) or approve_result.get("status") != "ok":
                error_message = "Unknown error"
                
                # Extract detailed error information
                if isinstance(approve_result, dict):
                    if "message" in approve_result:
                        error_message = approve_result["message"]
                    elif "error" in approve_result:
                        error_message = approve_result["error"]
                    elif "response" in approve_result and isinstance(approve_result["response"], dict):
                        if "error" in approve_result["response"]:
                            error_message = approve_result["response"]["error"]
                elif isinstance(approve_result, str):
                    error_message = approve_result
                
                # Check for specific error conditions
                if "deposit" in str(error_message).lower():
                    error_message = f"Master wallet needs funding before creating agent wallets: {error_message}"
                    
                logger.error(f"Error creating agent wallet: {error_message}")
                return {
                    "status": "error",
                    "message": f"Failed to create agent wallet: {error_message}"
                }
            
            if not agent_key:
                logger.error("No agent key returned")
                return {
                    "status": "error",
                    "message": "No agent key returned"
                }
            
            # Convert key to account
            agent_account = Account.from_key(agent_key)
            agent_address = agent_account.address
            
            # Store agent details
            agent_details = {
                "address": agent_address,
                "key": agent_key,
                "name": agent_name,
                "main_address": user_main_address,
                "created_at": datetime.now().isoformat(),
                "status": "active"
            }
            
            self.agent_details[user_id] = agent_details
            self._save_agent_details()
            
            # Store in database if available
            if bot_db:
                try:
                    await bot_db.add_agent_wallet(
                        user_id, 
                        agent_address, 
                        user_main_address,
                        agent_key
                    )
                except Exception as db_error:
                    logger.error(f"Error storing agent wallet in database: {db_error}")
            
            logger.info(f"Created agent wallet {agent_address} for user {user_id}")
            
            return {
                "status": "success",
                "message": "Agent wallet created successfully",
                "agent_address": agent_address,
                "agent_name": agent_name
            }
            
        except Exception as e:
            logger.error(f"Error creating user agent: {e}")
            return {
                "status": "error",
                "message": f"Error creating agent wallet: {str(e)}"
            }
    
    async def get_user_exchange(self, user_id: int) -> Optional[Exchange]:
        """
        Get Exchange instance for specific user
        
        Args:
            user_id: User ID
            
        Returns:
            Exchange instance or None if not found
        """
        # Return cached exchange if available
        if user_id in self.user_agents:
            return self.user_agents[user_id]
            
        # Check if agent details exist
        if user_id not in self.agent_details:
            logger.warning(f"No agent details found for user {user_id}")
            return None
        
        try:
            # Get agent details
            agent_details = self.agent_details[user_id]
            agent_key = agent_details["key"]
            
            # Create agent account
            agent_account = Account.from_key(agent_key)
            
            # Create exchange instance
            exchange = Exchange(
                wallet=agent_account,
                base_url=self.base_url,
                account_address=agent_details["address"]
            )
            
            # Cache the exchange instance
            self.user_agents[user_id] = exchange
            
            return exchange
            
        except Exception as e:
            logger.error(f"Error creating exchange for user {user_id}: {e}")
            return None
    
    async def fund_detection(self, user_id: int) -> Dict:
        """
        Check if user has funded their agent wallet
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with funding status and amount
        """
        # Check if agent details exist
        if user_id not in self.agent_details:
            return {
                "status": "error",
                "message": "No agent wallet found for this user",
                "funded": False,
                "balance": 0
            }
        
        # Rate limit balance checks (no more than once every 30 seconds per user)
        current_time = time.time()
        if user_id in self.last_balance_check:
            last_check = self.last_balance_check[user_id]
            if current_time - last_check < 30:
                # Return cached result if available
                if "last_balance" in self.agent_details[user_id]:
                    balance = self.agent_details[user_id]["last_balance"]
                    funded = balance > 0
                    return {
                        "status": "success",
                        "message": "Using cached balance",
                        "funded": funded,
                        "balance": balance
                    }
        
        try:
            # Get agent address
            agent_address = self.agent_details[user_id]["address"]
            
            # Check balance using info client
            user_state = self.info.user_state(agent_address)
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Update last check timestamp
            self.last_balance_check[user_id] = current_time
            
            # Store balance in agent details
            self.agent_details[user_id]["last_balance"] = account_value
            self.agent_details[user_id]["last_checked"] = current_time
            self._save_agent_details()
            
            # Update database if available
            if bot_db:
                try:
                    await bot_db.update_wallet_balance(user_id, account_value)
                except Exception as db_error:
                    logger.error(f"Error updating wallet balance in database: {db_error}")
            
            funded = account_value > 0
            funding_status = {
                "status": "success",
                "funded": funded,
                "balance": account_value,
                "address": agent_address
            }
            
            if funded:
                funding_status["message"] = f"Wallet funded with ${account_value:,.2f}"
            else:
                funding_status["message"] = "Wallet not funded yet"
            
            return funding_status
            
        except Exception as e:
            logger.error(f"Error checking funding for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error checking wallet balance: {str(e)}",
                "funded": False,
                "balance": 0
            }
    
    async def get_agent_details(self, user_id: int) -> Dict:
        """
        Get agent wallet details for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with agent details or empty dict if not found
        """
        if user_id not in self.agent_details:
            return {}
            
        # Return a copy without sensitive data
        details = self.agent_details[user_id].copy()
        
        # Remove private key from returned data
        if "key" in details:
            details["has_key"] = bool(details["key"])
            del details["key"]
            
        return details
        
    async def list_agents(self) -> Dict:
        """
        Get list of all agent wallets
        
        Returns:
            Dict with agent statistics and list
        """
        agents = []
        for user_id, details in self.agent_details.items():
            # Create safe version without private key
            agent_info = {
                "user_id": user_id,
                "address": details.get("address"),
                "name": details.get("name"),
                "main_address": details.get("main_address"),
                "created_at": details.get("created_at")
            }
            
            # Add balance if available
            if "last_balance" in details:
                agent_info["balance"] = details["last_balance"]
                agent_info["last_checked"] = details.get("last_checked")
                
            agents.append(agent_info)
            
        return {
            "count": len(agents),
            "agents": agents
        }
    
    async def remove_agent(self, user_id: int) -> Dict:
        """
        Remove an agent wallet
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with removal status
        """
        if user_id not in self.agent_details:
            return {
                "status": "error",
                "message": "No agent wallet found for this user"
            }
        
        try:
            # Remove from agents cache
            if user_id in self.user_agents:
                del self.user_agents[user_id]
            
            # Remove from balance check cache
            if user_id in self.last_balance_check:
                del self.last_balance_check[user_id]
            
            # Get address for log
            agent_address = self.agent_details[user_id].get("address")
            
            # Remove from agent details and save
            del self.agent_details[user_id]
            self._save_agent_details()
            
            # Remove from database if available
            if bot_db:
                try:
                    # Implement database removal if needed
                    pass
                except Exception as db_error:
                    logger.error(f"Error removing agent wallet from database: {db_error}")
            
            logger.info(f"Removed agent wallet {agent_address} for user {user_id}")
            
            return {
                "status": "success",
                "message": "Agent wallet removed successfully"
            }
            
        except Exception as e:
            logger.error(f"Error removing agent for user {user_id}: {e}")
            return {
                "status": "error",
                "message": f"Error removing agent wallet: {str(e)}"
            }
    
    async def monitor_funds(self) -> None:
        """
        Background task to monitor funding for all agent wallets
        """
        try:
            # Check funding for all agent wallets
            for user_id in list(self.agent_details.keys()):
                try:
                    # Get funding status
                    funding = await self.fund_detection(user_id)
                    
                    # Log if wallet is funded
                    if funding["funded"]:
                        logger.info(f"Wallet for user {user_id} is funded: ${funding['balance']:,.2f}")
                        
                        # Here you could trigger notifications or callbacks
                        # when a wallet is funded
                        
                except Exception as e:
                    logger.error(f"Error monitoring funding for user {user_id}: {e}")
                
                # Sleep briefly between checks to avoid rate limits
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in monitor_funds: {e}")
    
    def get_agent_stats(self) -> Dict:
        """
        Get statistics about agent wallets
        
        Returns:
            Dict with statistics
        """
        total_agents = len(self.agent_details)
        total_funded = sum(1 for details in self.agent_details.values() 
                           if details.get("last_balance", 0) > 0)
        
        # Calculate total balance across all agents
        total_balance = sum(details.get("last_balance", 0) 
                            for details in self.agent_details.values())
        
        return {
            "total_agents": total_agents,
            "funded_agents": total_funded,
            "total_balance": total_balance,
            "master_wallet": self.master_wallet.address if self.master_wallet else None
        }
    
    async def close(self) -> None:
        """Clean up resources"""
        # Save latest agent details
        self._save_agent_details()
        logger.info("AgentFactory closed")
