"""
SQLite database module for tracking users and profits
Production-ready database with proper schema and indexing
"""

import sqlite3
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal

class Database:
    def __init__(self, db_file: str = "bot_data.db"):
        self.db_file = db_file
        self.connection = None
        self.lock = asyncio.Lock()
        self._init_database()
        
    def _init_database(self):
        """Initialize database with proper schema"""
        self.connection = sqlite3.connect(self.db_file, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        
        # Create tables
        cursor = self.connection.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                wallet_address TEXT,
                joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_deposited REAL DEFAULT 0.0,
                total_withdrawn REAL DEFAULT 0.0,
                total_profit REAL DEFAULT 0.0,
                current_balance REAL DEFAULT 0.0,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                referred_by INTEGER,
                is_active BOOLEAN DEFAULT 1
            )
        """)
        
        # Deposits table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                tx_hash TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'confirmed',
                type TEXT DEFAULT 'deposit',
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        """)
        
        # Withdrawals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                tx_hash TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                type TEXT DEFAULT 'withdrawal',
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        """)
        
        # Trades table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT,
                side TEXT,
                size REAL,
                price REAL,
                notional REAL,
                pnl REAL,
                fee REAL,
                fee_type TEXT,
                vault_address TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Daily stats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                vault_address TEXT,
                account_value REAL,
                total_pnl REAL,
                volume_24h REAL,
                active_users INTEGER,
                total_deposits REAL,
                performance_fee_earned REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Vault performance table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vault_performance (
                date TEXT PRIMARY KEY,
                volume REAL DEFAULT 0.0,
                pnl REAL DEFAULT 0.0,
                fees_paid REAL DEFAULT 0.0,
                rebates_earned REAL DEFAULT 0.0,
                trades_count INTEGER DEFAULT 0,
                maker_trades INTEGER DEFAULT 0,
                taker_trades INTEGER DEFAULT 0
            )
        """)
        
        # Referrals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bonus_paid REAL DEFAULT 0.0,
                FOREIGN KEY (referrer_id) REFERENCES users (telegram_id),
                FOREIGN KEY (referred_id) REFERENCES users (telegram_id)
            )
        """)
        
        # Enhanced performance tracking tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS maker_rebate_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                coin TEXT,
                timestamp REAL,
                maker_volume REAL,
                total_volume REAL,
                rebate_earned REAL,
                maker_percentage REAL,
                efficiency_score REAL,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vault_user_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                vault_address TEXT,
                date TEXT,
                share_percentage REAL,
                profit_share REAL,
                performance_fee_paid REAL,
                cumulative_profit REAL,
                roi_daily REAL,
                volume_contribution REAL,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategy_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT,
                coin TEXT,
                timestamp REAL,
                entry_price REAL,
                exit_price REAL,
                position_size REAL,
                pnl REAL,
                duration_minutes INTEGER,
                win_rate REAL,
                sharpe_ratio REAL,
                max_drawdown REAL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin TEXT,
                timestamp REAL,
                mid_price REAL,
                spread_bps REAL,
                volume_1h REAL,
                volatility_1h REAL,
                orderbook_imbalance REAL,
                maker_rebate_opportunity REAL,
                trend_signal TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_trading_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                total_trades INTEGER,
                maker_trades INTEGER,
                avg_trade_size REAL,
                most_traded_coin TEXT,
                peak_trading_hour INTEGER,
                trading_frequency_score REAL,
                risk_score REAL,
                FOREIGN KEY (user_id) REFERENCES users (telegram_id)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deposits_user ON deposits(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON withdrawals(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_maker_rebate_user_coin ON maker_rebate_performance(user_id, coin)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vault_user_perf_date ON vault_user_performance(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategy_perf_name ON strategy_performance(strategy_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_analytics_coin ON market_analytics(coin, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_patterns_date ON user_trading_patterns(date)")
        
        self.connection.commit()
    
    async def add_user(self, telegram_id: int, wallet_address: str = None, referrer_id: int = None):
        """Add new user to database"""
        async with self.lock:
            cursor = self.connection.cursor()
            
            # Check if user exists
            cursor.execute("SELECT telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
            if cursor.fetchone():
                return await self.get_user(telegram_id)
            
            # Insert new user
            cursor.execute("""
                INSERT INTO users (telegram_id, wallet_address, referred_by)
                VALUES (?, ?, ?)
            """, (telegram_id, wallet_address, referrer_id))
            
            # Handle referral
            if referrer_id:
                await self.add_referral(referrer_id, telegram_id)
            
            self.connection.commit()
            return await self.get_user(telegram_id)
    
    async def get_user(self, telegram_id: int) -> Optional[Dict]:
        """Get user data"""
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    
    async def record_deposit(self, telegram_id: int, amount: float, tx_hash: str = None):
        """Record user deposit to vault"""
        async with self.lock:
            cursor = self.connection.cursor()
            
            # Insert deposit record
            cursor.execute("""
                INSERT INTO deposits (user_id, amount, tx_hash)
                VALUES (?, ?, ?)
            """, (telegram_id, amount, tx_hash))
            
            deposit_id = cursor.lastrowid
            
            # Update user stats
            cursor.execute("""
                UPDATE users 
                SET total_deposited = total_deposited + ?,
                    current_balance = current_balance + ?,
                    last_activity = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
            """, (amount, amount, telegram_id))
            
            # Create user if doesn't exist
            if cursor.rowcount == 0:
                await self.add_user(telegram_id)
                cursor.execute("""
                    UPDATE users 
                    SET total_deposited = ?,
                        current_balance = ?,
                        last_activity = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                """, (amount, amount, telegram_id))
            
            self.connection.commit()
            
            # Return deposit record
            cursor.execute("SELECT * FROM deposits WHERE id = ?", (deposit_id,))
            return dict(cursor.fetchone())
    
    async def record_withdrawal(self, telegram_id: int, amount: float, tx_hash: str = None):
        """Record user withdrawal from vault"""
        async with self.lock:
            cursor = self.connection.cursor()
            
            # Insert withdrawal record
            cursor.execute("""
                INSERT INTO withdrawals (user_id, amount, tx_hash)
                VALUES (?, ?, ?)
            """, (telegram_id, amount, tx_hash))
            
            withdrawal_id = cursor.lastrowid
            
            # Update user stats
            cursor.execute("""
                UPDATE users 
                SET total_withdrawn = total_withdrawn + ?,
                    current_balance = current_balance - ?,
                    last_activity = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
            """, (amount, amount, telegram_id))
            
            self.connection.commit()
            
            # Return withdrawal record
            cursor.execute("SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,))
            return dict(cursor.fetchone())
    
    async def record_trade(self, coin: str, side: str, size: float, price: float, pnl: float, 
                          fee: float, fee_type: str, vault_address: str = None):
        """Record executed trade from vault"""
        async with self.lock:
            cursor = self.connection.cursor()
            
            notional = size * price
            
            # Insert trade record
            cursor.execute("""
                INSERT INTO trades (coin, side, size, price, notional, pnl, fee, fee_type, vault_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (coin, side, size, price, notional, pnl, fee, fee_type, vault_address))
            
            trade_id = cursor.lastrowid
            
            # Update vault performance
            await self._update_daily_performance({
                "notional": notional,
                "pnl": pnl,
                "fee": fee,
                "fee_type": fee_type
            })
            
            self.connection.commit()
            
            # Return trade record
            cursor.execute("SELECT * FROM trades WHERE id = ?", (trade_id,))
            return dict(cursor.fetchone())
    
    async def _update_daily_performance(self, trade: Dict):
        """Update daily performance metrics"""
        today = datetime.now().date().isoformat()
        
        async with self.lock:
            cursor = self.connection.cursor()
            
            # Get existing performance or create new
            cursor.execute("SELECT * FROM vault_performance WHERE date = ?", (today,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing record
                if trade["fee_type"] == "maker_rebate":
                    cursor.execute("""
                        UPDATE vault_performance 
                        SET volume = volume + ?,
                            pnl = pnl + ?,
                            rebates_earned = rebates_earned + ?,
                            trades_count = trades_count + 1,
                            maker_trades = maker_trades + 1
                        WHERE date = ?
                    """, (trade["notional"], trade["pnl"], abs(trade["fee"]), today))
                else:
                    cursor.execute("""
                        UPDATE vault_performance 
                        SET volume = volume + ?,
                            pnl = pnl + ?,
                            fees_paid = fees_paid + ?,
                            trades_count = trades_count + 1,
                            taker_trades = taker_trades + 1
                        WHERE date = ?
                    """, (trade["notional"], trade["pnl"], trade["fee"], today))
            else:
                # Create new record
                if trade["fee_type"] == "maker_rebate":
                    cursor.execute("""
                        INSERT INTO vault_performance 
                        (date, volume, pnl, rebates_earned, trades_count, maker_trades)
                        VALUES (?, ?, ?, ?, 1, 1)
                    """, (today, trade["notional"], trade["pnl"], abs(trade["fee"])))
                else:
                    cursor.execute("""
                        INSERT INTO vault_performance 
                        (date, volume, pnl, fees_paid, trades_count, taker_trades)
                        VALUES (?, ?, ?, ?, 1, 1)
                    """, (today, trade["notional"], trade["pnl"], trade["fee"]))
    
    async def get_user_stats(self, telegram_id: int) -> Optional[Dict]:
        """Get comprehensive user statistics"""
        cursor = self.connection.cursor()
        
        # Get user data
        user_data = await self.get_user(telegram_id)
        if not user_data:
            return None
        
        # Get total vault deposits
        cursor.execute("""
            SELECT SUM(amount) as total FROM deposits WHERE status = 'confirmed'
        """)
        total_vault_deposits = cursor.fetchone()["total"] or 0
        
        # Calculate vault share
        user_deposits = user_data["total_deposited"]
        vault_share = user_deposits / total_vault_deposits if total_vault_deposits > 0 else 0
        
        # Get recent performance (last 7 days)
        week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
        cursor.execute("""
            SELECT 
                SUM(volume) as volume,
                SUM(pnl) as pnl,
                SUM(trades_count) as trades_count
            FROM vault_performance 
            WHERE date >= ?
        """, (week_ago,))
        
        recent_perf = cursor.fetchone()
        vault_pnl = recent_perf["pnl"] or 0
        
        # Calculate user's share of profits (90% after performance fee)
        user_profit_share = vault_pnl * vault_share * 0.9
        total_user_profit = user_data["total_profit"] + user_profit_share
        
        # Calculate ROI
        roi = (total_user_profit / user_deposits * 100) if user_deposits > 0 else 0
        
        return {
            "telegram_id": telegram_id,
            "wallet_address": user_data.get("wallet_address"),
            "joined": user_data["joined"],
            "days_active": (datetime.now() - datetime.fromisoformat(user_data["joined"])).days,
            "total_deposited": user_deposits,
            "total_withdrawn": user_data["total_withdrawn"],
            "current_balance": user_data["current_balance"],
            "vault_share_pct": vault_share * 100,
            "recent_profit": user_profit_share,
            "total_profit": total_user_profit,
            "roi_pct": roi,
            "recent_volume": recent_perf["volume"] or 0,
            "is_active": user_data.get("is_active", True),
            "last_activity": user_data.get("last_activity")
        }
    
    async def update_daily_stats(self, vault_address: str, account_value: float, 
                               total_pnl: float, volume_24h: float):
        """Update daily vault statistics"""
        today = datetime.now().date().isoformat()
        
        async with self.lock:
            cursor = self.connection.cursor()
            
            # Get active users count
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_active = 1")
            active_users = cursor.fetchone()["count"]
            
            # Get total deposits
            cursor.execute("SELECT SUM(amount) as total FROM deposits WHERE status = 'confirmed'")
            total_deposits = cursor.fetchone()["total"] or 0
            
            # Insert or update daily stats
            cursor.execute("""
                INSERT OR REPLACE INTO daily_stats 
                (date, vault_address, account_value, total_pnl, volume_24h, 
                 active_users, total_deposits, performance_fee_earned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (today, vault_address, account_value, total_pnl, volume_24h,
                  active_users, total_deposits, max(0, total_pnl * 0.1)))
            
            self.connection.commit()
    
    async def get_vault_stats(self) -> Dict:
        """Get comprehensive vault statistics"""
        cursor = self.connection.cursor()
        
        # Get deposits/withdrawals
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN status = 'confirmed' THEN amount ELSE 0 END) as total_deposits
            FROM deposits
        """)
        deposits_data = cursor.fetchone()
        
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN status = 'completed' THEN amount ELSE 0 END) as total_withdrawals
            FROM withdrawals
        """)
        withdrawals_data = cursor.fetchone()
        
        # Get trading stats
        cursor.execute("""
            SELECT 
                SUM(pnl) as total_pnl,
                SUM(notional) as total_volume,
                SUM(CASE WHEN fee_type = 'maker_rebate' THEN ABS(fee) ELSE 0 END) as total_rebates,
                SUM(CASE WHEN fee_type = 'taker_fee' THEN fee ELSE 0 END) as total_fees,
                COUNT(*) as total_trades,
                SUM(CASE WHEN fee_type = 'maker_rebate' THEN 1 ELSE 0 END) as maker_trades
            FROM trades
        """)
        trade_stats = cursor.fetchone()
        
        # Get recent performance (last 24h)
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        cursor.execute("""
            SELECT 
                SUM(volume) as volume,
                SUM(pnl) as pnl,
                SUM(trades_count) as trades_count
            FROM vault_performance 
            WHERE date >= ?
        """, (yesterday,))
        recent_perf = cursor.fetchone()
        
        # Get active users
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_active = 1")
        active_users = cursor.fetchone()["count"]
        
        total_deposits = deposits_data["total_deposits"] or 0
        total_withdrawals = withdrawals_data["total_withdrawals"] or 0
        total_pnl = trade_stats["total_pnl"] or 0
        total_trades = trade_stats["total_trades"] or 0
        maker_trades = trade_stats["maker_trades"] or 0
        
        return {
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "net_deposits": total_deposits - total_withdrawals,
            "total_pnl": total_pnl,
            "total_volume": trade_stats["total_volume"] or 0,
            "total_rebates": trade_stats["total_rebates"] or 0,
            "total_fees_paid": trade_stats["total_fees"] or 0,
            "net_fees": (trade_stats["total_rebates"] or 0) - (trade_stats["total_fees"] or 0),
            "total_trades": total_trades,
            "maker_percentage": (maker_trades / total_trades * 100) if total_trades > 0 else 0,
            "active_users": active_users,
            "performance_fees_earned": max(0, total_pnl * 0.1),
            "daily_volume": recent_perf["volume"] or 0,
            "daily_pnl": recent_perf["pnl"] or 0,
            "daily_trades": recent_perf["trades_count"] or 0
        }
    
    async def add_referral(self, referrer_id: int, referred_id: int):
        """Track referral relationship"""
        async with self.lock:
            cursor = self.connection.cursor()
            
            cursor.execute("""
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            """, (referrer_id, referred_id))
            
            self.connection.commit()
    
    async def pay_referral_bonus(self, referrer_id: int, referred_id: int, amount: float):
        """Pay referral bonus"""
        async with self.lock:
            cursor = self.connection.cursor()
            
            # Update referral bonus
            cursor.execute("""
                UPDATE referrals 
                SET bonus_paid = bonus_paid + ?
                WHERE referrer_id = ? AND referred_id = ?
            """, (amount, referrer_id, referred_id))
            
            # Update referrer's profit
            cursor.execute("""
                UPDATE users 
                SET total_profit = total_profit + ?
                WHERE telegram_id = ?
            """, (amount, referrer_id))
            
            self.connection.commit()
    
    async def get_referral_stats(self, telegram_id: int) -> Dict:
        """Get user's referral statistics"""
        cursor = self.connection.cursor()
        
        # Get referral stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_referrals,
                SUM(bonus_paid) as total_earnings
            FROM referrals 
            WHERE referrer_id = ?
        """, (telegram_id,))
        
        stats = cursor.fetchone()
        
        # Get active referrals (users who deposited)
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM referrals r
            JOIN users u ON r.referred_id = u.telegram_id
            WHERE r.referrer_id = ? AND u.total_deposited > 0
        """, (telegram_id,))
        
        active_referrals = cursor.fetchone()["count"]
        
        # Get recent referrals
        cursor.execute("""
            SELECT referred_id, timestamp, bonus_paid
            FROM referrals 
            WHERE referrer_id = ?
            ORDER BY timestamp DESC
            LIMIT 5
        """, (telegram_id,))
        
        recent_referrals = [dict(row) for row in cursor.fetchall()]
        
        return {
            "total_referrals": stats["total_referrals"] or 0,
            "active_referrals": active_referrals,
            "total_earnings": stats["total_earnings"] or 0.0,
            "referral_link": f"https://t.me/HyperLiquidBot?start=ref_{telegram_id}",
            "recent_referrals": recent_referrals
        }
    
    async def get_leaderboard(self, metric: str = "profit", limit: int = 10) -> List[Dict]:
        """Get user leaderboard by different metrics"""
        cursor = self.connection.cursor()
        
        if metric == "profit":
            cursor.execute("""
                SELECT telegram_id, total_profit as value
                FROM users 
                WHERE is_active = 1
                ORDER BY total_profit DESC
                LIMIT ?
            """, (limit,))
        elif metric == "deposits":
            cursor.execute("""
                SELECT telegram_id, total_deposited as value
                FROM users 
                WHERE is_active = 1
                ORDER BY total_deposited DESC
                LIMIT ?
            """, (limit,))
        elif metric == "roi":
            cursor.execute("""
                SELECT telegram_id, 
                       CASE WHEN total_deposited > 0 
                            THEN (total_profit / total_deposited * 100)
                            ELSE 0 END as value
                FROM users 
                WHERE is_active = 1 AND total_deposited > 0
                ORDER BY value DESC
                LIMIT ?
            """, (limit,))
        
        leaderboard = []
        for row in cursor.fetchall():
            user_stats = await self.get_user_stats(row["telegram_id"])
            if user_stats:
                leaderboard.append(user_stats)
        
        return leaderboard
    
    async def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to keep database performant"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).date().isoformat()
        
        async with self.lock:
            cursor = self.connection.cursor()
            
            # Clean old vault performance data
            cursor.execute("DELETE FROM vault_performance WHERE date < ?", (cutoff_date,))
            
            # Clean old daily stats
            cursor.execute("DELETE FROM daily_stats WHERE date < ?", (cutoff_date,))
            
            self.connection.commit()


# Singleton instance
bot_db = Database()

# Utility functions for backward compatibility
async def get_user_stats(telegram_id: int) -> Optional[Dict]:
    """Get user stats - convenience function"""
    return await bot_db.get_user_stats(telegram_id)

async def record_user_deposit(telegram_id: int, amount: float, tx_hash: str = None) -> Dict:
    """Record user deposit - convenience function"""
    return await bot_db.record_deposit(telegram_id, amount, tx_hash)

async def get_vault_performance() -> Dict:
    """Get vault performance - convenience function"""
    return await bot_db.get_vault_stats()


# Testing
async def test_database():
    """Test database functionality"""
    db = Database("test_bot_data.db")
    
    # Add users
    await db.add_user(123456789, "0x1234...", None)
    await db.add_user(987654321, "0x5678...", 123456789)
    
    # Record deposits
    await db.record_deposit(123456789, 1000.0, "0xabcd...")
    await db.record_deposit(987654321, 500.0, "0xefgh...")
    
    # Record trades
    await db.record_trade("ETH", "buy", 0.5, 3000, 15.0, -0.03, "maker_rebate")
    await db.record_trade("BTC", "sell", 0.01, 65000, 25.0, 0.23, "taker_fee")
    
    # Update daily stats
    await db.update_daily_stats("0xVault...", 1600.0, 40.0, 125000.0)
    
    # Test all functionality
    print("=== User Stats ===")
    user_stats = await db.get_user_stats(123456789)
    print(json.dumps(user_stats, indent=2, default=str))
    
    print("\n=== Vault Stats ===")
    vault_stats = await db.get_vault_stats()
    print(json.dumps(vault_stats, indent=2, default=str))
    
    print("\n=== Referral Stats ===")
    referral_stats = await db.get_referral_stats(123456789)
    print(json.dumps(referral_stats, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(test_database())
