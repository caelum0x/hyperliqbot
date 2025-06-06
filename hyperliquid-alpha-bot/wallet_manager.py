"""
WALLET MANAGER - Handle user wallets and vault operations
"""

import json
import hashlib
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class WalletManager:
    def __init__(self, api):
        self.api = api
        self.connected_users = {}
        self.vault_deposits = {}
        
    async def connect_user(self, user_id: int, private_key: str) -> Dict:
        """Connect user's API wallet"""
        try:
            # Hash the private key for storage (in production, use proper encryption)
            key_hash = hashlib.sha256(private_key.encode()).hexdigest()
            
            # Connect through API
            result = await self.api.connect_user_wallet(user_id, private_key)
            
            if result['success']:
                # Store user connection
                self.connected_users[user_id] = {
                    'address': result['address'],
                    'balance': result['balance'],
                    'key_hash': key_hash,
                    'connected_at': self.api.info._get_timestamp() if hasattr(self.api.info, '_get_timestamp') else 0
                }
                
                logger.info(f"User {user_id} connected: {result['address']}")
                
                return {
                    'success': True,
                    'user_info': {
                        'address': result['address'],
                        'balance': result['balance']
                    }
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Error connecting user {user_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def is_user_connected(self, user_id: int) -> bool:
        """Check if user is connected"""
        return user_id in self.connected_users
    
    async def get_user_info(self, user_id: int) -> Dict:
        """Get user information"""
        try:
            if user_id not in self.connected_users:
                return {'error': 'User not connected'}
            
            # Get fresh info from API
            api_info = await self.api.get_user_info(user_id)
            
            if 'error' not in api_info:
                # Update stored balance
                self.connected_users[user_id]['balance'] = api_info['balance']
                return api_info
            else:
                # Fallback to stored info
                return self.connected_users[user_id]
                
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return {'error': str(e)}
    
    async def get_vault_info(self) -> Dict:
        """Get vault information"""
        try:
            vault_stats = await self.api.get_vault_stats()
            
            if 'error' in vault_stats:
                # Return mock vault info if no real vault
                return {
                    'total_value': 0,
                    'user_count': 0,
                    'daily_return': 0.0015,
                    'total_profit': 0,
                    'vault_address': 'NOT_CONFIGURED'
                }
            
            return vault_stats
            
        except Exception as e:
            logger.error(f"Error getting vault info: {e}")
            return {'error': str(e)}
    
    async def record_vault_deposit(self, user_id: int, amount: float, tx_hash: str = None) -> Dict:
        """Record user's vault deposit"""
        try:
            timestamp = 1704067200  # Mock timestamp
            
            if user_id not in self.vault_deposits:
                self.vault_deposits[user_id] = []
            
            deposit = {
                'amount': amount,
                'timestamp': timestamp,
                'tx_hash': tx_hash,
                'status': 'confirmed'
            }
            
            self.vault_deposits[user_id].append(deposit)
            
            logger.info(f"Recorded vault deposit for user {user_id}: ${amount}")
            
            return {'success': True, 'deposit': deposit}
            
        except Exception as e:
            logger.error(f"Error recording deposit: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_user_vault_stats(self, user_id: int) -> Dict:
        """Get user's vault statistics"""
        try:
            if user_id not in self.vault_deposits:
                return {
                    'total_deposited': 0,
                    'current_balance': 0,
                    'total_profit': 0,
                    'roi_pct': 0
                }
            
            deposits = self.vault_deposits[user_id]
            total_deposited = sum(d['amount'] for d in deposits)
            
            # Mock calculations
            current_balance = total_deposited * 1.05  # 5% growth
            total_profit = current_balance - total_deposited
            roi_pct = (total_profit / total_deposited * 100) if total_deposited > 0 else 0
            
            return {
                'total_deposited': total_deposited,
                'current_balance': current_balance,
                'total_profit': total_profit,
                'roi_pct': roi_pct
            }
            
        except Exception as e:
            logger.error(f"Error getting vault stats: {e}")
            return {'error': str(e)}
    
    async def calculate_profit_share(self, user_id: int, total_vault_profit: float) -> float:
        """Calculate user's share of vault profits"""
        try:
            user_stats = await self.get_user_vault_stats(user_id)
            vault_info = await self.get_vault_info()
            
            if user_stats.get('total_deposited', 0) == 0:
                return 0
            
            # Calculate proportional share
            user_share = user_stats['total_deposited'] / vault_info['total_value']
            user_profit = total_vault_profit * user_share
            
            return user_profit
            
        except Exception as e:
            logger.error(f"Error calculating profit share: {e}")
            return 0
    
    async def get_all_connected_users(self) -> list:
        """Get list of all connected user IDs"""
        return list(self.connected_users.keys())
    
    async def disconnect_user(self, user_id: int) -> Dict:
        """Disconnect user"""
        try:
            if user_id in self.connected_users:
                del self.connected_users[user_id]
                logger.info(f"Disconnected user {user_id}")
                return {'success': True}
            else:
                return {'success': False, 'error': 'User not connected'}
                
        except Exception as e:
            logger.error(f"Error disconnecting user: {e}")
            return {'success': False, 'error': str(e)}
    
    async def backup_user_data(self):
        """Backup user data (implement proper storage in production)"""
        try:
            backup_data = {
                'connected_users': self.connected_users,
                'vault_deposits': self.vault_deposits
            }
            
            with open('user_backup.json', 'w') as f:
                json.dump(backup_data, f, indent=2)
            
            logger.info("User data backed up")
            
        except Exception as e:
            logger.error(f"Backup error: {e}")
    
    async def restore_user_data(self):
        """Restore user data from backup"""
        try:
            with open('user_backup.json', 'r') as f:
                backup_data = json.load(f)
            
            self.connected_users = backup_data.get('connected_users', {})
            self.vault_deposits = backup_data.get('vault_deposits', {})
            
            logger.info("User data restored from backup")
            
        except FileNotFoundError:
            logger.info("No backup file found - starting fresh")
        except Exception as e:
            logger.error(f"Restore error: {e}")
