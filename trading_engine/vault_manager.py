import asyncio
import json
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
import sqlite3

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

@dataclass
class VaultUser:
    """Vault user data"""
    user_id: str
    deposit_amount: float
    deposit_time: float
    initial_vault_value: float
    profit_share_rate: float

class ProfitSharingVaultManager:
    """
    Manages user vaults with automated profit sharing
    """
    
    def __init__(self, exchange: Exchange, info: Info, vault_address: str):
        self.exchange = exchange
        self.info = info
        self.vault_address = vault_address
        self.vault_users = {}
        self.profit_history = []
        
        # Initialize database for user tracking
        self._init_database()
    
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
    
    async def create_user_vault(
        self,
        user_id: str,
        initial_deposit: float,
        profit_share_rate: float = 0.10
    ) -> Dict:
        """
        Create a new user vault with profit sharing
        """
        try:
            # Get current vault value for baseline
            vault_state = self.info.user_state(self.vault_address)
            current_vault_value = float(vault_state.get("marginSummary", {}).get("accountValue", 0))
            
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
