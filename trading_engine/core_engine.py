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

class ProfitOptimizedTrader:
    """
    Profit optimization wrapper around TradingEngine
    """
    
    def __init__(self, trading_engine: TradingEngine, config: TradingConfig):
        self.engine = trading_engine
        self.config = config
        self.logger = logging.getLogger(__name__)
        
    async def smart_limit_order(self, coin: str, is_buy: bool, size: float, price: float):
        """Place optimized limit order for maximum rebates"""
        try:
            # Always use Alo (Add Liquidity Only) for maker rebates
            result = await self.engine.place_limit_order(coin, is_buy, size, price)
            
            if result.get("status") == "ok":
                # Query order status by oid like basic_order.py
                status = result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    order_status = self.engine.info.query_order_by_oid(
                        self.engine.address, status["resting"]["oid"]
                    )
                    self.logger.info(f"Order status by oid: {order_status}")
                    
            return result
        except Exception as e:
            self.logger.error(f"Error in smart limit order: {e}")
            return {"status": "error", "message": str(e)}

    async def profit_taking_strategy(self, coin: str, target_profit_pct: float = 0.02):
        """Profit taking using market close from basic_market_order.py"""
        try:
            user_state = await self.engine.get_user_state()
            
            for position in user_state.get("positions", []):
                if position["coin"] != coin or float(position["szi"]) == 0:
                    continue
                
                szi = float(position["szi"])
                entry_px = float(position["entryPx"])
                
                # Get current price
                all_mids = self.engine.info.all_mids()
                current_px = float(all_mids.get(coin, entry_px))
                
                # Calculate P&L
                if szi > 0:  # Long position
                    pnl_pct = (current_px - entry_px) / entry_px
                elif szi < 0:  # Short position
                    pnl_pct = (entry_px - current_px) / entry_px
                else:
                    continue
                
                if pnl_pct >= target_profit_pct:
                    # Close position using market_close
                    result = await self.engine.close_position(coin)
                    self.logger.info(f"Profit taken on {coin}: {pnl_pct:.2%}")
                    return {"action": "profit_taken", "pnl_pct": pnl_pct, "result": result}
            
            return {"action": "monitoring", "message": "No profit taking needed"}
            
        except Exception as e:
            self.logger.error(f"Error in profit taking: {e}")
            return {"action": "error", "message": str(e)}

    async def track_performance(self) -> Dict:
        """Track performance using user_state from basic_order.py"""
        try:
            user_state = await self.engine.get_user_state()
            margin_summary = user_state.get("marginSummary", {})
            
            account_value = float(margin_summary.get("accountValue", 0))
            total_ntl_pos = float(margin_summary.get("totalNtlPos", 0))
            total_raw_usd = float(margin_summary.get("totalRawUsd", 0))
            
            # Get recent fills for detailed tracking
            recent_fills = self.engine.info.user_fills(self.engine.address)
            
            total_pnl = 0
            total_fees = 0
            trade_count = len(recent_fills)
            
            for fill in recent_fills:
                total_pnl += float(fill.get("closedPnl", 0))
                total_fees += float(fill.get("fee", 0))
            
            return {
                "account_value": account_value,
                "total_ntl_pos": total_ntl_pos,
                "total_raw_usd": total_raw_usd,
                "total_pnl": total_pnl,
                "total_fees": total_fees,
                "trade_count": trade_count,
                "net_profit": total_pnl - total_fees,
                "positions": user_state.get("positions", [])
            }
            
        except Exception as e:
            self.logger.error(f"Error tracking performance: {e}")
            return {"error": str(e)}
