import asyncio
import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
import sys
import os

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.types import *
from trading_engine import main_bot, referral_manager, vault_manager, websocket_manager

# Import ALL actual examples from examples folder
examples_dir = os.path.join(os.path.dirname(__file__), '..', 'examples')
sys.path.append(examples_dir)

import basic_adding
import basic_agent
import basic_builder_fee
import basic_leverage_adjustment
import basic_market_order
import basic_order
import basic_order_modify
import basic_schedule_cancel
import basic_set_referrer
import basic_spot_order
import basic_spot_transfer
import basic_sub_account
import basic_tpsl
import basic_transfer
import basic_vault
import basic_vault_transfer
import basic_withdraw
import basic_ws
import cancel_open_orders
import example_utils

@dataclass
class TradingConfig:
    """Trading configuration based on actual Hyperliquid fee structure"""
    # Real Hyperliquid fee rates from knowledge doc
    base_taker_fee: float = 0.00035      # 0.035% for <$5M volume
    base_maker_fee: float = 0.0001       # 0.01% for <$5M volume
    
    # Maker rebate rates (negative = rebate)
    rebate_tier_1: float = -0.00001      # -0.001% for >0.5% maker volume
    rebate_tier_2: float = -0.00002      # -0.002% for >1.5% maker volume  
    rebate_tier_3: float = -0.00003      # -0.003% for >3% maker volume
    
    # Volume thresholds for fee tiers (14-day volume)
    tier_1_volume: float = 5000000       # $5M
    tier_2_volume: float = 25000000      # $25M
    tier_3_volume: float = 125000000     # $125M
    
    # Risk management
    max_position_size: float = 10000     # $10k max position
    min_profit_threshold: float = 0.001  # 0.1% minimum profit
    
    # Vault settings
    vault_profit_share: float = 0.10     # 10% profit share (actual rate)
    vault_minimum_capital: float = 100   # 100 USDC minimum
    vault_leader_min_ownership: float = 0.05  # 5% minimum ownership
    
    # Referral settings
    referral_commission_rate: float = 0.10    # 10% of referee fees
    referral_user_discount: float = 0.004    # 4% fee discount
    referral_volume_limit: float = 25000000  # $25M per referee

class TradingEngineContext:
    """
    TradingEngineContext exposes all trading engine modules and helpers for orchestrated bot use.
    """
    def __init__(self):
        self.basic_leverage_adjustment = basic_leverage_adjustment
        self.basic_schedule_cancel = basic_schedule_cancel
        self.cancel_open_orders = cancel_open_orders
        self.example_utils = example_utils
        self.main_bot = main_bot
        self.referral_manager = referral_manager
        self.vault_manager = vault_manager
        self.websocket_manager = websocket_manager

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
    
    def __init__(self, base_url=None, account=None, wallet_manager=None):
        if wallet_manager:
            self.wallet_manager = wallet_manager
            self.address = None  # Will be set when using specific wallet
            self.info = wallet_manager.info
            self.exchange = None  # Will be set when using specific wallet
        else:
            # Use example_utils.setup exactly as all examples do
            self.address, self.info, self.exchange = example_utils.setup(
                base_url=base_url or constants.TESTNET_API_URL,
                skip_ws=True
            )
            self.wallet_manager = None
        
        self.logger = logging.getLogger(__name__)
        
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
            raise ValueError("No wallet manager available")
        
        wallet = self.wallet_manager.get_wallet(wallet_name)
        if not wallet:
            raise ValueError(f"Wallet '{wallet_name}' not found")
        
        if sub_account_name:
            # Use sub-account following basic_sub_account.py pattern
            sub_accounts = self.wallet_manager.get_sub_accounts(wallet_name)
            sub_account = None
            for sa in sub_accounts:
                if sa.name == sub_account_name:
                    sub_account = sa
                    break
            
            if not sub_account:
                raise ValueError(f"Sub-account '{sub_account_name}' not found")
            
            # Create exchange with vault_address set to sub-account (basic_vault.py pattern)
            self.exchange = self.wallet_manager.get_exchange(wallet_name, vault_address=sub_account.address)
            self.address = sub_account.address
            self.logger.info(f"Using sub-account '{sub_account_name}' at {sub_account.address}")
        else:
            # Use main wallet
            self.exchange = self.wallet_manager.get_exchange(wallet_name)
            self.address = wallet.address
            self.logger.info(f"Using wallet '{wallet_name}' at {wallet.address}")

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
        try:
            # Exact pattern from basic_order.py main() function
            order_result = self.exchange.order(coin, is_buy, size, price, {"limit": {"tif": "Gtc"}})
            print(order_result)
            
            if order_result["status"] == "ok":
                status = order_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    order_status = self.info.query_order_by_oid(self.address, status["resting"]["oid"])
                    print("Order status by oid:", order_status)
            
            self.logger.info(f"Limit order placed: {coin} {size}@{price}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing limit order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_market_order(self, coin, is_buy, size):
        """Place market order using basic_market_order.py pattern exactly"""
        try:
            # Exact pattern from basic_market_order.py
            order_result = self.exchange.market_open(coin, is_buy, size, None, 0.01)
            print(order_result)
            self.logger.info(f"Market order placed: {coin} {size}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing market order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_adding_liquidity_order(self, coin, is_buy, size, price):
        """Place add liquidity order using basic_adding.py pattern exactly"""
        try:
            # Exact pattern from basic_adding.py for guaranteed maker rebates
            order_result = self.exchange.order(coin, is_buy, size, price, {"limit": {"tif": "Alo"}})
            print(order_result)
            
            if order_result["status"] == "ok":
                status = order_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    order_status = self.info.query_order_by_oid(self.address, status["resting"]["oid"])
                    print("Order status by oid:", order_status)
            
            self.logger.info(f"Add liquidity order placed: {coin} {size}@{price}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing add liquidity order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_tpsl_order(self, coin, is_buy, size, price, tp_price=None, sl_price=None):
        """Place order with take profit/stop loss using basic_tpsl.py pattern"""
        try:
            # Construct TPSL order following basic_tpsl.py pattern
            order_type = {"limit": {"tif": "Gtc"}}
            
            if tp_price or sl_price:
                order_type["tpsl"] = []
                if tp_price:
                    order_type["tpsl"].append({
                        "trigger": {"px": tp_price, "isMarket": True, "sz": size},
                        "condition": "tp"
                    })
                if sl_price:
                    order_type["tpsl"].append({
                        "trigger": {"px": sl_price, "isMarket": True, "sz": size},
                        "condition": "sl"
                    })
            
            order_result = self.exchange.order(coin, is_buy, size, price, order_type)
            print(order_result)
            
            self.logger.info(f"TPSL order placed: {coin} {size}@{price} TP:{tp_price} SL:{sl_price}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing TPSL order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def modify_order(self, coin, oid, new_price, new_size=None):
        """Modify order using basic_order_modify.py pattern"""
        try:
            # Use basic_order_modify.py pattern
            modify_result = self.exchange.modify_order(coin, oid, new_price, new_size)
            print(modify_result)
            
            self.logger.info(f"Order modified: {coin} oid:{oid} new_price:{new_price}")
            return modify_result
        except Exception as e:
            self.logger.error(f"Error modifying order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def set_referrer(self, referrer_code: str):
        """Set referrer using basic_set_referrer.py pattern"""
        try:
            # Use basic_set_referrer.py pattern
            result = self.exchange.set_referrer(referrer_code)
            print(result)
            
            self.logger.info(f"Referrer set: {referrer_code}")
            return result
        except Exception as e:
            self.logger.error(f"Error setting referrer: {e}")
            return {"status": "error", "message": str(e)}
        
    async def place_spot_order(self, coin, is_buy, size, price):
        """Place spot order using basic_spot_order.py pattern"""
        try:
            # Use basic_spot_order.py pattern
            order_result = self.exchange.spot_order(coin, is_buy, size, price, {"limit": {"tif": "Gtc"}})
            print(order_result)
            
            self.logger.info(f"Spot order placed: {coin} {size}@{price}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error placing spot order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def transfer_spot(self, amount, destination, token):
        """Transfer spot tokens using basic_spot_transfer.py pattern"""
        try:
            # Check permissions like basic_spot_transfer.py
            if self.exchange.account_address != self.exchange.wallet.address:
                return {"status": "error", "message": "Agents do not have permission to perform internal transfers"}
            
            # Use basic_spot_transfer.py pattern
            transfer_result = self.exchange.spot_transfer(amount, destination, token)
            print(transfer_result)
            
            self.logger.info(f"Spot transfer: {amount} {token} to {destination}")
            return transfer_result
        except Exception as e:
            self.logger.error(f"Error transferring spot: {e}")
            return {"status": "error", "message": str(e)}
        
    async def withdraw_from_bridge(self, amount, destination=None):
        """Withdraw using basic_withdraw.py pattern"""
        try:
            # Check permissions like basic_withdraw.py
            if self.exchange.account_address != self.exchange.wallet.address:
                return {"status": "error", "message": "Agents do not have permission to perform withdrawals"}
            
            destination = destination or self.address
            
            # Use basic_withdraw.py pattern
            withdraw_result = self.exchange.withdraw_from_bridge(amount, destination)
            print(withdraw_result)
            
            self.logger.info(f"Withdrawal: ${amount} to {destination}")
            return withdraw_result
        except Exception as e:
            self.logger.error(f"Error withdrawing: {e}")
            return {"status": "error", "message": str(e)}

    async def cancel_order(self, coin, oid):
        """Cancel order using basic_cancel.py pattern"""
        try:
            # Pattern from basic_cancel.py
            cancel_result = self.exchange.cancel(coin, oid)
            print(cancel_result)
            self.logger.info(f"Order cancelled: {coin} oid:{oid}")
            return cancel_result
        except Exception as e:
            self.logger.error(f"Error cancelling order: {e}")
            return {"status": "error", "message": str(e)}
        
    async def cancel_all_orders(self):
        """Cancel all open orders using cancel_open_orders.py pattern"""
        try:
            # From api/examples/cancel_open_orders.py
            open_orders = self.info.open_orders(self.address)
            results = []
            for open_order in open_orders:
                print(f"cancelling order {open_order}")
                result = self.exchange.cancel(open_order["coin"], open_order["oid"])
                results.append(result)
            return results
        except Exception as e:
            self.logger.error(f"Error cancelling all orders: {e}")
            return [{"status": "error", "message": str(e)}]
        
    async def adjust_leverage(self, coin, leverage, is_cross=True):
        """Adjust leverage using basic_leverage_adjustment.py pattern"""
        try:
            # Pattern from basic_leverage_adjustment.py
            result = self.exchange.update_leverage(leverage, coin, is_cross)
            print(result)
            self.logger.info(f"Leverage adjusted: {coin} {leverage}x {'cross' if is_cross else 'isolated'}")
            return result
        except Exception as e:
            self.logger.error(f"Error adjusting leverage: {e}")
            return {"status": "error", "message": str(e)}

    async def update_isolated_margin(self, coin: str, amount: float, is_buy: bool = True):
        """
        Update isolated margin for a position, using basic_leverage_adjustment.py pattern.
        Note: The Hyperliquid SDK's update_isolated_margin takes a signed amount.
        This method simplifies it by taking an absolute amount and a direction (is_buy implies adding margin).
        Adjust 'is_buy' to False if you intend to remove margin, though the SDK might not directly support negative values in this specific call.
        The SDK's `update_isolated_margin` expects `amount_usd` which is the change in margin.
        """
        try:
            # The SDK's update_isolated_margin expects amount_usd as the change.
            # Positive to add margin, negative to remove (if supported by the specific call).
            # For simplicity, this example assumes adding margin.
            # If 'is_buy' is False, it implies reducing margin, which might need a negative amount.
            # However, the example `exchange.update_isolated_margin(1, "ETH")` adds $1.
            # Let's assume 'amount' is always positive and we are adding margin.
            # If removing margin is intended, the SDK might require a different approach or validation.
            
            margin_change = amount # Positive for adding margin
            
            result = self.exchange.update_isolated_margin(margin_change, coin)
            print(result)
            self.logger.info(f"Isolated margin updated for {coin} by ${margin_change}")
            return result
        except Exception as e:
            self.logger.error(f"Error updating isolated margin for {coin}: {e}")
            return {"status": "error", "message": str(e)}

    async def schedule_cancel_all_orders(self, cancel_time_ms: Optional[int] = None, delay_seconds: int = 10):
        """
        Schedule cancellation of all open orders using basic_schedule_cancel.py pattern.
        If cancel_time_ms is not provided, it will be set to delay_seconds from now.
        """
        try:
            if cancel_time_ms is None:
                from hyperliquid.utils.signing import get_timestamp_ms
                cancel_time_ms = get_timestamp_ms() + (delay_seconds * 1000)
            
            # The exchange.schedule_cancel method in the SDK cancels all orders if no specific OID is given.
            # The example basic_schedule_cancel.py uses `exchange.schedule_cancel(cancel_time)`
            result = self.exchange.schedule_cancel(cancel_time_ms)
            print(result)
            self.logger.info(f"Scheduled cancellation of all orders for timestamp {cancel_time_ms}")
            return result
        except Exception as e:
            self.logger.error(f"Error scheduling cancel all orders: {e}")
            return {"status": "error", "message": str(e)}

    async def get_user_state(self):
        """Get user state using api/examples/basic_order.py pattern"""
        try:
            # From api/examples/basic_order.py
            user_state = self.info.user_state(self.address)
            positions = []
            for position in user_state["assetPositions"]:
                positions.append(position["position"])
            
            if len(positions) > 0:
                print("positions:")
                for position in positions:
                    print(json.dumps(position, indent=2))
            else:
                print("no open positions")
            
            return {
                "positions": positions,
                "marginSummary": user_state.get("marginSummary", {}),
                "crossMaintenanceMarginUsed": user_state.get("crossMaintenanceMarginUsed", 0)
            }
        except Exception as e:
            self.logger.error(f"Error getting user state: {e}")
            return {"status": "error", "message": str(e)}

    async def get_open_orders(self):
        """Get open orders using cancel_open_orders.py pattern"""
        try:
            # From cancel_open_orders.py
            open_orders = self.info.open_orders(self.address)
            return open_orders
        except Exception as e:
            self.logger.error(f"Error getting open orders: {e}")
            return []

    async def close_position(self, coin):
        """Close position using basic_market_order.py pattern"""
        try:
            # From basic_market_order.py - market close
            order_result = self.exchange.market_close(coin)
            self.logger.info(f"Position closed: {coin}")
            return order_result
        except Exception as e:
            self.logger.error(f"Error closing position: {e}")
            return {"status": "error", "message": str(e)}

    async def calculate_optimal_position_size(self, coin: str, risk_pct: float = 0.01) -> float:
        """Calculate optimal position size based on account value and volatility"""
        try:
            # Get account value
            user_state = await self.get_user_state()
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Get coin volatility
            volatility = await self._calculate_coin_volatility(coin)
            
            # Risk management adjustment
            risk_adjustment = self.risk_manager.get_risk_adjustment(coin)
            adjusted_risk_pct = risk_pct * risk_adjustment
            
            # Kelly criterion calculation
            if volatility > 0:
                # Risk no more than x% of account
                max_risk = account_value * adjusted_risk_pct
                position_size = max_risk / volatility
                
                # Apply additional position limits
                current_exposure = await self._get_current_exposure()
                max_account_exposure = 0.5  # Max 50% of account in all positions
                
                if current_exposure + position_size > account_value * max_account_exposure:
                    position_size = max(0, (account_value * max_account_exposure) - current_exposure)
                
                self.logger.info(f"Calculated position size for {coin}: ${position_size:.2f} " +
                                f"(volatility: {volatility:.4f}, risk: {adjusted_risk_pct:.2%})")
                return position_size
            return 0
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            return 0

    async def _calculate_coin_volatility(self, coin: str, lookback_hours: int = 24) -> float:
        """Calculate coin volatility based on price history"""
        try:
            # Check cache first (refresh every hour)
            current_time = time.time()
            if (coin in self.volatility_cache and 
                current_time - self.volatility_cache_time.get(coin, 0) < 3600):
                return self.volatility_cache[coin]
            
            # Get price history
            candles = self.info.candles_snapshot(coin, "1h", lookback_hours)
            
            if len(candles) < 6:
                self.logger.warning(f"Insufficient price history for {coin}")
                return 0.02  # Default 2% volatility
            
            # Calculate returns
            prices = [float(candle["c"]) for candle in candles]
            returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
            
            # Calculate volatility (standard deviation of returns)
            import numpy as np
            volatility = np.std(returns)
            
            # Annualize and normalize
            annualized_volatility = volatility * np.sqrt(24 * 365)  # 24 hours in a day
            normalized_volatility = min(0.05, max(0.005, annualized_volatility))  # Cap between 0.5% and 5%
            
            # Cache result
            self.volatility_cache[coin] = normalized_volatility
            self.volatility_cache_time[coin] = current_time
            
            return normalized_volatility
        except Exception as e:
            self.logger.error(f"Error calculating volatility for {coin}: {e}")
            return 0.02  # Default 2% volatility

    async def _get_current_exposure(self) -> float:
        """Get current position exposure"""
        try:
            user_state = await self.get_user_state()
            positions = user_state.get("positions", [])
            
            total_exposure = 0
            for position in positions:
                size = abs(float(position.get("szi", 0)))
                entry_price = float(position.get("entryPx", 0))
                exposure = size * entry_price
                total_exposure += exposure
            
            return total_exposure
        except Exception as e:
            self.logger.error(f"Error calculating current exposure: {e}")
            return 0

    async def place_smart_order(self, coin: str, is_buy: bool, risk_pct: float = 0.01, 
                             limit_price=None, order_type="limit"):
        """Place order with intelligent position sizing and risk management"""
        try:
            # Check risk management first
            if not self.risk_manager.can_trade(coin):
                return {"status": "rejected", "reason": "risk_management", 
                        "message": f"Trading {coin} blocked by risk management"}
                
            # Calculate optimal position size
            position_size_usd = await self.calculate_optimal_position_size(coin, risk_pct)
            
            # Get current price if limit price not specified
            if not limit_price:
                mids = self.info.all_mids()
                mid_price = float(mids.get(coin, 0))
                # Add a small buffer for market orders or use mid price for limit orders
                limit_price = mid_price * (0.998 if is_buy else 1.002) if order_type == "market" else mid_price
            else:
                limit_price = float(limit_price)
                
            # Convert USD size to coin quantity
            size = position_size_usd / limit_price
            
            # Round size to appropriate precision
            # Most coins use different precision, implement proper rounding
            if coin in ["BTC"]:
                size = round(size, 4)  # 0.0001 BTC precision
            elif coin in ["ETH"]:
                size = round(size, 3)  # 0.001 ETH precision
            else:
                size = round(size, 2)  # 0.01 precision for others
            
            # Check minimum viable size
            if size * limit_price < 5:  # $5 minimum order
                return {"status": "rejected", "reason": "size_too_small",
                        "message": f"Order size ${size * limit_price:.2f} below minimum $5"}
            
            # Place appropriate order type
            if order_type == "market":
                result = await self.place_market_order(coin, is_buy, size)
            else:
                result = await self.place_limit_order(coin, is_buy, size, limit_price)
            
            # Log order placement with full details
            self.logger.info(f"Smart order placed: {coin} {'BUY' if is_buy else 'SELL'} "
                          f"{size} @ ${limit_price} (${position_size_usd:.2f}, "
                          f"risk: {risk_pct:.2%})")
            
            # Update risk management system
            self.risk_manager.record_trade(coin, size * limit_price, is_buy)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error placing smart order: {e}")
            return {"status": "error", "message": str(e)}

    async def update_correlation_matrix(self, coins: list = None):
        """Update cross-coin correlation matrix"""
        try:
            current_time = time.time()
            
            # Update at most once every 4 hours
            if current_time - self.last_correlation_update < 14400:
                return self.correlation_matrix
            
            if not coins:
                # Get all available coins
                all_mids = self.info.all_mids()
                coins = list(all_mids.keys())
            
            # Limit to common coins for performance
            major_coins = [c for c in coins if c in ["BTC", "ETH", "SOL", "ARB", "AVAX", "APT", "OP", "MATIC", "DOGE"]]
            
            # Get price history for each coin
            price_data = {}
            for coin in major_coins:
                try:
                    candles = self.info.candles_snapshot(coin, "4h", 30)  # 5 days of 4-hour candles
                    if len(candles) >= 10:  # Need reasonable amount of data
                        price_data[coin] = [float(c["c"]) for c in candles]
                except Exception:
                    continue
            
            # Calculate correlation matrix
            import numpy as np
            correlation = {}
            
            for coin1 in price_data:
                correlation[coin1] = {}
                for coin2 in price_data:
                    # Get common length
                    min_len = min(len(price_data[coin1]), len(price_data[coin2]))
                    if min_len < 10:
                        correlation[coin1][coin2] = 0
                        continue
                    
                    # Calculate returns
                    returns1 = np.diff(price_data[coin1][-min_len:]) / price_data[coin1][-min_len:-1]
                    returns2 = np.diff(price_data[coin2][-min_len:]) / price_data[coin2][-min_len:-1]
                    
                    # Calculate correlation
                    try:
                        corr = np.corrcoef(returns1, returns2)[0, 1]
                        correlation[coin1][coin2] = corr
                    except:
                        correlation[coin1][coin2] = 0
            
            self.correlation_matrix = correlation
            self.last_correlation_update = current_time
            
            self.logger.info(f"Updated correlation matrix for {len(correlation)} coins")
            return correlation
            
        except Exception as e:
            self.logger.error(f"Error updating correlation matrix: {e}")
            return {}

    async def find_correlated_opportunities(self, base_coin: str, correlation_threshold: float = 0.7):
        """Find trading opportunities based on correlated coins"""
        try:
            # Make sure correlation matrix is updated
            await self.update_correlation_matrix()
            
            if not self.correlation_matrix or base_coin not in self.correlation_matrix:
                return []
            
            # Find coins with high correlation to base_coin
            correlated_coins = []
            for coin, corr in self.correlation_matrix[base_coin].items():
                if coin != base_coin and abs(corr) >= correlation_threshold:
                    correlated_coins.append({
                        "coin": coin,
                        "correlation": corr
                    })
            
            # Get base coin performance
            base_performance = await self._get_coin_performance(base_coin)
            
            # Find opportunities where base is up but correlated coin lags
            opportunities = []
            for coin_data in correlated_coins:
                coin = coin_data["coin"]
                corr = coin_data["correlation"]
                
                performance = await self._get_coin_performance(coin)
                
                # If coins are positively correlated
                if corr > 0:
                    # Base is up but correlated coin is lagging
                    if base_performance["change_24h"] > 0.01 and performance["change_24h"] < base_performance["change_24h"] * 0.5:
                        opportunities.append({
                            "coin": coin,
                            "signal": "BUY",
                            "correlation": corr,
                            "base_coin": base_coin,
                            "base_change": base_performance["change_24h"],
                            "coin_change": performance["change_24h"],
                            "type": "positive_correlation_lag",
                            "description": f"{coin} lagging behind {base_coin} despite positive correlation"
                        })
                    # Base is down but correlated coin hasn't fallen
                    elif base_performance["change_24h"] < -0.01 and performance["change_24h"] > base_performance["change_24h"] * 0.5:
                        opportunities.append({
                            "coin": coin,
                            "signal": "SELL",
                            "correlation": corr,
                            "base_coin": base_coin,
                            "base_change": base_performance["change_24h"],
                            "coin_change": performance["change_24h"],
                            "type": "positive_correlation_drop_pending",
                            "description": f"{coin} likely to follow {base_coin}'s decline"
                        })
                # If coins are negatively correlated
                elif corr < 0:
                    # Base is up, so negatively correlated should drop
                    if base_performance["change_24h"] > 0.01 and performance["change_24h"] > -0.01:
                        opportunities.append({
                            "coin": coin,
                            "signal": "SELL",
                            "correlation": corr,
                            "base_coin": base_coin,
                            "base_change": base_performance["change_24h"],
                            "coin_change": performance["change_24h"],
                            "type": "negative_correlation_drop_expected",
                            "description": f"{coin} likely to drop as {base_coin} rises (negative correlation)"
                        })
                    # Base is down, so negatively correlated should rise
                    elif base_performance["change_24h"] < -0.01 and performance["change_24h"] < 0.01:
                        opportunities.append({
                            "coin": coin,
                            "signal": "BUY",
                            "correlation": corr,
                            "base_coin": base_coin,
                            "base_change": base_performance["change_24h"],
                            "coin_change": performance["change_24h"],
                            "type": "negative_correlation_rise_expected",
                            "description": f"{coin} likely to rise as {base_coin} falls (negative correlation)"
                        })
            
            return opportunities
            
        except Exception as e:
            self.logger.error(f"Error finding correlation opportunities: {e}")
            return []

    async def _get_coin_performance(self, coin: str) -> dict:
        """Get coin performance metrics"""
        try:
            # Get recent candles
            candles = self.info.candles_snapshot(coin, "1h", 25)  # 24h + 1 for calculation
            if len(candles) < 2:
                return {"change_24h": 0, "volume_24h": 0}
            
            # Calculate 24h change
            current_price = float(candles[-1]["c"])
            price_24h_ago = float(candles[0]["c"])
            change_24h = (current_price - price_24h_ago) / price_24h_ago
            
            # Calculate 24h volume
            volume_24h = sum(float(c["v"]) for c in candles[1:])  # Skip first candle
            
            return {
                "price": current_price,
                "change_24h": change_24h,
                "volume_24h": volume_24h
            }
            
        except Exception as e:
            self.logger.error(f"Error getting performance for {coin}: {e}")
            return {"change_24h": 0, "volume_24h": 0}

    async def execute_correlation_trade(self, opportunity):
        """Execute trade based on correlation opportunity"""
        try:
            coin = opportunity["coin"]
            signal = opportunity["signal"]
            is_buy = signal == "BUY"
            
            # Use a smaller risk percentage for correlation trades
            risk_pct = 0.005  # 0.5% of account
            
            # Place the trade with smart sizing
            result = await self.place_smart_order(
                coin=coin,
                is_buy=is_buy,
                risk_pct=risk_pct,
                order_type="limit"
            )
            
            # Log the correlation-based trade
            self.logger.info(f"Correlation trade: {signal} {coin} based on {opportunity['type']}")
            
            return {
                "status": "executed" if result.get("status") == "ok" else "failed",
                "trade_result": result,
                "opportunity": opportunity
            }
            
        except Exception as e:
            self.logger.error(f"Error executing correlation trade: {e}")
            return {"status": "error", "message": str(e)}

class RiskManagementSystem:
    """Advanced risk management system for trading"""
    
    def __init__(self):
        self.trade_limits = {
            "daily_max_trades": 100,
            "daily_max_volume": 100000,  # $100k per day
            "max_drawdown_pct": 0.05,    # 5% max drawdown
            "max_position_size": 10000,  # $10k max position
            "max_open_positions": 10     # Maximum 10 open positions
        }
        
        self.daily_trades = {}
        self.daily_volumes = {}
        self.drawdowns = {}
        self.banned_coins = set()
        self.position_limits = {}
        self.trade_history = []
        
        self.logger = logging.getLogger(__name__)
    
    def can_trade(self, coin: str) -> bool:
        """Check if trading is allowed for this coin"""
        today = time.strftime("%Y-%m-%d")
        
        # Check banned coins
        if coin in self.banned_coins:
            return False
        
        # Check daily trade count
        if today in self.daily_trades and self.daily_trades[today] >= self.trade_limits["daily_max_trades"]:
            return False
        
        # Check daily volume
        if today in self.daily_volumes and self.daily_volumes[today] >= self.trade_limits["daily_max_volume"]:
            return False
        
        return True
    
    def get_risk_adjustment(self, coin: str) -> float:
        """Get risk adjustment factor based on coin and market conditions"""
        # Default is 1.0 (no adjustment)
        adjustment = 1.0
        
        # If coin has had recent drawdowns, reduce risk
        if coin in self.drawdowns and self.drawdowns[coin] > 0.02:  # 2%+ drawdown
            adjustment *= 0.5  # Half risk
        
        # Reduce risk if we've had many trades today
        today = time.strftime("%Y-%m-%d")
        if today in self.daily_trades:
            trades_factor = 1.0 - (self.daily_trades[today] / self.trade_limits["daily_max_trades"])
            adjustment *= max(0.25, trades_factor)  # Reduce to at most 75%
        
        # Apply coin-specific limits
        if coin in self.position_limits:
            adjustment *= self.position_limits.get(coin, 1.0)
        
        return min(1.0, max(0.1, adjustment))  # Constrain between 0.1 and 1.0
    
    def record_trade(self, coin: str, trade_value: float, is_buy: bool):
        """Record a trade for risk management tracking"""
        today = time.strftime("%Y-%m-%d")
        timestamp = time.time()
        
        # Update daily counters
        if today not in self.daily_trades:
            self.daily_trades[today] = 0
            self.daily_volumes[today] = 0
        
        self.daily_trades[today] += 1
        self.daily_volumes[today] += trade_value
        
        # Record in history
        self.trade_history.append({
            "timestamp": timestamp,
            "coin": coin,
            "value": trade_value,
            "is_buy": is_buy
        })
        
        # Limit history size
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-1000:]
        
        self.logger.info(f"Trade recorded: {coin} {'BUY' if is_buy else 'SELL'} ${trade_value:.2f} "
                       f"(daily: {self.daily_trades[today]}/{self.trade_limits['daily_max_trades']} trades, "
                       f"${self.daily_volumes[today]:,.2f}/${self.trade_limits['daily_max_volume']:,.2f} volume)")

    def update_drawdown(self, coin: str, drawdown_pct: float):
        """Update drawdown tracking for a coin"""
        self.drawdowns[coin] = drawdown_pct
        
        # Ban coin if drawdown exceeds threshold
        if drawdown_pct > self.trade_limits["max_drawdown_pct"]:
            self.banned_coins.add(coin)
            self.logger.warning(f"{coin} banned due to {drawdown_pct:.2%} drawdown exceeding {self.trade_limits['max_drawdown_pct']:.2%} limit")
    
    def set_position_limit(self, coin: str, limit_factor: float):
        """Set position size limit factor for a specific coin"""
        self.position_limits[coin] = limit_factor
    
    def get_risk_report(self) -> dict:
        """Get comprehensive risk report"""
        today = time.strftime("%Y-%m-%d")
        
        return {
            "daily_trades": self.daily_trades.get(today, 0),
            "daily_volume": self.daily_volumes.get(today, 0),
            "banned_coins": list(self.banned_coins),
            "drawdowns": self.drawdowns,
            "position_limits": self.position_limits,
            "limits": self.trade_limits,
            "risk_status": "normal" if self.daily_trades.get(today, 0) < self.trade_limits["daily_max_trades"] * 0.8 else "elevated"
        }
