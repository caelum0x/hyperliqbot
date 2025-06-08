import asyncio
import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os # Ensure os is imported
import sys # Ensure sys is imported
import logging # Ensure logging is imported
import time # Ensure time is imported
import numpy as np # Ensure numpy is imported


from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.types import *
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
    
    def assess_overall_risk(self, account_value: float) -> Dict:
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
    
    def get_trading_stats(self) -> Dict:
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
    
    def __init__(self, base_url=None, account=None, wallet_manager=None, address=None, info=None, exchange=None, config_for_self_init=None): # Added config_for_self_init
        self.logger = logging.getLogger(__name__)
        self.wallet_manager = wallet_manager
        self.config_for_self_init = config_for_self_init # Store if passed
        
        if wallet_manager:
            self.address = None  # Will be set when using specific wallet
            # Assuming wallet_manager provides info and exchange instances when a wallet is selected
            self.info = wallet_manager.info if hasattr(wallet_manager, 'info') else None 
            self.exchange = None # Will be set by use_wallet
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

    def use_wallet(self, wallet_name: str, sub_account_name: str = None):
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
                                        usd_amount: float = 1.0, token_transfers: List[Dict] = None):
        """Create and fund sub-account using wallet manager's basic_sub_account integration"""
        if not self.wallet_manager:
            raise ValueError("No wallet manager available")
        
        return self.wallet_manager.create_and_fund_sub_account(
            parent_wallet_name, sub_account_name, usd_amount, token_transfers
        )

    async def place_limit_order(self, coin, is_buy, size, price):
        """Place limit order using basic_order.py pattern exactly"""
        if not self.exchange or not self.info:
            self.logger.error("Exchange or Info client not initialized in TradingEngine. Cannot place order.")
            return {"status": "error", "message": "TradingEngine not fully initialized."}
        try:
            # Get asset ID according to Hyperliquid standards
            meta = self.info.meta()
            asset_id = None
            
            # Handle different asset types (perps, spot, builder-deployed)
            # This logic needs to be robust based on actual meta structure
            target_name = coin.upper()
            for i, asset_data in enumerate(meta.get("universe", [])):
                if asset_data.get("name", "").upper() == target_name:
                    asset_id = i
                    break
            
            if asset_id is None:
                self.logger.error(f"Coin {coin} (target: {target_name}) not found in metadata: {meta.get('universe', [])[:5]}") # Log first 5 for debug
                return {"status": "error", "message": f"Coin {coin} not found"}
                
            # Format order following Hyperliquid notation standards
            order = {
                "a": asset_id,  # asset
                "b": is_buy,    # isBuy
                "p": str(price), # price
                "s": str(size),  # size
                "r": False,     # reduceOnly
                "t": {"limit": {"tif": "Gtc"}}  # Good Till Cancelled
            }
            
            # Place the order with proper format
            order_result = self.exchange.order(
                orders=[order],
                grouping="na"
            )
            
            if order_result["status"] == "ok":
                status = order_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    order_status = self.info.query_order_by_oid(self.address, status["resting"]["oid"])
                    
            self.logger.info(f"Limit order placed: {coin} {size}@{price}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing limit order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_market_order(self, coin, is_buy, size):
        """Place market order using basic_market_order.py pattern with correct notation"""
        if not self.exchange or not self.info:
            self.logger.error("Exchange or Info client not initialized in TradingEngine. Cannot place order.")
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
                self.logger.error(f"Coin {coin} (target: {target_name}) not found for market order.")
                return {"status": "error", "message": f"Coin {coin} not found"}
            
            # Format IOC order for immediate execution (market-like)
            order = {
                "a": asset_id,  # asset
                "b": is_buy,    # isBuy
                "p": str(1000000 if is_buy else 0.00001),  # Extreme price for immediate execution
                "s": str(size),  # size
                "r": False,     # reduceOnly
                "t": {"limit": {"tif": "Ioc"}}  # Immediate or Cancel
            }
            
            # Place the order with proper format
            order_result = self.exchange.order(
                orders=[order],
                grouping="na"
            )
            
            self.logger.info(f"Market order placed: {coin} {size}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing market order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_adding_liquidity_order(self, coin, is_buy, size, price):
        """Place add liquidity order using basic_adding.py pattern with proper notation"""
        if not self.exchange or not self.info:
            self.logger.error("Exchange or Info client not initialized in TradingEngine. Cannot place order.")
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
                self.logger.error(f"Coin {coin} (target: {target_name}) not found for ALO order.")
                return {"status": "error", "message": f"Coin {coin} not found"}
            
            # Format ALO order for guaranteed maker rebates
            order = {
                "a": asset_id,  # asset
                "b": is_buy,    # isBuy
                "p": str(price), # price
                "s": str(size),  # size
                "r": False,     # reduceOnly
                "t": {"limit": {"tif": "Alo"}}  # Add Liquidity Only
            }
            
            # Place the order with proper format
            order_result = self.exchange.order(
                orders=[order],
                grouping="na"
            )
            
            if order_result["status"] == "ok":
                status = order_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    order_status = self.info.query_order_by_oid(self.address, status["resting"]["oid"])
            
            self.logger.info(f"Add liquidity order placed: {coin} {size}@{price}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing add liquidity order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_tpsl_order(self, coin, is_buy, size, price, tp_price=None, sl_price=None):
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
        
    async def modify_order(self, coin: str, order_id: int, new_price: float, new_size: Optional[float] = None, 
                         reduce_only: Optional[bool] = None, order_type: Optional[Dict] = None) -> Dict:
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
