from typing import Dict, List, Optional, Any
from .config import BotConfig


def format_number(value: float, decimals: int = 4) -> str:
    """Format number for display"""
    if abs(value) >= 1000000:
        return f"{value/1000000:.2f}M"
    elif abs(value) >= 1000:
        return f"{value/1000:.2f}K"
    else:
        return f"{value:.{decimals}f}"


def parse_order_params(args: List[str], is_market: bool) -> Optional[Dict[str, Any]]:
    """Parse order parameters from command arguments"""
    if is_market:
        if len(args) < 2:
            return None
        
        try:
            params = {
                "coin": args[0],
                "size": float(args[1])
            }
            
            if len(args) > 2:
                params["slippage"] = float(args[2])
            
            return params
        except ValueError:
            return None
    else:
        if len(args) < 3:
            return None
        
        try:
            return {
                "coin": args[0],
                "size": float(args[1]),
                "price": float(args[2])
            }
        except ValueError:
            return None


def validate_user_access(user_id: int, config: BotConfig) -> bool:
    """Validate if user has access to the bot"""
    if not config.get("security.require_auth", True):
        return True
    
    allowed_users = config.get("telegram.allowed_users", [])
    return user_id in allowed_users or len(allowed_users) == 0


def is_admin_user(user_id: int, config: BotConfig) -> bool:
    """Check if user is an admin"""
    admin_users = config.get("telegram.admin_users", [])
    return user_id in admin_users
