"""
Audit logging for security and compliance
"""
import asyncio
import json
import logging
import time
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import aiosqlite
from pathlib import Path

logger = logging.getLogger(__name__)

class AuditLogger:
    """Enhanced audit logging for security and compliance"""
    
    def __init__(self, db_path: str = "audit.db", log_file: str = "audit.log"):
        self.db_path = db_path
        self.log_file = log_file
        self.db_initialized = False
        self._setup_lock = asyncio.Lock()
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        
        # Set up file logger
        self.file_logger = logging.getLogger("audit")
        handler = logging.FileHandler(log_file, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.file_logger.addHandler(handler)
        self.file_logger.setLevel(logging.INFO)
    
    async def initialize(self) -> None:
        """Initialize audit database"""
        async with self._setup_lock:
            if self.db_initialized:
                return
                
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    # User actions table
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS user_actions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            username TEXT,
                            action TEXT NOT NULL,
                            category TEXT NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            success BOOLEAN NOT NULL,
                            details TEXT,
                            error_message TEXT,
                            ip_address TEXT
                        )
                    ''')
                    
                    # Security events table
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS security_events (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            event_type TEXT NOT NULL,
                            severity TEXT NOT NULL,
                            description TEXT NOT NULL,
                            user_id INTEGER,
                            username TEXT,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            details TEXT,
                            resolved BOOLEAN DEFAULT FALSE
                        )
                    ''')
                    
                    # Admin actions table
                    await db.execute('''
                        CREATE TABLE IF NOT EXISTS admin_actions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            admin_user_id INTEGER NOT NULL,
                            admin_username TEXT NOT NULL,
                            action TEXT NOT NULL,
                            target_user_id INTEGER,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            details TEXT,
                            result TEXT
                        )
                    ''')
                    
                    await db.commit()
                
                self.db_initialized = True
                logger.info("Audit logging initialized")
                
            except Exception as e:
                logger.error(f"Error initializing audit database: {e}")
                raise
    
    async def log_user_action(self, user_id: int, username: str, action: str, 
                            category: str, success: bool, details: Dict[str, Any] = None,
                            error_message: str = None, ip_address: str = None) -> None:
        """Log user action for audit trail"""
        if not self.db_initialized:
            await self.initialize()
            
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO user_actions 
                    (user_id, username, action, category, success, details, error_message, ip_address)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id, username, action, category, success,
                    json.dumps(details) if details else None,
                    error_message, ip_address
                ))
                await db.commit()
        except Exception as e:
            logger.error(f"Error logging user action: {e}")
    
    async def log_security_event(self, event_type: str, severity: str, description: str,
                               user_id: int = None, username: str = None,
                               details: Dict[str, Any] = None) -> None:
        """Log security event"""
        if not self.db_initialized:
            await self.initialize()
            
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO security_events 
                    (event_type, severity, description, user_id, username, details)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    event_type, severity, description, user_id, username,
                    json.dumps(details) if details else None
                ))
                await db.commit()
        except Exception as e:
            logger.error(f"Error logging security event: {e}")
    
    async def log_admin_action(self, admin_user_id: int, admin_username: str,
                             action: str, target_user_id: int = None,
                             details: Dict[str, Any] = None, result: str = None) -> None:
        """Log admin action"""
        if not self.db_initialized:
            await self.initialize()
            
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO admin_actions 
                    (admin_user_id, admin_username, action, target_user_id, details, result)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    admin_user_id, admin_username, action, target_user_id,
                    json.dumps(details) if details else None, result
                ))
                await db.commit()
        except Exception as e:
            logger.error(f"Error logging admin action: {e}")

# Global instance
audit_logger = AuditLogger()
