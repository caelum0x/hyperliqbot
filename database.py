"""
SQLite database module for tracking users and profits
Production-ready database with proper schema and indexing
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from decimal import Decimal
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
import json
import os
import aiosqlite
import logging
import asyncio

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_file: str = "bot_data.db"):
        self.db_file = db_file
        self.conn = None
        self._connection_lock = asyncio.Lock()
        self.encryption_key = None
        
        # Ensure db directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_file)), exist_ok=True)
        
        # Version tracking for schema migrations
        self.current_version = "0.2.0"
        
    def _generate_encryption_key(self) -> bytes:
        """Generate encryption key from environment or create a new one"""
        env_key = os.environ.get("BOT_ENCRYPTION_KEY")
        if env_key:
            # Use environment variable if available
            try:
                return base64.urlsafe_b64decode(env_key)
            except Exception as e:
                logger.error(f"Invalid encryption key format in environment: {e}")
        
        # Create a salt and derive a key
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        # Use a default passphrase if not provided
        passphrase = os.urandom(16)  # Random passphrase
        key = base64.urlsafe_b64encode(kdf.derive(passphrase))
        
        # Save the key for future use
        key_file = "encryption_key.bin"
        with open(key_file, "wb") as f:
            f.write(key)
        
        logger.info(f"Generated new encryption key and saved to {key_file}")
        return key
    
    async def _init_database(self):
        """Initialize the database schema"""
        async with self._connection_lock:
            if self.conn is None:
                import aiosqlite
                self.conn = await aiosqlite.connect(self.db_file)
                self.conn.row_factory = aiosqlite.Row
            
            # Generate encryption key if not already available
            if self.encryption_key is None:
                self.encryption_key = self._generate_encryption_key()
            
            # Create tables
            async with self.conn.cursor() as cursor:
                # Schema version tracking
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schema_version (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        version TEXT NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description TEXT
                    )
                ''')
                
                # Users table with agent wallet columns
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER UNIQUE NOT NULL,
                        telegram_username TEXT,
                        hyperliquid_main_address TEXT,
                        agent_wallet_address TEXT,
                        agent_private_key TEXT,
                        status TEXT DEFAULT 'unregistered',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        wallet_balance REAL DEFAULT 0.0,
                        referrer_id INTEGER
                    )
                ''')
                
                # Approvals for tracking agent wallet approvals
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS approvals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        approval_type TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMP,
                        processed_by INTEGER,
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (processed_by) REFERENCES users(id)
                    )
                ''')
                
                # Wallet operations for tracking deposits, withdrawals, etc.
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS wallet_operations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        operation_type TEXT NOT NULL,
                        amount REAL,
                        status TEXT DEFAULT 'pending',
                        tx_hash TEXT,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                ''')
                
                # User strategies
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_strategies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        strategy_name TEXT NOT NULL,
                        status TEXT DEFAULT 'inactive',
                        config TEXT,
                        performance TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_run TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        UNIQUE(user_id, strategy_name)
                    )
                ''')
                
                # User trades
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        strategy_id INTEGER,
                        coin TEXT NOT NULL,
                        side TEXT NOT NULL,
                        size REAL NOT NULL,
                        price REAL NOT NULL,
                        pnl REAL,
                        fee REAL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        tx_hash TEXT,
                        metadata TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(id),
                        FOREIGN KEY (strategy_id) REFERENCES user_strategies(id)
                    )
                ''')
                
                # Check for existing schema version
                await cursor.execute("SELECT COUNT(*) FROM schema_version")
                has_version = await cursor.fetchone()
                if not has_version or has_version[0] == 0:
                    # Insert initial version
                    await cursor.execute(
                        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                        (self.current_version, f"Initial schema creation at {datetime.now().isoformat()}")
                    )
                
                # Add indexes for performance
                await cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
                await cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_agent_wallet ON users(agent_wallet_address)")
                await cursor.execute("CREATE INDEX IF NOT EXISTS idx_approvals_user_id ON approvals(user_id)")
                await cursor.execute("CREATE INDEX IF NOT EXISTS idx_wallet_operations_user_id ON wallet_operations(user_id)")
                
            await self.conn.commit()
            
            # Check for necessary columns in users table
            await self._ensure_columns_exist()
    
    async def _ensure_columns_exist(self):
        """Ensure all required columns exist in the users table"""
        async with self.conn.cursor() as cursor:
            # Check columns in users table
            await cursor.execute("PRAGMA table_info(users)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Add missing columns
            columns_to_check = {
                "agent_wallet_address": "TEXT",
                "agent_private_key": "TEXT",
                "wallet_balance": "REAL DEFAULT 0.0"
            }
            
            for column_name, column_type in columns_to_check.items():
                if column_name not in column_names:
                    try:
                        await cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                        logger.info(f"Added missing column {column_name} to users table")
                    except Exception as e:
                        logger.error(f"Error adding column {column_name}: {e}")
            
            await self.conn.commit()
    
    async def initialize(self):
        """Initialize the database and perform any needed migrations"""
        await self._init_database()
        await self._check_migrations()
    
    async def _check_migrations(self):
        """Check if any schema migrations are needed"""
        async with self.conn.cursor() as cursor:
            try:
                # ✅ DATABASE FIX: Create schema_version table with proper structure
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS schema_version (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description TEXT NOT NULL DEFAULT ''
                    )
                ''')
                
                # Check current version
                await cursor.execute("SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1")
                result = await cursor.fetchone()
                current_version = result[0] if result else "0.0.0"
                
                # Apply migrations if needed
                if self._compare_versions(current_version, self.current_version) < 0:
                    logger.info(f"Applying database migrations from {current_version} to {self.current_version}")
                    
                    # Apply version-specific migrations
                    if self._compare_versions(current_version, "0.1.0") < 0:
                        await self._migration_0_1_0()
                        await cursor.execute(
                            "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
                            ("0.1.0", "Initial schema with user tables")
                        )
                    
                    if self._compare_versions(current_version, "0.2.0") < 0:
                        await self._migration_0_2_0()
                        await cursor.execute(
                            "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
                            ("0.2.0", "Added agent wallet support and enhanced security")
                        )
                    
                    # Update to current version
                    await cursor.execute(
                        "INSERT OR REPLACE INTO schema_version (version, description) VALUES (?, ?)",
                        (self.current_version, "Current production version")
                    )
                    await self.conn.commit()
                    
                    logger.info(f"Database migrated to version {self.current_version}")
                    
            except Exception as e:
                logger.error(f"Migration error: {e}")
                # Don't raise - allow bot to continue with existing schema

    async def _migration_0_1_0(self):
        """Migration to version 0.1.0 - Initial schema"""
        async with self.conn.cursor() as cursor:
            # Add any schema changes for 0.1.0
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS migration_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            ''')
        await self.conn.commit()
    
    async def _migration_0_2_0(self):
        """Migration to version 0.2.0 - Agent wallet enhancements"""
        async with self.conn.cursor() as cursor:
            # Add security audit table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS security_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    user_id INTEGER,
                    description TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Add rate limiting table
            await cursor.execute('''
                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id INTEGER NOT NULL,
                    command TEXT NOT NULL,
                    count INTEGER DEFAULT 1,
                    window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, command)
                )
            ''')
            
        await self.conn.commit()
    
    async def execute(self, query: str, parameters: tuple = ()) -> List[Dict]:
        """Execute a query and return results as a list of dictionaries"""
        if self.conn is None:
            await self._init_database()
            
        async with self.conn.execute(query, parameters) as cursor:
            columns = [column[0] for column in cursor.description] if cursor.description else []
            result = await cursor.fetchall()
            
            # Convert rows to dictionaries
            return [dict(zip(columns, row)) for row in result]
    
    def encrypt_private_key(self, private_key: str) -> str:
        """Encrypt a private key using Fernet symmetric encryption"""
        if not private_key:
            return ""
            
        if not private_key.startswith("0x"):
            private_key = f"0x{private_key}"
            
        if not self.encryption_key:
            self.encryption_key = self._generate_encryption_key()
            
        f = Fernet(self.encryption_key)
        encrypted_key = f.encrypt(private_key.encode())
        return encrypted_key.decode()
    
    def decrypt_private_key(self, encrypted_key: str) -> str:
        """Decrypt an encrypted private key"""
        if not encrypted_key:
            return ""
            
        if not self.encryption_key:
            self.encryption_key = self._generate_encryption_key()
            
        f = Fernet(self.encryption_key)
        decrypted_key = f.decrypt(encrypted_key.encode())
        return decrypted_key.decode()
    
    async def add_user(self, telegram_id: int, telegram_username: str = None, 
                       referrer_id: int = None) -> Dict:
        """
        Add a new user to the database
        Returns the user record
        """
        if self.conn is None:
            await self._init_database()
            
        # Check if user already exists
        async with self.conn.cursor() as cursor:
            await cursor.execute(
                "SELECT id FROM users WHERE telegram_id = ?", 
                (telegram_id,)
            )
            existing_user = await cursor.fetchone()
            
            if existing_user:
                # User exists, just update last_active
                await cursor.execute(
                    "UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                    (telegram_id,)
                )
                await self.conn.commit()
                
                # Return user data
                await cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
                user_data = await cursor.fetchone()
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, user_data))
                
            # Create new user
            current_time = datetime.now().isoformat()
            await cursor.execute(
                """
                INSERT INTO users (
                    telegram_id, telegram_username, status, 
                    created_at, last_active, referrer_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (telegram_id, telegram_username, "unregistered", 
                 current_time, current_time, referrer_id)
            )
            await self.conn.commit()
            
            # Get user ID
            await cursor.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            user_data = await cursor.fetchone()
            columns = [column[0] for column in cursor.description]
            
            return dict(zip(columns, user_data))
    
    async def add_agent_wallet(self, telegram_id: int, agent_address: str,
                             main_address: str, private_key: str) -> Dict:
        """
        Add agent wallet to user
        Encrypts the private key before storage
        """
        if self.conn is None:
            await self._init_database()
            
        # Encrypt private key
        encrypted_key = self.encrypt_private_key(private_key)
        
        async with self.conn.cursor() as cursor:
            # Update user with agent wallet info
            await cursor.execute(
                """
                UPDATE users SET
                    hyperliquid_main_address = ?,
                    agent_wallet_address = ?,
                    agent_private_key = ?,
                    status = ?,
                    last_active = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (main_address, agent_address, encrypted_key, "pending_approval", telegram_id)
            )
            
            # Create approval record
            await cursor.execute(
                """
                INSERT INTO approvals (
                    user_id, approval_type, status, metadata
                ) VALUES (
                    (SELECT id FROM users WHERE telegram_id = ?),
                    'agent_wallet', 'pending', ?
                )
                """,
                (telegram_id, json.dumps({
                    "agent_address": agent_address,
                    "main_address": main_address,
                    "created_at": datetime.now().isoformat()
                }))
            )
            
            await self.conn.commit()
            
            # Return updated user data
            await cursor.execute(
                """
                SELECT id, telegram_id, hyperliquid_main_address, 
                       agent_wallet_address, status
                FROM users WHERE telegram_id = ?
                """, 
                (telegram_id,)
            )
            user_data = await cursor.fetchone()
            if user_data:
                columns = [column[0] for column in cursor.description]
                return dict(zip(columns, user_data))
            return {}
    
    async def get_agent_wallet(self, telegram_id: int, agent_address: str = None) -> Optional[Dict]:
        """
        Get agent wallet details for a user
        If agent_address is provided, it also validates the address matches
        """
        if self.conn is None:
            await self._init_database()
            
        async with self.conn.cursor() as cursor:
            query = """
                SELECT id, telegram_id, hyperliquid_main_address,
                       agent_wallet_address, agent_private_key, status,
                       created_at, last_active, wallet_balance
                FROM users
                WHERE telegram_id = ?
            """
            params = [telegram_id]
            
            if agent_address:
                query += " AND agent_wallet_address = ?"
                params.append(agent_address)
                
            await cursor.execute(query, params)
            result = await cursor.fetchone()
            
            if result:
                columns = [column[0] for column in cursor.description]
                wallet_data = dict(zip(columns, result))
                
                # Don't return the encrypted key directly
                wallet_data["has_private_key"] = bool(wallet_data.get("agent_private_key"))
                del wallet_data["agent_private_key"]
                
                return wallet_data
                
            return None
    
    async def get_agent_private_key(self, telegram_id: int, agent_address: str, 
                                  access_reason: str = "api_call",
                                  access_ip: str = None) -> Optional[str]:
        """
        Get decrypted private key for a user's agent wallet
        Logs access for security and limits access to verified requests
        """
        if self.conn is None:
            await self._init_database()
            
        async with self.conn.cursor() as cursor:
            # Get encrypted private key
            await cursor.execute(
                """
                SELECT agent_private_key, status
                FROM users
                WHERE telegram_id = ? AND agent_wallet_address = ?
                """,
                (telegram_id, agent_address)
            )
            result = await cursor.fetchone()
            
            if not result or not result[0]:
                return None
                
            encrypted_key, status = result
            
            # Only approved or trading status can access private keys
            if status not in ("approved", "funded", "trading"):
                logger.warning(f"Attempted key access for unapproved agent: {agent_address}")
                return None
                
            # Log access
            await cursor.execute(
                """
                INSERT INTO wallet_operations (
                    user_id, operation_type, status, metadata
                ) VALUES (
                    (SELECT id FROM users WHERE telegram_id = ?),
                    'key_access', 'completed', ?
                )
                """,
                (
                    telegram_id, 
                    json.dumps({
                        "reason": access_reason,
                        "ip": access_ip,
                        "timestamp": datetime.now().isoformat()
                    })
                )
            )
            await self.conn.commit()
            
            # Decrypt and return
            return self.decrypt_private_key(encrypted_key)
    
    async def update_agent_wallet_status(self, telegram_id: int, agent_address: str,
                                       status: str, approved: bool = False) -> bool:
        """Update agent wallet status"""
        if self.conn is None:
            await self._init_database()
            
        valid_statuses = ["pending_approval", "approved", "funded", "trading"]
        if status not in valid_statuses:
            return False
            
        async with self.conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE users SET
                    status = ?,
                    last_active = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND agent_wallet_address = ?
                """,
                (status, telegram_id, agent_address)
            )
            
            if approved:
                # Update approval status
                await cursor.execute(
                    """
                    UPDATE approvals SET
                        status = 'approved',
                        processed_at = CURRENT_TIMESTAMP
                    WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?)
                    AND approval_type = 'agent_wallet'
                    AND status = 'pending'
                    """,
                    (telegram_id,)
                )
                
            await self.conn.commit()
            return True
    
    async def enable_agent_wallet_trading(self, telegram_id: int, agent_address: str,
                                        enable: bool = True) -> bool:
        """Enable or disable trading for an agent wallet"""
        if self.conn is None:
            await self._init_database()
            
        status = "trading" if enable else "funded"
        
        async with self.conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE users SET
                    status = ?,
                    last_active = CURRENT_TIMESTAMP
                WHERE telegram_id = ? AND agent_wallet_address = ?
                AND status IN ('funded', 'trading')
                """,
                (status, telegram_id, agent_address)
            )
            
            changed = cursor.rowcount > 0
            await self.conn.commit()
            return changed
    
    async def update_wallet_balance(self, telegram_id: int, balance: float) -> bool:
        """Update user's wallet balance"""
        if self.conn is None:
            await self._init_database()
            
        async with self.conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE users SET
                    wallet_balance = ?,
                    last_active = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
                """,
                (balance, telegram_id)
            )
            
            changed = cursor.rowcount > 0
            await self.conn.commit()
            return changed
            
    async def register_user_strategy(self, telegram_id: int, strategy_name: str, 
                                   config: Dict) -> Dict:
        """Register a strategy for a user"""
        if self.conn is None:
            await self._init_database()
            
        async with self.conn.cursor() as cursor:
            # Get user ID
            await cursor.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            user = await cursor.fetchone()
            
            if not user:
                return {"status": "error", "message": "User not found"}
                
            user_id = user[0]
            
            # Check if strategy already exists
            await cursor.execute(
                """
                SELECT id FROM user_strategies 
                WHERE user_id = ? AND strategy_name = ?
                """,
                (user_id, strategy_name)
            )
            
            existing = await cursor.fetchone()
            
            if existing:
                # Update existing strategy
                await cursor.execute(
                    """
                    UPDATE user_strategies SET
                        config = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(config), existing[0])
                )
                strategy_id = existing[0]
            else:
                # Create new strategy
                await cursor.execute(
                    """
                    INSERT INTO user_strategies (
                        user_id, strategy_name, config, status,
                        performance, created_at, updated_at
                    ) VALUES (?, ?, ?, 'paused', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        user_id, strategy_name, json.dumps(config),
                        json.dumps({"total_pnl": 0, "win_rate": 0, "trades": 0})
                    )
                )
                strategy_id = cursor.lastrowid
                
            await self.conn.commit()
            
            return {
                "status": "success",
                "strategy_id": strategy_id,
                "message": "Strategy registered successfully"
            }
    
    async def record_trade(self, telegram_id: int, strategy: str, trade_data: Dict) -> Dict:
        """Record a trade for a user"""
        if self.conn is None:
            await self._init_database()
            
        required_fields = ["coin", "side", "size", "price", "timestamp"]
        for field in required_fields:
            if field not in trade_data:
                return {"status": "error", "message": f"Missing required field: {field}"}
                
        async with self.conn.cursor() as cursor:
            # Get user ID
            await cursor.execute(
                "SELECT id FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            user = await cursor.fetchone()
            
            if not user:
                return {"status": "error", "message": "User not found"}
                
            user_id = user[0]
            
            # Record trade
            await cursor.execute(
                """
                INSERT INTO user_trades (
                    user_id, strategy, coin, side, size, price,
                    timestamp, pnl, tx_hash, fee, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, strategy,
                    trade_data["coin"],
                    trade_data["side"],
                    trade_data["size"],
                    trade_data["price"],
                    trade_data["timestamp"],
                    trade_data.get("pnl", 0),
                    trade_data.get("tx_hash", ""),
                    trade_data.get("fee", 0),
                    json.dumps(trade_data.get("metadata", {}))
                )
            )
            
            trade_id = cursor.lastrowid
            await self.conn.commit()
            
            return {
                "status": "success",
                "trade_id": trade_id,
                "message": "Trade recorded successfully"
            }
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            self.conn = None

# Singleton instance
bot_db = Database()

# Utility functions for backward compatibility
async def get_user_stats(telegram_id: int) -> Optional[Dict]:
    """Get user statistics (for backward compatibility)"""
    if not bot_db.conn:
        await bot_db.initialize()
        
    async with bot_db.conn.cursor() as cursor:
        await cursor.execute(
            """
            SELECT u.*, 
                   COUNT(ut.id) as total_trades,
                   SUM(CASE WHEN ut.pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                   SUM(CASE WHEN ut.pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                   SUM(ut.pnl) as total_pnl
            FROM users u
            LEFT JOIN user_trades ut ON u.id = ut.user_id
            WHERE u.telegram_id = ?
            GROUP BY u.id
            """,
            (telegram_id,)
        )
        
        result = await cursor.fetchone()
        
        if result:
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, result))
            
        return None

async def record_user_deposit(telegram_id: int, amount: float, tx_hash: str = None) -> Dict:
    """Record a user deposit (for backward compatibility)"""
    if not bot_db.conn:
        await bot_db.initialize()
        
    async with bot_db.conn.cursor() as cursor:
        # Get user ID
        await cursor.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        user = await cursor.fetchone()
        
        if not user:
            return {"status": "error", "message": "User not found"}
            
        user_id = user[0]
        
        # Record deposit
        await cursor.execute(
            """
            INSERT INTO wallet_operations (
                user_id, operation_type, amount, status, tx_hash
            ) VALUES (?, 'deposit', ?, 'confirmed', ?)
            """,
            (user_id, amount, tx_hash)
        )
        
        # Update user status to funded if appropriate
        await cursor.execute(
            """
            UPDATE users SET
                status = CASE 
                    WHEN status IN ('approved', 'pending_approval') THEN 'funded'
                    ELSE status
                END,
                wallet_balance = wallet_balance + ?,
                last_active = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (amount, user_id)
        )
        
        await bot_db.conn.commit()
        
        return {
            "status": "success",
            "message": "Deposit recorded successfully",
            "amount": amount
        }

async def get_vault_performance() -> Dict:
    """Get vault performance metrics (for backward compatibility)"""
    # Legacy function - implement if needed
    return {
        "tvl": 0,
        "daily_return": 0,
        "weekly_return": 0,
        "monthly_return": 0,
        "total_return": 0
    }

# Testing
async def test_database():
    """Test database functionality"""
    db = Database(":memory:")
    await db.initialize()
    
    # Test user creation
    user = await db.add_user(12345, "testuser")
    assert user["telegram_id"] == 12345
    
    # Test agent wallet
    wallet = await db.add_agent_wallet(
        12345,
        "0x1234567890123456789012345678901234567890",
        "0x0987654321098765432109876543210987654321",
        "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    )
    assert wallet["agent_wallet_address"] == "0x1234567890123456789012345678901234567890"
    
    # Test getting wallet
    get_wallet = await db.get_agent_wallet(12345)
    assert get_wallet["agent_wallet_address"] == "0x1234567890123456789012345678901234567890"
    
    # Test strategy registration
    strategy = await db.register_user_strategy(12345, "grid", {"param1": "value1"})
    assert strategy["status"] == "success"
    
    # Test trade recording
    trade = await db.record_trade(
        12345,
        "grid",
        {
            "coin": "BTC",
            "side": "buy",
            "size": 0.1,
            "price": 50000,
            "timestamp": datetime.now().isoformat()
        }
    )
    assert trade["status"] == "success"
    
    print("All database tests passed!")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_database())
