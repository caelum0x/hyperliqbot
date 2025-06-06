import json
import os
import time
import numpy as np
import pandas as pd
import websocket
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
import ta  # technical analysis library

import eth_account
from eth_account.signers.local import LocalAccount
from eth_account import Account
import asyncio

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from hyperliquid.utils.signing import sign_l1_action


class UserSession:
    def __init__(self, user_id: int, private_key: str, account_address: str = ""):
        self.user_id = user_id
        self.account: LocalAccount = eth_account.Account.from_key(private_key)
        self.account_address = account_address if account_address else self.account.address
        self.created_at = time.time()
        self.last_activity = time.time()
        self._exchange: Optional[Exchange] = None
        self._info: Optional[Info] = None
    
    def get_exchange(self, base_url: str) -> Exchange:
        """Get Exchange instance for this user"""
        if self._exchange is None:
            self._exchange = Exchange(
                self.account, 
                base_url, 
                account_address=self.account_address
            )
        return self._exchange
    
    def get_info(self, base_url: str) -> Info:
        """Get Info instance for this user"""
        if self._info is None:
            self._info = Info(base_url, skip_ws=True)
        return self._info
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = time.time()
    
    def is_expired(self, timeout: int) -> bool:
        """Check if session is expired"""
        return time.time() - self.last_activity > timeout


class UserManager:
    def __init__(self, storage_path: str = "telegram_bot/users.json"):
        self.storage_path = storage_path
        self.sessions: Dict[int, UserSession] = {}
        self.user_data = self._load_user_data()
    
    def _load_user_data(self) -> Dict:
        """Load user data from storage"""
        try:
            with open(self.storage_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _save_user_data(self):
        """Save user data to storage"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(self.user_data, f, indent=2)
    
    def register_user(self, user_id: int, private_key: str, account_address: str = "") -> bool:
        """Register a new user"""
        try:
            # Validate private key
            account = eth_account.Account.from_key(private_key)
            address = account_address if account_address else account.address
            
            # Store user data (encrypted in production)
            self.user_data[str(user_id)] = {
                "private_key": private_key,  # Should be encrypted in production
                "account_address": address,
                "registered_at": time.time()
            }
            self._save_user_data()
            return True
        except Exception:
            return False
    
    def authenticate_user(self, user_id: int) -> Optional[UserSession]:
        """Authenticate user and create session"""
        user_data = self.user_data.get(str(user_id))
        if not user_data:
            return None
        
        try:
            session = UserSession(
                user_id,
                user_data["private_key"],
                user_data["account_address"]
            )
            self.sessions[user_id] = session
            return session
        except Exception:
            return None
    
    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Get active user session"""
        return self.sessions.get(user_id)
    
    def cleanup_expired_sessions(self, timeout: int):
        """Remove expired sessions"""
        expired_users = [
            user_id for user_id, session in self.sessions.items()
            if session.is_expired(timeout)
        ]
        for user_id in expired_users:
            del self.sessions[user_id]


class HyperliquidTrader:
    """
    A comprehensive Hyperliquid trading class with Web3 integration patterns
    """
    
    def __init__(self, config_path: str = "config.json", testnet: bool = True):
        """
        Initialize the Hyperliquid trader with configuration
        
        Args:
            config_path: Path to configuration file
            testnet: Whether to use testnet (True) or mainnet (False)
        """
        self.config = self._load_config(config_path)
        self.api_url = constants.TESTNET_API_URL if testnet else constants.MAINNET_API_URL
        self.info = Info(self.api_url, skip_ws=True)
        self.exchange = Exchange(
            self.config['account_address'],
            self.config['secret_key'],
            self.api_url
        )
        
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    async def get_user_state(self, address: Optional[str] = None) -> Dict:
        """
        Get user state including balances and positions
        
        Args:
            address: User address (defaults to configured address)
        """
        address = address or self.config['account_address']
        return self.info.user_state(address)
    
    async def get_all_mids(self) -> Dict[str, float]:
        """Get mid prices for all assets"""
        return self.info.all_mids()
    
    async def place_limit_order(
        self,
        coin: str,
        is_buy: bool,
        size: float,
        price: float,
        reduce_only: bool = False,
        post_only: bool = False
    ) -> Dict:
        """
        Place a limit order
        
        Args:
            coin: Trading pair symbol (e.g., "BTC")
            is_buy: True for buy, False for sell
            size: Order size
            price: Limit price
            reduce_only: If True, order can only reduce position
            post_only: If True, order will only post to orderbook
        """
        order = {
            "a": self.info.get_asset_index(coin),
            "b": is_buy,
            "p": str(price),
            "s": str(size),
            "r": reduce_only,
            "t": {"limit": {"tif": "Gtc"}}  # Good Till Cancelled
        }
        
        if post_only:
            order["t"]["limit"]["tif"] = "Alo"  # Add Liquidity Only
            
        return self.exchange.order(order, {"grouping": "na"})
    
    async def place_market_order(
        self,
        coin: str,
        is_buy: bool,
        size: float,
        slippage: float = 0.01
    ) -> Dict:
        """
        Place a market order with slippage protection
        
        Args:
            coin: Trading pair symbol
            is_buy: True for buy, False for sell
            size: Order size
            slippage: Maximum acceptable slippage (default 1%)
        """
        # Get current mid price
        mids = await self.get_all_mids()
        mid_price = mids.get(coin)
        
        if not mid_price:
            raise ValueError(f"No mid price available for {coin}")
        
        # Calculate limit price with slippage
        if is_buy:
            limit_price = mid_price * (1 + slippage)
        else:
            limit_price = mid_price * (1 - slippage)
        
        order = {
            "a": self.info.get_asset_index(coin),
            "b": is_buy,
            "p": str(limit_price),
            "s": str(size),
            "r": False,
            "t": {"limit": {"tif": "Ioc"}}  # Immediate or Cancel
        }
        
        return self.exchange.order(order, {"grouping": "na"})
    
    async def cancel_order(self, coin: str, order_id: int) -> Dict:
        """Cancel a specific order"""
        return self.exchange.cancel(coin, order_id)
    
    async def cancel_all_orders(self, coin: Optional[str] = None) -> Dict:
        """Cancel all orders for a specific coin or all coins"""
        if coin:
            return self.exchange.cancel_by_coin(coin)
        else:
            # Cancel all orders across all coins
            open_orders = self.info.open_orders(self.config['account_address'])
            results = []
            for order in open_orders:
                result = await self.cancel_order(order['coin'], order['oid'])
                results.append(result)
            return {"results": results}
    
    async def transfer_usd(self, amount: float, destination: str) -> Dict:
        """
        Transfer USD to another address
        
        Args:
            amount: Amount in USD
            destination: Destination address
        """
        return self.exchange.usd_transfer(amount, destination)
    
    async def update_leverage(self, coin: str, leverage: int, is_cross: bool = True) -> Dict:
        """
        Update leverage for a trading pair
        
        Args:
            coin: Trading pair symbol
            leverage: Leverage multiplier
            is_cross: True for cross margin, False for isolated
        """
        return self.exchange.update_leverage(leverage, coin, is_cross)
    
    async def get_orderbook(self, coin: str) -> Dict:
        """Get orderbook for a specific coin"""
        return self.info.l2_snapshot(coin)
    
    async def get_user_fills(self, start_time: Optional[int] = None) -> List[Dict]:
        """Get user's trade history"""
        return self.info.user_fills(self.config['account_address'], start_time)
    
    async def get_funding_history(self, coin: str, start_time: Optional[int] = None) -> List[Dict]:
        """Get funding rate history for a coin"""
        return self.info.funding_history(coin, start_time)


class HyperliquidTokenDeployer:
    """
    Class for deploying HIP-1 and HIP-2 tokens on Hyperliquid
    """
    
    def __init__(self, exchange: Exchange):
        self.exchange = exchange
    
    async def deploy_token(
        self,
        symbol: str,
        sz_decimals: int,
        wei_decimals: int,
        max_gas: int,
        description: str,
        initial_distribution: List[Tuple[str, str]],
        enable_freeze: bool = False
    ) -> Dict:
        """
        Deploy a new token following HIP-1/HIP-2 standards
        
        Args:
            symbol: Token symbol
            sz_decimals: Size decimals
            wei_decimals: Wei decimals (precision)
            max_gas: Maximum gas for deploy auction (in USDC)
            description: Token description
            initial_distribution: List of (address, amount) tuples
            enable_freeze: Enable freeze/unfreeze functionality
        """
        # Step 1: Register token
        register_result = self.exchange.spot_deploy_register_token(
            symbol, sz_decimals, wei_decimals, max_gas, description
        )
        
        if register_result["status"] != "ok":
            return register_result
        
        token_index = register_result["response"]["data"]
        
        # Step 2: User genesis - distribute initial tokens
        genesis_result = self.exchange.spot_deploy_user_genesis(
            token_index,
            initial_distribution,
            []
        )
        
        if genesis_result["status"] != "ok":
            return genesis_result
        
        # Step 2a: Enable freeze privilege if requested
        if enable_freeze:
            freeze_result = self.exchange.spot_deploy_enable_freeze_privilege(token_index)
            if freeze_result["status"] != "ok":
                return freeze_result
        
        # Step 3: Finalize genesis
        total_supply = sum(int(amount) for _, amount in initial_distribution)
        genesis_final = self.exchange.spot_deploy_genesis(
            token_index,
            str(total_supply),
            False  # noHyperliquidity
        )
        
        if genesis_final["status"] != "ok":
            return genesis_final
        
        # Step 4: Register spot pair (with USDC)
        spot_result = self.exchange.spot_deploy_register_spot(token_index, 0)  # 0 = USDC
        
        if spot_result["status"] != "ok":
            return spot_result
        
        spot_index = spot_result["response"]["data"]
        
        # Step 5: Register hyperliquidity
        hyperliquidity_result = self.exchange.spot_deploy_register_hyperliquidity(
            spot_index,
            1.0,    # starting price
            10.0,   # order size
            100,    # number of orders
            None
        )
        
        return {
            "status": "ok",
            "token_index": token_index,
            "spot_index": spot_index,
            "results": {
                "register": register_result,
                "genesis": genesis_final,
                "spot": spot_result,
                "hyperliquidity": hyperliquidity_result
            }
        }
    

class HyperliquidMultiSig:
    """
    Multi-signature transaction handler for Hyperliquid
    """
    
    def __init__(self, exchange: Exchange, multi_sig_wallets: List[Account]):
        self.exchange = exchange
        self.wallets = multi_sig_wallets
    
    async def execute_multi_sig_order(
        self,
        multi_sig_user: str,
        orders: List[Dict],
        timestamp: Optional[int] = None
    ) -> Dict:
        """
        Execute a multi-sig order
        
        Args:
            multi_sig_user: Address of the multi-sig user
            orders: List of order dictionaries
            timestamp: Transaction timestamp (auto-generated if None)
        """
        from hyperliquid.utils.signing import get_timestamp_ms, sign_multi_sig_l1_action_payload
        
        if timestamp is None:
            timestamp = get_timestamp_ms()
        
        # Define the action
        action = {
            "type": "order",
            "orders": orders,
            "grouping": "na"
        }
        
        # Collect signatures
        signatures = []
        for wallet in self.wallets:
            signature = sign_multi_sig_l1_action_payload(
                wallet,
                action,
                self.exchange.base_url == constants.MAINNET_API_URL,
                None,
                timestamp,
                multi_sig_user,
                self.exchange.account_address,
                self.exchange.expires_after
            )
            signatures.append(signature)
        
        # Execute the multi-sig action
        return self.exchange.multi_sig(multi_sig_user, action, signatures, timestamp)


class AlphaStrategyManager:
    """
    Advanced alpha strategies for Hyperliquid trading
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.active_strategies = {}
        self.profit_targets = {}
        self.stop_losses = {}
    
    async def momentum_scalping(self, coin: str, size: float, lookback_minutes: int = 5) -> Dict:
        """
        High-frequency momentum scalping strategy
        """
        try:
            # Get recent candles for momentum analysis
            candles = self.trader.info.candles_snapshot(coin, "1m", lookback_minutes)
            
            if len(candles) < 3:
                return {"status": "error", "message": "Insufficient data"}
            
            # Calculate momentum indicators
            prices = [float(c['c']) for c in candles]  # closing prices
            volumes = [float(c['v']) for c in candles]  # volumes
            
            # Simple momentum calculation
            momentum = (prices[-1] - prices[-3]) / prices[-3]
            volume_spike = volumes[-1] > (sum(volumes[:-1]) / len(volumes[:-1])) * 1.5
            
            if abs(momentum) > 0.002 and volume_spike:  # 0.2% move with volume
                is_buy = momentum > 0
                
                # Dynamic pricing based on orderbook
                orderbook = await self.trader.get_orderbook(coin)
                if is_buy:
                    entry_price = float(orderbook["levels"][1][0][0]) * 1.001  # Slight premium
                else:
                    entry_price = float(orderbook["levels"][0][0][0]) * 0.999  # Slight discount
                
                # Place order with tight stops
                result = await self.trader.place_limit_order(
                    coin, is_buy, size, entry_price, post_only=True
                )
                
                # Set profit target and stop loss
                if result.get("status") == "ok":
                    profit_target = entry_price * (1.005 if is_buy else 0.995)  # 0.5% target
                    stop_loss = entry_price * (0.998 if is_buy else 1.002)  # 0.2% stop
                    
                    order_id = result["response"]["data"]["statuses"][0]["resting"]["oid"]
                    self.profit_targets[order_id] = {"price": profit_target, "size": size, "is_buy": not is_buy}
                    self.stop_losses[order_id] = {"price": stop_loss, "size": size, "is_buy": not is_buy}
                
                return result
            
            return {"status": "no_signal", "momentum": momentum, "volume_spike": volume_spike}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def arbitrage_hunter(self, coin: str, size: float) -> Dict:
        """
        Cross-exchange arbitrage opportunities (simulated for single exchange)
        """
        try:
            # Simulate funding rate arbitrage
            funding_history = await self.trader.get_funding_history(coin)
            if not funding_history:
                return {"status": "no_data"}
            
            current_funding = funding_history[-1]["funding"]
            
            # High funding rate = short bias, Low/negative = long bias
            if abs(current_funding) > 0.0001:  # 0.01% threshold
                is_buy = current_funding < 0  # Buy when funding is negative (longs pay shorts)
                
                mids = await self.trader.get_all_mids()
                current_price = mids.get(coin)
                
                if current_price:
                    # Place position to capture funding
                    result = await self.trader.place_market_order(coin, is_buy, size, slippage=0.001)
                    
                    return {
                        "status": "funding_arb",
                        "funding_rate": current_funding,
                        "position": "long" if is_buy else "short",
                        "result": result
                    }
            
            return {"status": "no_opportunity", "funding": current_funding}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def whale_tracker(self, coin: str) -> Dict:
        """
        Track large orders and whale movements
        """
        try:
            orderbook = await self.trader.get_orderbook(coin)
            
            # Analyze orderbook for large orders
            bid_levels = orderbook["levels"][0]  # bids
            ask_levels = orderbook["levels"][1]  # asks
            
            large_bids = [level for level in bid_levels if float(level[1]) > 100000]  # $100k+ orders
            large_asks = [level for level in ask_levels if float(level[1]) > 100000]
            
            whale_signals = []
            
            # Detect walls and large orders
            if large_bids:
                whale_signals.append({
                    "type": "large_bid_wall",
                    "price": large_bids[0][0],
                    "size": large_bids[0][1],
                    "signal": "potential_support"
                })
            
            if large_asks:
                whale_signals.append({
                    "type": "large_ask_wall", 
                    "price": large_asks[0][0],
                    "size": large_asks[0][1],
                    "signal": "potential_resistance"
                })
            
            return {"status": "ok", "whale_signals": whale_signals}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def liquidation_hunter(self, coin: str, size: float) -> Dict:
        """
        Hunt for liquidation cascades and capitalize on them
        """
        try:
            # Get user states to find highly leveraged positions
            user_state = await self.trader.get_user_state()
            positions = user_state.get("assetPositions", [])
            
            target_position = None
            for pos in positions:
                if pos["position"]["coin"] == coin:
                    target_position = pos
                    break
            
            if not target_position:
                return {"status": "no_position"}
            
            # Calculate liquidation price estimation
            position_size = float(target_position["position"]["szi"])
            entry_px = float(target_position["position"]["entryPx"])
            
            if position_size != 0:
                # Estimate high leverage positions might liquidate
                mids = await self.trader.get_all_mids()
                current_price = mids.get(coin)
                
                if current_price:
                    # If price moved significantly against position, others might liquidate
                    price_change = (current_price - entry_px) / entry_px
                    
                    if abs(price_change) > 0.05:  # 5% move
                        # Place orders to catch liquidation wicks
                        is_buy = price_change < 0  # Buy the dip if price dropped
                        
                        wick_price = current_price * (0.98 if is_buy else 1.02)  # 2% wick target
                        
                        result = await self.trader.place_limit_order(
                            coin, is_buy, size, wick_price, post_only=True
                        )
                        
                        return {
                            "status": "liquidation_setup",
                            "price_change": price_change,
                            "wick_target": wick_price,
                            "result": result
                        }
            
            return {"status": "no_opportunity"}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class MEVStrategies:
    """
    Maximum Extractable Value strategies
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
    
    async def sandwich_attack_defense(self, coin: str, size: float) -> Dict:
        """
        Detect and defend against sandwich attacks
        """
        try:
            # Monitor mempool equivalent (recent orders)
            recent_fills = await self.trader.get_user_fills()
            
            if len(recent_fills) >= 2:
                # Check for suspicious patterns
                last_two = recent_fills[:2]
                
                # If same coin, opposite directions, similar timestamps
                if (last_two[0]["coin"] == last_two[1]["coin"] == coin and
                    last_two[0]["side"] != last_two[1]["side"] and
                    abs(last_two[0]["time"] - last_two[1]["time"]) < 1000):  # 1 second
                    
                    # Potential sandwich detected, place defensive order
                    mids = await self.trader.get_all_mids()
                    current_price = mids.get(coin)
                    
                    if current_price:
                        # Place order at better price to front-run
                        is_buy = last_two[0]["side"] == "B"
                        better_price = current_price * (1.0005 if is_buy else 0.9995)
                        
                        result = await self.trader.place_limit_order(
                            coin, is_buy, size, better_price, post_only=False
                        )
                        
                        return {"status": "sandwich_defense", "result": result}
            
            return {"status": "no_threat"}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def front_running_opportunities(self, coin: str) -> Dict:
        """
        Identify front-running opportunities from order flow
        """
        try:
            orderbook = await self.trader.get_orderbook(coin)
            
            # Look for large orders that might move the market
            bid_levels = orderbook["levels"][0]
            ask_levels = orderbook["levels"][1]
            
            # Find thin areas in orderbook
            if len(bid_levels) > 5 and len(ask_levels) > 5:
                # Calculate orderbook density
                total_bid_volume = sum(float(level[1]) for level in bid_levels[:5])
                total_ask_volume = sum(float(level[1]) for level in ask_levels[:5])
                
                # If one side is significantly thinner
                imbalance_ratio = total_bid_volume / total_ask_volume if total_ask_volume > 0 else float('inf')
                
                if imbalance_ratio > 3:  # 3:1 bid/ask imbalance
                    return {
                        "status": "opportunity",
                        "signal": "buy_pressure",
                        "imbalance_ratio": imbalance_ratio,
                        "recommendation": "front_run_long"
                    }
                elif imbalance_ratio < 0.33:  # 1:3 bid/ask imbalance
                    return {
                        "status": "opportunity", 
                        "signal": "sell_pressure",
                        "imbalance_ratio": imbalance_ratio,
                        "recommendation": "front_run_short"
                    }
            
            return {"status": "balanced_book"}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class AdvancedRiskManager:
    """
    Advanced risk management for alpha strategies
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.max_position_size = {}
        self.correlation_matrix = {}
    
    async def dynamic_position_sizing(self, coin: str, base_size: float, volatility_lookback: int = 24) -> float:
        """
        Dynamic position sizing based on volatility
        """
        try:
            # Get volatility data
            candles = self.trader.info.candles_snapshot(coin, "1h", volatility_lookback)
            
            if len(candles) < 10:
                return base_size * 0.5  # Conservative if insufficient data
            
            # Calculate volatility
            returns = []
            for i in range(1, len(candles)):
                ret = (float(candles[i]['c']) - float(candles[i-1]['c'])) / float(candles[i-1]['c'])
                returns.append(ret)
            
            # Standard deviation of returns
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = variance ** 0.5
            
            # Inverse volatility scaling
            vol_scalar = min(2.0, max(0.1, 0.02 / volatility))  # Scale between 0.1x and 2x
            
            return base_size * vol_scalar
            
        except Exception:
            return base_size * 0.5
    
    async def portfolio_heat_check(self) -> Dict:
        """
        Check overall portfolio risk and heat
        """
        try:
            user_state = await self.trader.get_user_state()
            positions = user_state.get("assetPositions", [])
            
            total_exposure = 0
            risk_metrics = []
            
            for pos in positions:
                if float(pos["position"]["szi"]) != 0:
                    size = abs(float(pos["position"]["szi"]))
                    entry_px = float(pos["position"]["entryPx"])
                    
                    exposure = size * entry_px
                    total_exposure += exposure;
                    
                    risk_metrics.append({
                        "coin": pos["position"]["coin"],
                        "exposure": exposure,
                        "side": "long" if float(pos["position"]["szi"]) > 0 else "short"
                    })
            
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            return {
                "total_exposure": total_exposure,
                "account_value": account_value,
                "leverage_ratio": total_exposure / account_value if account_value > 0 else 0,
                "position_breakdown": risk_metrics,
                "risk_level": "high" if total_exposure / account_value > 10 else "medium" if total_exposure / account_value > 5 else "low"
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class ProfitOptimizer:
    """
    Profit optimization and compound strategies
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.profit_history = []
    
    async def compound_profits(self, reinvest_percentage: float = 0.8) -> Dict:
        """
        Automatically compound profits into larger positions
        """
        try:
            user_state = await self.trader.get_user_state()
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            withdrawable = float(user_state.get("withdrawable", 0))
            
            # Calculate available profits to compound
            available_for_compound = withdrawable * reinvest_percentage
            
            if available_for_compound > 100:  # Minimum $100 to compound
                # Find best performing strategies/coins
                recent_fills = await self.trader.get_user_fills()
                
                if recent_fills:
                    # Analyze which coins/strategies performed best
                    coin_performance = {}
                    for fill in recent_fills[-50:]:  # Last 50 trades
                        coin = fill["coin"]
                        pnl = float(fill.get("closedPnl", 0))
                        
                        if coin not in coin_performance:
                            coin_performance[coin] = {"pnl": 0, "trades": 0}
                        
                        coin_performance[coin]["pnl"] += pnl
                        coin_performance[coin]["trades"] += 1
                    
                    # Find best performing coin
                    best_coin = max(coin_performance.items(), key=lambda x: x[1]["pnl"])[0]
                    
                    return {
                        "status": "ready_to_compound",
                        "available_amount": available_for_compound,
                        "best_coin": best_coin,
                        "performance": coin_performance[best_coin]
                    }
            
            return {"status": "insufficient_profits", "available": available_for_compound}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def yield_farming_opportunities(self) -> Dict:
        """
        Find yield farming and staking opportunities
        """
        try:
            # Check funding rates for carry trades
            coins = ["BTC", "ETH", "SOL", "ARB", "AVAX"]  # Popular coins
            opportunities = []
            
            for coin in coins:
                funding_history = await self.trader.get_funding_history(coin)
                if funding_history:
                    avg_funding = sum(float(f["funding"]) for f in funding_history[-24:]) / len(funding_history[-24:])
                    
                    # Positive funding = longs pay shorts (short to earn)
                    # Negative funding = shorts pay longs (long to earn)
                    if abs(avg_funding) > 0.0001:  # 0.01% threshold
                        opportunities.append({
                            "coin": coin,
                            "avg_funding": avg_funding,
                            "strategy": "short" if avg_funding > 0 else "long",
                            "expected_apr": avg_funding * 365 * 3  # 3 times daily
                        })
            
            # Sort by expected return
            opportunities.sort(key=lambda x: abs(x["expected_apr"]), reverse=True)
            
            return {"status": "ok", "opportunities": opportunities}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class AutomatedTradingEngine:
    """
    Automated trading engine with advanced strategies
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.active_bots = {}
        self.performance_tracker = {}
        
    async def grid_trading_bot(self, coin: str, grid_size: float, num_grids: int, base_amount: float) -> Dict:
        """
        Advanced grid trading bot with dynamic adjustment
        """
        try:
            mids = await self.trader.get_all_mids()
            current_price = mids.get(coin)
            
            if not current_price:
                return {"status": "error", "message": f"No price data for {coin}"}
            
            # Calculate grid levels
            grid_spacing = current_price * grid_size
            buy_orders = []
            sell_orders = []
            
            for i in range(1, num_grids + 1):
                # Buy orders below current price
                buy_price = current_price - (grid_spacing * i)
                buy_orders.append({
                    "coin": coin,
                    "is_buy": True,
                    "size": base_amount,
                    "price": buy_price
                })
                
                # Sell orders above current price
                sell_price = current_price + (grid_spacing * i)
                sell_orders.append({
                    "coin": coin,
                    "is_buy": False,
                    "size": base_amount,
                    "price": sell_price
                })
            
            # Place all grid orders
            placed_orders = []
            for order in buy_orders + sell_orders:
                result = await self.trader.place_limit_order(
                    order["coin"], order["is_buy"], order["size"], 
                    order["price"], post_only=True
                )
                placed_orders.append(result)
            
            bot_id = f"grid_{coin}_{int(time.time())}"
            self.active_bots[bot_id] = {
                "type": "grid",
                "coin": coin,
                "orders": placed_orders,
                "created_at": time.time()
            }
            
            return {
                "status": "grid_active",
                "bot_id": bot_id,
                "orders_placed": len(placed_orders),
                "grid_range": f"{current_price - grid_spacing * num_grids:.2f} - {current_price + grid_spacing * num_grids:.2f}"
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def dca_bot(self, coin: str, buy_amount: float, interval_hours: int, target_amount: float) -> Dict:
        """
        Dollar Cost Averaging bot
        """
        try:
            bot_id = f"dca_{coin}_{int(time.time())}"
            
            # Get current position
            user_state = await self.trader.get_user_state()
            current_position = 0
            for pos in user_state.get("assetPositions", []):
                if pos["position"]["coin"] == coin:
                    current_position = float(pos["position"]["szi"])
                    break
            
            remaining_to_buy = target_amount - current_position
            
            if remaining_to_buy <= 0:
                return {"status": "target_reached", "current_position": current_position}
            
            # Place immediate buy order
            mids = await self.trader.get_all_mids()
            current_price = mids.get(coin)
            
            if current_price:
                result = await self.trader.place_market_order(
                    coin, True, min(buy_amount / current_price, remaining_to_buy), slippage=0.005
                )
                
                self.active_bots[bot_id] = {
                    "type": "dca",
                    "coin": coin,
                    "buy_amount": buy_amount,
                    "interval_hours": interval_hours,
                    "target_amount": target_amount,
                    "current_position": current_position,
                    "last_buy": time.time(),
                    "total_bought": min(buy_amount / current_price, remaining_to_buy)
                }
                
                return {
                    "status": "dca_started",
                    "bot_id": bot_id,
                    "first_buy": result,
                    "remaining": remaining_to_buy - min(buy_amount / current_price, remaining_to_buy)
                }
            
            return {"status": "error", "message": "No price data"}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def momentum_breakout_bot(self, coin: str, lookback_periods: int, breakout_threshold: float, position_size: float) -> Dict:
        """
        Momentum breakout trading bot
        """
        try:
            # Get historical data
            candles = self.trader.info.candles_snapshot(coin, "15m", lookback_periods)
            
            if len(candles) < lookback_periods:
                return {"status": "insufficient_data"}
            
            # Calculate recent high and low
            highs = [float(c['h']) for c in candles[-lookback_periods:]]
            lows = [float(c['l']) for c in candles[-lookback_periods:]]
            
            recent_high = max(highs)
            recent_low = min(lows)
            
            mids = await self.trader.get_all_mids()
            current_price = mids.get(coin)
            
            if not current_price:
                return {"status": "no_price_data"}
            
            # Check for breakout conditions
            upper_breakout = recent_high * (1 + breakout_threshold)
            lower_breakout = recent_low * (1 - breakout_threshold)
            
            signals = []
            
            if current_price > upper_breakout:
                # Bullish breakout - place long order
                result = await self.trader.place_market_order(
                    coin, True, position_size, slippage=0.01
                )
                signals.append({"type": "long_breakout", "price": current_price, "result": result})
            
            elif current_price < lower_breakout:
                # Bearish breakout - place short order  
                result = await self.trader.place_market_order(
                    coin, False, position_size, slippage=0.01
                )
                signals.append({"type": "short_breakout", "price": current_price, "result": result})
            
            bot_id = f"momentum_{coin}_{int(time.time())}"
            self.active_bots[bot_id] = {
                "type": "momentum",
                "coin": coin,
                "upper_breakout": upper_breakout,
                "lower_breakout": lower_breakout,
                "signals": signals
            }
            
            return {
                "status": "monitoring",
                "bot_id": bot_id,
                "breakout_levels": {"upper": upper_breakout, "lower": lower_breakout},
                "current_price": current_price,
                "signals": signals
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class AdvancedOrderManager:
    """
    Advanced order management with sophisticated order types
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.conditional_orders = {}
        
    async def trailing_stop_order(self, coin: str, position_size: float, trail_percentage: float) -> Dict:
        """
        Implement trailing stop loss
        """
        try:
            mids = await self.trader.get_all_mids()
            current_price = mids.get(coin)
            
            if not current_price:
                return {"status": "error", "message": "No price data"}
            
            # Determine if we're long or short based on position_size sign
            is_long = position_size > 0
            
            # Calculate initial stop price
            if is_long:
                stop_price = current_price * (1 - trail_percentage)
            else:
                stop_price = current_price * (1 + trail_percentage)
            
            order_id = f"trailing_{coin}_{int(time.time())}"
            self.conditional_orders[order_id] = {
                "type": "trailing_stop",
                "coin": coin,
                "position_size": position_size,
                "trail_percentage": trail_percentage,
                "stop_price": stop_price,
                "highest_price": current_price if is_long else None,
                "lowest_price": current_price if not is_long else None,
                "is_long": is_long,
                "created_at": time.time()
            }
            
            return {
                "status": "trailing_stop_active",
                "order_id": order_id,
                "initial_stop": stop_price,
                "current_price": current_price
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def iceberg_order(self, coin: str, total_size: float, slice_size: float, is_buy: bool, price: float) -> Dict:
        """
        Iceberg order execution - break large orders into smaller pieces
        """
        try:
            slices = []
            remaining_size = abs(total_size)
            slice_count = 0
            
            while remaining_size > 0:
                current_slice = min(slice_size, remaining_size)
                
                # Add some randomization to slice sizes and timing
                randomized_slice = current_slice * (0.8 + 0.4 * (time.time() % 1))  # 80-120% of slice_size
                randomized_slice = min(randomized_slice, remaining_size)
                
                result = await self.trader.place_limit_order(
                    coin, is_buy, randomized_slice, price, post_only=True
                )
                
                slices.append({
                    "slice_number": slice_count + 1,
                    "size": randomized_slice,
                    "result": result
                })
                
                remaining_size -= randomized_slice
                slice_count += 1
                
                # Wait between slices (randomized timing)
                await asyncio.sleep(1 + (time.time() % 3))  # 1-4 second delay
            
            return {
                "status": "iceberg_completed",
                "total_slices": slice_count,
                "total_size": total_size,
                "slices": slices
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def twap_order(self, coin: str, total_size: float, duration_minutes: int, is_buy: bool) -> Dict:
        """
        Time Weighted Average Price order execution
        """
        try:
            start_time = time.time()
            end_time = start_time + (duration_minutes * 60)
            
            # Calculate number of intervals (every 30 seconds)
            interval_seconds = 30
            num_intervals = (duration_minutes * 60) // interval_seconds
            size_per_interval = total_size / num_intervals
            
            executed_orders = []
            total_executed = 0
            
            for i in range(num_intervals):
                if time.time() >= end_time:
                    break
                
                # Get current market price for TWAP calculation
                mids = await self.trader.get_all_mids()
                current_price = mids.get(coin)
                
                if current_price:
                    # Place market order at current price
                    result = await self.trader.place_market_order(
                        coin, is_buy, size_per_interval, slippage=0.002
                    )
                    
                    executed_orders.append({
                        "interval": i + 1,
                        "size": size_per_interval,
                        "price": current_price,
                        "timestamp": time.time(),
                        "result": result
                    })
                    
                    total_executed += size_per_interval
                
                # Wait for next interval
                await asyncio.sleep(interval_seconds)
            
            # Calculate TWAP
            total_value = sum(order["size"] * order["price"] for order in executed_orders if "price" in order)
            twap_price = total_value / total_executed if total_executed > 0 else 0
            
            return {
                "status": "twap_completed",
                "total_executed": total_executed,
                "twap_price": twap_price,
                "num_orders": len(executed_orders),
                "duration_actual": time.time() - start_time,
                "orders": executed_orders
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class MarketMakingEngine:
    """
    Professional market making strategies
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.mm_positions = {}
        
    async def basic_market_maker(self, coin: str, spread_bps: int, order_size: float, max_position: float) -> Dict:
        """
        Basic market making strategy
        """
        try:
            mids = await self.trader.get_all_mids()
            mid_price = mids.get(coin)
            
            if not mid_price:
                return {"status": "error", "message": "No price data"}
            
            # Calculate bid/ask prices
            spread = mid_price * (spread_bps / 10000)  # Convert bps to decimal
            bid_price = mid_price - (spread / 2)
            ask_price = mid_price + (spread / 2)
            
            # Check current position
            user_state = await self.trader.get_user_state()
            current_position = 0
            for pos in user_state.get("assetPositions", []):
                if pos["position"]["coin"] == coin:
                    current_position = float(pos["position"]["szi"])
                    break
            
            orders_placed = []
            
            # Place bid if we're not too long
            if current_position < max_position:
                bid_result = await self.trader.place_limit_order(
                    coin, True, order_size, bid_price, post_only=True
                )
                orders_placed.append({"side": "bid", "price": bid_price, "result": bid_result})
            
            # Place ask if we're not too short
            if current_position > -max_position:
                ask_result = await self.trader.place_limit_order(
                    coin, False, order_size, ask_price, post_only=True
                )
                orders_placed.append({"side": "ask", "price": ask_price, "result": ask_result})
            
            mm_id = f"mm_{coin}_{int(time.time())}"
            self.mm_positions[mm_id] = {
                "coin": coin,
                "mid_price": mid_price,
                "spread_bps": spread_bps,
                "current_position": current_position,
                "orders": orders_placed,
                "created_at": time.time()
            }
            
            return {
                "status": "market_making_active",
                "mm_id": mm_id,
                "mid_price": mid_price,
                "bid_price": bid_price,
                "ask_price": ask_price,
                "current_position": current_position,
                "orders_placed": len(orders_placed)
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def inventory_management(self, coin: str, target_inventory: float, rebalance_threshold: float) -> Dict:
        """
        Inventory management for market makers
        """
        try:
            user_state = await self.trader.get_user_state()
            current_position = 0
            
            for pos in user_state.get("assetPositions", []):
                if pos["position"]["coin"] == coin:
                    current_position = float(pos["position"]["szi"])
                    break
            
            inventory_deviation = current_position - target_inventory
            
            if abs(inventory_deviation) > rebalance_threshold:
                # Need to rebalance
                mids = await self.trader.get_all_mids()
                current_price = mids.get(coin)
                
                if current_price:
                    # If we're too long, sell the excess
                    # If we're too short, buy to cover
                    is_buy = inventory_deviation < 0
                    rebalance_size = abs(inventory_deviation)
                    
                    result = await self.trader.place_market_order(
                        coin, is_buy, rebalance_size, slippage=0.005
                    )
                    
                    return {
                        "status": "rebalanced",
                        "previous_position": current_position,
                        "target_inventory": target_inventory,
                        "rebalance_size": rebalance_size,
                        "direction": "buy" if is_buy else "sell",
                        "result": result
                    }
            
            return {
                "status": "within_threshold",
                "current_position": current_position,
                "target_inventory": target_inventory,
                "deviation": inventory_deviation
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class PerpetualDexManager:
    """
    Manager for perpetual DEX operations
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
    
    async def deploy_perp_dex(self, dex_name: str, full_name: str, oracle_updater: str, max_gas: int) -> Dict:
        """
        Deploy a new perpetual DEX
        """
        try:
            perp_dex_schema_input = {
                "fullName": full_name,
                "collateralToken": 0,  # USDC
                "oracleUpdater": oracle_updater,
            }
            
            # Register first asset to create the DEX
            register_result = self.trader.exchange.perp_deploy_register_asset(
                dex=dex_name,
                max_gas=max_gas,
                coin=f"{dex_name}:ASSET0",
                sz_decimals=2,
                oracle_px="1.0",
                margin_table_id=10,
                only_isolated=False,
                schema=perp_dex_schema_input
            )
            
            return {
                "status": "dex_deployed" if register_result.get("status") == "ok" else "deployment_failed",
                "dex_name": dex_name,
                "result": register_result
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def add_perp_asset(self, dex_name: str, asset_name: str, oracle_price: str, max_gas: int) -> Dict:
        """
        Add new asset to existing perpetual DEX
        """
        try:
            coin_symbol = f"{dex_name}:{asset_name}"
            
            register_result = self.trader.exchange.perp_deploy_register_asset(
                dex=dex_name,
                max_gas=max_gas,
                coin=coin_symbol,
                sz_decimals=2,
                oracle_px=oracle_price,
                margin_table_id=10,
                only_isolated=False,
                schema=None  # No schema needed for additional assets
            )
            
            return {
                "status": "asset_added" if register_result.get("status") == "ok" else "add_failed",
                "dex_name": dex_name,
                "asset_name": asset_name,
                "coin_symbol": coin_symbol,
                "result": register_result
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def update_oracle_prices(self, dex_name: str, price_updates: Dict[str, str]) -> Dict:
        """
        Update oracle prices for DEX assets
        """
        try:
            # Format prices for oracle update
            oracle_prices = {}
            twap_prices = {}
            
            for asset, price in price_updates.items():
                coin_symbol = f"{dex_name}:{asset}"
                oracle_prices[coin_symbol] = price
                # Set TWAP slightly different for volatility
                twap_prices[coin_symbol] = str(float(price) * 1.001)
            
            oracle_result = self.trader.exchange.perp_deploy_set_oracle(
                dex_name,
                oracle_prices,
                twap_prices
            )
            
            return {
                "status": "oracle_updated" if oracle_result.get("status") == "ok" else "update_failed",
                "dex_name": dex_name,
                "updated_assets": list(price_updates.keys()),
                "result": oracle_result
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


class PortfolioAnalyzer:
    """
    Advanced portfolio analysis and optimization
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
    
    async def portfolio_performance(self, days_back: int = 30) -> Dict:
        """
        Comprehensive portfolio performance analysis
        """
        try:
            # Get user fills for the period
            start_time = int((time.time() - days_back * 24 * 3600) * 1000)
            fills = await self.trader.get_user_fills(start_time)
            
            # Get current user state
            user_state = await self.trader.get_user_state()
            current_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Calculate performance metrics
            total_pnl = sum(float(fill.get("closedPnl", 0)) for fill in fills)
            total_fees = sum(float(fill.get("fee", 0)) for fill in fills)
            trade_count = len(fills)
            
            # Win rate calculation
            winning_trades = sum(1 for fill in fills if float(fill.get("closedPnl", 0)) > 0)
            win_rate = (winning_trades / trade_count * 100) if trade_count > 0 else 0
            
            # Average trade metrics
            avg_trade_pnl = total_pnl / trade_count if trade_count > 0 else 0
            avg_trade_fee = total_fees / trade_count if trade_count > 0 else 0
            
            # Coin-wise performance
            coin_performance = {}
            for fill in fills:
                coin = fill["coin"]
                pnl = float(fill.get("closedPnl", 0))
                
                if coin not in coin_performance:
                    coin_performance[coin] = {"pnl": 0, "trades": 0, "fees": 0}
                
                coin_performance[coin]["pnl"] += pnl
                coin_performance[coin]["trades"] += 1
                coin_performance[coin]["fees"] += float(fill.get("fee", 0))
            
            # Sort coins by performance
            sorted_coins = sorted(coin_performance.items(), key=lambda x: x[1]["pnl"], reverse=True)
            
            return {
                "period_days": days_back,
                "current_account_value": current_value,
                "total_pnl": total_pnl,
                "total_fees": total_fees,
                "net_pnl": total_pnl - abs(total_fees),
                "trade_count": trade_count,
                "win_rate": win_rate,
                "avg_trade_pnl": avg_trade_pnl,
                "avg_trade_fee": avg_trade_fee,
                "best_coin": sorted_coins[0] if sorted_coins else None,
                "worst_coin": sorted_coins[-1] if sorted_coins else None,
                "coin_breakdown": dict(sorted_coins[:10])  # Top 10 coins
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def risk_metrics(self) -> Dict:
        """
        Calculate comprehensive risk metrics
        """
        try:
            user_state = await self.trader.get_user_state()
            margin_summary = user_state.get("marginSummary", {})
            
            account_value = float(margin_summary.get("accountValue", 0))
            total_margin_used = float(margin_summary.get("totalMarginUsed", 0))
            total_ntl_pos = float(margin_summary.get("totalNtlPos", 0))
            total_raw_usd = float(margin_summary.get("totalRawUsd", 0))
            
            # Calculate leverage and utilization
            effective_leverage = total_ntl_pos / account_value if account_value > 0 else 0
            margin_utilization = total_margin_used / account_value if account_value > 0 else 0
            
            # Position analysis
            positions = user_state.get("assetPositions", [])
            position_count = sum(1 for pos in positions if float(pos["position"]["szi"]) != 0)
            
            # Largest position risk
            largest_position = 0
            largest_coin = ""
            for pos in positions:
                if float(pos["position"]["szi"]) != 0:
                    position_value = abs(float(pos["position"]["szi"]) * float(pos["position"]["entryPx"]))
                    if position_value > largest_position:
                        largest_position = position_value
                        largest_coin = pos["position"]["coin"]
            
            concentration_risk = largest_position / account_value if account_value > 0 else 0
            
            # Risk level assessment
            risk_level = "low"
            if effective_leverage > 10 or margin_utilization > 0.8 or concentration_risk > 0.5:
                risk_level = "high"
            elif effective_leverage > 5 or margin_utilization > 0.5 or concentration_risk > 0.3:
                risk_level = "medium"
            
            return {
                "account_value": account_value,
                "effective_leverage": effective_leverage,
                "margin_utilization": margin_utilization,
                "position_count": position_count,
                "largest_position": {"coin": largest_coin, "value": largest_position},
                "concentration_risk": concentration_risk,
                "risk_level": risk_level,
                "total_notional": total_ntl_pos,
                "available_margin": account_value - total_margin_used
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


@dataclass
class TradingSignal:
    """Data class for trading signals"""
    coin: str
    signal: str  # "BUY", "SELL", "HOLD"
    confidence: float
    price_target: float
    stop_loss: float
    timeframe: str
    strategy: str
    timestamp: float

class AITradingEngine:
    """
    AI-powered trading engine with machine learning models
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.models = {}
        self.scalers = {}
        self.price_history = {}
        self.signals_history = []
        
    async def train_ml_model(self, coin: str, lookback_days: int = 30) -> Dict:
        """
        Train ML model for price prediction
        """
        try:
            # Get historical data
            start_time = int((time.time() - lookback_days * 24 * 3600) * 1000)
            fills = await self.trader.get_user_fills(start_time)
            
            if len(fills) < 100:
                return {"status": "insufficient_data", "fills_count": len(fills)}
            
            # Prepare features and targets
            df = pd.DataFrame(fills)
            df = df[df['coin'] == coin].copy()
            
            if len(df) < 50:
                return {"status": "insufficient_coin_data", "coin_fills": len(df)}
            
            # Create features
            df['price'] = df['px'].astype(float)
            df['volume'] = df['sz'].astype(float)
            df['timestamp'] = pd.to_datetime(df['time'], unit='ms')
            df = df.set_index('timestamp').sort_index()
            
            # Technical indicators
            df['rsi'] = ta.momentum.RSIIndicator(df['price']).rsi()
            df['macd'] = ta.trend.MACD(df['price']).macd()
            df['bb_upper'] = ta.volatility.BollingerBands(df['price']).bollinger_hband()
            df['bb_lower'] = ta.volatility.BollingerBands(df['price']).bollinger_lband()
            df['sma_20'] = ta.trend.SMAIndicator(df['price'], window=20).sma_indicator()
            df['ema_12'] = ta.trend.EMAIndicator(df['price'], window=12).ema_indicator()
            
            # Price change features
            df['price_change_1h'] = df['price'].pct_change(periods=1)
            df['price_change_4h'] = df['price'].pct_change(periods=4)
            df['volume_ma'] = df['volume'].rolling(window=10).mean()
            df['volume_ratio'] = df['volume'] / df['volume_ma']
            
            # Create target (future price movement)
            df['future_return'] = df['price'].shift(-5).pct_change()
            df['target'] = (df['future_return'] > 0.005).astype(int)  # 0.5% threshold
            
            # Prepare training data
            feature_cols = ['rsi', 'macd', 'price_change_1h', 'price_change_4h', 'volume_ratio']
            df_clean = df[feature_cols + ['target']].dropna()
            
            if len(df_clean) < 30:
                return {"status": "insufficient_clean_data", "clean_rows": len(df_clean)}
            
            X = df_clean[feature_cols].values
            y = df_clean['target'].values
            
            # Scale features
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # Train model
            model = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=3,
                random_state=42
            )
            model.fit(X_scaled, y)
            
            # Store model and scaler
            self.models[coin] = model
            self.scalers[coin] = scaler
            
            # Calculate accuracy
            accuracy = model.score(X_scaled, y)
            
            return {
                "status": "model_trained",
                "coin": coin,
                "accuracy": accuracy,
                "features": feature_cols,
                "training_samples": len(X)
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def generate_ai_signal(self, coin: str) -> Optional[TradingSignal]:
        """
        Generate AI-powered trading signal
        """
        try:
            if coin not in self.models:
                # Train model if not exists
                train_result = await self.train_ml_model(coin)
                if train_result["status"] != "model_trained":
                    return None
            
            # Get current market data
            mids = await self.trader.get_all_mids()
            current_price = mids.get(coin)
            orderbook = await self.trader.get_orderbook(coin)
            
            if not current_price:
                return None
            
            # Get recent fills for feature calculation
            recent_fills = await self.trader.get_user_fills()
            coin_fills = [f for f in recent_fills if f['coin'] == coin][-20:]  # Last 20 fills
            
            if len(coin_fills) < 10:
                return None
            
            # Calculate current features
            prices = [float(f['px']) for f in coin_fills]
            volumes = [float(f['sz']) for f in coin_fills]
            
            if len(prices) < 5:
                return None
            
            # Simple technical indicators
            rsi = self._calculate_rsi(prices)
            price_change_1h = (prices[-1] - prices[-2]) / prices[-2] if len(prices) > 1 else 0
            price_change_4h = (prices[-1] - prices[-5]) / prices[-5] if len(prices) > 4 else 0
            volume_avg = np.mean(volumes[:-1]) if len(volumes) > 1 else volumes[0]
            volume_ratio = volumes[-1] / volume_avg if volume_avg > 0 else 1
            
            # Calculate MACD
            macd = self._calculate_macd(prices)
            
            # Prepare features
            features = np.array([[rsi, macd, price_change_1h, price_change_4h, volume_ratio]])
            
            # Scale features
            features_scaled = self.scalers[coin].transform(features)
            
            # Get prediction
            model = self.models[coin]
            prediction = model.predict(features_scaled)[0]
            confidence = max(model.predict_proba(features_scaled)[0])
            
            # Generate signal
            if prediction == 1 and confidence > 0.7:  # High confidence buy
                signal_type = "BUY"
                price_target = current_price * 1.02  # 2% target
                stop_loss = current_price * 0.995   # 0.5% stop
            elif prediction == 0 and confidence > 0.7:  # High confidence sell
                signal_type = "SELL"
                price_target = current_price * 0.98  # 2% target
                stop_loss = current_price * 1.005   # 0.5% stop
            else:
                signal_type = "HOLD"
                price_target = current_price
                stop_loss = current_price
            
            signal = TradingSignal(
                coin=coin,
                signal=signal_type,
                confidence=confidence,
                price_target=price_target,
                stop_loss=stop_loss,
                timeframe="15m",
                strategy="AI_ML",
                timestamp=time.time()
            )
            
            self.signals_history.append(signal)
            return signal
            
        except Exception as e:
            print(f"Error generating AI signal: {e}")
            return None
    
    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI indicator"""
        if len(prices) < period + 1:
            return 50.0  # Neutral RSI
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, prices: List[float]) -> float:
        """Calculate MACD indicator"""
        if len(prices) < 26:
            return 0.0
        
        ema_12 = self._calculate_ema(prices, 12)
        ema_26 = self._calculate_ema(prices, 26)
        return ema_12 - ema_26
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return np.mean(prices)
        
        multiplier = 2 / (period + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema


class RealTimeMonitor:
    """
    Real-time market monitoring with WebSocket connections
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.ws_connections = {}
        self.price_alerts = {}
        self.volume_alerts = {}
        self.running = False
        
    def start_monitoring(self, coins: List[str]):
        """Start real-time monitoring for specified coins"""
        self.running = True
        
        for coin in coins:
            threading.Thread(
                target=self._monitor_coin,
                args=(coin,),
                daemon=True
            ).start()
    
    def stop_monitoring(self):
        """Stop all monitoring"""
        self.running = False
        for ws in self.ws_connections.values():
            if ws:
                ws.close()
    
    def _monitor_coin(self, coin: str):
        """Monitor a specific coin via WebSocket"""
        try:
            # Create WebSocket connection for real-time data
            ws_url = f"wss://api.hyperliquid.xyz/ws"
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    self._process_market_data(coin, data)
                except Exception as e:
                    print(f"Error processing WebSocket message: {e}")
            
            def on_error(ws, error):
                print(f"WebSocket error for {coin}: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                print(f"WebSocket closed for {coin}")
            
            def on_open(ws):
                # Subscribe to market data
                subscribe_msg = {
                    "method": "subscribe",
                    "subscription": {"type": "l2Book", "coin": coin}
                }
                ws.send(json.dumps(subscribe_msg))
            
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            self.ws_connections[coin] = ws
            ws.run_forever()
            
        except Exception as e:
            print(f"Error setting up WebSocket for {coin}: {e}")
    
    def _process_market_data(self, coin: str, data: Dict):
        """Process incoming market data and trigger alerts"""
        try:
            if data.get("channel") == "l2Book":
                orderbook_data = data.get("data", {})
                
                # Check for large orders (whale alerts)
                self._check_whale_activity(coin, orderbook_data)
                
                # Check price alerts
                self._check_price_alerts(coin, orderbook_data)
                
                # Check volume spikes
                self._check_volume_spikes(coin, orderbook_data)
                
        except Exception as e:
            print(f"Error processing market data: {e}")
    
    def _check_whale_activity(self, coin: str, orderbook: Dict):
        """Detect large orders (whale activity)"""
        try:
            bids = orderbook.get("levels", [[], []])[0]
            asks = orderbook.get("levels", [[], []])[1]
            
            whale_threshold = 50000  # $50k+ orders
            
            for level in bids[:5]:  # Top 5 bid levels
                if len(level) >= 2 and float(level[1]) > whale_threshold:
                    self._trigger_whale_alert(coin, "large_bid", level[0], level[1])
            
            for level in asks[:5]:  # Top 5 ask levels
                if len(level) >= 2 and float(level[1]) > whale_threshold:
                    self._trigger_whale_alert(coin, "large_ask", level[0], level[1])
                    
        except Exception as e:
            print(f"Error checking whale activity: {e}")
    
    def _trigger_whale_alert(self, coin: str, order_type: str, price: str, size: str):
        """Trigger whale activity alert"""
        alert = {
            "type": "whale_alert",
            "coin": coin,
            "order_type": order_type,
            "price": price,
            "size": size,
            "timestamp": time.time(),
            "usd_value": float(price) * float(size)
        }
        
        # Store alert for processing
        print(f"🐋 WHALE ALERT: {coin} - {order_type} ${alert['usd_value']:,.0f} at ${price}")
        
        # Could trigger automatic trading here
        asyncio.create_task(self._handle_whale_signal(alert))
    
    async def _handle_whale_signal(self, alert: Dict):
        """Handle whale activity with trading action"""
        try:
            coin = alert["coin"]
            order_type = alert["order_type"]
            
            # Simple whale following strategy
            if order_type == "large_bid" and alert["usd_value"] > 100000:
                # Large bid detected - might indicate bullish sentiment
                size = min(1000 / float(alert["price"]), 0.1)  # $1000 or 0.1 coins max
                
                result = await self.trader.place_limit_order(
                    coin, True, size, float(alert["price"]) * 1.001, post_only=True
                )
                print(f"🚀 Following whale: Placed buy order for {coin}")
                
        except Exception as e:
            print(f"Error handling whale signal: {e}")


class CrossChainArbitrage:
    """
    Cross-chain arbitrage opportunities detector and executor
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.external_prices = {}
        self.arbitrage_opportunities = []
        
    async def scan_arbitrage_opportunities(self, coins: List[str]) -> List[Dict]:
        """
        Scan for arbitrage opportunities across exchanges
        """
        opportunities = []
        
        try:
            # Get Hyperliquid prices
            hl_prices = await self.trader.get_all_mids()
            
            for coin in coins:
                hl_price = hl_prices.get(coin)
                if not hl_price:
                    continue
                
                # Get external exchange prices (simulated)
                external_price = await self._get_external_price(coin)
                
                if external_price:
                    price_diff = abs(hl_price - external_price) / min(hl_price, external_price)
                    
                    if price_diff > 0.005:  # 0.5% arbitrage threshold
                        opportunity = {
                            "coin": coin,
                            "hl_price": hl_price,
                            "external_price": external_price,
                            "price_diff_pct": price_diff * 100,
                            "direction": "buy_hl" if hl_price < external_price else "sell_hl",
                            "potential_profit": price_diff,
                            "timestamp": time.time()
                        }
                        opportunities.append(opportunity)
            
            self.arbitrage_opportunities = opportunities
            return opportunities
            
        except Exception as e:
            print(f"Error scanning arbitrage: {e}")
            return []
    
    async def _get_external_price(self, coin: str) -> Optional[float]:
        """
        Get price from external exchanges (implement actual API calls)
        """
        # Simulate external price with slight variation
        hl_prices = await self.trader.get_all_mids()
        base_price = hl_prices.get(coin)
        
        if base_price:
            # Simulate 0.1-1% price difference
            variation = np.random.uniform(0.999, 1.01)
            return base_price * variation
        
        return None
    
    async def execute_arbitrage(self, opportunity: Dict, max_size: float = 1000) -> Dict:
        """
        Execute arbitrage trade
        """
        try:
            coin = opportunity["coin"]
            direction = opportunity["direction"]
            
            if direction == "buy_hl":
                # Buy on Hyperliquid, sell on external
                size = min(max_size / opportunity["hl_price"], 1.0)
                
                result = await self.trader.place_market_order(
                    coin, True, size, slippage=0.001
                )
                
                return {
                    "status": "executed",
                    "coin": coin,
                    "direction": direction,
                    "size": size,
                    "expected_profit": opportunity["potential_profit"] * size * opportunity["hl_price"],
                    "result": result
                }
            
            else:  # sell_hl
                # Sell on Hyperliquid, buy on external
                size = min(max_size / opportunity["hl_price"], 1.0)
                
                result = await self.trader.place_market_order(
                    coin, False, size, slippage=0.001
                )
                
                return {
                    "status": "executed",
                    "coin": coin,
                    "direction": direction,
                    "size": size,
                    "expected_profit": opportunity["potential_profit"] * size * opportunity["hl_price"],
                    "result": result
                }
                
        except Exception as e:
            return {"status": "error", "message": str(e)}


class AdvancedSecurityManager:
    """
    Advanced security features for trading operations
    """
    
    def __init__(self):
        self.risk_limits = {}
        self.suspicious_activity = []
        self.daily_limits = {}
        
    def setup_risklimits(self, user_id: int, limits: Dict):
        """Setup risk limits for a user"""
        self.risk_limits[user_id] = {
            "max_daily_volume": limits.get("max_daily_volume", 10000),
            "max_position_size": limits.get("max_position_size", 5000),
            "max_leverage": limits.get("max_leverage", 10),
            "allowed_coins": limits.get("allowed_coins", ["BTC", "ETH"]),
            "max_slippage": limits.get("max_slippage", 0.02),
            "created_at": time.time()
        }
    
    async def validate_trade(self, user_id: int, trade: Dict) -> Dict:
        """Validate trade against risk limits"""
        if user_id not in self.risk_limits:
            return {"status": "error", "message": "No risk limits set"}
        
        limits = self.risk_limits[user_id]
        
        # Check coin whitelist
        if trade["coin"] not in limits["allowed_coins"]:
            return {"status": "rejected", "reason": "coin_not_allowed"}
        
        # Check position size
        trade_value = trade["size"] * trade.get("price", 0)
        if trade_value > limits["max_position_size"]:
            return {"status": "rejected", "reason": "position_too_large"}
        
        # Check daily volume
        today = time.strftime("%Y-%m-%d")
        if user_id not in self.daily_limits:
            self.daily_limits[user_id] = {}
        
        if today not in self.daily_limits[user_id]:
            self.daily_limits[user_id][today] = 0
        
        if self.daily_limits[user_id][today] + trade_value > limits["max_daily_volume"]:
            return {"status": "rejected", "reason": "daily_limit_exceeded"}
        
        # Update daily volume
        self.daily_limits[user_id][today] += trade_value
        
        return {"status": "approved"}
    
    def detect_suspicious_activity(self, user_id: int, activity: Dict) -> bool:
        """Detect suspicious trading activity"""
        # Check for rapid fire trading
        recent_trades = [a for a in self.suspicious_activity 
                        if a.get("user_id") == user_id and 
                        time.time() - a.get("timestamp", 0) < 300]  # 5 minutes
        
        if len(recent_trades) > 20:  # More than 20 trades in 5 minutes
            return True
        
        # Check for unusual trade sizes
        if activity.get("trade_value", 0) > 50000:  # $50k+ trades
            return True
        
        return False
    
    def encrypt_sensitive_data(self, data: str, key: bytes) -> bytes:
        """Encrypt sensitive data like private keys"""
        from cryptography.fernet import Fernet
        f = Fernet(key)
        return f.encrypt(data.encode())
    
    def decrypt_sensitive_data(self, encrypted_data: bytes, key: bytes) -> str:
        """Decrypt sensitive data"""
        from cryptography.fernet import Fernet
        f = Fernet(key)
        return f.decrypt(encrypted_data).decode()


class ProfitMaximizer:
    """
    Advanced profit maximization engine
    """
    
    def __init__(self, trader: HyperliquidTrader):
        self.trader = trader
        self.profit_strategies = []
        self.performance_metrics = {}
        
    async def optimize_strategy_allocation(self) -> Dict:
        """
        Optimize capital allocation across strategies based on performance
        """
        try:
            # Get recent performance data
            user_state = await self.trader.get_user_state()
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Get recent fills to analyze strategy performance
            recent_fills = await self.trader.get_user_fills()
            
            if not recent_fills:
                return {"status": "no_data"}
            
            # Analyze performance by coin/strategy
            strategy_performance = {}
            for fill in recent_fills[-100:]:  # Last 100 trades
                coin = fill["coin"]
                pnl = float(fill.get("closedPnl", 0))
                
                if coin not in strategy_performance:
                    strategy_performance[coin] = {"total_pnl": 0, "trades": 0, "win_rate": 0}
                
                strategy_performance[coin]["total_pnl"] += pnl
                strategy_performance[coin]["trades"] += 1
                if pnl > 0:
                    strategy_performance[coin]["win_rate"] += 1
            
            # Calculate win rates and Sharpe ratios
            for coin in strategy_performance:
                perf = strategy_performance[coin]
                perf["win_rate"] = perf["win_rate"] / perf["trades"] if perf["trades"] > 0 else 0
                perf["avg_pnl"] = perf["total_pnl"] / perf["trades"] if perf["trades"] > 0 else 0
            
            # Sort by performance
            sorted_strategies = sorted(
                strategy_performance.items(),
                key=lambda x: x[1]["total_pnl"],
                reverse=True
            )
            
            # Allocate capital based on performance
            total_allocation = account_value * 0.8  # Use 80% of account
            allocations = {}
            
            for i, (coin, perf) in enumerate(sorted_strategies[:5]):  # Top 5 performers
                if perf["total_pnl"] > 0 and perf["win_rate"] > 0.6:
                    # Allocate more to better performers
                    weight = (6 - i) / 15  # Weights: 5/15, 4/15, 3/15, 2/15, 1/15
                    allocations[coin] = total_allocation * weight
            
            return {
                "status": "optimized",
                "total_allocation": total_allocation,
                "allocations": allocations,
                "top_performers": dict(sorted_strategies[:3])
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def compound_winning_trades(self, compound_rate: float = 0.5) -> Dict:
        """
        Automatically compound profits from winning trades
        """
        try:
            # Get recent profitable trades
            recent_fills = await self.trader.get_user_fills()
            winning_trades = [f for f in recent_fills[-20:] if float(f.get("closedPnl", 0)) > 10]
            
            if not winning_trades:
                return {"status": "no_winning_trades"}
            
            total_profits = sum(float(f.get("closedPnl", 0)) for f in winning_trades)
            compound_amount = total_profits * compound_rate
            
            if compound_amount < 100:  # Minimum $100 to compound
                return {"status": "insufficient_profits", "profits": total_profits}
            
            # Find best performing coin to compound into
            coin_profits = {}
            for trade in winning_trades:
                coin = trade["coin"]
                pnl = float(trade.get("closedPnl", 0))
                coin_profits[coin] = coin_profits.get(coin, 0) + pnl
            
            best_coin = max(coin_profits.items(), key=lambda x: x[1])[0]
            
            # Place compound trade
            mids = await self.trader.get_all_mids()
            current_price = mids.get(best_coin)
            
            if current_price:
                size = compound_amount / current_price
                
                result = await self.trader.place_market_order(
                    best_coin, True, size, slippage=0.005
                )
                
                return {
                    "status": "compounded",
                    "amount": compound_amount,
                    "coin": best_coin,
                    "size": size,
                    "result": result
                }
            
            return {"status": "no_price_data"}
            
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Example usage patterns
async def main():
    """Example usage of the comprehensive trading system"""
    
    # Initialize all components
    trader = HyperliquidTrader("config.json", testnet=True)
    ai_engine = AITradingEngine(trader)
    monitor = RealTimeMonitor(trader)
    arbitrage = CrossChainArbitrage(trader)
    security = AdvancedSecurityManager()
    profit_max = ProfitMaximizer(trader)
    
    # Setup security limits
    security.setup_risk_limits(123, {
        "max_daily_volume": 10000,
        "max_position_size": 2000,
        "allowed_coins": ["BTC", "ETH", "SOL"]
    })
    
    # Start real-time monitoring
    monitor.start_monitoring(["BTC", "ETH", "SOL"])
    
    # Train AI models
    for coin in ["BTC", "ETH"]:
        await ai_engine.train_ml_model(coin)
    
    # Main trading loop
    try:
        while True:
            # Generate AI signals
            for coin in ["BTC", "ETH"]:
                signal = await ai_engine.generate_ai_signal(coin)
                if signal and signal.signal != "HOLD":
                    print(f"🤖 AI Signal: {signal.signal} {signal.coin} (confidence: {signal.confidence:.2f})")
                    
                    # Validate trade with security manager
                    trade_request = {
                        "coin": signal.coin,
                        "size": 0.01,
                        "price": signal.price_target
                    }
                    
                    validation = await security.validate_trade(123, trade_request)
                    if validation["status"] == "approved":
                        # Execute AI signal
                        if signal.signal == "BUY":
                            await trader.place_limit_order(
                                signal.coin, True, 0.01, signal.price_target, post_only=True
                            )
                        else:
                            await trader.place_limit_order(
                                signal.coin, False, 0.01, signal.price_target, post_only=True
                            )
            
            # Scan for arbitrage opportunities
            arb_opportunities = await arbitrage.scan_arbitrage_opportunities(["BTC", "ETH"])
            for opp in arb_opportunities:
                if opp["price_diff_pct"] > 1.0:  # 1%+ arbitrage
                    print(f"💰 Arbitrage: {opp['coin']} - {opp['price_diff_pct']:.2f}% profit")
                    await arbitrage.execute_arbitrage(opp, max_size=500)
            
            # Optimize strategy allocation
            optimization = await profit_max.optimize_strategy_allocation()
            if optimization["status"] == "optimized":
                print(f"📊 Portfolio optimized: {len(optimization['allocations'])} strategies")
            
            # Compound profits
            compound_result = await profit_max.compound_winning_trades()
            if compound_result["status"] == "compounded":
                print(f"💎 Compounded ${compound_result['amount']:.2f} into {compound_result['coin']}")
            
            # Wait before next iteration
            await asyncio.sleep(30)  # 30 second intervals
            
    except KeyboardInterrupt:
        print("Stopping trading system...")
        monitor.stop_monitoring()

if __name__ == "__main__":
    # Run the comprehensive trading system
    asyncio.run(main())
