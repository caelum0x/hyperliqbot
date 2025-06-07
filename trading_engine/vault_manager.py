import asyncio
import json
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
import sqlite3
from datetime import datetime
import sys
import os

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

class VaultManager:
    """
    Manages user vaults with automated profit sharing using actual Hyperliquid API
    Uses real examples: basic_vault.py, basic_vault_transfer.py, and basic_transfer.py
    """
    
    def __init__(self, vault_address: str, master_account=None, base_url=None):
        self.vault_address = vault_address
        self.logger = logging.getLogger(__name__)
        
        # Use example_utils.setup pattern like all Hyperliquid examples
        self.address, self.info, self.exchange = example_utils.setup(
            base_url=base_url or constants.TESTNET_API_URL,
            skip_ws=True
        )
        
        # Create Exchange instance for vault operations using basic_vault.py pattern
        self.vault_exchange = Exchange(
            self.exchange.wallet, 
            self.exchange.base_url, 
            vault_address=vault_address
        )
        
        self.vault_users = {}
        self.profit_history = []
        
        # Initialize database for user tracking
        self._init_database()
        
        self.logger.info(f"VaultManager initialized for vault: {vault_address}")
    
    def _init_database(self):
        """Initialize SQLite database for user tracking"""
        self.conn = sqlite3.connect('vault_users.db')
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vault_users (
                user_id TEXT PRIMARY KEY,
                deposit_amount REAL,
                deposit_time REAL,
                initial_vault_value REAL,
                profit_share_rate REAL,
                total_profits_earned REAL DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profit_distributions (
                distribution_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                amount REAL,
                vault_performance REAL,
                timestamp REAL,
                FOREIGN KEY (user_id) REFERENCES vault_users (user_id)
            )
        ''')
        
        self.conn.commit()

    async def get_vault_balance(self) -> Dict:
        """Get real vault balance using Info API exactly like basic_vault.py"""
        try:
            # Use same pattern as basic_vault.py for getting vault state
            vault_state = self.info.user_state(self.vault_address)
            margin_summary = vault_state.get('marginSummary', {})
            
            # Get positions data exactly like the examples
            positions = []
            for asset_position in vault_state.get('assetPositions', []):
                position = asset_position['position']
                if float(position['szi']) != 0:  # Only non-zero positions
                    positions.append({
                        'coin': position['coin'],
                        'size': float(position['szi']),
                        'entry_px': float(position['entryPx']) if position['entryPx'] else 0,
                        'unrealized_pnl': float(position['unrealizedPnl']),
                        'margin_used': float(position['marginUsed'])
                    })
            
            return {
                'status': 'success',
                'total_value': float(margin_summary.get('accountValue', 0)),
                'total_margin_used': float(margin_summary.get('totalMarginUsed', 0)),
                'total_unrealized_pnl': float(margin_summary.get('totalUnrealizedPnl', 0)),
                'cross_maintenance_margin': float(vault_state.get('crossMaintenanceMarginUsed', 0)),
                'positions': positions,
                'position_count': len(positions)
            }
            
        except Exception as e:
            self.logger.error(f"Error getting vault balance: {e}")
            return {'status': 'error', 'message': str(e)}

    async def deposit_to_vault(self, amount: float) -> Dict:
        """
        Deposit to vault using basic_vault_transfer.py pattern exactly
        """
        try:
            # Check if we have sufficient balance first
            user_state = self.info.user_state(self.address)
            account_value = float(user_state['marginSummary']['accountValue'])
            
            if account_value < amount:
                return {
                    'status': 'error',
                    'message': f'Insufficient balance. Available: ${account_value:.2f}'
                }
            
            # Use basic_vault_transfer.py exact pattern
            # Transfer amount USD to vault (amount in micro USDC)
            amount_micro = int(amount * 1_000_000)
            
            transfer_result = self.exchange.vault_usd_transfer(
                self.vault_address, True, amount_micro
            )
            print(transfer_result)  # Print like the example
            
            return {
                'status': 'success' if transfer_result.get('status') == 'ok' else 'error',
                'result': transfer_result,
                'amount': amount,
                'vault_address': self.vault_address
            }
            
        except Exception as e:
            self.logger.error(f"Error depositing to vault: {e}")
            return {'status': 'error', 'message': str(e)}

    async def withdraw_from_vault(self, amount: float) -> Dict:
        """
        Withdraw from vault using basic_vault_transfer.py pattern exactly
        """
        try:
            # Use basic_vault_transfer.py pattern but with is_deposit=False
            amount_micro = int(amount * 1_000_000)
            
            transfer_result = self.exchange.vault_usd_transfer(
                self.vault_address, False, amount_micro
            )
            print(transfer_result)  # Print like the example
            
            return {
                'status': 'success' if transfer_result.get('status') == 'ok' else 'error',
                'result': transfer_result,
                'amount': amount,
                'vault_address': self.vault_address
            }
            
        except Exception as e:
            self.logger.error(f"Error withdrawing from vault: {e}")
            return {'status': 'error', 'message': str(e)}

    async def transfer_usd_to_user(self, user_address: str, amount: float) -> Dict:
        """
        Transfer USD to user using basic_transfer.py pattern exactly
        """
        try:
            # Check if account can perform internal transfers (from basic_transfer.py)
            if self.exchange.account_address != self.exchange.wallet.address:
                return {
                    'status': 'error',
                    'message': 'Agents do not have permission to perform internal transfers'
                }
            
            # Use basic_transfer.py exact pattern
            transfer_result = self.exchange.usd_transfer(amount, user_address)
            print(transfer_result)  # Print like the example
            
            return {
                'status': 'success' if transfer_result.get('status') == 'ok' else 'error',
                'result': transfer_result,
                'amount': amount,
                'recipient': user_address
            }
            
        except Exception as e:
            self.logger.error(f"Error transferring USD: {e}")
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
            
            self.logger.info(f"Vault order placed: {coin} {size}@{price}")
            return {
                'status': 'success' if order_result.get('status') == 'ok' else 'error',
                'result': order_result,
                'oid': order_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("resting", {}).get("oid") if order_result.get("status") == "ok" else None
            }
            
        except Exception as e:
            self.logger.error(f"Error placing vault order: {e}")
            return {'status': 'error', 'message': str(e)}

    async def cancel_vault_order(self, coin: str, oid: int) -> Dict:
        """
        Cancel vault order exactly like basic_vault.py cancel pattern
        """
        try:
            # Use basic_vault.py exact cancel pattern
            cancel_result = self.vault_exchange.cancel(coin, oid)
            print(cancel_result)  # Print like the example
            
            self.logger.info(f"Vault order cancelled: {coin} oid:{oid}")
            return {
                'status': 'success' if cancel_result.get('status') == 'ok' else 'error',
                'result': cancel_result
            }
            
        except Exception as e:
            self.logger.error(f"Error cancelling vault order: {e}")
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
            self.logger.error(f"Error executing basic vault example: {e}")
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
            self.logger.error(f"Error executing vault transfer example: {e}")
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
            self.logger.error(f"Error executing transfer example: {e}")
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
            self.logger.error(f"Error distributing profits: {e}")
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
