"""
Rate limiting and abuse prevention for Telegram bot
Prevents spam and ensures fair usage
"""
import time
import logging
from typing import Dict, List, Optional, Tuple
from collections import defaultdict, deque
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Multi-level rate limiting system
    """
    
    def __init__(self):
        # Command-specific rate limits (command -> (max_calls, time_window_seconds))
        self.rate_limits = {
            'create_agent': (1, 3600),      # 1 per hour
            'enable_trading': (3, 300),     # 3 per 5 minutes
            'test_trade': (10, 300),        # 10 per 5 minutes
            'agent_status': (20, 300),      # 20 per 5 minutes
            'portfolio': (30, 300),         # 30 per 5 minutes
            'emergency_stop': (2, 300),     # 2 per 5 minutes
            'global': (50, 300),            # 50 total commands per 5 minutes
        }
        
        # User command history: {user_id: {command: deque([timestamps])}}
        self.user_history: Dict[int, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        
        # Global user activity: {user_id: deque([timestamps])}
        self.global_history: Dict[int, deque] = defaultdict(deque)
        
        # Blocked users: {user_id: block_until_timestamp}
        self.blocked_users: Dict[int, float] = {}
        
        # Cleanup task
        self._cleanup_task = None
    
    async def check_rate_limit(self, user_id: int, command: str) -> Tuple[bool, Optional[str]]:
        """
        Check if user is within rate limits for a command
        
        Args:
            user_id: Telegram user ID
            command: Command name
            
        Returns:
            Tuple of (allowed, error_message)
        """
        current_time = time.time()
        
        # Check if user is blocked
        if user_id in self.blocked_users:
            if current_time < self.blocked_users[user_id]:
                remaining = int(self.blocked_users[user_id] - current_time)
                return False, f"You are temporarily blocked. Try again in {remaining} seconds."
            else:
                del self.blocked_users[user_id]
        
        # Check command-specific rate limit
        if command in self.rate_limits:
            max_calls, window = self.rate_limits[command]
            
            # Clean old entries
            user_cmd_history = self.user_history[user_id][command]
            while user_cmd_history and user_cmd_history[0] < current_time - window:
                user_cmd_history.popleft()
            
            # Check if limit exceeded
            if len(user_cmd_history) >= max_calls:
                oldest_call = user_cmd_history[0]
                remaining = int(window - (current_time - oldest_call))
                return False, f"Rate limit exceeded for {command}. Try again in {remaining} seconds."
        
        # Check global rate limit
        max_global, global_window = self.rate_limits['global']
        global_history = self.global_history[user_id]
        
        # Clean old entries
        while global_history and global_history[0] < current_time - global_window:
            global_history.popleft()
        
        # Check global limit
        if len(global_history) >= max_global:
            oldest_call = global_history[0]
            remaining = int(global_window - (current_time - oldest_call))
            
            # Temporary block for severe abuse
            if len(global_history) >= max_global * 2:
                self.blocked_users[user_id] = current_time + 3600  # 1 hour block
                logger.warning(f"User {user_id} blocked for 1 hour due to severe rate limit abuse")
                return False, "You have been temporarily blocked due to excessive usage. Contact support if this is an error."
            
            return False, f"Global rate limit exceeded. Try again in {remaining} seconds."
        
        return True, None
    
    async def record_command(self, user_id: int, command: str) -> None:
        """
        Record a command execution
        
        Args:
            user_id: Telegram user ID
            command: Command name
        """
        current_time = time.time()
        
        # Record command-specific usage
        if command in self.rate_limits:
            self.user_history[user_id][command].append(current_time)
        
        # Record global usage
        self.global_history[user_id].append(current_time)
        
        # Log for audit
        logger.info(f"Rate limiter: User {user_id} executed {command}")
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """
        Get rate limiting stats for a user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dict with usage statistics
        """
        current_time = time.time()
        stats = {}
        
        # Check each command's usage
        for command, (max_calls, window) in self.rate_limits.items():
            if command == 'global':
                continue
                
            user_cmd_history = self.user_history[user_id][command]
            # Clean old entries
            while user_cmd_history and user_cmd_history[0] < current_time - window:
                user_cmd_history.popleft()
            
            stats[command] = {
                'used': len(user_cmd_history),
                'limit': max_calls,
                'window_seconds': window,
                'reset_in': int(window - (current_time - user_cmd_history[0])) if user_cmd_history else 0
            }
        
        # Global stats
        global_history = self.global_history[user_id]
        max_global, global_window = self.rate_limits['global']
        
        # Clean old entries
        while global_history and global_history[0] < current_time - global_window:
            global_history.popleft()
        
        stats['global'] = {
            'used': len(global_history),
            'limit': max_global,
            'window_seconds': global_window,
            'reset_in': int(global_window - (current_time - global_history[0])) if global_history else 0
        }
        
        return stats
    
    async def start_cleanup_task(self):
        """Start periodic cleanup of old entries"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Periodically clean up old rate limit entries"""
        while True:
            try:
                await asyncio.sleep(300)  # Clean every 5 minutes
                current_time = time.time()
                
                # Clean user command histories
                for user_id in list(self.user_history.keys()):
                    user_commands = self.user_history[user_id]
                    for command in list(user_commands.keys()):
                        if command in self.rate_limits:
                            _, window = self.rate_limits[command]
                            cmd_history = user_commands[command]
                            
                            # Remove old entries
                            while cmd_history and cmd_history[0] < current_time - window:
                                cmd_history.popleft()
                            
                            # Remove empty histories
                            if not cmd_history:
                                del user_commands[command]
                    
                    # Remove empty user entries
                    if not user_commands:
                        del self.user_history[user_id]
                
                # Clean global histories
                for user_id in list(self.global_history.keys()):
                    global_history = self.global_history[user_id]
                    _, global_window = self.rate_limits['global']
                    
                    # Remove old entries
                    while global_history and global_history[0] < current_time - global_window:
                        global_history.popleft()
                    
                    # Remove empty histories
                    if not global_history:
                        del self.global_history[user_id]
                
                # Clean expired blocks
                expired_blocks = [user_id for user_id, block_until in self.blocked_users.items() 
                                if current_time >= block_until]
                for user_id in expired_blocks:
                    del self.blocked_users[user_id]
                
                logger.debug("Rate limiter cleanup completed")
                
            except Exception as e:
                logger.error(f"Error in rate limiter cleanup: {e}")

# Global rate limiter instance
rate_limiter = RateLimiter()

"""
Rate limiting for bot commands
"""
import asyncio
import time
from collections import defaultdict, deque
from typing import Dict, Tuple

class RateLimiter:
    """Rate limiting for bot commands to prevent abuse"""
    
    def __init__(self):
        # Rate limits per command type (requests per minute)
        self.limits = {
            'create_agent': 3,      # 3 agent creations per hour
            'enable_trading': 10,   # 10 trading enables per hour
            'test_trade': 30,       # 30 test trades per hour
            'portfolio': 60,        # 60 portfolio checks per hour
            'default': 20           # Default limit
        }
        
        # Track user command usage
        self.user_commands: Dict[int, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        
        # Cleanup interval
        self.cleanup_interval = 300  # 5 minutes
        
    async def check_rate_limit(self, user_id: int, command: str) -> Tuple[bool, str]:
        """Check if user can execute command within rate limit"""
        current_time = time.time()
        limit = self.limits.get(command, self.limits['default'])
        
        # Clean old entries
        self._cleanup_old_entries(user_id, command, current_time)
        
        # Check current usage
        usage = len(self.user_commands[user_id][command])
        
        if usage >= limit:
            return False, f"Rate limit exceeded. Try again in a few minutes. (Limit: {limit}/hour)"
        
        return True, ""
    
    async def record_command(self, user_id: int, command: str):
        """Record command usage"""
        current_time = time.time()
        self.user_commands[user_id][command].append(current_time)
    
    def _cleanup_old_entries(self, user_id: int, command: str, current_time: float):
        """Remove entries older than 1 hour"""
        hour_ago = current_time - 3600
        command_queue = self.user_commands[user_id][command]
        
        while command_queue and command_queue[0] < hour_ago:
            command_queue.popleft()
    
    async def start_cleanup_task(self):
        """Start background cleanup task"""
        asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Periodic cleanup of old entries"""
        while True:
            try:
                current_time = time.time()
                hour_ago = current_time - 3600
                
                # Clean up all users and commands
                for user_id in list(self.user_commands.keys()):
                    for command in list(self.user_commands[user_id].keys()):
                        self._cleanup_old_entries(user_id, command, current_time)
                        
                        # Remove empty queues
                        if not self.user_commands[user_id][command]:
                            del self.user_commands[user_id][command]
                    
                    # Remove empty user entries
                    if not self.user_commands[user_id]:
                        del self.user_commands[user_id]
                
                await asyncio.sleep(self.cleanup_interval)
                
            except Exception as e:
                # Log error but don't crash
                print(f"Error in rate limiter cleanup: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying

# Global instance
rate_limiter = RateLimiter()
