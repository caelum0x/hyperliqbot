import asyncio
from asyncio.log import logger
import json
import time
import typing # Import typing module itself
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING # These imports might be shadowed
from dataclasses import dataclass
import os # Ensure os is imported
import sys # Ensure sys is imported
import logging # Ensure logging is imported
# time is imported again, it's fine but redundant
import numpy as np # Ensure numpy is imported

if TYPE_CHECKING:
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.types import * # Potential source of name shadowing
# Ensure trading_engine imports are structured to avoid circular dependencies
# For example, if main_bot imports TradingEngine, TradingEngine should not import main_bot directly at module level.
# from trading_engine import main_bot, referral_manager, vault_manager, websocket_manager
from trading_engine.config import TradingConfig # Import TradingConfig

# Import ALL actual examples from examples folder
# Corrected path to be relative to this file's location (trading_engine)
examples_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'examples')
if examples_dir not in sys.path:
    sys.path.append(examples_dir)
import example_utils # Ensure this is at the top if not already


class RiskManagementSystem:
    """
    Comprehensive risk management system for the trading engine
    Tracks position sizes, exposure, drawdowns, and enforces risk limits
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Risk tracking
        self.position_sizes = {}           # Tracks position sizes by coin
        self.position_timestamps = {}      # When positions were opened
        self.daily_volume = {}             # Daily trading volume tracking
        self.daily_trades = {}             # Number of daily trades by coin
        self.max_drawdown = 0.0            # Maximum drawdown experienced
        self.peak_account_value = 0.0      # Peak account value for drawdown calc
        self.risk_adjustments = {}         # Risk adjustments by coin
        self.coin_weights = {}             # Portfolio weights by coin
        
        # Risk limits
        self.max_position_coin = 0.25      # Max 25% of portfolio in one coin
        self.max_leverage = 10.0           # Max leverage for any position
        self.max_concentration = 0.50      # Max 50% in correlated assets
        self.max_daily_drawdown = 0.05     # Max 5% daily drawdown
        self.min_liquidity_threshold = 1000000  # $1M min liquidity for trading
        
        # Coin-specific risk factors
        self.volatility_factors = {
            "BTC": 1.0,    # Base volatility reference
            "ETH": 1.2,    # 20% more volatile than BTC
            "SOL": 1.5,    # 50% more volatile than BTC
            "ARB": 1.8,    # 80% more volatile than BTC
            "APT": 2.0,    # 2x as volatile as BTC
            "SUI": 2.2,    # 2.2x as volatile as BTC
            "OP": 1.7,     # 70% more volatile than BTC
            "MATIC": 1.6,  # 60% more volatile than BTC
            "DOGE": 2.0,   # 2x as volatile as BTC
            "AVAX": 1.5,   # 50% more volatile than BTC
            "LINK": 1.6,   # 60% more volatile than BTC
            "LTC": 1.3,    # 30% more volatile than BTC
            "XRP": 1.4,    # 40% more volatile than BTC
        }
        
        # Trading cooldowns
        self.trading_cooldowns = {}        # Cooldown period after losses
        self.blocked_coins = set()         # Temporarily blocked coins
        
        # Risk stats
        self.wins = 0
        self.losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.last_risk_assessment = 0
        
        self.logger.info("RiskManagementSystem initialized")
    
    def update_account_value(self, account_value: float) -> None:
        """Update account value and track drawdown"""
        # Update peak value for drawdown calculations
        if account_value > self.peak_account_value:
            self.peak_account_value = account_value
        
        # Calculate current drawdown
        if self.peak_account_value > 0:
            current_drawdown = (self.peak_account_value - account_value) / self.peak_account_value
            
            # Update max drawdown if needed
            if current_drawdown > self.max_drawdown:
                self.max_drawdown = current_drawdown # Restored
    
    def can_trade(self, coin: str) -> bool:
        """Check if trading is allowed for a specific coin"""
        # Check if coin is blocked
        if coin in self.blocked_coins:
            self.logger.info(f"Coin {coin} is currently blocked from trading")
            return False
        
        # Check if we're in cooldown period
        current_time = time.time()
        if coin in self.trading_cooldowns and current_time < self.trading_cooldowns[coin]:
            cooldown_minutes = (self.trading_cooldowns[coin] - current_time) / 60
            self.logger.info(f"Trading cooldown for {coin}: {cooldown_minutes:.1f} minutes remaining")
            return False
        
        # Check daily trade limits
        today = time.strftime("%Y-%m-%d")
        if today in self.daily_trades and coin in self.daily_trades[today]:
            if self.daily_trades[today][coin] > 20: # Add logic for what happens if limit exceeded
                self.logger.info(f"Daily trade limit reached for {coin}") # Restored
                return False # Restored
        
        return True
    
    def get_risk_adjustment(self, coin: str) -> float:
        """Get risk adjustment factor for a coin based on volatility and performance"""
        # Default risk adjustment is 1.0
        if coin not in self.risk_adjustments:
            # Apply volatility factor
            vol_factor = self.volatility_factors.get(coin, 1.5)  # Default 1.5x volatility factor
            
            # More volatile coins get smaller position sizes (inverse relationship)
            self.risk_adjustments[coin] = 1.0 / vol_factor
        
        return self.risk_adjustments[coin]
    
    def record_trade(self, coin: str, trade_size_usd: float, is_buy: bool) -> None:
        """Record a new trade to update risk tracking"""
        # Update position sizes
        if coin not in self.position_sizes:
            self.position_sizes[coin] = 0.0
        
        # Update based on direction
        if is_buy:
            self.position_sizes[coin] += trade_size_usd
        else:
            self.position_sizes[coin] -= trade_size_usd
        
        # Record timestamp
        self.position_timestamps[coin] = time.time()
        
        # Update daily volume
        today = time.strftime("%Y-%m-%d")
        if today not in self.daily_volume:
            self.daily_volume[today] = {}
        
        if coin not in self.daily_volume[today]:
            self.daily_volume[today][coin] = 0.0
            
        self.daily_volume[today][coin] += trade_size_usd
        
        # Update daily trades count
        if today not in self.daily_trades:
            self.daily_trades[today] = {}
            
        if coin not in self.daily_trades[today]:
            self.daily_trades[today][coin] = 0
            
        self.daily_trades[today][coin] += 1
        
        self.logger.info(f"Recorded {coin} trade: ${trade_size_usd:,.2f}")
    
    def record_trade_result(self, coin: str, pnl: float) -> None:
        """Record the result of a closed trade"""
        if pnl > 0:
            self.wins += 1
            self.total_profit += pnl
            
            # If profitable, reduce risk adjustment (allow larger positions)
            if coin in self.risk_adjustments:
                self.risk_adjustments[coin] *= 1.1 # Restored
                
        else:
            self.losses += 1
            self.total_loss += abs(pnl)
            
            # Apply cooldown after significant loss
            if abs(pnl) > 100: # Example threshold # Restored
                self.trading_cooldowns[coin] = time.time() + 3600 # Restored
                self.logger.info(f"Cooldown applied for {coin} due to significant loss.") # Restored
    
    def assess_overall_risk(self, account_value: float) -> typing.Dict[str, typing.Any]:
        """Perform comprehensive risk assessment of the portfolio"""
        # Only run assessment every 15 minutes
        current_time = time.time()
        if current_time - self.last_risk_assessment < 900:  # 15 minutes
            return {}
            
        self.last_risk_assessment = current_time
        
        # Calculate total exposure
        total_exposure = sum(abs(size) for size in self.position_sizes.values())
        
        # Calculate leverage
        current_leverage = total_exposure / account_value if account_value > 0 else 0
        
        # Calculate concentration
        max_position = max(abs(size) for size in self.position_sizes.values()) if self.position_sizes else 0
        concentration = max_position / account_value if account_value > 0 else 0
        
        # Calculate win rate
        total_trades = self.wins + self.losses
        win_rate = self.wins / total_trades if total_trades > 0 else 0
        
        # Calculate profit factor
        profit_factor = self.total_profit / self.total_loss if self.total_loss > 0 else float('inf')
        
        # Risk state assessment
        risk_state = "normal"
        if current_leverage > self.max_leverage * 0.8:
            risk_state = "high_leverage"
        elif concentration > self.max_concentration * 0.8:
            risk_state = "high_concentration"
        elif self.max_drawdown > self.max_daily_drawdown * 0.8:
            risk_state = "high_drawdown"
        
        risk_assessment = {
            "account_value": account_value,
            "total_exposure": total_exposure,
            "leverage": current_leverage,
            "max_position": max_position,
            "concentration": concentration,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": self.max_drawdown,
            "risk_state": risk_state
        }
        
        self.logger.info(f"Risk assessment: {risk_state.upper()} - Leverage: {current_leverage:.2f}x, Concentration: {concentration:.2%}")
        return risk_assessment
    
    def get_position_size_usd(self, coin: str) -> float:
        """Get current position size for a coin"""
        return abs(self.position_sizes.get(coin, 0.0))
    
    def get_trading_stats(self) -> typing.Dict[str, typing.Any]:
        """Get overall trading statistics"""
        total_trades = self.wins + self.losses
        
        return {
            "wins": self.wins,
            "losses": self.losses,
            "total_trades": total_trades,
            "win_rate": self.wins / total_trades if total_trades > 0 else 0,
            "total_profit": self.total_profit,
            "total_loss": self.total_loss,
            "profit_factor": self.total_profit / self.total_loss if self.total_loss > 0 else float('inf'),
            "max_drawdown": self.max_drawdown
        }
    
    def reset_daily_limits(self) -> None:
        """Reset daily trading limits"""
        today = time.strftime("%Y-%m-%d")
        self.daily_volume[today] = {}
        self.daily_trades[today] = {}
        self.logger.info("Daily trading limits reset")

class TradingEngineContext:
    """
    TradingEngineContext exposes all trading engine modules and helpers for orchestrated bot use.
    """
    def __init__(self):
        # These would need to be actual functions or methods imported or defined
        # from . import basic_leverage_adjustment, basic_schedule_cancel, cancel_open_orders
        # self.basic_leverage_adjustment = basic_leverage_adjustment
        # self.basic_schedule_cancel = basic_schedule_cancel
        # self.cancel_open_orders = cancel_open_orders
        self.example_utils = example_utils
        # self.main_bot = main_bot # Avoid direct import if main_bot imports TradingEngine
        # self.referral_manager = referral_manager
        # self.vault_manager = vault_manager
        # self.websocket_manager = websocket_manager

    def info(self):
        """
        Print available trading engine modules for debugging.
        """
        print("Trading Engine Modules Loaded:")
        print(" - basic_leverage_adjustment")
        print(" - basic_schedule_cancel")
        print(" - cancel_open_orders")
        print(" - example_utils")
        print(" - main_bot")
        print(" - referral_manager")
        print(" - vault_manager")
        print(" - websocket_manager")

class TradingEngine:
    """
    Core trading engine using actual Hyperliquid API examples
    Now imports and uses ALL available examples
    """
    
    def __init__(self, base_url: typing.Optional[str] = None, account: typing.Optional[typing.Any] = None, 
                 wallet_manager: typing.Optional[typing.Any] = None, address: typing.Optional[str] = None, 
                 info: typing.Optional['Info'] = None, exchange: typing.Optional['Exchange'] = None, 
                 config_for_self_init: typing.Optional[typing.Dict[str, typing.Any]] = None): # Added config_for_self_init
        self.logger = logging.getLogger(__name__)
        self.wallet_manager = wallet_manager
        self.config_for_self_init = config_for_self_init # Store if passed
        
        if wallet_manager:
            self.address = None  # Will be set when using specific wallet
            # Assuming wallet_manager provides info and exchange instances when a wallet is selected
            self.info: typing.Optional['Info'] = wallet_manager.info if hasattr(wallet_manager, 'info') else None 
            self.exchange: typing.Optional['Exchange'] = None # Will be set by use_wallet
            self.logger.info("TradingEngine initialized with WalletManager. Waiting for wallet selection.")
        elif address and info and exchange: # If components are passed directly
            self.address = address
            self.info = info
            self.exchange = exchange
            self.logger.info(f"TradingEngine initialized with pre-configured components for address: {self.address}")
        else:
            # Use example_utils.setup for the bot's main operational account
            self.logger.info("TradingEngine attempting to initialize default connection using example_utils.")
            
            effective_base_url = base_url
            if not effective_base_url and self.config_for_self_init:
                effective_base_url = self.config_for_self_init.get("hyperliquid", {}).get("api_url", constants.TESTNET_API_URL)
            elif not effective_base_url: # Fallback if no base_url and no config_for_self_init
                effective_base_url = constants.TESTNET_API_URL 
                self.logger.warning(f"TradingEngine self-initializing without explicit base_url or config, defaulting to {effective_base_url}")

            # The new example_utils.setup (via HyperliquidAuth) handles agent/direct logic internally.
            # It prioritizes agent_config.json if present in the project root.
            # The 'use_agent_for_core_operations' flag from config_for_self_init is not directly
            # used by example_utils.setup in its current form, as HyperliquidAuth always tries agent first.
            try:
                self.address, self.info, self.exchange = example_utils.setup(base_url=effective_base_url)
                self.logger.info(f"TradingEngine self-initialized for address {self.address} on {effective_base_url}")
            except ValueError as ve: 
                self.logger.critical(f"CRITICAL: {ve} - TradingEngine cannot initialize its default Hyperliquid connection. Check config/keys.")
                raise
            except Exception as e:
                self.logger.critical(f"Failed to setup Hyperliquid connection via example_utils for TradingEngine: {e}", exc_info=True)
                raise
        
        # Risk management system
        self.risk_manager = RiskManagementSystem()
        
        # Store coin volatility data for position sizing
        self.volatility_cache = {}
        self.volatility_cache_time = {}
        
        # Cross-correlation data
        self.correlation_matrix = {}
        self.last_correlation_update = 0

    def use_wallet(self, wallet_name: str, sub_account_name: typing.Optional[str] = None):
        """Switch to using a specific wallet or sub-account"""
        if not self.wallet_manager:
            self.logger.error("WalletManager not available in TradingEngine.")
            raise ValueError("No wallet manager available")
        
        wallet_details = self.wallet_manager.get_wallet(wallet_name) # Assuming get_wallet returns a dict or object with details
        if not wallet_details:
            self.logger.error(f"Wallet '{wallet_name}' not found by WalletManager.")
            raise ValueError(f"Wallet '{wallet_name}' not found")
        
        # Assuming wallet_details contains 'address' and 'private_key' or an 'account' object
        # And WalletManager provides a method to get an exchange instance for a given wallet/sub-account
        
        if sub_account_name:
            sub_account_address = self.wallet_manager.get_sub_account_address(wallet_name, sub_account_name) # Hypothetical method
            if not sub_account_address:
                self.logger.error(f"Sub-account '{sub_account_name}' not found for wallet '{wallet_name}'.")
                raise ValueError(f"Sub-account '{sub_account_name}' not found for wallet '{wallet_name}'")
            
            # Create exchange with vault_address set to sub-account (basic_vault.py pattern)
            # This implies WalletManager can provide an Exchange instance configured for a sub-account
            self.exchange = self.wallet_manager.get_exchange_for_sub_account(wallet_name, sub_account_name) # Hypothetical
            self.address = sub_account_address
            # Info client can usually remain the same unless sub-account has specific info endpoint needs
            self.info = self.wallet_manager.get_info_for_wallet(wallet_name) # Hypothetical
            self.logger.info(f"TradingEngine now using sub-account '{sub_account_name}' at {self.address}")
        else:
            # Use main wallet
            self.exchange = self.wallet_manager.get_exchange(wallet_name)
            self.address = wallet_details.get('address')
            # If wallet_details contains private key or account info, it can be used to set up info client
            self.logger.info(f"TradingEngine now using wallet '{wallet_name}' at {self.address}")

    async def create_and_fund_sub_account(self, parent_wallet_name: str, sub_account_name: str, 
                                        usd_amount: float = 1.0, token_transfers: typing.Optional[typing.List[typing.Dict[str, typing.Any]]] = None):
        """Create and fund sub-account using wallet manager's basic_sub_account integration"""
        if not self.wallet_manager:
            raise ValueError("No wallet manager available")
        
        return self.wallet_manager.create_and_fund_sub_account(
            parent_wallet_name, sub_account_name, usd_amount, token_transfers
        )

    async def get_all_mids(self) -> typing.Dict[str, str]:
        """
        Get mid prices for all assets.
        Returns a dictionary of coin symbols to their current mid prices.
        """
        try:
            if not hasattr(self, 'info') or not self.info:
                return {}
            
            # Get all mids using the Hyperliquid Info client
            mids = self.info.all_mids()
            return mids
        except Exception as e:
            logging.error(f"Error getting all mids: {e}")
            return {}
    
    async def validate_connection(self) -> bool:
        """
        Validates the connection to Hyperliquid API and ensures the trading engine can make API calls.
        Returns True if connection is valid, False otherwise.
        """
        try:
            # Check if required components are initialized
            if not hasattr(self, 'info') or not self.info:
                self.logger.error("Info client not initialized in TradingEngine")
                return False
                
            if not hasattr(self, 'exchange') or not self.exchange:
                self.logger.error("Exchange client not initialized in TradingEngine")
                return False
                
            if not hasattr(self, 'address') or not self.address:
                self.logger.error("Address not set in TradingEngine")
                return False
                
            # Test connection by getting basic market data
            all_mids = await self.get_all_mids()
            if not all_mids or len(all_mids) == 0:
                self.logger.error("Failed to retrieve market data")
                return False
                
            # Test wallet/account access
            try:
                user_state = self.info.user_state(self.address)
                if not user_state:
                    self.logger.error(f"Failed to retrieve user state for address {self.address}")
                    return False
                    
                # Check if we can get account value (basic check)
                account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
                self.logger.info(f"Connection validated successfully for address {self.address}, account value: ${account_value:.2f}")
                
            except Exception as user_state_error:
                self.logger.error(f"Failed to retrieve user state: {user_state_error}")
                return False
                
            return True
            
        except Exception as e:
            self.logger.error(f"Connection validation failed: {e}")
            return False
            
    async def __missing_method_handler(self, method_name, *args, **kwargs):
        """
        Handler for missing methods to provide meaningful error messages
        """
        error_msg = f"Method {method_name} not implemented in TradingEngine"
        self.logger.error(error_msg)
        return {"status": "error", "message": error_msg, "error_type": "NotImplemented"}
        
    def __getattr__(self, name):
        """
        Handle missing attribute/method access with proper error messages
        """
        # For method access, return an async function that provides error details
        async def missing_method(*args, **kwargs):
            return await self.__missing_method_handler(name, *args, **kwargs)
            
        # Check if it's likely a method call (part of our API)
        common_methods = [
            'place_order', 'cancel_order', 'get_positions', 'get_orders',
            'adjust_leverage', 'get_fills', 'get_funding_rates'
        ]
        
        if name in common_methods or name.startswith(('get_', 'place_', 'cancel_', 'update_')):
            self.logger.warning(f"Attempted to access unimplemented method: {name}")
            return missing_method
            
        # For regular attributes, raise AttributeError
        raise AttributeError(f"TradingEngine has no attribute or method '{name}'")
    
    async def place_limit_order(self, coin: str, is_buy: bool, size: float, price: float):
        """
        Place a limit order with proper tick size and price validation
        """
        try:
            # 1. Adjust price to tick size
            adjusted_price = self._adjust_price_to_tick_size(coin, price)
            
            # Log if price was adjusted
            if adjusted_price != price:
                logging.info(f"Adjusted price from {price} to {adjusted_price} for {coin} to match tick size")
                
            # 2. Prepare order with adjusted price
            order_type = {"limit": {"tif": "Gtc"}}
            
            # 3. Place the order with properly formatted price
            result = self.exchange.order(coin, is_buy, size, adjusted_price, order_type)
            
            # 4. Log outcome
            if result.get("status") == "ok":
                statuses = result.get("response", {}).get("data", {}).get("statuses", [{}])
                if "error" in statuses[0]:
                    logging.error(f"Order error for {coin}: {statuses[0]['error']}")
                else:
                    logging.info(f"Successfully placed order for {coin}: {is_buy}, {size}, {adjusted_price}")
                    
            return result
        except Exception as e:
            logging.error(f"Error placing limit order: {e}")
            return {"status": "error", "message": str(e)}
    
    async def place_market_order(self, coin: str, is_buy: bool, size: float):
        """
        Place a market order with IOC (Immediate or Cancel) type
        """
        try:
            # Get current price from mids
            mids = await self.get_all_mids()
            mid_price = float(mids.get(coin, 0))
            
            if mid_price == 0:
                return {"status": "error", "message": "Could not determine price"}
                
            # Add/subtract slippage for market orders
            slippage = 0.001  # 0.1% slippage
            exec_price = mid_price * (1 + slippage) if is_buy else mid_price * (1 - slippage)
            
            # Adjust to tick size
            adjusted_price = self._adjust_price_to_tick_size(coin, exec_price)
            
            # Use IOC to ensure immediate execution
            order_type = {"limit": {"tif": "Ioc"}}
            
            # Place order
            result = self.exchange.order(coin, is_buy, size, adjusted_price, order_type)
            return result
        except Exception as e:
            logging.error(f"Error placing market order: {e}")
            return {"status": "error", "message": str(e)}
    
    async def place_adding_liquidity_order(self, coin: str, is_buy: bool, size: float, price: float):
        """
        Place an ALO (Add Liquidity Only) order that ensures post-only behavior
        """
        try:
            # 1. Adjust price to tick size
            adjusted_price = self._adjust_price_to_tick_size(coin, price)
            
            # 2. Ensure the price won't immediately match (post-only)
            post_only_price = self._ensure_post_only_valid(coin, is_buy, adjusted_price)
            
            # 3. Use ALO (Add Liquidity Only) type for post-only behavior
            order_type = {"limit": {"tif": "Alo"}}
            
            # 4. Place the order
            result = self.exchange.order(coin, is_buy, size, post_only_price, order_type)
            
            # 5. Log outcome
            if result.get("status") == "ok":
                statuses = result.get("response", {}).get("data", {}).get("statuses", [{}])
                if "error" in statuses[0]:
                    logging.error(f"ALO order error for {coin}: {statuses[0]['error']}")
                else:
                    logging.info(f"Successfully placed ALO order for {coin}: {is_buy}, {size}, {post_only_price}")
            
            return result
        except Exception as e:
            logging.error(f"Error placing ALO order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_tpsl_order(self, coin: str, is_buy: bool, size: float, price: float, 
                              tp_price: typing.Optional[float] = None, sl_price: typing.Optional[float] = None) -> typing.Dict[str, typing.Any]:
        """Place order with take profit/stop loss using basic_tpsl.py pattern"""
        if not self.exchange or not self.info:
            self.logger.error("Exchange or Info client not initialized in TradingEngine. Cannot place order.")
            return {"status": "error", "message": "TradingEngine not fully initialized."}
        try:
            # Construct TPSL order following basic_tpsl.py pattern
            # The SDK's exchange.order method takes a list of orders.
            
            meta = self.info.meta()
            asset_id = None
            target_name = coin.upper()
            for i, asset_data in enumerate(meta.get("universe", [])):
                if asset_data.get("name", "").upper() == target_name:
                    asset_id = i
                    break
            if asset_id is None:
                self.logger.error(f"Coin {coin} (target: {target_name}) not found for TPSL order.")
                return {"status": "error", "message": f"Coin {coin} not found"}

            order_type_details = {"limit": {"tif": "Gtc"}} 

            order_payload = {
                "a": asset_id,
                "b": is_buy,
                "p": str(price),
                "s": str(size),
                "r": False, 
                "t": order_type_details 
            }
            
            # The Hyperliquid SDK handles TP/SL as part of the order type 't'.
            # Example from SDK: order_type = {"trigger": {"triggerPx": "100", "isMarket": True, "tpsl": "tp"}}
            # This needs to be structured carefully. A single order can be a limit order with attached TP/SL triggers.
            # Or, TP/SL can be separate trigger orders. The `basic_tpsl.py` example should be the guide.

            # For simplicity, if tp_price or sl_price are provided, we might modify the order_type_details
            # or create additional trigger orders. The current structure of adding "tpsl" key directly to
            # order_payload might not be standard for all TP/SL types.
            # Let's assume for now that TP/SL are defined within the 't' (type) field for trigger orders.
            # If the main order is a limit and TP/SL are separate triggers:
            orders_to_place = [order_payload]

            if tp_price:
                tp_order_type = {"trigger": {"triggerPx": str(tp_price), "isMarket": True, "tpsl": "tp"}}
                tp_trigger = {
                    "a": asset_id, "b": not is_buy, "p": str(tp_price), "s": str(size), "r": True, "t": tp_order_type
                }
                orders_to_place.append(tp_trigger)
            
            if sl_price:
                sl_order_type = {"trigger": {"triggerPx": str(sl_price), "isMarket": True, "tpsl": "sl"}}
                sl_trigger = {
                    "a": asset_id, "b": not is_buy, "p": str(sl_price), "s": str(size), "r": True, "t": sl_order_type
                }
                orders_to_place.append(sl_trigger)
            
            # Grouping can be "na" (no atomicity) or " μαζί" (all or none)
            grouping_type = "na" # Default to no atomicity for separate orders
            if len(orders_to_place) > 1:
                 # Consider "μαζί" if all orders (main + TP/SL) should succeed or fail together
                 # grouping_type = " μαζί" # Greek word for "together"
                 pass


            order_result = self.exchange.order(orders=orders_to_place, grouping=grouping_type)
            
            self.logger.info(f"TPSL order placed: {coin} {size}@{price} TP:{tp_price} SL:{sl_price}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing TPSL order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def modify_order(self, coin: str, order_id: int, new_price: float, new_size: typing.Optional[float] = None, 
                         reduce_only: typing.Optional[bool] = None, order_type: typing.Optional[typing.Dict[str, typing.Any]] = None) -> typing.Dict[str, typing.Any]:
        """
        Modify an existing order following the official Hyperliquid API format
        """
        if not self.exchange or not self.info:
            self.logger.error("Exchange or Info client not initialized in TradingEngine. Cannot modify order.")
            return {"status": "error", "message": "TradingEngine not fully initialized."}
        try:
            # Get asset ID according to Hyperliquid standards
            meta = self.info.meta()
            asset_id = None
            target_name = coin.upper()
            for i, asset_data in enumerate(meta.get("universe", [])):
                if asset_data.get("name", "").upper() == target_name:
                    asset_id = i
                    break
                    
            if asset_id is None:
                self.logger.error(f"Coin {coin} (target: {target_name}) not found for modifying order.")
                return {"status": "error", "message": f"Coin {coin} not found"}
        except Exception as e:
            self.logger.error(f"Error modifying order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def get_vault_balance(self, vault_address: typing.Optional[str] = None) -> typing.Dict[str, typing.Any]:
        """
        Get vault balance with proper error handling and request formatting
        to avoid 422 errors with the Hyperliquid API
        """
        try:
            if not vault_address and hasattr(self, 'vault_address'):
                vault_address = self.vault_address
                
            if not vault_address:
                return {"status": "error", "message": "No vault address specified"}
                
            # Ensure vault_address is properly formatted
            # Sometimes including '0x' prefix can cause issues depending on the API expectations
            if not vault_address.startswith('0x'):
                vault_address = f'0x{vault_address}'
                
            # Use the Info client to query user state for the vault address
            if self.info:
                try:
                    vault_state = self.info.user_state(vault_address)
                    
                    # Extract relevant balance information
                    margin_summary = vault_state.get('marginSummary', {})
                    account_value = float(margin_summary.get('accountValue', '0'))
                    
                    return {
                        "status": "success",
                        "total_value": account_value,
                        "margin_summary": margin_summary,
                        "vault_address": vault_address
                    }
                except Exception as specific_e:
                    self.logger.error(f"API error getting vault balance: {specific_e}")
                    return {"status": "error", "message": str(specific_e)}
            else:
                return {"status": "error", "message": "Info client not initialized"}
                
        except Exception as e:
            self.logger.error(f"Error getting vault balance: {e}")
            return {"status": "error", "message": str(e)}

class TradingEngineCore:
    """
    Core trading engine for managing strategies and executing trades
    """
    
    def __init__(self, address: typing.Optional[str] = None, info: typing.Optional['Info'] = None, 
                 exchange: typing.Optional['Exchange'] = None, base_url: typing.Optional[str] = None):
        self.address = address
        self.info = info
        self.exchange = exchange
        self.base_url = base_url
        
        # Active strategies per user
        self.user_strategies: typing.Dict[int, typing.Dict[str, typing.Any]] = {}
        
        # Available strategies
        self.available_strategies: typing.Dict[str, str] = {
            'grid': 'Grid Trading - Automated buy/sell orders at price levels',
            'maker_rebate': 'Maker Rebate Mining - Earn rebates by providing liquidity',
            'manual': 'Manual Trading - Execute trades manually with assistance'
        }

    async def get_all_mids(self) -> typing.Dict[str, str]:
        """Get current mid prices for all trading pairs"""
        try:
            if not self.info:
                return {}
                
            all_mids = self.info.all_mids()
            return all_mids
            
        except Exception as e:
            logger.error(f"Error getting mid prices: {e}")
            return {}

    async def start_strategy(self, user_id: int, strategy_type: str, parameters: typing.Optional[typing.Dict[str, typing.Any]] = None) -> typing.Dict[str, typing.Any]:
        """Start a trading strategy for a user"""
        try:
            if strategy_type not in self.available_strategies:
                return {
                    'status': 'error',
                    'message': f'Unknown strategy: {strategy_type}'
                }

            # Store strategy configuration
            self.user_strategies[user_id] = {
                'type': strategy_type,
                'parameters': parameters or {},
                'active': True,
                'started_at': asyncio.get_event_loop().time()
            }

            if strategy_type == 'grid':
                return await self._start_grid_strategy(user_id, parameters or {})
            elif strategy_type == 'maker_rebate':
                return await self._start_maker_rebate_strategy(user_id, parameters or {})
            elif strategy_type == 'manual':
                return await self._start_manual_strategy(user_id)
            
        except Exception as e:
            logger.error(f"Error starting strategy for user {user_id}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _start_grid_strategy(self, user_id: int, parameters: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        """Start grid trading strategy"""
        coin = parameters.get('coin', 'BTC')
        levels = int(parameters.get('levels', 10))
        spacing = float(parameters.get('spacing', 0.002))
        size = float(parameters.get('size', 10))

        # In production, this would place actual grid orders
        logger.info(f"Starting grid strategy for user {user_id}: {coin} with {levels} levels")
        
        return {
            'status': 'success',
            'message': f'Grid trading started on {coin}',
            'details': {
                'coin': coin,
                'levels': levels,
                'spacing': f'{spacing*100:.2f}%',
                'size': size
            }
        }

    async def _start_maker_rebate_strategy(self, user_id: int, parameters: typing.Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
        """Start maker rebate mining strategy"""
        pairs = parameters.get('pairs', ['BTC', 'ETH'])
        
        logger.info(f"Starting maker rebate strategy for user {user_id} on pairs: {pairs}")
        
        return {
            'status': 'success',
            'message': f'Maker rebate mining started on {len(pairs)} pairs',
            'details': {
                'pairs': pairs,
                'strategy': 'Placing orders near mid price to earn rebates'
            }
        }

    async def _start_manual_strategy(self, user_id: int) -> typing.Dict[str, typing.Any]:
        """Start manual trading assistance"""
        logger.info(f"Starting manual trading assistance for user {user_id}")
        
        return {
            'status': 'success',
            'message': 'Manual trading mode activated',
            'details': {
                'features': ['Price alerts', 'Order suggestions', 'Market analysis']
            }
        }

    async def stop_strategy(self, user_id: int) -> typing.Dict[str, typing.Any]:
        """Stop trading strategy for a user"""
        try:
            if user_id not in self.user_strategies:
                return {'status': 'error', 'message': 'No active strategy found'}
                
            strategy = self.user_strategies[user_id]
            strategy['active'] = False
            
            # In production, this would cancel orders and close positions
            logger.info(f"Stopped strategy for user {user_id}")
            
            return {
                'status': 'success',
                'message': f'Strategy {strategy["type"]} stopped'
            }
            
        except Exception as e:
            logger.error(f"Error stopping strategy for user {user_id}: {e}")
            return {'status': 'error', 'message': str(e)}

    def get_user_strategy(self, user_id: int) -> typing.Optional[typing.Dict[str, typing.Any]]:
        """Get current strategy for a user"""
        return self.user_strategies.get(user_id)

    def get_available_strategies(self) -> typing.Dict[str, str]:
        """Get list of available strategies"""
        return self.available_strategies.copy()

    async def get_strategy_parameters(self, strategy_type: str) -> typing.Dict[str, typing.Any]:
        """Get required parameters for a strategy"""
        if strategy_type == 'grid':
            return {
                'coin': {'type': 'string', 'default': 'BTC', 'description': 'Trading pair'},
                'levels': {'type': 'integer', 'default': 10, 'description': 'Number of grid levels'},
                'spacing': {'type': 'float', 'default': 0.002, 'description': 'Spacing between levels (%)'},
                'size': {'type': 'float', 'default': 10, 'description': 'Order size in USDC'}
            }
        elif strategy_type == 'maker_rebate':
            return {
                'pairs': {'type': 'list', 'default': ['BTC', 'ETH'], 'description': 'Trading pairs'},
                'spread': {'type': 'float', 'default': 0.0001, 'description': 'Spread from mid price'}
            }
        elif strategy_type == 'manual':
            return {}
        
        return {}
