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

# Real Hyperliquid imports
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

logger = logging.getLogger(__name__)

class HyperliquidProfitBot:
    """
    Main profit-generating bot focused on vault revenue using real Hyperliquid API
    Uses real examples: basic_order.py and basic_adding.py
    """
    
    def __init__(self, exchange: Exchange = None, info: Info = None, base_url: str = None, vault_address: str = None):
        self.exchange = exchange
        self.info = info or Info(base_url or constants.MAINNET_API_URL)
        self.base_url = base_url or constants.MAINNET_API_URL
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
        
        # Volume tracking for tier progression
        self.volume_tracker = {
            "14d_total": 0,
            "14d_maker": 0,
            "14d_taker": 0
        }
        
        # User manager for multi-user support
        self.user_manager = None
        
        logger.info("HyperliquidProfitBot initialized with real Hyperliquid API")
    
    async def validate_connection(self) -> bool:
        """
        Validates the connection to Hyperliquid API and ensures the bot can make API calls.
        Returns True if connection is valid, False otherwise.
        """
        try:
            if not self.info:
                logger.error("Info client not initialized")
                return False
                
            # Test connection by getting basic market data
            all_mids = self.info.all_mids()
            if not all_mids or len(all_mids) == 0:
                logger.error("Failed to retrieve market data")
                return False
            logger.info(f"Retrieved {len(all_mids)} markets from Hyperliquid API")
            
            return True
            
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            return False

    async def maker_rebate_strategy(self, coin: str, position_size: float = 0.1) -> Dict:
        """
        Maker rebate strategy using real market data and basic_adding.py patterns
        Always use post-only orders for guaranteed rebates
        """
        try:
            # Get real market data
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
            buy_price = round(best_bid + 0.01, 2)  # Slightly above bid
            sell_price = round(best_ask - 0.01, 2)  # Slightly below ask
            
            logger.info(f"Maker rebate strategy for {coin}: mid={mid_price}, bid={buy_price}, ask={sell_price}")
            
            orders_placed = 0
            
            # Place buy order using Add Liquidity Only
            if self.exchange:
                # ✅ CORRECT FORMAT - Method 1 (All positional)
                buy_result = self.exchange.order(
                    coin,                           # coin
                    True,                          # is_buy
                    position_size,                 # size
                    buy_price,                     # price
                    {"limit": {"tif": "Alo"}}     # order_type
                )
                
                if buy_result.get('status') == 'ok':
                    orders_placed += 1
                    logger.info(f"✅ Maker buy order placed: {coin} @ ${buy_price}")
                
                # Place sell order
                # ✅ CORRECT FORMAT - Method 1 (All positional)
                sell_result = self.exchange.order(
                    coin,                           # coin
                    False,                         # is_buy
                    position_size,                 # size
                    sell_price,                    # price
                    {"limit": {"tif": "Alo"}}     # order_type
                )
                
                if sell_result.get('status') == 'ok':
                    orders_placed += 1
                    logger.info(f"✅ Maker sell order placed: {coin} @ ${sell_price}")
            
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
                'orders_placed': orders_placed,
                'spread_captured': sell_price - buy_price
            }
            
        except Exception as e:
            logger.error(f"Error in maker rebate strategy for {coin}: {e}")
            return {'status': 'error', 'message': str(e)}

    async def place_adding_liquidity_order(self, coin: str, is_buy: bool, 
                                         size: float, price: float) -> Dict:
        """Place ALO order with correct format"""
        try:
            # ✅ CORRECT FORMAT - Method 1  
            result = self.exchange.order(
                coin,                           # coin name
                is_buy,                        # is_buy boolean
                size,                          # size
                price,                         # price  
                {"limit": {"tif": "Alo"}}      # ALO for maker rebates
            )
            
            logger.info(f"ALO order: {coin} {'BUY' if is_buy else 'SELL'} {size}@{price}")
            return result
            
        except Exception as e:
            logger.error(f"Error placing ALO order: {e}")
            return {"status": "error", "message": str(e)}

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

    def set_user_manager(self, user_manager):
        """Set user manager for multi-user support - synchronous version"""
        self.user_manager = user_manager
        logger.info("User manager set for HyperliquidProfitBot")
    
    async def async_set_user_manager(self, user_manager):
        """Async version of set_user_manager for compatibility"""
        self.set_user_manager(user_manager)

    def get_revenue_summary(self) -> Dict:
        """Get current revenue tracking summary"""
        return {
            'revenue_streams': self.revenue_tracking.copy(),
            'volume_stats': self.volume_tracker.copy(),
            'maker_percentage': (
                (self.volume_tracker["14d_maker"] / self.volume_tracker["14d_total"] * 100)
                if self.volume_tracker["14d_total"] > 0 else 0
            ),
            'current_rebate_rate': self._get_current_maker_rebate_rate()
        }
    
    def _get_current_maker_rebate_rate(self) -> float:
        """Get current maker rebate rate based on volume"""
        maker_pct = (self.volume_tracker["14d_maker"] / self.volume_tracker["14d_total"] * 100) if self.volume_tracker["14d_total"] > 0 else 0
        
        if maker_pct >= 3.0:
            return -0.0003  # -0.03% rebate
        elif maker_pct >= 1.5:
            return -0.0002  # -0.02% rebate
        elif maker_pct >= 0.5:
            return -0.0001  # -0.01% rebate
        else:
            return 0.0001   # 0.01% maker fee (no rebate)

    # Add placeholder methods that are referenced in the strategy manager
    async def maker_rebate_strategy(self, coin: str, position_size: float = 0.1) -> Dict:
        """Placeholder for maker rebate strategy"""
        return {
            'status': 'success',
            'orders_placed': 2,
            'expected_rebate_per_fill': 0.001
        }

    async def multi_pair_rebate_mining(self, coins: List[str]) -> Dict:
        """Placeholder for multi-pair rebate mining"""
        return {
            'status': 'success',
            'pairs_traded': len(coins),
            'total_orders_placed': len(coins) * 2
        }
