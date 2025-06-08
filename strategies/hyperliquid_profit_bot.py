import asyncio
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid
import sys
import os
import logging
import numpy as np
from scipy.optimize import minimize

# Real Hyperliquid imports
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Import actual examples for real patterns
examples_dir = os.path.join(os.path.dirname(__file__), '..', 'examples')
sys.path.append(examples_dir)

import basic_order
import basic_adding
import example_utils

logger = logging.getLogger(__name__)

class PriceUtils:
    """
    Utility class to handle price precision, tick sizes, and order placement validation
    for different assets on Hyperliquid
    """
    
    # Define standard tick sizes for common assets
    TICK_SIZES = {
        "BTC": 0.1,       # BTC uses 0.1 increments
        "ETH": 0.01,      # ETH uses 0.01 increments
        "SOL": 0.01,      # SOL uses 0.01 increments
        "AVAX": 0.01,     # AVAX uses 0.01 increments
        "ARB": 0.0001,    # ARB uses 0.0001 increments
        "DOGE": 0.00001,  # DOGE uses 0.00001 increments
        "LINK": 0.001,    # LINK uses 0.001 increments
        "LTC": 0.01,      # LTC uses 0.01 increments
        "MATIC": 0.0001,  # MATIC uses 0.0001 increments
        "OP": 0.001,      # OP uses 0.001 increments
        "XRP": 0.0001     # XRP uses 0.0001 increments
    }
    
    # Minimum price increments from the current best bid/ask
    # to ensure orders don't immediately match (post-only)
    SAFE_INCREMENTS = {
        "BTC": 0.1,
        "ETH": 0.01,
        "SOL": 0.01,
        "AVAX": 0.01,
        "ARB": 0.0001,
        "DOGE": 0.00001,
        "LINK": 0.001
    }
    
    @staticmethod
    def get_tick_size(coin: str) -> float:
        """
        Get the tick size for a specific coin
        
        Args:
            coin (str): Coin symbol (e.g., "BTC", "ETH")
            
        Returns:
            float: Tick size for the coin, defaults to 0.0001 if not explicitly defined
        """
        return PriceUtils.TICK_SIZES.get(coin.upper(), 0.0001)
    
    @staticmethod
    def get_safe_increment(coin: str) -> float:
        """
        Get the safe price increment to avoid immediate matching
        
        Args:
            coin (str): Coin symbol
            
        Returns:
            float: Safe increment, defaults to the coin's tick size
        """
        coin = coin.upper()
        return PriceUtils.SAFE_INCREMENTS.get(coin, PriceUtils.get_tick_size(coin))
    
    @staticmethod
    def round_to_tick(price: float, coin: str) -> float:
        """
        Round a price to the nearest valid tick size for the specified coin
        
        Args:
            price (float): Raw price to round
            coin (str): Coin symbol 
            
        Returns:
            float: Price rounded to the nearest valid tick
        """
        tick_size = PriceUtils.get_tick_size(coin)
        # Round to nearest tick to avoid floating point errors
        return round(round(price / tick_size) * tick_size, 10)
    
    @staticmethod
    def validate_price(price: float, coin: str) -> Tuple[bool, str]:
        """
        Validate if a price is valid for the specified coin
        
        Args:
            price (float): Price to validate
            coin (str): Coin symbol
            
        Returns:
            tuple: (is_valid, error_message)
        """
        tick_size = PriceUtils.get_tick_size(coin)
        rounded_price = PriceUtils.round_to_tick(price, coin)
        
        # Check if price is divisible by tick size (within floating point tolerance)
        remainder = abs((price / tick_size) - round(price / tick_size))
        if remainder > 1e-10:
            return False, f"Price {price} must be divisible by tick size {tick_size} for {coin}"
            
        # Check if price is positive
        if price <= 0:
            return False, f"Price must be positive for {coin}"
            
        return True, ""
    
    @staticmethod
    def calc_post_only_buy_price(best_bid: float, best_ask: float, coin: str) -> float:
        """
        Calculate a valid buy price that won't immediately match (for post-only orders)
        
        Args:
            best_bid (float): Current best bid price
            best_ask (float): Current best ask price
            coin (str): Coin symbol
            
        Returns:
            float: Optimal buy price for post-only order
        """
        # For buy orders, price must be less than best ask to be post-only
        tick_size = PriceUtils.get_tick_size(coin)
        safe_increment = PriceUtils.get_safe_increment(coin)
        
        # Start with price just below ask
        price = best_ask - safe_increment
        
        # Make sure it's above best bid (within the spread)
        if price <= best_bid:
            # If spread is too tight, default to a price exactly at best bid
            price = best_bid
        
        # Ensure price is valid tick size
        return PriceUtils.round_to_tick(price, coin)
    
    @staticmethod
    def calc_post_only_sell_price(best_bid: float, best_ask: float, coin: str) -> float:
        """
        Calculate a valid sell price that won't immediately match (for post-only orders)
        
        Args:
            best_bid (float): Current best bid price
            best_ask (float): Current best ask price
            coin (str): Coin symbol
            
        Returns:
            float: Optimal sell price for post-only order
        """
        # For sell orders, price must be greater than best bid to be post-only
        tick_size = PriceUtils.get_tick_size(coin)
        safe_increment = PriceUtils.get_safe_increment(coin)
        
        # Start with price just above bid
        price = best_bid + safe_increment
        
        # Make sure it's below best ask (within the spread)
        if price >= best_ask:
            # If spread is too tight, default to a price exactly at best ask
            price = best_ask
        
        # Ensure price is valid tick size
        return PriceUtils.round_to_tick(price, coin)
    
    @staticmethod
    def fix_price_precision(price: float, coin: str) -> float:
        """
        Fix price precision issues and ensure the price is valid for the specified coin
        
        Args:
            price (float): Raw price that may have precision issues
            coin (str): Coin symbol
            
        Returns:
            float: Price with correct precision
        """
        # First round to correct tick size
        rounded_price = PriceUtils.round_to_tick(price, coin)
        
        # Handle potential floating-point errors by converting to string and back
        # This avoids issues like 2535.0899999999997 by guaranteeing exact representation
        tick_size = PriceUtils.get_tick_size(coin)
        
        # Determine number of decimal places based on tick size
        decimal_places = 0
        temp_tick = tick_size
        while temp_tick < 1:
            decimal_places += 1
            temp_tick *= 10
        
        # Format price with correct decimal places and convert back to float
        formatted_price = float(f"{rounded_price:.{decimal_places}f}")
        
        return formatted_price

@dataclass
class UserProfile:
    """User profile for revenue tracking"""
    user_id: str
    wallet_address: str
    bot_referral_code: str  # Internal bot referral, not Hyperliquid
    vault_deposits: float
    total_fees_paid: float
    lifetime_rebates: float
    join_date: datetime
    tier: str

class HyperliquidProfitBot:
    """
    Main profit-generating bot focused on vault revenue using real Hyperliquid API
    Uses real examples: basic_order.py and basic_adding.py
    """
    
    def __init__(self, exchange: Exchange = None, info: Info = None, base_url: str = None, vault_address: str = None):
        if exchange and info:
            self.exchange = exchange
            self.info = info
            self.address = exchange.account_address
        else:
            # Use example_utils.setup like all real examples
            self.address, self.info, self.exchange = example_utils.setup(
                base_url=base_url or constants.TESTNET_API_URL,
                skip_ws=True
            )
        
        self.vault_address = vault_address or "HL_VAULT_001" 
        self.bot_name = "HLALPHA_BOT"
        self.users = {}
        self.revenue_tracking = {
            "vault_performance_fees": 0,
            "bot_referral_bonuses": 0,
            "maker_rebates": 0,
            "hlp_staking_yield": 0,
            "daily_total": 0
        }
        
        # Store market liquidity data
        self.market_liquidity_cache = {}
        self.market_liquidity_timestamp = 0
        
        # Store correlation data for portfolio optimization
        self.correlation_matrix = {}
        self.volatility_data = {}
        self.last_correlation_update = 0
        
        # VaultManager integration
        self.vault_manager = None
        
        logger.info("HyperliquidProfitBot initialized with real Hyperliquid API")
    
    async def validate_connection(self) -> bool:
        """
        Validates the connection to Hyperliquid API and ensures the bot can make API calls.
        Returns True if connection is valid, False otherwise.
        """
        try:
            # 1. Test if info client is initialized
            if not self.info:
                logger.error("Info client not initialized")
                return False
                
            # 2. Test if exchange client is initialized
            if not self.exchange:
                logger.error("Exchange client not initialized")
                return False
                
            # 3. Test if address is set
            if not self.address:
                logger.error("Address not set")
                return False
                
            # 4. Test connection by getting basic market data
            try:
                all_mids = self.info.all_mids()
                if not all_mids or len(all_mids) == 0:
                    logger.error("Failed to retrieve market data")
                    return False
                logger.info(f"Retrieved {len(all_mids)} markets from Hyperliquid API")
            except Exception as market_error:
                logger.error(f"Failed to retrieve market data: {market_error}")
                return False
                
            # 5. Test wallet/account access
            try:
                user_state = self.info.user_state(self.address)
                if not user_state:
                    logger.error(f"Failed to retrieve user state for address {self.address}")
                    return False
                    
                # Check if we can get account value (basic check)
                account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
                logger.info(f"User state retrieved, account value: ${account_value:.2f}")
            except Exception as user_state_error:
                logger.error(f"Failed to retrieve user state: {user_state_error}")
                return False
                
            # 6. Test whether exchange nonce generation works (needed for signing transactions)
            try:
                # Just get the nonce, don't execute anything
                if hasattr(self.exchange, '_get_nonce'):
                    nonce = self.exchange._get_nonce()
                    logger.info("Exchange nonce generation validated")
                else:
                    logger.info("Exchange nonce method not directly accessible, assuming valid")
            except Exception as nonce_error:
                logger.warning(f"Could not validate exchange nonce generation: {nonce_error}")
                # Don't fail validation just for this, but log the warning
            
            # 7. Test connectivity to L2 book (optional but useful)
            try:
                l2_book = self.info.l2_snapshot("BTC")
                if l2_book and "levels" in l2_book:
                    logger.info("L2 book data accessible")
                else:
                    logger.warning("L2 book data format unexpected or empty")
            except Exception as l2_error:
                logger.warning(f"Could not access L2 book: {l2_error}")
                # Don't fail validation just for this, but log the warning
                
            logger.info(f"Connection validated successfully for address {self.address}")
            return True
            
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False
            
    async def check_connection_health(self) -> Dict:
        """
        Performs a comprehensive health check on the connection
        Returns a dictionary with health status details
        """
        health_status = {
            "is_connected": False,
            "account_accessible": False,
            "market_data_accessible": False,
            "l2_data_accessible": False,
            "connection_latency_ms": None,
            "errors": []
        }
        
        try:
            # 1. Check if components are initialized
            if not self.info:
                health_status["errors"].append("Info client not initialized")
                return health_status
                
            if not self.exchange:
                health_status["errors"].append("Exchange client not initialized") 
                return health_status
                
            # 2. Test basic connectivity with latency measurement
            start_time = time.time()
            try:
                mids = self.info.all_mids()
                end_time = time.time()
                latency_ms = (end_time - start_time) * 1000
                health_status["connection_latency_ms"] = round(latency_ms, 2)
                
                if mids and len(mids) > 0:
                    health_status["market_data_accessible"] = True
                    health_status["is_connected"] = True
                else:
                    health_status["errors"].append("Market data not available")
            except Exception as market_error:
                health_status["errors"].append(f"Market data error: {str(market_error)}")
                
            # 3. Test account access 
            try:
                user_state = self.info.user_state(self.address)
                if user_state:
                    health_status["account_accessible"] = True
                    # Extract account value for reporting
                    account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
                    health_status["account_value"] = account_value
                else:
                    health_status["errors"].append("User state not accessible")
            except Exception as user_error:
                health_status["errors"].append(f"User state error: {str(user_error)}")
                
            # 4. Test L2 book access
            try:
                l2_book = self.info.l2_snapshot("BTC")
                if l2_book and "levels" in l2_book:
                    health_status["l2_data_accessible"] = True
                else:
                    health_status["errors"].append("L2 book data format unexpected")
            except Exception as l2_error:
                health_status["errors"].append(f"L2 book error: {str(l2_error)}")
                
            return health_status
            
        except Exception as e:
            health_status["errors"].append(f"Health check error: {str(e)}")
            return health_status

    def set_vault_manager(self, vault_manager):
        """Set the vault manager for integration"""
        self.vault_manager = vault_manager
        logger.info(f"VaultManager integration enabled for ProfitBot")

    async def maker_rebate_strategy(self, coin: str, position_size: float = 0.1) -> Dict:
        """
        Maker rebate strategy using real market data and basic_adding.py patterns
        Always use post-only orders for guaranteed rebates
        """
        try:
            # Get real market data following basic_order.py pattern
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                return {'status': 'error', 'message': f'No price data for {coin}'}
            
            mid_price = float(all_mids[coin])
            
            # Get real L2 book data
            l2_book = self.info.l2_snapshot(coin)
            if not l2_book or 'levels' not in l2_book or len(l2_book['levels']) < 2:
                return {'status': 'error', 'message': f'No L2 data for {coin}'}
            
            # Get best bid/ask
            best_bid = float(l2_book['levels'][0][0]['px'])
            best_ask = float(l2_book['levels'][1][0]['px'])
            
            # Calculate optimal prices that respect tick sizes and won't immediately match
            buy_price = PriceUtils.calc_post_only_buy_price(best_bid, best_ask, coin)
            sell_price = PriceUtils.calc_post_only_sell_price(best_bid, best_ask, coin)
            
            # Validate prices before placing orders
            buy_valid, buy_error = PriceUtils.validate_price(buy_price, coin)
            if not buy_valid:
                return {'status': 'error', 'message': f'Buy price error: {buy_error}'}
                
            sell_valid, sell_error = PriceUtils.validate_price(sell_price, coin)
            if not sell_valid:
                return {'status': 'error', 'message': f'Sell price error: {sell_error}'}
            
            logger.info(f"Maker rebate strategy for {coin}: mid={mid_price}, bid={buy_price}, ask={sell_price}")
            
            # Place buy order using basic_adding.py pattern with Add Liquidity Only
            buy_result = self.exchange.order(
                coin, True, position_size, buy_price,
                {"limit": {"tif": "Alo"}},  # MUST be Alo for guaranteed rebates
                reduce_only=False
            )
            print(buy_result)  # Print like basic_order.py
            
            if buy_result.get('status') == 'ok':
                status = buy_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    buy_oid = status["resting"]["oid"]
                    
                    # Query order status like basic_order.py
                    order_status = self.info.query_order_by_oid(self.address, buy_oid)
                    print("Buy order status by oid:", order_status)
                else:
                    logger.warning(f"Buy order not resting: {status}")
            else:
                logger.error(f"Failed to place buy order: {buy_result}")
            
            # Place sell order using basic_adding.py pattern
            sell_result = self.exchange.order(
                coin, False, position_size, sell_price,
                {"limit": {"tif": "Alo"}},  # MUST be Alo for guaranteed rebates
                reduce_only=False
            )
            print(sell_result)  # Print like basic_order.py
            
            if sell_result.get('status') == 'ok':
                status = sell_result["response"]["data"]["statuses"][0]
                if "resting" in status:
                    sell_oid = status["resting"]["oid"]
                    
                    # Query order status like basic_order.py
                    order_status = self.info.query_order_by_oid(self.address, sell_oid)
                    print("Sell order status by oid:", order_status)
                else:
                    logger.warning(f"Sell order not resting: {status}")
            else:
                logger.error(f"Failed to place sell order: {sell_result}")
            
            # Calculate expected rebates
            position_value = position_size * mid_price
            expected_rebate_per_fill = position_value * 0.0001  # 0.01% maker rebate
            
            # Track revenue from rebates
            self.revenue_tracking["maker_rebates"] += expected_rebate_per_fill * 2  # Both orders
            
            return {
                'status': 'success',
                'strategy': 'maker_rebate',
                'coin': coin,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'position_size': position_size,
                'expected_rebate_per_fill': expected_rebate_per_fill,
                'orders': {
                    'buy': buy_result,
                    'sell': sell_result
                },
                'spread_captured': sell_price - buy_price
            }
            
        except Exception as e:
            logger.error(f"Error in maker rebate strategy for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def multi_pair_rebate_mining(self, pairs: List[str] = None) -> Dict:
        """
        Run maker rebate strategy across multiple pairs for maximum rebate generation
        """
        if not pairs:
            pairs = ['BTC', 'ETH', 'SOL']  # Default high-liquidity pairs
        
        results = []
        total_expected_rebates = 0
        
        for coin in pairs:
            try:
                result = await self.maker_rebate_strategy(coin, position_size=0.05)  # Smaller size per pair
                if result['status'] == 'success':
                    results.append(result)
                    total_expected_rebates += result['expected_rebate_per_fill'] * 2
                    
                    logger.info(f"Placed maker orders for {coin}: rebate potential ${result['expected_rebate_per_fill']:.4f}")
                    
                # Small delay between orders
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error placing maker orders for {coin}: {e}")
        
        return {
            'status': 'success',
            'strategy': 'multi_pair_rebate_mining',
            'pairs_traded': len(results),
            'total_orders_placed': len(results) * 2,
            'total_expected_rebates': total_expected_rebates,
            'results': results
        }

    async def vault_performance_strategy(self, vault_capital: float = 10000) -> Dict:
        """
        Execute comprehensive vault strategy for performance fees
        Using real Hyperliquid API patterns
        """
        try:
            # Get current account state
            user_state = self.info.user_state(self.address)
            account_value = float(user_state['marginSummary']['accountValue'])
            
            if account_value < vault_capital * 0.1:  # Need at least 10% of target
                return {
                    'status': 'error', 
                    'message': f'Insufficient capital. Have: ${account_value:.2f}, Need: ${vault_capital * 0.1:.2f}'
                }
            
            # Allocate capital across strategies
            strategy_allocation = {
                'maker_rebate_mining': vault_capital * 0.4,    # 40% for maker rebates
                'grid_trading': vault_capital * 0.3,           # 30% for grid trading
                'arbitrage': vault_capital * 0.2,              # 20% for arbitrage
                'reserve': vault_capital * 0.1                 # 10% reserve
            }
            
            # Execute maker rebate mining on multiple pairs
            rebate_result = await self.multi_pair_rebate_mining(['BTC', 'ETH', 'SOL', 'ARB'])
            
            # Calculate performance metrics
            total_orders_placed = rebate_result.get('total_orders_placed', 0)
            expected_daily_rebates = rebate_result.get('total_expected_rebates', 0) * 10  # Assume 10 fills per day
            
            # Performance fee calculation (10% of profits)
            expected_daily_profit = expected_daily_rebates * 2  # Conservative 2x multiplier from other strategies
            performance_fee = expected_daily_profit * 0.10
            
            # Track vault revenue
            self.revenue_tracking["vault_performance_fees"] += performance_fee
            self.revenue_tracking["maker_rebates"] += expected_daily_rebates
            self.revenue_tracking["daily_total"] = sum(self.revenue_tracking.values())
            
            return {
                'status': 'success',
                'vault_capital': vault_capital,
                'strategy_allocation': strategy_allocation,
                'orders_placed': total_orders_placed,
                'expected_daily_rebates': expected_daily_rebates,
                'expected_daily_profit': expected_daily_profit,
                'performance_fee_earned': performance_fee,
                'revenue_tracking': self.revenue_tracking,
                'apr_estimate': (performance_fee * 365) / vault_capital
            }
            
        except Exception as e:
            logger.error(f"Error in vault performance strategy: {e}")
            return {'status': 'error', 'message': str(e)}

    async def optimized_maker_orders(self, coin: str, spread_target_bps: float = 5.0) -> Dict:
        """
        Place optimized maker orders targeting specific spread conditions
        """
        try:
            # Get L2 book for spread analysis
            l2_book = self.info.l2_snapshot(coin)
            if not l2_book or 'levels' not in l2_book:
                return {'status': 'error', 'message': f'No L2 data for {coin}'}
            
            best_bid = float(l2_book['levels'][0][0]['px'])
            best_ask = float(l2_book['levels'][1][0]['px'])
            mid_price = (best_bid + best_ask) / 2
            current_spread_bps = ((best_ask - best_bid) / mid_price) * 10000
            
            logger.info(f"Optimized maker for {coin}: spread={current_spread_bps:.1f}bps, target={spread_target_bps}bps")
            
            # Only place orders if spread is tight enough for good rebate potential
            if current_spread_bps > spread_target_bps:
                return {
                    'status': 'waiting',
                    'message': f'Spread too wide: {current_spread_bps:.1f}bps > {spread_target_bps}bps'
                }
            
            # Calculate optimal order placement with proper tick sizes
            # Use the PriceUtils to ensure proper price precision
            buy_price = PriceUtils.calc_post_only_buy_price(best_bid, best_ask, coin)
            sell_price = PriceUtils.calc_post_only_sell_price(best_bid, best_ask, coin)
            
            size = 0.1  # Fixed size for now
            
            # Place both orders using basic_adding.py pattern
            buy_order = self.exchange.order(
                coin, True, size, buy_price,
                {"limit": {"tif": "Alo"}},
                reduce_only=False
            )
            print("Optimized buy order:", buy_order)
            
            sell_order = self.exchange.order(
                coin, False, size, sell_price,
                {"limit": {"tif": "Alo"}},
                reduce_only=False
            )
            print("Optimized sell order:", sell_order)
            
            # Calculate rebate potential
            position_value = size * mid_price
            rebate_per_fill = position_value * 0.0001  # 0.01% maker rebate
            
            return {
                'status': 'success',
                'coin': coin,
                'spread_bps': current_spread_bps,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'size': size,
                'rebate_per_fill': rebate_per_fill,
                'total_rebate_potential': rebate_per_fill * 2,
                'orders': {'buy': buy_order, 'sell': sell_order}
            }
            
        except Exception as e:
            logger.error(f"Error in optimized maker orders for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    # Add a new utility method for placing orders with proper price validation
    async def place_limit_order_with_validation(self, coin: str, is_buy: bool, 
                                          size: float, price: float) -> Dict:
        """
        Place a limit order with proper tick size and price validation
        
        Args:
            coin (str): Coin symbol
            is_buy (bool): True for buy, False for sell
            size (float): Order size
            price (float): Original price (will be adjusted to valid tick)
            
        Returns:
            dict: Order result
        """
        try:
            # Fix price precision
            adjusted_price = PriceUtils.fix_price_precision(price, coin)
            
            # Validate price
            is_valid, error_msg = PriceUtils.validate_price(adjusted_price, coin)
            if not is_valid:
                return {'status': 'error', 'message': error_msg}
            
            # Log the adjustment if price changed
            if adjusted_price != price:
                logger.info(f"Adjusted price from {price} to {adjusted_price} for {coin} to match tick size")
                
            # Place the order with Add Liquidity Only to ensure post-only behavior
            result = self.exchange.order(
                coin, is_buy, size, adjusted_price,
                {"limit": {"tif": "Alo"}},
                reduce_only=False
            )
            
            return result
        except Exception as e:
            logger.error(f"Error placing validated limit order: {e}")
            return {'status': 'error', 'message': str(e)}

    async def get_real_performance_metrics(self) -> Dict:
        """
        Get real performance metrics using actual fill data
        """
        try:
            # Get real fills from the account
            user_fills = self.info.user_fills(self.address)
            
            # Calculate real metrics
            total_rebates = 0
            total_volume = 0
            maker_fills = 0
            
            for fill in user_fills:
                volume = float(fill.get('sz', 0)) * float(fill.get('px', 0))
                total_volume += volume
                
                # Check if it was a maker fill (Add Liquidity)
                if fill.get('dir') == 'Add Liquidity':
                    maker_fills += 1
                    # Rebate is typically 0.01% for maker orders
                    rebate = volume * 0.0001
                    total_rebates += rebate
            
            # Get current account state
            user_state = self.info.user_state(self.address)
            account_value = float(user_state['marginSummary']['accountValue'])
            total_pnl = sum(float(fill.get('closedPnl', 0)) for fill in user_fills)
            
            return {
                'status': 'success',
                'account_value': account_value,
                'total_volume': total_volume,
                'total_rebates': total_rebates,
                'maker_fills': maker_fills,
                'total_fills': len(user_fills),
                'total_pnl': total_pnl,
                'rebate_rate': total_rebates / total_volume if total_volume > 0 else 0,
                'maker_percentage': maker_fills / len(user_fills) if user_fills else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {e}")
            return {'status': 'error', 'message': str(e)}

    async def execute_fee_tier_progression_strategy(self, target_tier: int = 3, 
                                              max_daily_capital: float = 1000) -> Dict:
        """
        Execute a complete strategy to progress to a higher fee tier by
        automating market making across optimal pairs
        
        Args:
            target_tier: Target fee tier (1-3)
            max_daily_capital: Maximum daily capital to deploy
        """
        try:
            # First get current tier status
            tier_analysis = await self.optimize_rebate_tier_progression(target_tier)
            
            if tier_analysis.get('status') == 'already_achieved':
                return {
                    'status': 'already_achieved',
                    'message': f'Already at target tier {target_tier}',
                    'current_tier': tier_analysis.get('current_tier'),
                    'current_maker_pct': tier_analysis.get('current_maker_pct')
                }
            
            if tier_analysis.get('status') != 'success':
                return tier_analysis
                
            # Calculate daily maker volume target
            daily_volume_target = tier_analysis.get('additional_maker_volume_needed', 0) / 14
            
            # Calculate capital needed based on efficient capital utilization
            # Assume each unit of capital can generate ~3x in daily maker volume
            capital_needed = daily_volume_target / 3
            
            # Limit to max daily capital
            capital_to_deploy = min(capital_needed, max_daily_capital)
            
            # Get recommended pairs for efficient market making
            recommended_pairs = tier_analysis.get('recommended_pairs', ['BTC', 'ETH', 'SOL'])
            
            # Prioritize pairs with highest liquidity
            market_data = await self._get_market_liquidity_data()
            
            # Sort by maker rebate opportunity score (liquidity * spread)
            optimal_pairs = []
            for coin_data in market_data:
                if coin_data['coin'] in recommended_pairs:
                    # Calculate maker rebate opportunity score
                    spread_bps = coin_data.get('spread_bps', 10)
                    liquidity = coin_data.get('liquidity', 0)
                    
                    if 3 <= spread_bps <= 20 and liquidity > 50000:
                        opportunity_score = liquidity / 1000000 * spread_bps
                        optimal_pairs.append({
                            'coin': coin_data['coin'],
                            'score': opportunity_score,
                            'liquidity': liquidity,
                            'spread_bps': spread_bps
                        })
            
            # Sort by opportunity score
            optimal_pairs.sort(key=lambda x: x['score'], reverse=True)
            
            # Limit to top 5 pairs
            optimal_pairs = optimal_pairs[:5]
            
            if not optimal_pairs:
                return {
                    'status': 'error',
                    'message': 'No suitable pairs found for fee tier progression'
                }
            
            # Allocate capital across pairs weighted by opportunity score
            total_score = sum(pair['score'] for pair in optimal_pairs)
            
            if total_score <= 0:
                return {
                    'status': 'error',
                    'message': 'Invalid opportunity scores'
                }
            
            for pair in optimal_pairs:
                pair['allocation'] = (pair['score'] / total_score) * capital_to_deploy
            
            # Execute market making on each pair
            execution_results = []
            for pair in optimal_pairs:
                # Calculate position size based on allocation and mid price
                mid_price = float(self.info.all_mids().get(pair['coin'], 0))
                if mid_price <= 0:
                    continue
                
                position_size = pair['allocation'] / (mid_price * 2)  # Divide by 2 for buy+sell
                
                # Execute adaptive market making
                result = await self.adaptive_market_making(
                    coin=pair['coin'],
                    position_size=position_size,
                    min_spread_bps=3.0,
                    max_spread_bps=20.0
                )
                
                execution_results.append({
                    'coin': pair['coin'],
                    'allocation': pair['allocation'],
                    'position_size': position_size,
                    'result': result
                })
            
            successful_executions = sum(1 for r in execution_results 
                                      if r['result'] and r['result'].get('status') == 'success')
            
            # Calculate expected rebates
            total_maker_volume = sum(
                r['allocation'] * 2  # Both buy and sell side
                for r in execution_results 
                if r['result'] and r['result'].get('status') == 'success'
            )
            
            # Calculate rebate tier improvement
            current_rebate = 0
            target_rebate = 0
            
            current_maker_pct = tier_analysis.get('current_maker_pct', 0) / 100
            if current_maker_pct >= 0.03:
                current_rebate = 0.00003  # -0.003%
            elif current_maker_pct >= 0.015:
                current_rebate = 0.00002  # -0.002%
            elif current_maker_pct >= 0.005:
                current_rebate = 0.00001  # -0.001%
            
            if target_tier == 3:
                target_rebate = 0.00003  # -0.003%
            elif target_tier == 2:
                target_rebate = 0.00002  # -0.002%
            elif target_tier == 1:
                target_rebate = 0.00001  # -0.001%
                
            rebate_improvement = target_rebate - current_rebate
            daily_rebate_gain = total_maker_volume * rebate_improvement
            
            # Update in revenue tracking
            self.revenue_tracking["maker_rebates"] += daily_rebate_gain
            
            return {
                'status': 'success' if successful_executions > 0 else 'error',
                'tier_progression': {
                    'current_tier': tier_analysis.get('current_tier', 0),
                    'target_tier': target_tier,
                    'current_maker_pct': tier_analysis.get('current_maker_pct', 0),
                    'additional_maker_pct_needed': tier_analysis.get('additional_maker_pct_needed', 0)
                },
                'execution': {
                    'capital_deployed': capital_to_deploy,
                    'pairs_executed': successful_executions,
                    'total_maker_volume': total_maker_volume
                },
                'rebate_optimization': {
                    'rebate_improvement': rebate_improvement,
                    'daily_rebate_gain': daily_rebate_gain,
                    'monthly_projection': daily_rebate_gain * 30
                },
                'execution_details': execution_results
            }
            
        except Exception as e:
            self.logger.error(f"Error executing fee tier progression: {e}")
            return {'status': 'error', 'message': str(e)}

    async def optimize_all_rebate_strategies(self, max_capital: float = 2000) -> Dict:
        """
        Execute comprehensive rebate optimization across all available strategies
        
        Args:
            max_capital: Maximum capital to deploy
        """
        try:
            results = {}
            
            # 1. First optimize fee tier progression
            tier_progression = await self.execute_fee_tier_progression_strategy(
                target_tier=3,
                max_daily_capital=max_capital * 0.5  # Use 50% for tier progression
            )
            results['tier_progression'] = tier_progression
            
            # Track capital used
            capital_used = tier_progression.get('execution', {}).get('capital_deployed', 0) \
                          if tier_progression.get('status') in ['success', 'already_achieved'] else 0
            
            # 2. Execute multi-pair market making with remaining capital
            remaining_capital = max_capital - capital_used
            
            if remaining_capital >= 100:  # Only if we have at least $100 left
                mm_result = await self.market_make_multiple_coins(
                    max_coins=5,
                    total_allocation=remaining_capital
                )
                results['market_making'] = mm_result
                
                if mm_result.get('status') == 'success':
                    capital_used += remaining_capital
            
            # 3. Calculate overall expected returns
            total_rebates = 0
            
            # Add tier progression rebates
            if tier_progression.get('status') == 'success':
                tier_rebates = tier_progression.get('rebate_optimization', {}).get('daily_rebate_gain', 0)
                total_rebates += tier_rebates
            
            # Add market making rebates
            if 'market_making' in results and results['market_making'].get('status') == 'success':
                mm_rebates = results['market_making'].get('expected_rebate', 0)
                total_rebates += mm_rebates
            
            # Calculate ROI
            daily_roi = total_rebates / max_capital if max_capital > 0 else 0
            
            return {
                'status': 'success',
                'capital': {
                    'max_capital': max_capital,
                    'capital_used': capital_used,
                    'remaining': max_capital - capital_used
                },
                'rebate_estimate': {
                    'daily_rebates': total_rebates,
                    'monthly_rebates': total_rebates * 30,
                    'daily_roi': daily_roi,
                    'annual_roi': daily_roi * 365
                },
                'strategy_results': results
            }
            
        except Exception as e:
            self.logger.error(f"Error optimizing rebate strategies: {e}")
            return {'status': 'error', 'message': str(e)}

class BotReferralSystem:
    """
    Internal bot referral system (separate from Hyperliquid)
    """
    
    def __init__(self, profit_bot):
        self.profit_bot = profit_bot
        self.internal_referrals = {}
        
    async def create_bot_referral_system(self, user_id: str) -> Dict:
        """Create internal referral system for the bot"""
        try:
            user = self.profit_bot.users.get(user_id)
            if not user:
                return {"status": "error", "message": "User not found"}
            
            bot_referral_system = {
                "referral_code": user.bot_referral_code,
                "referral_link": f"t.me/HyperLiquidBot?start=ref_{user_id}",
                "benefits": {
                    "referrer_bonus": "1% of referee deposits",
                    "referee_bonus": "0.5% extra yield",
                    "max_referrals": 50,
                    "lifetime_earnings": True
                },
                "revenue_model": "Bot pays bonuses from vault profits"
            }
            
            # Calculate potential bot referral earnings
            projections = {
                "per_referral": {
                    "avg_deposit": 500,
                    "referrer_bonus": 5,     # 1% of $500
                    "referee_extra_yield": 2.5,  # 0.5% on $500
                    "our_cost": 7.5          # Total cost to bot
                },
                "10_referrals": {
                    "total_deposits": 5000,
                    "total_bonuses_paid": 75,
                    "additional_vault_size": 5000,
                    "additional_monthly_fees": 25  # 10% of 5% monthly profit
                },
                "break_even": "3-4 referrals to break even on bonus costs"
            }
            
            return {
                "status": "success",
                "bot_referral_system": bot_referral_system,
                "projections": projections,
                "note": "This is our bot's internal referral system, not Hyperliquid's"
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def process_bot_referral(self, referrer_id: str, referee_id: str, deposit_amount: float) -> Dict:
        """Process internal bot referral bonus"""
        try:
            referrer_bonus = deposit_amount * 0.01  # 1% to referrer
            referee_bonus = deposit_amount * 0.005  # 0.5% extra yield to referee
            
            # Track in our system
            if referrer_id not in self.internal_referrals:
                self.internal_referrals[referrer_id] = {
                    "total_referrals": 0,
                    "total_bonuses": 0,
                    "referral_list": []
                }
            
            self.internal_referrals[referrer_id]["total_referrals"] += 1
            self.internal_referrals[referrer_id]["total_bonuses"] += referrer_bonus
            self.internal_referrals[referrer_id]["referral_list"].append({
                "referee_id": referee_id,
                "deposit_amount": deposit_amount,
                "bonus_earned": referrer_bonus,
                "date": datetime.now().isoformat()
            })
            
            return {
                "status": "success",
                "referrer_bonus": referrer_bonus,
                "referee_bonus": referee_bonus,
                "total_cost_to_bot": referrer_bonus + referee_bonus,
                "referrer_total_earnings": self.internal_referrals[referrer_id]["total_bonuses"]
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}

class RevenueCalculator:
    """
    Calculate revenue without Hyperliquid referrals
    """
    
    def __init__(self, profit_bot, bot_referral_system):
        self.profit_bot = profit_bot
        self.bot_referral_system = bot_referral_system
        
    async def calculate_vault_only_revenue(self, user_count: int, avg_deposit: float) -> Dict:
        """Calculate revenue from vault performance fees only"""
        try:
            total_vault_size = user_count * avg_deposit
            
            # Conservative monthly profit targets
            monthly_profit_targets = {
                "conservative": total_vault_size * 0.03,  # 3% monthly
                "moderate": total_vault_size * 0.05,      # 5% monthly 
                "aggressive": total_vault_size * 0.08     # 8% monthly
            }
            
            # Our revenue (10% of profits)
            monthly_revenue = {
                scenario: profit * 0.10 
                for scenario, profit in monthly_profit_targets.items()
            }
            
            # Costs (bot referral bonuses)
            monthly_costs = {
                "bot_referral_bonuses": user_count * 2,  # $2 avg per user
                "infrastructure": 200,                   # Server costs
                "development": 500                       # Development time
            }
            
            total_monthly_costs = sum(monthly_costs.values())
            
            return {
                "user_count": user_count,
                "avg_deposit": avg_deposit,
                "total_vault_size": total_vault_size,
                "monthly_profit_targets": monthly_profit_targets,
                "monthly_revenue": monthly_revenue,
                "monthly_costs": monthly_costs,
                "total_monthly_costs": total_monthly_costs,
                "net_monthly_profit": {
                    scenario: revenue - total_monthly_costs
                    for scenario, revenue in monthly_revenue.items()
                },
                "break_even_users": int(total_monthly_costs / (avg_deposit * 0.05 * 0.10)),
                "sustainability": "High - revenue grows with vault performance"
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def generate_realistic_revenue_report(self) -> str:
        """Generate revenue report without Hyperliquid referral assumptions"""
        try:
            calc_100 = await self.calculate_vault_only_revenue(100, 500)
            calc_500 = await self.calculate_vault_only_revenue(500, 750)
            calc_1000 = await self.calculate_vault_only_revenue(1000, 1000)
            
            report = f"""
💰 HYPERLIQUID VAULT BOT - REALISTIC REVENUE MODEL

🎯 NO HYPERLIQUID REFERRALS NEEDED
(Referrals require $10k trading volume first)

📊 VAULT-ONLY REVENUE MODEL:

💼 CONSERVATIVE (100 Users @ $500 avg):
• Vault Size: ${calc_100['total_vault_size']:,.0f}
• Monthly Profit (5%): ${calc_100['monthly_profit_targets']['moderate']:,.0f}
• Our Revenue (10%): ${calc_100['monthly_revenue']['moderate']:,.0f}
• Net Profit: ${calc_100['net_monthly_profit']['moderate']:,.0f}

🚀 GROWTH TARGET (500 Users @ $750 avg):
• Vault Size: ${calc_500['total_vault_size']:,.0f}
• Monthly Profit (5%): ${calc_500['monthly_profit_targets']['moderate']:,.0f}
• Our Revenue (10%): ${calc_500['monthly_revenue']['moderate']:,.0f}
• Net Profit: ${calc_500['net_monthly_profit']['moderate']:,.0f}

🎯 SCALE TARGET (1000 Users @ $1000 avg):
• Vault Size: ${calc_1000['total_vault_size']:,.0f}
• Monthly Profit (5%): ${calc_1000['monthly_profit_targets']['moderate']:,.0f}
• Our Revenue (10%): ${calc_1000['monthly_revenue']['moderate']:,.0f}
• Net Profit: ${calc_1000['net_monthly_profit']['moderate']:,.0f}

💡 REVENUE SOURCES (No External Referrals):
• Vault Performance Fees: 90% of revenue
• Bot Internal Referrals: 5% of revenue
• HLP Staking Yield Share: 3% of revenue
• Maker Rebate Optimization: 2% of revenue

✅ COMPETITIVE ADVANTAGES:
• No Hyperliquid referral dependency
• Lower minimum deposit ($50 vs $100+)
• No management fees (only performance)
• Transparent profit sharing
• Multiple alpha strategies

⚡ BREAK-EVEN: {calc_100['break_even_users']} users
🎯 TARGET: $5K+ monthly profit with realistic vault growth
📈 SCALABILITY: Revenue grows with vault performance

#VaultRevenue #RealStrategy #NoReferralDependency
            """
            
            return report.strip()
            
        except Exception as e:
            return f"Error generating report: {str(e)}"

# Helper functions to run examples directly
def run_basic_order_example():
    """Run the basic_order.py example directly"""
    try:
        basic_order.main()
    except Exception as e:
        print(f"Error running basic_order example: {e}")

def run_basic_adding_example():
    """Run the basic_adding.py example directly"""
    try:
        basic_adding.main()
    except Exception as e:
        print(f"Error running basic_adding example: {e}")

# Example usage
async def main():
    """Example of how to use the profit bot"""
    bot = HyperliquidProfitBot()
    
    # Execute maker rebate strategy
    result = await bot.maker_rebate_strategy('BTC')
    print(f"Maker rebate result: {result}")
    
    # Execute vault performance strategy
    vault_result = await bot.vault_performance_strategy(5000)
    print(f"Vault strategy result: {vault_result}")
    
    # Get performance metrics
    metrics = await bot.get_real_performance_metrics()
    print(f"Performance metrics: {metrics}")

if __name__ == "__main__":
    asyncio.run(main())
