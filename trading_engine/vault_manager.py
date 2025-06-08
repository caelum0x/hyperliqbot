import asyncio
from asyncio.log import logger
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import sqlite3
from datetime import datetime, timedelta
import sys
import os
import numpy as np
from collections import deque

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Import actual example files from examples folder
examples_dir = os.path.join(os.path.dirname(__file__), '..', 'examples')
sys.path.append(examples_dir)

import basic_vault
import basic_vault_transfer
import basic_transfer
import example_utils

@dataclass
class VaultUser:
    """Vault user data"""
    user_id: str
    deposit_amount: float
    deposit_time: float
    initial_vault_value: float
    profit_share_rate: float

@dataclass
class VaultPerformanceMetrics:
    """Enhanced vault performance tracking"""
    tvl: float
    daily_return: float
    weekly_return: float
    monthly_return: float
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    maker_rebate_earned: float
    maker_ratio: float
    active_users: int
    profitable_days: int
    total_days: int
    win_rate: float
    best_performing_asset: str
    timestamp: float

class VaultManager:
    """
    Manages user vaults with automated profit sharing using actual Hyperliquid API
    Uses real examples: basic_vault.py, basic_vault_transfer.py, and basic_transfer.py
    """
    
    def __init__(self, vault_address=None, base_url=None, exchange=None, info=None):
        self.vault_address = vault_address
        self.base_url = base_url
        self.exchange = exchange
        self.info = info
        self.initialized = False
        
        # Validate whether this vault manager can operate
        self.operational = bool(self.vault_address and self.exchange and self.info)
        
        if not self.vault_address:
            logger.warning("No vault address provided - vault manager will operate in limited mode")
        
        if not self.exchange or not self.info:
            logger.warning("Missing exchange or info client - vault manager will operate in limited mode")
    
    def check_health(self) -> bool:
        """Check if vault manager is operational"""
        return self.operational and self.initialized
    
    def validate_vault_address(self) -> bool:
        """
        Validate vault address format and existence
        Returns True if valid, False otherwise
        """
        if not self.vault_address:
            logger.warning("No vault address configured")
            return False
            
        # Check if the address is properly formatted (starts with 0x and 42 chars)
        if not self.vault_address.startswith('0x') or len(self.vault_address) != 42:
            logger.warning(f"Invalid vault address format: {self.vault_address}")
            return False
            
        # Ensure it's a string to avoid serialization issues
        if not isinstance(self.vault_address, str):
            logger.warning(f"Vault address must be a string, got {type(self.vault_address)}")
            return False
            
        return True
    
    def ensure_vault_address_format(self) -> str:
        """
        Ensure vault address has proper format for API calls
        Returns properly formatted vault address or empty string if invalid
        """
        if not self.vault_address:
            return ""
            
        # Ensure address starts with 0x prefix
        address = self.vault_address
        if not address.startswith('0x'):
            address = f'0x{address}'
            
        return address

    async def initialize(self):
        """Initialize the vault manager with validation"""
        if not self.operational:
            logger.warning("Cannot initialize vault manager: missing required components")
            self.initialized = False
            return False
            
        # Validate vault address
        if not self.validate_vault_address():
            logger.error("Invalid vault address - cannot initialize")
            self.initialized = False
            return False
            
        try:
            # Test connection to vault
            formatted_address = self.ensure_vault_address_format()
            state = self.info.user_state(formatted_address)
            if state and "marginSummary" in state:
                self.initialized = True
                logger.info(f"Vault manager initialized for {formatted_address}")
                return True
            else:
                logger.error(f"Failed to fetch vault state for {formatted_address}")
                self.initialized = False
                return False
        except Exception as e:
            logger.error(f"Error initializing vault manager: {e}")
            self.initialized = False
            return False
    
    async def get_vault_balance(self) -> Dict:
        """Get real vault balance using Info API exactly like basic_vault.py"""
        # Return graceful response if vault is not operational
        if not self.operational or not self.initialized:
            return {
                "status": "not_configured",
                "total_value": 0.0,
                "message": "Vault not configured (missing address or API clients)",
                "position_count": 0,
                "positions": [],
                "total_margin_used": 0.0,
                "total_unrealized_pnl": 0.0
            }
            
        # Validate vault address
        if not self.validate_vault_address():
            return {
                "status": "error",
                "message": "Invalid vault address",
                "total_value": 0.0,
                "position_count": 0,
                "positions": [],
                "total_margin_used": 0.0,
                "total_unrealized_pnl": 0.0
            }
            
        try:
            # Format address properly to avoid API errors
            formatted_address = self.ensure_vault_address_format()
            
            # Fetch vault account data
            vault_state = self.info.user_state(formatted_address)
            
            # Extract account value and other key metrics
            margin_summary = vault_state.get("marginSummary", {})
            account_value = float(margin_summary.get("accountValue", 0))
            total_margin_used = float(margin_summary.get("totalMarginUsed", 0))
            total_unrealized_pnl = float(margin_summary.get("totalUnrealizedPnl", 0))
            
            # Get positions
            positions = []
            asset_positions = vault_state.get("assetPositions", [])
            position_count = len(asset_positions)
            
            for asset_position in asset_positions:
                position = asset_position.get("position", {})
                if position:
                    coin = position.get("coin", "Unknown")
                    size = float(position.get("szi", 0))
                    entry_price = float(position.get("entryPx", 0))
                    unrealized_pnl = float(position.get("unrealizedPnl", 0))
                    
                    if abs(size) > 1e-10:  # Only include non-zero positions
                        positions.append({
                            "coin": coin,
                            "size": size,
                            "entry_price": entry_price,
                            "unrealized_pnl": unrealized_pnl,
                            "notional_value": abs(size) * entry_price
                        })
            
            return {
                "status": "success",
                "total_value": account_value,
                "position_count": position_count,
                "positions": positions,
                "total_margin_used": total_margin_used,
                "total_unrealized_pnl": total_unrealized_pnl
            }
            
        except Exception as e:
            logger.error(f"Error getting vault balance: {e}")
            return {
                "status": "error",
                "message": str(e),
                "total_value": 0.0,
                "position_count": 0,
                "positions": [],
                "total_margin_used": 0.0,
                "total_unrealized_pnl": 0.0
            }

    async def deposit_to_vault(self, amount: float) -> Dict:
        """
        Deposit to vault using basic_vault_transfer.py pattern exactly
        """
        # Skip if vault not configured or initialized
        if not self.operational or not self.initialized:
            return {
                'status': 'error',
                'message': 'Vault not configured or initialized'
            }
            
        # Validate vault address
        if not self.validate_vault_address():
            return {
                'status': 'error',
                'message': 'Invalid vault address'
            }
            
        try:
            # Check if we have sufficient balance first
            if not hasattr(self, 'address') or not self.address:
                if hasattr(self.exchange, 'account_address'):
                    self.address = self.exchange.account_address
                else:
                    return {
                        'status': 'error',
                        'message': 'No source address configured'
                    }

            user_state = self.info.user_state(self.address)
            account_value = float(user_state['marginSummary']['accountValue'])
            
            if account_value < amount:
                return {
                    'status': 'error',
                    'message': f'Insufficient balance. Available: ${account_value:.2f}'
                }
            
            # Format vault address properly
            formatted_address = self.ensure_vault_address_format()
            
            # Use basic_vault_transfer.py exact pattern
            # Transfer amount USD to vault (amount in micro USDC)
            amount_micro = int(amount * 1_000_000)
            
            transfer_result = self.exchange.vault_usd_transfer(
                formatted_address, True, amount_micro
            )
            
            return {
                'status': 'success' if transfer_result.get('status') == 'ok' else 'error',
                'result': transfer_result,
                'amount': amount,
                'vault_address': formatted_address
            }
            
        except Exception as e:
            logger.error(f"Error depositing to vault: {e}")
            return {'status': 'error', 'message': str(e)}

    async def withdraw_from_vault(self, amount: float) -> Dict:
        """
        Withdraw from vault using basic_vault_transfer.py pattern exactly
        """
        # Skip if vault not configured or initialized
        if not self.operational or not self.initialized:
            return {
                'status': 'error',
                'message': 'Vault not configured or initialized'
            }
            
        # Validate vault address
        if not self.validate_vault_address():
            return {
                'status': 'error',
                'message': 'Invalid vault address'
            }
            
        try:
            # Check if vault has sufficient balance first
            formatted_address = self.ensure_vault_address_format()
            vault_balance = await self.get_vault_balance()
            
            if vault_balance['status'] != 'success' or vault_balance['total_value'] < amount:
                return {
                    'status': 'error',
                    'message': f"Insufficient vault balance. Available: ${vault_balance.get('total_value', 0):.2f}"
                }
            
            # Use basic_vault_transfer.py pattern but with is_deposit=False
            amount_micro = int(amount * 1_000_000)
            
            transfer_result = self.exchange.vault_usd_transfer(
                formatted_address, False, amount_micro
            )
            
            return {
                'status': 'success' if transfer_result.get('status') == 'ok' else 'error',
                'result': transfer_result,
                'amount': amount,
                'vault_address': formatted_address
            }
            
        except Exception as e:
            logger.error(f"Error withdrawing from vault: {e}")
            return {'status': 'error', 'message': str(e)}

    async def transfer_usd_to_user(self, user_address: str, amount: float) -> Dict:
        """
        Transfer USD to user using basic_transfer.py pattern exactly
        """
        # Skip if not operational
        if not self.operational:
            return {
                'status': 'error',
                'message': 'Vault manager not operational'
            }
            
        try:
            # Validate user address
            if not user_address or not isinstance(user_address, str) or len(user_address) != 42 or not user_address.startswith('0x'):
                return {
                    'status': 'error',
                    'message': f'Invalid user address: {user_address}'
                }
            
            # Check if account can perform internal transfers (from basic_transfer.py)
            if self.exchange.account_address != self.exchange.wallet.address:
                return {
                    'status': 'error',
                    'message': 'Agents do not have permission to perform internal transfers'
                }
            
            # Use basic_transfer.py exact pattern
            # Amount should be a valid number
            if not isinstance(amount, (int, float)) or amount <= 0:
                return {
                    'status': 'error',
                    'message': f'Invalid amount: {amount}'
                }
                
            transfer_result = self.exchange.usd_transfer(amount, user_address)
            
            return {
                'status': 'success' if transfer_result.get('status') == 'ok' else 'error',
                'result': transfer_result,
                'amount': amount,
                'recipient': user_address
            }
            
        except Exception as e:
            logger.error(f"Error transferring USD: {e}")
            return {'status': 'error', 'message': str(e)}

    async def place_vault_order(self, coin: str, is_buy: bool, size: float, price: float) -> Dict:
        """
        Place order using vault exchange exactly like basic_vault.py main() function
        """
        try:
            # Use basic_vault.py exact pattern
            order_result = self.vault_exchange.order(
                coin, is_buy, size, price, 
                {"limit": {"tif": "Gtc"}}
            )
            print(order_result)  # Print like the example
            
            logger.info(f"Vault order placed: {coin} {size}@{price}")
            return {
                'status': 'success' if order_result.get('status') == 'ok' else 'error',
                'result': order_result,
                'oid': order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("resting", {}).get("oid") if order_result.get("status") == "ok" else None
            }
            
        except Exception as e:
            logger.error(f"Error placing vault order: {e}")
            return {'status': 'error', 'message': str(e)}

    async def cancel_vault_order(self, coin: str, oid: int) -> Dict:
        """
        Cancel vault order exactly like basic_vault.py cancel pattern
        """
        try:
            # Use basic_vault.py exact cancel pattern
            cancel_result = self.vault_exchange.cancel(coin, oid)
            print(cancel_result)  # Print like the example
            
            logger.info(f"Vault order cancelled: {coin} oid:{oid}")
            return {
                'status': 'success' if cancel_result.get('status') == 'ok' else 'error',
                'result': cancel_result
            }
            
        except Exception as e:
            logger.error(f"Error cancelling vault order: {e}")
            return {'status': 'error', 'message': str(e)}

    async def execute_basic_vault_example(self) -> Dict:
        """
        Execute the exact strategy from basic_vault.py main() function
        """
        try:
            # Run basic_vault.py main() function directly
            basic_vault.main()
            
            return {
                'status': 'success',
                'strategy': 'basic_vault_example',
                'message': 'Executed basic_vault.py main() function'
            }
            
        except Exception as e:
            logger.error(f"Error executing basic vault example: {e}")
            return {'status': 'error', 'message': str(e)}

    async def execute_basic_vault_transfer_example(self, amount: float = 5.0) -> Dict:
        """
        Execute basic_vault_transfer.py pattern exactly
        """
        try:
            # Run basic_vault_transfer.py main() function directly
            basic_vault_transfer.main()
            
            return {
                'status': 'success',
                'strategy': 'basic_vault_transfer_example',
                'message': 'Executed basic_vault_transfer.py main() function'
            }
            
        except Exception as e:
            logger.error(f"Error executing vault transfer example: {e}")
            return {'status': 'error', 'message': str(e)}

    async def execute_basic_transfer_example(self, recipient: str, amount: float = 1.0) -> Dict:
        """
        Execute basic_transfer.py pattern exactly
        """
        try:
            # Run basic_transfer.py main() function directly
            basic_transfer.main()
            
            return {
                'status': 'success',
                'strategy': 'basic_transfer_example',
                'message': 'Executed basic_transfer.py main() function'
            }
            
        except Exception as e:
            logger.error(f"Error executing transfer example: {e}")
            return {'status': 'error', 'message': str(e)}

    async def distribute_profits(self, profit_share: float = 0.1) -> Dict:
        """
        Calculate and distribute real profits from vault fills
        Using real fill data from Info API
        """
        try:
            # Get real fills data for vault
            fills = self.info.user_fills(self.vault_address)
            
            # Calculate total realized PnL from actual fills
            total_realized_pnl = 0.0
            total_volume = 0.0
            
            for fill in fills:
                pnl = float(fill.get('closedPnl', 0))
                volume = float(fill.get('sz', 0)) * float(fill.get('px', 0))
                total_realized_pnl += pnl
                total_volume += volume
            
            # Get current unrealized PnL
            vault_balance = await self.get_vault_balance()
            if vault_balance['status'] != 'success':
                return vault_balance
            
            total_unrealized_pnl = vault_balance['total_unrealized_pnl']
            total_pnl = total_realized_pnl + total_unrealized_pnl
            
            if total_pnl > 0:
                keeper_share = total_pnl * profit_share
                user_share = total_pnl * (1 - profit_share)
                
                return {
                    'status': 'success',
                    'total_profit': total_pnl,
                    'realized_pnl': total_realized_pnl,
                    'unrealized_pnl': total_unrealized_pnl,
                    'keeper_share': keeper_share,
                    'user_share': user_share,
                    'total_volume': total_volume,
                    'fill_count': len(fills),
                    'profit_share_rate': profit_share
                }
            else:
                return {
                    'status': 'success',
                    'total_profit': total_pnl,
                    'message': 'No profits to distribute'
                }
                
        except Exception as e:
            logger.error(f"Error distributing profits: {e}")
            return {'status': 'error', 'message': str(e)}

    async def create_user_vault(
        self,
        user_id: str,
        initial_deposit: float,
        profit_share_rate: float = 0.10
    ) -> Dict:
        """Create a new user vault with profit sharing"""
        try:
            # Get current vault value for baseline
            vault_balance = await self.get_vault_balance()
            if vault_balance['status'] != 'success':
                return vault_balance
            
            current_vault_value = vault_balance['total_value']
            
            # Create vault user record
            vault_user = VaultUser(
                user_id=user_id,
                deposit_amount=initial_deposit,
                deposit_time=time.time(),
                initial_vault_value=current_vault_value,
                profit_share_rate=profit_share_rate
            )
            
            # Store in database
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO vault_users 
                (user_id, deposit_amount, deposit_time, initial_vault_value, profit_share_rate)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, initial_deposit, vault_user.deposit_time, 
                  current_vault_value, profit_share_rate))
            self.conn.commit()
            
            self.vault_users[user_id] = vault_user
            
            return {
                "status": "vault_created",
                "user_id": user_id,
                "deposit_amount": initial_deposit,
                "profit_share_rate": profit_share_rate,
                "vault_address": self.vault_address,
                "baseline_value": current_vault_value
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def calculate_user_profits(self, user_id: str) -> Dict:
        """
        Calculate profits for a specific user based on vault performance
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM vault_users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()
            
            if not user_data:
                return {"status": "error", "message": "User not found"}
            
            _, deposit_amount, deposit_time, initial_vault_value, profit_share_rate, _ = user_data
            
            # Get current vault value
            vault_state = self.info.user_state(self.vault_address)
            current_vault_value = float(vault_state.get("marginSummary", {}).get("accountValue", 0))
            
            # Calculate vault performance since user joined
            vault_performance = (current_vault_value - initial_vault_value) / initial_vault_value
            
            # Calculate user's share of profits
            user_capital_contribution = deposit_amount / initial_vault_value
            attributable_profit = vault_performance * initial_vault_value * user_capital_contribution
            user_profit_share = attributable_profit * profit_share_rate
            
            # Calculate time-based metrics
            days_invested = (time.time() - deposit_time) / 86400
            annualized_return = (vault_performance / (days_invested / 365)) if days_invested > 0 else 0
            
            return {
                "user_id": user_id,
                "deposit_amount": deposit_amount,
                "days_invested": days_invested,
                "vault_performance": vault_performance,
                "attributable_profit": attributable_profit,
                "user_profit_share": user_profit_share,
                "profit_share_rate": profit_share_rate,
                "annualized_return": annualized_return,
                "current_vault_value": current_vault_value
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def distribute_profits(self, min_profit_threshold: float = 100.0) -> Dict:
        """
        Distribute profits to all vault users
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT user_id FROM vault_users')
            user_ids = [row[0] for row in cursor.fetchall()]
            
            distributions = []
            total_distributed = 0
            
            for user_id in user_ids:
                profit_calc = await self.calculate_user_profits(user_id)
                
                if profit_calc["status"] == "error":
                    continue
                
                profit_amount = profit_calc["user_profit_share"]
                
                if profit_amount >= min_profit_threshold:
                    # Record the distribution
                    cursor.execute('''
                        INSERT INTO profit_distributions 
                        (user_id, amount, vault_performance, timestamp)
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, profit_amount, profit_calc["vault_performance"], time.time()))
                    
                    # Update user's total profits
                    cursor.execute('''
                        UPDATE vault_users 
                        SET total_profits_earned = total_profits_earned + ?
                        WHERE user_id = ?
                    ''', (profit_amount, user_id))
                    
                    distributions.append({
                        "user_id": user_id,
                        "profit_amount": profit_amount,
                        "vault_performance": profit_calc["vault_performance"]
                    })
                    
                    total_distributed += profit_amount
            
            self.conn.commit()
            
            return {
                "status": "profits_distributed",
                "distributions": distributions,
                "total_distributed": total_distributed,
                "distribution_count": len(distributions),
                "timestamp": time.time()
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def get_vault_analytics(self) -> Dict:
        """
        Get comprehensive vault analytics
        """
        try:
            cursor = self.conn.cursor()
            
            # Get user statistics
            cursor.execute('''
                SELECT COUNT(*) as user_count,
                       SUM(deposit_amount) as total_deposits,
                       AVG(profit_share_rate) as avg_profit_share,
                       SUM(total_profits_earned) as total_profits_distributed
                FROM vault_users
            ''')
            user_stats = cursor.fetchone()
            
            # Get recent distributions
            cursor.execute('''
                SELECT user_id, amount, timestamp
                FROM profit_distributions
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT 10
            ''', (time.time() - 86400 * 7,))  # Last 7 days
            recent_distributions = cursor.fetchall()
            
            # Get current vault performance
            vault_state = self.info.user_state(self.vault_address)
            current_vault_value = float(vault_state.get("marginSummary", {}).get("accountValue", 0))
            
            return {
                "vault_address": self.vault_address,
                "current_value": current_vault_value,
                "user_count": user_stats[0],
                "total_deposits": user_stats[1],
                "avg_profit_share_rate": user_stats[2],
                "total_profits_distributed": user_stats[3],
                "recent_distributions": [
                    {"user_id": dist[0], "amount": dist[1], "timestamp": dist[2]}
                    for dist in recent_distributions
                ],
                "vault_utilization": (user_stats[1] / current_vault_value) if current_vault_value > 0 else 0
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def withdraw_user_funds(
        self,
        user_id: str,
        withdrawal_amount: Optional[float] = None
    ) -> Dict:
        """
        Process user withdrawal including their profit share
        """
        try:
            # Calculate current profits
            profit_calc = await self.calculate_user_profits(user_id)
            if profit_calc["status"] == "error":
                return profit_calc
            
            # Get user data
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM vault_users WHERE user_id = ?', (user_id,))
            user_data = cursor.fetchone()
            
            if not user_data:
                return {"status": "error", "message": "User not found"}
            
            _, deposit_amount, _, _, _, total_profits_earned = user_data
            
            # Calculate total available (deposit + new profits)
            available_amount = deposit_amount + profit_calc["user_profit_share"]
            
            if withdrawal_amount is None:
                withdrawal_amount = available_amount
            
            if withdrawal_amount > available_amount:
                return {
                    "status": "error", 
                    "message": "Insufficient funds",
                    "available": available_amount,
                    "requested": withdrawal_amount
                }
            
            # Execute withdrawal (in practice, you'd transfer funds)
            # For now, just update records
            if withdrawal_amount == available_amount:
                # Full withdrawal - remove user
                cursor.execute('DELETE FROM vault_users WHERE user_id = ?', (user_id,))
            else:
                # Partial withdrawal - update deposit amount
                new_deposit = deposit_amount - (withdrawal_amount - profit_calc["user_profit_share"])
                cursor.execute('''
                    UPDATE vault_users 
                    SET deposit_amount = ?,
                        total_profits_earned = total_profits_earned + ?
                    WHERE user_id = ?
                ''', (new_deposit, profit_calc["user_profit_share"], user_id))
            
            self.conn.commit()
            
            return {
                "status": "withdrawal_processed",
                "user_id": user_id,
                "withdrawal_amount": withdrawal_amount,
                "profit_component": profit_calc["user_profit_share"],
                "deposit_component": withdrawal_amount - profit_calc["user_profit_share"],
                "remaining_balance": available_amount - withdrawal_amount
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def handle_deposit(self, user_id: int, update, context) -> Dict:
        """Handle telegram user deposit request"""
        try:
            # This would integrate with telegram bot for user deposits
            return {
                'status': 'pending',
                'message': 'Deposit functionality requires user wallet integration',
                'vault_address': self.vault_address
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    async def handle_withdrawal_request(self, user_id: int, update, context) -> Dict:
        """Handle telegram user withdrawal request"""
        try:
            # This would process withdrawal for telegram users
            return {
                'status': 'pending',
                'message': 'Withdrawal functionality requires user verification',
                'processing_time': '24 hours'
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    async def get_vault_stats(self) -> Dict:
        """Get comprehensive vault statistics"""
        try:
            vault_balance = await self.get_vault_balance()
            profit_info = await self.distribute_profits()
            
            cursor = self.conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM vault_users')
            user_count = cursor.fetchone()[0]
            
            return {
                'tvl': vault_balance.get('total_value', 0),
                'total_return': profit_info.get('total_profit', 0),
                'active_days': 30,  # Could be calculated from database
                'active_users': user_count,
                'vault_address': self.vault_address
            }
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    async def get_available_balance(self, user_id: int) -> Dict:
        """Get available balance for user"""
        try:
            # This would check user's contribution to vault
            return {
                'available': 1000.0,  # Placeholder
                'total_deposited': 1000.0,
                'unrealized_pnl': 0.0
            }
        except Exception as e:
            return {'available': 0, 'error': str(e)}

    async def distribute_profits_by_contribution(self, profit_share: float = 0.1) -> Dict:
        """
        Distribute profits based on user contribution time and amount
        Uses time-weighted average contribution
        """
        try:
            # Calculate total profits
            vault_balance = await self.get_vault_balance()
            if vault_balance['status'] != 'success':
                return vault_balance
                
            total_profits = vault_balance['total_unrealized_pnl']
            if total_profits <= 0:
                return {'status': 'info', 'message': 'No profits to distribute'}
                
            # Get all users with time-weighted contributions
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT user_id, deposit_amount, deposit_time
                FROM vault_users
            ''')
            
            users = cursor.fetchall()
            total_weighted_contribution = 0
            user_weights = {}
            
            current_time = time.time()
            for user_id, amount, deposit_time in users:
                # Time weight: longer time = higher weight (max 2x)
                time_factor = min(2.0, 1 + (current_time - deposit_time) / 2592000)  # 30 days = 2x
                weighted_contribution = amount * time_factor
                total_weighted_contribution += weighted_contribution
                user_weights[user_id] = weighted_contribution
                
            # Distribute profits proportionally
            distributions = []
            keeper_share = total_profits * profit_share
            user_profit_pool = total_profits - keeper_share
            
            for user_id, weighted_contribution in user_weights.items():
                if total_weighted_contribution > 0:
                    user_share = user_profit_pool * (weighted_contribution / total_weighted_contribution)
                    
                    # Record distribution
                    cursor.execute('''
                        INSERT INTO profit_distributions 
                        (user_id, amount, vault_performance, timestamp, weighted_factor)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, user_share, vault_balance['total_unrealized_pnl'], 
                          current_time, weighted_contribution / total_weighted_contribution))
                    
                    distributions.append({
                        'user_id': user_id,
                        'profit_amount': user_share,
                        'contribution_weight': weighted_contribution / total_weighted_contribution
                    })
                    
            self.conn.commit()
            
            return {
                'status': 'success',
                'keeper_share': keeper_share,
                'user_profit_pool': user_profit_pool,
                'distributions': distributions,
                'total_weighted_contribution': total_weighted_contribution
            }
            
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    async def distribute_profits_with_loyalty_tiers(self, profit_share: float = 0.1) -> Dict:
        """
        Distribute profits with loyalty tiers for long-term vault users
        Users with longer history get better rates
        """
        try:
            # Calculate total profits
            vault_balance = await self.get_vault_balance()
            if vault_balance['status'] != 'success':
                return vault_balance
                
            total_profits = vault_balance['total_unrealized_pnl']
            if total_profits <= 0:
                return {'status': 'info', 'message': 'No profits to distribute'}
            
            # Define loyalty tiers (days in vault)
            loyalty_tiers = {
                30: 1.0,   # 1 month - base rate
                90: 1.1,   # 3 months - 10% bonus
                180: 1.2,  # 6 months - 20% bonus
                365: 1.35  # 1 year - 35% bonus
            }
            
            # Get all users with deposits
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT user_id, deposit_amount, deposit_time
                FROM vault_users
            ''')
            
            users = cursor.fetchall()
            total_weighted_contribution = 0
            user_weights = {}
            user_tiers = {}
            
            current_time = time.time()
            for user_id, amount, deposit_time in users:
                # Calculate days in vault
                days_in_vault = (current_time - deposit_time) / 86400
                
                # Determine loyalty tier
                loyalty_factor = 1.0
                for days, factor in sorted(loyalty_tiers.items()):
                    if days_in_vault >= days:
                        loyalty_factor = factor
                    else:
                        break
                
                weighted_contribution = amount * loyalty_factor
                total_weighted_contribution += weighted_contribution
                user_weights[user_id] = weighted_contribution
                user_tiers[user_id] = {
                    'days': days_in_vault,
                    'tier': loyalty_factor
                }
            print(user_weights)
            # Distribute profits proportionally with loyalty bonus
            distributions = []
            keeper_share = total_profits * profit_share
            user_profit_pool = total_profits - keeper_share
            
            for user_id, weighted_contribution in user_weights.items():
                if total_weighted_contribution > 0:
                    user_share = user_profit_pool * (weighted_contribution / total_weighted_contribution)
                    
                    # Record distribution with loyalty info
                    cursor.execute('''
                        INSERT INTO profit_distributions 
                        (user_id, amount, vault_performance, timestamp, weighted_factor)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (user_id, user_share, vault_balance['total_unrealized_pnl'], 
                          current_time, weighted_contribution / total_weighted_contribution))
                    
                    distributions.append({
                        'user_id': user_id,
                        'profit_amount': user_share,
                        'contribution_weight': weighted_contribution / total_weighted_contribution,
                        'loyalty_tier': user_tiers[user_id]['tier'],
                        'days_in_vault': user_tiers[user_id]['days']
                    })
                    
            self.conn.commit()
            
            # Update performance metrics with this distribution
            metrics_update = {
                'distribution_timestamp': current_time,
                'total_distributed': user_profit_pool,
                'keeper_share': keeper_share,
                'user_count': len(users),
                'loyal_users': sum(1 for tier in user_tiers.values() if tier['tier'] > 1.0)
            }
            
            await self._update_performance_metrics(metrics_update)
            
            return {
                'status': 'success',
                'keeper_share': keeper_share,
                'user_profit_pool': user_profit_pool,
                'distributions': distributions,
                'loyalty_tiers': loyalty_tiers,
                'total_weighted_contribution': total_weighted_contribution
            }
            
        except Exception as e:
            logger.error(f"Error in loyalty distribution: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _start_performance_tracking(self):
        """Start background task for performance tracking"""
        try:
            # Initial metrics calculation
            await self._calculate_performance_metrics()
            
            # Start background monitoring
            self.real_time_monitor = asyncio.create_task(self._run_real_time_monitoring())
            logger.info("Started vault performance tracking and monitoring")
            
            # Schedule regular updates
            while True:
                await self._calculate_performance_metrics()
                await self._update_benchmark_comparison()
                await self._detect_drawdowns()
                
                # Store current metrics for historical analysis
                current_value = await self._get_current_vault_value()
                if current_value > 0:
                    self.historical_values.append((time.time(), current_value))
                    
                    # Calculate daily return if we have previous value
                    if len(self.historical_values) >= 2:
                        prev_time, prev_value = self.historical_values[-2]
                        if time.time() - prev_time >= 86400:  # At least a day apart
                            daily_return = (current_value - prev_value) / prev_value
                            self.daily_returns.append(daily_return)
                
                # Wait for next update (every 6 hours)
                await asyncio.sleep(21600)
                
        except asyncio.CancelledError:
            logger.info("Performance tracking stopped")
        except Exception as e:
            logger.error(f"Error in performance tracking: {e}")

    async def _run_real_time_monitoring(self):
        """Run real-time monitoring of vault performance"""
        try:
            while True:
                # Get real-time metrics
                vault_balance = await self.get_vault_balance()
                
                if vault_balance['status'] == 'success':
                    # Update real-time metrics
                    metrics = {
                        'tvl': vault_balance['total_value'],
                        'unrealized_pnl': vault_balance['total_unrealized_pnl'],
                        'position_count': len(vault_balance['positions']),
                        'margin_utilization': vault_balance['total_margin_used'] / vault_balance['total_value'] 
                            if vault_balance['total_value'] > 0 else 0
                    }
                    
                    # Store real-time metrics
                    cursor = self.conn.cursor()
                    timestamp = time.time()
                    
                    for name, value in metrics.items():
                        cursor.execute('''
                            INSERT OR REPLACE INTO vault_real_time_metrics 
                            (metric_name, metric_value, updated_at)
                            VALUES (?, ?, ?)
                        ''', (name, value, timestamp))
                    
                    # Check for critical alerts
                    if metrics['margin_utilization'] > 0.8:
                        logger.warning(f"HIGH MARGIN UTILIZATION: {metrics['margin_utilization']:.1%}")
                    
                    self.conn.commit()
                
                # Wait before next check (every 5 minutes)
                await asyncio.sleep(300)
                
        except asyncio.CancelledError:
            logger.info("Real-time monitoring stopped")
        except Exception as e:
            logger.error(f"Error in real-time monitoring: {e}")

    async def _calculate_performance_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics"""
        try:
            vault_balance = await self.get_vault_balance()
            if vault_balance['status'] != 'success':
                return {'status': 'error', 'message': 'Failed to get vault balance'}
            
            # Get fills for more detailed metrics
            fills = self.info.user_fills(self.vault_address)
            if not fills:
                fills = []
            
            # Calculate daily, weekly, monthly returns
            current_value = vault_balance['total_value']
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Get historical values from database
            cursor = self.conn.cursor()
            
            # Get previous day value
            cursor.execute('''
                SELECT tvl FROM vault_performance_daily
                WHERE date != ? 
                ORDER BY date DESC LIMIT 1
            ''', (today,))
            prev_day = cursor.fetchone()
            daily_return = 0.0
            
            if prev_day:
                prev_value = prev_day[0]
                if prev_value > 0:
                    daily_return = (current_value - prev_value) / prev_value
            
            # Get week ago value
            week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            cursor.execute('''
                SELECT tvl FROM vault_performance_daily
                WHERE date <= ?
                ORDER BY date DESC LIMIT 1
            ''', (week_ago,))
            week_ago_data = cursor.fetchone()
            weekly_return = 0.0
            
            if week_ago_data:
                week_ago_value = week_ago_data[0]
                if week_ago_value > 0:
                    weekly_return = (current_value - week_ago_value) / week_ago_value
            
            # Get month ago value
            month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            cursor.execute('''
                SELECT tvl FROM vault_performance_daily
                WHERE date <= ?
                ORDER BY date DESC LIMIT 1
            ''', (month_ago,))
            month_ago_data = cursor.fetchone()
            monthly_return = 0.0
            
            if month_ago_data:
                month_ago_value = month_ago_data[0]
                if month_ago_value > 0:
                    monthly_return = (current_value - month_ago_value) / month_ago_value
            
            # Calculate maker rebates and taker fees
            maker_rebates = 0.0
            taker_fees = 0.0
            maker_trades = 0
            total_trades = len(fills)
            
            for fill in fills:
                fee = float(fill.get('fee', 0))
                if fee < 0:  # Maker rebate
                    maker_rebates += abs(fee)
                    maker_trades += 1
                else:  # Taker fee
                    taker_fees += fee
            
            maker_ratio = maker_trades / total_trades if total_trades > 0 else 0
            
            # Calculate Sharpe ratio using daily returns
            daily_returns_list = list(self.daily_returns)
            if len(daily_returns_list) > 0:
                avg_return = sum(daily_returns_list) / len(daily_returns_list)
                std_dev = np.std(daily_returns_list) if len(daily_returns_list) > 1 else 0
                sharpe = (avg_return / std_dev) * (252 ** 0.5) if std_dev > 0 else 0
            else:
                sharpe = 0
            
            # Calculate max drawdown
            max_drawdown = await self._calculate_max_drawdown()
            
            # Find best performing asset
            asset_performance = {}
            for position in vault_balance['positions']:
                coin = position['coin']
                pnl = position['unrealized_pnl']
                asset_performance[coin] = pnl
            
            best_asset = max(asset_performance.items(), key=lambda x: x[1])[0] if asset_performance else 'None'
            
            # Get user count
            cursor.execute('SELECT COUNT(*) FROM vault_users')
            user_count = cursor.fetchone()[0]
            
            # Calculate profitable days ratio
            cursor.execute('''
                SELECT COUNT(*) FROM vault_performance_daily
                WHERE daily_return > 0
            ''')
            profitable_days = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM vault_performance_daily')
            total_days = cursor.fetchone()[0] or 1  # Avoid division by zero
            
            # Create metrics object
            metrics = VaultPerformanceMetrics(
                tvl=current_value,
                daily_return=daily_return,
                weekly_return=weekly_return,
                monthly_return=monthly_return,
                total_return=0,  # Will calculate from initial value
                sharpe_ratio=sharpe,
                max_drawdown=max_drawdown,
                maker_rebate_earned=maker_rebates,
                maker_ratio=maker_ratio,
                active_users=user_count,
                profitable_days=profitable_days,
                total_days=total_days,
                win_rate=profitable_days / total_days,
                best_performing_asset=best_asset,
                timestamp=time.time()
            )
            
            # Store daily performance
            cursor.execute('''
                INSERT OR REPLACE INTO vault_performance_daily
                (date, tvl, daily_return, total_return, maker_rebate, taker_fee,
                 active_positions, user_count, best_asset, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (today, current_value, daily_return, 0, maker_rebates,
                  taker_fees, len(vault_balance['positions']), user_count,
                  best_asset, time.time()))
            
            self.conn.commit()
            
            # Update in-memory metrics
            self.performance_metrics = {
                'tvl': current_value,
                'daily_return': daily_return,
                'weekly_return': weekly_return,
                'monthly_return': monthly_return,
                'sharpe_ratio': sharpe,
                'max_drawdown': max_drawdown,
                'maker_rebates': maker_rebates,
                'maker_ratio': maker_ratio,
                'win_rate': profitable_days / total_days,
                'active_users': user_count
            }
            
            self.last_metrics_update = time.time()
            
            return {
                'status': 'success',
                'metrics': self.performance_metrics
            }
            
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _update_benchmark_comparison(self) -> Dict:
        """Update benchmark comparison between vault and market indices"""
        try:
            # In a real implementation, you would fetch price data for benchmarks
            # Here we'll simulate it for demonstration
            
            # Get vault's current return
            vault_balance = await self.get_vault_balance()
            if vault_balance['status'] != 'success':
                return {'status': 'error', 'message': 'Failed to get vault balance'}
            
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Calculate vault's daily return
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT tvl FROM vault_performance_daily
                WHERE date != ? 
                ORDER BY date DESC LIMIT 1
            ''', (today,))
            
            prev_day = cursor.fetchone()
            vault_return = 0.0
            
            if prev_day and prev_day[0] > 0:
                vault_return = (vault_balance['total_value'] - prev_day[0]) / prev_day[0]
            
            # Simulate benchmark returns (in a real implementation, fetch from API)
            # These would be daily returns for various benchmarks
            btc_return = np.random.normal(0.001, 0.03)  # 0.1% average daily return with 3% std dev
            eth_return = np.random.normal(0.001, 0.04)  # 0.1% average daily return with 4% std dev
            sp500_return = np.random.normal(0.0005, 0.01)  # 0.05% average daily return with 1% std dev
            
            # Calculate alpha and beta (simplified)
            # Alpha = vault return - risk-free rate - beta * (market return - risk-free rate)
            risk_free_rate = 0.0001  # 0.01% daily risk-free rate
            beta = 1.2  # Assume higher volatility than BTC
            alpha = vault_return - risk_free_rate - beta * (btc_return - risk_free_rate)
            
            # Store benchmark comparison
            cursor.execute('''
                INSERT OR REPLACE INTO vault_benchmark_comparison
                (date, vault_return, btc_return, eth_return, sp500_return, alpha, beta, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (today, vault_return, btc_return, eth_return, sp500_return, alpha, beta, time.time()))
            
            self.conn.commit()
            
            # Store in memory
            self.benchmark_comparisons.append({
                'date': today,
                'vault_return': vault_return,
                'btc_return': btc_return,
                'eth_return': eth_return,
                'sp500_return': sp500_return,
                'alpha': alpha,
                'beta': beta
            })
            
            if len(self.benchmark_comparisons) > 90:  # Keep last 90 days
                self.benchmark_comparisons.pop(0)
            
            return {
                'status': 'success',
                'benchmark': {
                    'vault_return': vault_return,
                    'btc_return': btc_return,
                    'eth_return': eth_return,
                    'sp500_return': sp500_return,
                    'alpha': alpha,
                    'beta': beta
                }
            }
            
        except Exception as e:
            logger.error(f"Error updating benchmark comparison: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from historical values"""
        try:
            if len(self.historical_values) < 2:
                return 0.0
            
            values = [value for _, value in self.historical_values]
            max_drawdown = 0.0
            peak = values[0]
            
            for value in values:
                if value > peak:
                    peak = value
                else:
                    drawdown = (peak - value) / peak
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
            
            return max_drawdown
            
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0

    async def _detect_drawdowns(self) -> Dict:
        """Detect and record significant drawdowns"""
        try:
            if len(self.historical_values) < 5:  # Need enough data
                return {'status': 'insufficient_data'}
            
            values = [value for _, value in self.historical_values]
            times = [ts for ts, _ in self.historical_values]
            
            potential_drawdowns = []
            in_drawdown = False
            peak = values[0]
            peak_time = times[0]
            trough = peak
            trough_time = peak_time
            
            for i in range(1, len(values)):
                if not in_drawdown:
                    if values[i] > peak:
                        peak = values[i]
                        peak_time = times[i]
                    elif (peak - values[i]) / peak > 0.05:  # 5% drawdown threshold to start tracking
                        in_drawdown = True
                        trough = values[i]
                        trough_time = times[i]
                else:  # In drawdown
                    if values[i] < trough:
                        trough = values[i]
                        trough_time = times[i]
                    elif values[i] > trough * 1.05:  # 5% recovery from trough
                        # Record drawdown
                        drawdown_depth = (peak - trough) / peak
                        if drawdown_depth >= 0.1:  # Only record significant drawdowns (10%+)
                            potential_drawdowns.append({
                                'start_date': datetime.fromtimestamp(peak_time).strftime('%Y-%m-%d'),
                                'end_date': datetime.fromtimestamp(trough_time).strftime('%Y-%m-%d'),
                                'depth': drawdown_depth,
                                'duration_days': (trough_time - peak_time) / 86400,
                                'recovery_date': datetime.fromtimestamp(times[i]).strftime('%Y-%m-%d')
                            })
                        
                        # Reset drawdown tracking
                        in_drawdown = False
                        peak = values[i]
                        peak_time = times[i]
            
            # Store significant drawdowns
            cursor = self.conn.cursor()
            for drawdown in potential_drawdowns:
                cursor.execute('''
                    INSERT INTO vault_drawdowns
                    (start_date, end_date, depth, duration_days, recovery_date, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (drawdown['start_date'], drawdown['end_date'], drawdown['depth'],
                      drawdown['duration_days'], drawdown['recovery_date'], time.time()))
            
            self.conn.commit()
            
            return {
                'status': 'success',
                'drawdowns_detected': len(potential_drawdowns),
                'drawdowns': potential_drawdowns
            }
            
        except Exception as e:
            logger.error(f"Error detecting drawdowns: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _update_performance_metrics(self, new_metrics: Dict):
        """Update performance metrics with new data"""
        try:
            timestamp = new_metrics.get('timestamp', time.time())
            
            # Update in-memory metrics
            for key, value in new_metrics.items():
                if key != 'timestamp':
                    self.performance_metrics[key] = value
            
            self.last_metrics_update = timestamp
            
            # Store historical point
            self.performance_history.append({
                'timestamp': timestamp,
                'metrics': self.performance_metrics.copy()
            })
            
            # Limit history size
            if len(self.performance_history) > 100:
                self.performance_history.pop(0)
                
        except Exception as e:
            logger.error(f"Error updating performance metrics: {e}")

    async def _get_current_vault_value(self) -> float:
        """Get current vault value"""
        try:
            vault_state = self.info.user_state(self.vault_address)
            return float(vault_state.get('marginSummary', {}).get('accountValue', 0))
        except Exception:
            return 0.0

    async def get_enhanced_performance_analytics(self) -> Dict:
        """Get comprehensive performance analytics for the vault"""
        try:
            # Force refresh performance metrics
            await self._calculate_performance_metrics()
            
            # Get benchmark comparison
            await self._update_benchmark_comparison()
            
            # Get drawdown information
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT * FROM vault_drawdowns
                ORDER BY timestamp DESC
                LIMIT 5
            ''')
            recent_drawdowns = [dict(zip(
                ['id', 'start_date', 'end_date', 'depth', 'duration_days', 'recovery_date', 'timestamp'], 
                row)) for row in cursor.fetchall()]
            
            # Get real-time metrics
            cursor.execute('''
                SELECT metric_name, metric_value, updated_at
                FROM vault_real_time_metrics
            ''')
            real_time = {row[0]: {'value': row[1], 'updated_at': row[2]} for row in cursor.fetchall()}
            
            # Get periodic performance
            cursor.execute('''
                SELECT date, tvl, daily_return
                FROM vault_performance_daily
                ORDER BY date DESC
                LIMIT 30
            ''')
            daily_performance = [dict(zip(['date', 'tvl', 'return'], row)) for row in cursor.fetchall()]
            
            # Most profitable coins
            position_analytics = await self._analyze_positions_by_coin()
            
            # Build full analytics response
            return {
                'status': 'success',
                'metrics': self.performance_metrics,
                'benchmarks': self.benchmark_comparisons[-7:] if self.benchmark_comparisons else [],
                'drawdowns': recent_drawdowns,
                'real_time': real_time,
                'daily_performance': daily_performance,
                'position_analytics': position_analytics
            }
            
        except Exception as e:
            logger.error(f"Error getting enhanced performance analytics: {e}")
            return {'status': 'error', 'message': str(e)}

    async def _analyze_positions_by_coin(self) -> Dict:
        """Analyze position performance by coin"""
        try:
            # Get fills grouped by coin
            fills = self.info.user_fills(self.vault_address)
            
            if not fills:
                return {'coins': []}
            
            coin_performance = {}
            for fill in fills:
                coin = fill.get('coin', 'unknown')
                pnl = float(fill.get('closedPnl', 0))
                fee = float(fill.get('fee', 0))
                size = float(fill.get('sz', 0))
                price = float(fill.get('px', 0))
                
                if coin not in coin_performance:
                    coin_performance[coin] = {
                        'coin': coin,
                        'total_pnl': 0,
                        'total_fees': 0,
                        'trade_count': 0,
                        'total_volume': 0,
                        'winning_trades': 0,
                        'largest_win': 0,
                        'largest_loss': 0
                    }
                
                coin_stats = coin_performance[coin]
                coin_stats['total_pnl'] += pnl
                coin_stats['total_fees'] += fee
                coin_stats['trade_count'] += 1
                coin_stats['total_volume'] += price * size
                
                if pnl > 0:
                    coin_stats['winning_trades'] += 1
                    if pnl > coin_stats['largest_win']:
                        coin_stats['largest_win'] = pnl
                elif pnl < 0:
                    if pnl < coin_stats['largest_loss']:
                        coin_stats['largest_loss'] = pnl
            
            # Calculate win rates and average trade
            for coin, stats in coin_performance.items():
                if stats['trade_count'] > 0:
                    stats['win_rate'] = stats['winning_trades'] / stats['trade_count']
                    stats['avg_trade_pnl'] = stats['total_pnl'] / stats['trade_count']
                else:
                    stats['win_rate'] = 0
                    stats['avg_trade_pnl'] = 0
            
            # Sort by total PnL
            sorted_coins = sorted(coin_performance.values(), key=lambda x: x['total_pnl'], reverse=True)
            
            return {'coins': sorted_coins}
            
        except Exception as e:
            logger.error(f"Error analyzing positions by coin: {e}")
            return {'coins': [], 'error': str(e)}

    async def get_performance_benchmarks(self) -> Dict:
        """Get performance benchmarks compared to market"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT date, vault_return, btc_return, eth_return, sp500_return, alpha, beta
                FROM vault_benchmark_comparison
                ORDER BY date DESC
                LIMIT 30
            ''')
            
            benchmarks = [dict(zip(
                ['date', 'vault_return', 'btc_return', 'eth_return', 'sp500_return', 'alpha', 'beta'], 
                row)) for row in cursor.fetchall()]
            
            # Calculate cumulative returns
            if benchmarks:
                cumulative = {
                    'vault': 1.0,
                    'btc': 1.0,
                    'eth': 1.0,
                    'sp500': 1.0
                }
                
                cumulative_series = []
                
                for b in reversed(benchmarks):
                    cumulative['vault'] *= (1 + b['vault_return'])
                    cumulative['btc'] *= (1 + b['btc_return'])
                    cumulative['eth'] *= (1 + b['eth_return'])
                    cumulative['sp500'] *= (1 + b['sp500_return'])
                    
                    cumulative_series.append({
                        'date': b['date'],
                        'vault': cumulative['vault'],
                        'btc': cumulative['btc'],
                        'eth': cumulative['eth'],
                        'sp500': cumulative['sp500']
                    })
                
                # Calculate average alpha and beta
                avg_alpha = sum(b['alpha'] for b in benchmarks) / len(benchmarks)
                avg_beta = sum(b['beta'] for b in benchmarks) / len(benchmarks)
                
                return {
                    'status': 'success',
                    'daily_returns': benchmarks,
                    'cumulative_returns': cumulative_series,
                    'avg_alpha': avg_alpha,
                    'avg_beta': avg_beta
                }
            
            return {'status': 'success', 'benchmarks': [], 'message': 'No benchmark data available'}
            
        except Exception as e:
            logger.error(f"Error getting performance benchmarks: {e}")
            return {'status': 'error', 'message': str(e)}

    async def get_profit_attribution_analysis(self) -> Dict:
        """Get profit attribution analysis by strategy and asset"""
        try:
            # In a real implementation, you would track strategies separately
            # Here we'll simulate strategy attribution
            
            # Get fills for analysis
            fills = self.info.user_fills(self.vault_address)
            if not fills:
                return {'status': 'success', 'attribution': [], 'message': 'No fill data available'}
            
            # Simulate strategy labels (in production, each order would be tagged with strategy)
            strategies = ['grid', 'momentum', 'market_making', 'volatility', 'trend']
            
            # Group by coin first
            coin_attribution = {}
            for fill in fills:
                coin = fill.get('coin', 'unknown')
                pnl = float(fill.get('closedPnl', 0))
                
                if coin not in coin_attribution:
                    coin_attribution[coin] = 0
                    
                coin_attribution[coin] += pnl
            
            # Simulate strategy attribution
            strategy_attribution = {}
            for strategy in strategies:
                strategy_attribution[strategy] = 0
            
            # Distribute PnL to strategies based on coin (simplified simulation)
            for coin, pnl in coin_attribution.items():
                # Randomly distribute PnL to strategies based on coin
                # This is just a simulation - in a real system, each trade would be tagged
                import random
                # Pick 1-3 strategies for this coin
                strategy_count = random.randint(1, min(3, len(strategies)))
                selected_strategies = random.sample(strategies, strategy_count)
                
                # Distribute PnL among selected strategies
                weights = [random.random() for _ in range(strategy_count)]
                total_weight = sum(weights)
                
                for i, strategy in enumerate(selected_strategies):
                    strategy_share = pnl * (weights[i] / total_weight)
                    strategy_attribution[strategy] += strategy_share
            
            # Format response
            attribution = [
                {'strategy': strategy, 'pnl': pnl, 'percentage': 0}  # Percentage will be calculated
                for strategy, pnl in strategy_attribution.items()
            ]
            
            # Calculate percentages
            total_pnl = sum(item['pnl'] for item in attribution)
            if total_pnl != 0:
                for item in attribution:
                    item['percentage'] = item['pnl'] / total_pnl * 100
            
            # Sort by PnL contribution
            attribution.sort(key=lambda x: x['pnl'], reverse=True)
            
            return {
                'status': 'success',
                'total_pnl': total_pnl,
                'attribution': attribution,
                'coin_attribution': [
                    {'coin': coin, 'pnl': pnl}
                    for coin, pnl in coin_attribution.items()
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting profit attribution: {e}")
            return {'status': 'error', 'message': str(e)}

# Legacy alias for backward compatibility
class ProfitSharingVaultManager(VaultManager):
    """Legacy alias for backward compatibility"""
    pass

# Helper functions to run examples directly
def run_basic_vault_example():
    """Run the basic_vault.py example directly"""
    try:
        basic_vault.main()
    except Exception as e:
        print(f"Error running basic_vault example: {e}")

def run_basic_vault_transfer_example():
    """Run the basic_vault_transfer.py example directly"""  
    try:
        basic_vault_transfer.main()
    except Exception as e:
        print(f"Error running basic_vault_transfer example: {e}")

def run_basic_transfer_example():
    """Run the basic_transfer.py example directly"""
    try:
        basic_transfer.main()
    except Exception as e:
        print(f"Error running basic_transfer example: {e}")
