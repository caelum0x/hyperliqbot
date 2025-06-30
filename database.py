"""
SQLite database module for tracking users and profits
Production-ready database with proper schema and indexing
"""
import sqlite3
import asyncio
import aiosqlite
import json
import time
import logging
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "hyperliquid_bot.db"):
        self.db_path = db_path
        self.conn = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """MISSING METHOD - Initialize database connection and create tables"""
        try:
            self.conn = await aiosqlite.connect(self.db_path)
            await self.conn.execute("PRAGMA foreign_keys = ON")
            await self._create_tables()
            self._initialized = True
            logger.info(f"✅ Database initialized: {self.db_path}")
            return True
        except Exception as e:
            logger.error(f"❌ Database initialization failed: {e}")
            return False
    
    async def execute(self, query: str, params: tuple = ()) -> Optional[aiosqlite.Cursor]:
        """MISSING METHOD - Execute SQL query with parameters"""
        try:
            if not self.conn:
                await self.initialize()
            
            cursor = await self.conn.execute(query, params)
            await self.conn.commit()
            return cursor
        except Exception as e:
            logger.error(f"Database execute error: {e}")
            return None
    
    async def fetchone(self, query: str, params: tuple = ()) -> Optional[tuple]:
        """Fetch single row"""
        try:
            cursor = await self.execute(query, params)
            if cursor:
                return await cursor.fetchone()
            return None
        except Exception as e:
            logger.error(f"Database fetchone error: {e}")
            return None
    
    async def fetchall(self, query: str, params: tuple = ()) -> List[tuple]:
        """Fetch all rows"""
        try:
            cursor = await self.execute(query, params)
            if cursor:
                return await cursor.fetchall()
            return []
        except Exception as e:
            logger.error(f"Database fetchall error: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Health check method for main.py"""
        try:
            cursor = await self.execute("SELECT 1")
            return cursor is not None
        except:
            return False
    
    async def _create_tables(self):
        """Create all necessary tables"""
        tables = [
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                hyperliquid_address TEXT,
                agent_wallet_address TEXT,
                agent_private_key TEXT,
                status TEXT DEFAULT 'unregistered',
                config TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            
            """CREATE TABLE IF NOT EXISTS user_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                strategy TEXT NOT NULL,
                coin TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                price REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pnl REAL DEFAULT 0,
                order_id TEXT,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )""",
            
            """CREATE TABLE IF NOT EXISTS trading_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                total_pnl REAL DEFAULT 0,
                volume_usd REAL DEFAULT 0,
                trades_count INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0,
                account_value REAL DEFAULT 0,
                strategy TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )""",
            
            """CREATE TABLE IF NOT EXISTS hyperevm_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                protocol_name TEXT NOT NULL,
                amount_usd REAL DEFAULT 0,
                transaction_hash TEXT,
                points_earned REAL DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'completed',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )""",
            
            """CREATE TABLE IF NOT EXISTS vault_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                vault_address TEXT NOT NULL,
                deposit_amount REAL NOT NULL,
                deposit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                withdrawal_amount REAL DEFAULT 0,
                withdrawal_time TIMESTAMP,
                current_balance REAL NOT NULL,
                profit_share REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                FOREIGN KEY (user_id) REFERENCES users (id)
            )""",
            
            """CREATE TABLE IF NOT EXISTS referral_commissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referee_id INTEGER NOT NULL,
                commission_amount REAL NOT NULL,
                volume_generated REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (referrer_id) REFERENCES users (id),
                FOREIGN KEY (referee_id) REFERENCES users (id)
            )"""
        ]
        
        for table_sql in tables:
            await self.execute(table_sql)
    
    # USER MANAGEMENT METHODS
    async def create_user(self, telegram_id: int, hyperliquid_address: str = None) -> Optional[int]:
        """Create new user and return user ID"""
        try:
            cursor = await self.execute(
                "INSERT INTO users (telegram_id, hyperliquid_address) VALUES (?, ?)",
                (telegram_id, hyperliquid_address)
            )
            return cursor.lastrowid if cursor else None
        except Exception as e:
            logger.error(f"Create user error: {e}")
            return None
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict]:
        """Get user by Telegram ID"""
        try:
            row = await self.fetchone(
                "SELECT * FROM users WHERE telegram_id = ?", 
                (telegram_id,)
            )
            if row:
                return {
                    'id': row[0],
                    'telegram_id': row[1],
                    'hyperliquid_address': row[2],
                    'agent_wallet_address': row[3],
                    'agent_private_key': row[4],
                    'status': row[5],
                    'config': json.loads(row[6]) if row[6] else {},
                    'created_at': row[7],
                    'last_active': row[8]
                }
            return None
        except Exception as e:
            logger.error(f"Get user error: {e}")
            return None
    
    async def update_user_status(self, user_id: int, status: str) -> bool:
        """Update user status"""
        try:
            cursor = await self.execute(
                "UPDATE users SET status = ?, last_active = CURRENT_TIMESTAMP WHERE id = ?",
                (status, user_id)
            )
            return cursor is not None
        except Exception as e:
            logger.error(f"Update user status error: {e}")
            return False
    
    async def update_user_agent_wallet(self, user_id: int, agent_address: str, agent_private_key: str) -> bool:
        """Update user's agent wallet info"""
        try:
            cursor = await self.execute(
                "UPDATE users SET agent_wallet_address = ?, agent_private_key = ? WHERE id = ?",
                (agent_address, agent_private_key, user_id)
            )
            return cursor is not None
        except Exception as e:
            logger.error(f"Update agent wallet error: {e}")
            return False
    
    # TRADING METHODS
    async def log_trade(self, user_id: int, strategy: str, coin: str, side: str, 
                       size: float, price: float, order_id: str = None) -> bool:
        """Log a trade to database"""
        try:
            cursor = await self.execute(
                """INSERT INTO user_trades 
                   (user_id, strategy, coin, side, size, price, order_id) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, strategy, coin, side, size, price, order_id)
            )
            return cursor is not None
        except Exception as e:
            logger.error(f"Log trade error: {e}")
            return False
    
    async def get_user_trades(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get user's recent trades"""
        try:
            rows = await self.fetchall(
                """SELECT * FROM user_trades 
                   WHERE user_id = ? 
                   ORDER BY timestamp DESC 
                   LIMIT ?""",
                (user_id, limit)
            )
            
            trades = []
            for row in rows:
                trades.append({
                    'id': row[0],
                    'strategy': row[2],
                    'coin': row[3],
                    'side': row[4],
                    'size': row[5],
                    'price': row[6],
                    'timestamp': row[7],
                    'pnl': row[8],
                    'order_id': row[9],
                    'status': row[10]
                })
            return trades
        except Exception as e:
            logger.error(f"Get user trades error: {e}")
            return []
    
    async def update_trade_pnl(self, trade_id: int, pnl: float) -> bool:
        """Update trade PnL"""
        try:
            cursor = await self.execute(
                "UPDATE user_trades SET pnl = ? WHERE id = ?",
                (pnl, trade_id)
            )
            return cursor is not None
        except Exception as e:
            logger.error(f"Update trade PnL error: {e}")
            return False
    
    # HYPEREVM ACTIVITY TRACKING
    async def log_hyperevm_activity(self, user_id: int, activity_type: str, 
                                   protocol_name: str, amount_usd: float = 0,
                                   transaction_hash: str = None, points_earned: float = 0) -> bool:
        """Log HyperEVM activity for airdrop tracking"""
        try:
            cursor = await self.execute(
                """INSERT INTO hyperevm_activity 
                   (user_id, activity_type, protocol_name, amount_usd, transaction_hash, points_earned) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, activity_type, protocol_name, amount_usd, transaction_hash, points_earned)
            )
            return cursor is not None
        except Exception as e:
            logger.error(f"Log HyperEVM activity error: {e}")
            return False
    
    async def get_user_hyperevm_stats(self, user_id: int) -> Dict:
        """Get user's HyperEVM activity stats"""
        try:
            # Total transactions
            total_tx = await self.fetchone(
                "SELECT COUNT(*) FROM hyperevm_activity WHERE user_id = ?",
                (user_id,)
            )
            
            # Total volume
            total_volume = await self.fetchone(
                "SELECT SUM(amount_usd) FROM hyperevm_activity WHERE user_id = ?",
                (user_id,)
            )
            
            # Total points
            total_points = await self.fetchone(
                "SELECT SUM(points_earned) FROM hyperevm_activity WHERE user_id = ?",
                (user_id,)
            )
            
            # Unique protocols
            unique_protocols = await self.fetchone(
                "SELECT COUNT(DISTINCT protocol_name) FROM hyperevm_activity WHERE user_id = ?",
                (user_id,)
            )
            
            return {
                'total_transactions': total_tx[0] if total_tx else 0,
                'total_volume_usd': total_volume[0] if total_volume and total_volume[0] else 0,
                'total_points': total_points[0] if total_points and total_points[0] else 0,
                'unique_protocols': unique_protocols[0] if unique_protocols else 0
            }
        except Exception as e:
            logger.error(f"Get HyperEVM stats error: {e}")
            return {'total_transactions': 0, 'total_volume_usd': 0, 'total_points': 0, 'unique_protocols': 0}
    
    # PERFORMANCE TRACKING
    async def update_daily_performance(self, user_id: int, date: str, total_pnl: float, 
                                     volume_usd: float, trades_count: int, account_value: float,
                                     strategy: str = None) -> bool:
        """Update daily performance metrics"""
        try:
            # Check if record exists
            existing = await self.fetchone(
                "SELECT id FROM trading_performance WHERE user_id = ? AND date = ?",
                (user_id, date)
            )
            
            if existing:
                # Update existing record
                cursor = await self.execute(
                    """UPDATE trading_performance 
                       SET total_pnl = ?, volume_usd = ?, trades_count = ?, account_value = ?, strategy = ?
                       WHERE user_id = ? AND date = ?""",
                    (total_pnl, volume_usd, trades_count, account_value, strategy, user_id, date)
                )
            else:
                # Insert new record
                cursor = await self.execute(
                    """INSERT INTO trading_performance 
                       (user_id, date, total_pnl, volume_usd, trades_count, account_value, strategy)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, date, total_pnl, volume_usd, trades_count, account_value, strategy)
                )
            
            return cursor is not None
        except Exception as e:
            logger.error(f"Update daily performance error: {e}")
            return False
    
    async def get_user_performance_summary(self, user_id: int, days: int = 30) -> Dict:
        """Get user performance summary for last N days"""
        try:
            rows = await self.fetchall(
                """SELECT date, total_pnl, volume_usd, trades_count, account_value 
                   FROM trading_performance 
                   WHERE user_id = ? 
                   ORDER BY date DESC 
                   LIMIT ?""",
                (user_id, days)
            )
            
            if not rows:
                return {'total_pnl': 0, 'total_volume': 0, 'total_trades': 0, 'current_value': 0, 'daily_data': []}
            
            total_pnl = sum(row[1] for row in rows if row[1])
            total_volume = sum(row[2] for row in rows if row[2])
            total_trades = sum(row[3] for row in rows if row[3])
            current_value = rows[0][4] if rows[0][4] else 0
            
            daily_data = []
            for row in rows:
                daily_data.append({
                    'date': row[0],
                    'pnl': row[1] or 0,
                    'volume': row[2] or 0,
                    'trades': row[3] or 0,
                    'account_value': row[4] or 0
                })
            
            return {
                'total_pnl': total_pnl,
                'total_volume': total_volume,
                'total_trades': total_trades,
                'current_value': current_value,
                'daily_data': daily_data
            }
        except Exception as e:
            logger.error(f"Get performance summary error: {e}")
            return {'total_pnl': 0, 'total_volume': 0, 'total_trades': 0, 'current_value': 0, 'daily_data': []}
    
    # VAULT MANAGEMENT
    async def add_vault_user(self, user_id: int, vault_address: str, deposit_amount: float) -> bool:
        """Add user to vault"""
        try:
            cursor = await self.execute(
                """INSERT INTO vault_users 
                   (user_id, vault_address, deposit_amount, current_balance) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, vault_address, deposit_amount, deposit_amount)
            )
            return cursor is not None
        except Exception as e:
            logger.error(f"Add vault user error: {e}")
            return False
    
    async def get_vault_users(self, vault_address: str) -> List[Dict]:
        """Get all users in a vault"""
        try:
            rows = await self.fetchall(
                "SELECT * FROM vault_users WHERE vault_address = ? AND status = 'active'",
                (vault_address,)
            )
            
            users = []
            for row in rows:
                users.append({
                    'user_id': row[1],
                    'deposit_amount': row[3],
                    'deposit_time': row[4],
                    'current_balance': row[7],
                    'profit_share': row[8]
                })
            return users
        except Exception as e:
            logger.error(f"Get vault users error: {e}")
            return []
    
    # REFERRAL SYSTEM
    async def log_referral_commission(self, referrer_id: int, referee_id: int, 
                                    commission_amount: float, volume_generated: float) -> bool:
        """Log referral commission"""
        try:
            cursor = await self.execute(
                """INSERT INTO referral_commissions 
                   (referrer_id, referee_id, commission_amount, volume_generated) 
                   VALUES (?, ?, ?, ?)""",
                (referrer_id, referee_id, commission_amount, volume_generated)
            )
            return cursor is not None
        except Exception as e:
            logger.error(f"Log referral commission error: {e}")
            return False
    
    async def get_user_referral_stats(self, user_id: int) -> Dict:
        """Get user's referral statistics"""
        try:
            total_commission = await self.fetchone(
                "SELECT SUM(commission_amount) FROM referral_commissions WHERE referrer_id = ?",
                (user_id,)
            )
            
            total_volume = await self.fetchone(
                "SELECT SUM(volume_generated) FROM referral_commissions WHERE referrer_id = ?",
                (user_id,)
            )
            
            referee_count = await self.fetchone(
                "SELECT COUNT(DISTINCT referee_id) FROM referral_commissions WHERE referrer_id = ?",
                (user_id,)
            )
            
            return {
                'total_commission': total_commission[0] if total_commission and total_commission[0] else 0,
                'total_volume': total_volume[0] if total_volume and total_volume[0] else 0,
                'referee_count': referee_count[0] if referee_count else 0
            }
        except Exception as e:
            logger.error(f"Get referral stats error: {e}")
            return {'total_commission': 0, 'total_volume': 0, 'referee_count': 0}
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            logger.info("Database connection closed")

# Create global database instance
database = DatabaseManager()
