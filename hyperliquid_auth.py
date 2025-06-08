"""
Production-grade Hyperliquid authentication module with agent wallet support
"""
import json
import os
import logging
import time
from typing import Tuple, Dict, Optional, Any
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Configure logging
logger = logging.getLogger(__name__)

class HyperliquidAuth:
    """Secure Hyperliquid authentication with agent wallet support"""
    
    def __init__(
        self, 
        config_dir: str = ".",
        config_file: str = "config.json",
        agent_config_file: str = "agent_config.json",
        network: str = "mainnet",
        auto_reconnect: bool = True,
        reconnect_interval: int = 300,  # 5 minutes
        max_retries: int = 3
    ):
        self.config_dir = os.path.abspath(config_dir) # Ensure absolute path
        self.config_path = os.path.join(self.config_dir, config_file)
        self.agent_config_path = os.path.join(self.config_dir, agent_config_file)
        
        # Network settings
        self.network = network
        self.base_url = constants.MAINNET_API_URL if network == "mainnet" else constants.TESTNET_API_URL
        
        # Connection state
        self.address = None
        self.info = None
        self.exchange = None
        self.connected = False
        self.last_connected = 0
        self.connection_attempts = 0
        
        # Reconnection settings
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.max_retries = max_retries
        
    def connect(self, force_refresh: bool = False) -> Tuple[str, Info, Exchange]:
        """
        Connect to Hyperliquid API with agent wallet if available
        
        Args:
            force_refresh: Force a new connection even if recently connected
            
        Returns:
            Tuple of (address, info, exchange)
            
        Raises:
            ValueError: If authentication fails
            ConnectionError: If API connection fails
        """
        # Check if already connected and not forced refresh
        current_time = time.time()
        if (
            self.connected and 
            self.address and self.info and self.exchange and # Ensure all components are set
            not force_refresh and 
            (current_time - self.last_connected) < self.reconnect_interval
        ):
            logger.debug(f"Using existing connection for {self.address} on {self.network}")
            return self.address, self.info, self.exchange
        
        # Reset connection state
        self.connected = False
        # Only increment connection_attempts if not forcing a refresh of an already established connection logic path
        # or if it's a genuine new attempt.
        if not (self.address and self.info and self.exchange and force_refresh):
             self.connection_attempts += 1
        
        if self.connection_attempts > self.max_retries:
            self.connection_attempts = 0 # Reset for future attempts after external delay
            logger.error(f"Failed to connect to {self.network} after {self.max_retries} attempts. Max retries exceeded.")
            raise ConnectionError(f"Failed to connect to {self.network} after {self.max_retries} attempts")
        
        try:
            logger.info(f"Attempting to connect to {self.network}. Attempt {self.connection_attempts}/{self.max_retries}.")
            # First try agent wallet authentication
            if os.path.exists(self.agent_config_path):
                logger.info(f"Agent config found at {self.agent_config_path}. Attempting agent connection.")
                result = self._connect_with_agent()
                if result:
                    self.address, self.info, self.exchange = result
                    self.connected = True
                    self.last_connected = current_time
                    self.connection_attempts = 0 # Reset on successful connection
                    logger.info(f"Successfully connected as agent for main address {self.address} on {self.network}.")
                    return self.address, self.info, self.exchange
                else:
                    logger.warning(f"Agent connection failed using {self.agent_config_path}. Falling back.")
            else:
                logger.info(f"Agent config not found at {self.agent_config_path}. Proceeding to direct authentication.")
            
            # Fall back to direct authentication
            logger.info(f"Attempting direct connection using {self.config_path}.")
            result = self._connect_direct()
            if result:
                self.address, self.info, self.exchange = result
                self.connected = True
                self.last_connected = current_time
                self.connection_attempts = 0 # Reset on successful connection
                logger.info(f"Successfully connected with direct key for address {self.address} on {self.network}.")
                return self.address, self.info, self.exchange
            
            logger.error(f"Failed to authenticate with Hyperliquid on {self.network}. Neither agent nor direct connection succeeded.")
            raise ValueError(f"Failed to authenticate with Hyperliquid on {self.network}")
            
        except Exception as e:
            logger.error(f"Authentication error on {self.network} (attempt {self.connection_attempts}): {e}")
            if self.auto_reconnect and self.connection_attempts < self.max_retries: # Check max_retries here
                logger.info(f"Will retry connection to {self.network} in {self.reconnect_interval} seconds if connect() is called again.")
                time.sleep(1) # Small delay to prevent rapid retry loops if called in a tight loop
            raise
    
    def _connect_with_agent(self) -> Optional[Tuple[str, Info, Exchange]]:
        """Connect using agent wallet"""
        try:
            logger.info(f"Attempting agent wallet authentication for {self.network} using {self.agent_config_path}")
            
            # Load agent configuration
            with open(self.agent_config_path, "r") as f:
                agent_config = json.load(f)
            
            # Validate agent config
            required_fields = ["main_address", "agent_key", "agent_address", "network"]
            for field in required_fields:
                if field not in agent_config:
                    logger.error(f"Agent config {self.agent_config_path} missing required field: {field}")
                    return None
            
            # Check if agent config matches network
            if agent_config["network"] != self.network:
                logger.warning(f"Agent wallet at {self.agent_config_path} is for {agent_config['network']}, but current context is {self.network}. This may lead to issues.")
            
            # Create agent account
            agent_key = agent_config["agent_key"]
            agent_account: LocalAccount = eth_account.Account.from_key(agent_key)
            main_address = agent_config["main_address"]
            
            # Verify agent key matches expected address
            if agent_account.address.lower() != agent_config["agent_address"].lower():
                logger.error(f"Agent address mismatch in {self.agent_config_path}: derived {agent_account.address}, configured {agent_config['agent_address']}")
                return None
            
            # Create info and exchange instances
            info = Info(self.base_url, skip_ws=True)
            exchange = Exchange(
                wallet=agent_account,
                base_url=self.base_url,
                vault_address=main_address # Corrected: Use vault_address for agent's main account
            )
            
            # Test connection
            try:
                user_state = info.user_state(main_address)
                account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
                logger.info(f"Connected to {self.network} using agent wallet for main address {main_address}")
                logger.info(f"Agent address: {agent_account.address}")
                logger.info(f"Account value: ${account_value:.2f}")
            except Exception as e:
                logger.error(f"Agent connection test failed for main address {main_address}: {e}")
                return None
            
            return main_address, info, exchange
            
        except FileNotFoundError:
            logger.info(f"Agent config file not found at {self.agent_config_path}. Cannot connect as agent.")
            return None
        except Exception as e:
            logger.error(f"Agent wallet authentication for {self.network} failed: {e}", exc_info=True)
            return None
    
    def _connect_direct(self) -> Optional[Tuple[str, Info, Exchange]]:
        """Connect using direct wallet authentication"""
        try:
            logger.info(f"Attempting direct wallet authentication for {self.network} using {self.config_path}")
            
            # Check if config exists
            if not os.path.exists(self.config_path):
                # Try to load from environment variable if config file not found
                pk_env = os.environ.get("HYPERLIQUID_PRIVATE_KEY")
                if not pk_env:
                    logger.error(f"Direct config file not found: {self.config_path} and HYPERLIQUID_PRIVATE_KEY env var not set.")
                    return None
                logger.info("Using HYPERLIQUID_PRIVATE_KEY environment variable for direct authentication.")
                private_key = pk_env
                # account_address from env is optional, if the key is for a different address (e.g. vault)
                account_address_config = os.environ.get("HYPERLIQUID_ACCOUNT_ADDRESS", "") 
            else:
                # Load config from file
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                
                # Validate config
                if "secret_key" not in config: # Ensure this key matches what setup_agent.py writes
                    logger.error(f"Config {self.config_path} missing required field: secret_key")
                    return None
                
                private_key = config["secret_key"]
                account_address_config = config.get("account_address", "") # Optional account_address from config
            
            # Create account
            account: LocalAccount = eth_account.Account.from_key(private_key)
            derived_address = account.address
            
            # Determine effective address for operations
            effective_address = derived_address
            if account_address_config and account_address_config.lower() != derived_address.lower():
                logger.warning(f"Address mismatch: configured '{account_address_config}', derived from key '{derived_address}'. Using derived address for operations by default unless SDK behavior implies otherwise for account_address in Exchange.")
                # If account_address_config is meant to be the address Exchange operates on, and 'account' is just the signer:
                effective_address = account_address_config 
            elif account_address_config: # If configured address matches derived, use it (ensures checksum matching if provided)
                 effective_address = account_address_config

            # Create info and exchange instances
            info = Info(self.base_url, skip_ws=True)
            exchange = Exchange(
                wallet=account,
                base_url=self.base_url,
                # If account_address_config is set and different, it means 'wallet' signs for 'account_address_config'
                account_address=account_address_config if account_address_config and account_address_config.lower() != derived_address.lower() else None
            )
            
            # Test connection against the effective_address the exchange will operate on
            # If exchange.account_address is set, operations target that. Otherwise, they target wallet.address.
            target_query_address = exchange.account_address if exchange.account_address else account.address

            try:
                user_state = info.user_state(target_query_address)
                account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
                logger.info(f"Connected to {self.network} using direct wallet authentication for address {target_query_address}")
                logger.info(f"Account value: ${account_value:.2f}")
            except Exception as e:
                logger.error(f"Direct connection test failed for address {target_query_address}: {e}")
                return None
            
            return target_query_address, info, exchange # Return the address that was successfully queried
            
        except FileNotFoundError: # Should be caught by os.path.exists or env var check
             logger.info(f"Direct config file not found at {self.config_path} and env var not used. Cannot connect directly.")
             return None
        except Exception as e:
            logger.error(f"Direct wallet authentication for {self.network} failed: {e}", exc_info=True)
            return None
    
    def create_agent_wallet(self, agent_name: str = "trading_bot") -> Dict[str, Any]:
        """
        Create a new agent wallet for enhanced security
        
        Args:
            agent_name: Name for the agent wallet
            
        Returns:
            Dict with agent wallet information
            
        Raises:
            ValueError: If agent creation fails
        """
        try:
            # Connect with direct authentication first
            # This uses _connect_direct which reads from self.config_path or env var
            direct_auth_result = self._connect_direct()
            if not direct_auth_result:
                raise ValueError("Direct authentication (e.g. via config.json or HYPERLIQUID_PRIVATE_KEY) required to create agent wallet.")
            
            main_account_address, _, main_exchange_instance = direct_auth_result
            
            # Create agent wallet
            logger.info(f"Creating agent wallet '{agent_name}' on {self.network} for main account {main_account_address}.")
            approve_result, agent_key = main_exchange_instance.approve_agent(agent_name)
            
            if approve_result.get("status") != "ok": # Check specific status field
                error_detail = approve_result.get("response", {}).get("error", str(approve_result))
                raise ValueError(f"Failed to create agent wallet '{agent_name}': {error_detail}")
            
            # Create agent account
            agent_account: LocalAccount = eth_account.Account.from_key(agent_key)
            agent_wallet_address = agent_account.address
            
            logger.info(f"Agent wallet '{agent_name}' created successfully on {self.network}. Agent Address: {agent_wallet_address}")
            
            # Save agent configuration
            agent_config_data = {
                "main_address": main_account_address,
                "agent_name": agent_name,
                "agent_address": agent_wallet_address,
                "agent_key": agent_key,
                "network": self.network,
                "created_at": int(time.time())
            }
            
            # Ensure config_dir exists before writing agent_config.json
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.agent_config_path, "w") as f:
                json.dump(agent_config_data, f, indent=2)
            
            # Set proper file permissions
            try:
                os.chmod(self.agent_config_path, 0o600)  # Read/write for owner only
            except Exception as e_perm: # Specific exception variable
                logger.warning(f"Could not set file permissions for {self.agent_config_path}: {e_perm}")
            
            logger.info(f"Agent configuration for '{agent_name}' saved to {self.agent_config_path}")
            
            return agent_config_data
            
        except Exception as e:
            logger.error(f"Failed to create agent wallet '{agent_name}' on {self.network}: {e}", exc_info=True)
            # Raise a more specific error or re-raise
            raise ValueError(f"Agent wallet creation for '{agent_name}' failed on {self.network}: {e}")
    
    def check_connection(self) -> bool:
        """
        Check if connection is still valid
        
        Returns:
            True if connected, False otherwise
        """
        if not self.connected or not self.info or not self.address: # Check all components
            self.connected = False # Ensure consistent state
            return False
        
        try:
            # Simple API call to verify connection using the established address
            user_state = self.info.user_state(self.address)
            is_valid = "marginSummary" in user_state # More robust check
            if not is_valid:
                self.connected = False # Update state if check fails
            return is_valid
        except Exception as e: # Catch specific exceptions if possible, or general Exception
            logger.warning(f"Connection check failed for {self.address} on {self.network}: {e}")
            self.connected = False
            return False
    
    def reconnect_if_needed(self) -> bool:
        """
        Reconnect if connection is lost or expired
        
        Returns:
            True if reconnection succeeded, False otherwise
        """
        if self.check_connection():
            return True
        
        logger.info(f"Reconnection needed for {self.network}. Attempting to reconnect...")
        try:
            self.connection_attempts = 0 # Reset attempts for a fresh cycle
            self.connect(force_refresh=True) # connect() handles its own retry logic
            return self.connected # Return the new connection status
        except Exception as e:
            logger.error(f"Reconnection attempt failed for {self.network}: {e}")
            self.connected = False # Ensure disconnected state on failure
            return False

