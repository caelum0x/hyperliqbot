"""
Configuration management system for the Hyperliquid trading bot.
Centralizes all configurable parameters and provides methods to access and update them.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import copy

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    Configuration manager for centralized access to all bot settings
    """
    
    DEFAULT_CONFIG = {
        "general": {
            "environment": "testnet",  # "testnet" or "mainnet"
            "api_url": "https://api.hyperliquid-testnet.xyz",  # Will be overridden based on environment
            "log_level": "INFO",
            "data_directory": "data",
            "backup_interval_hours": 24
        },
        "telegram_bot": {
            "bot_token": "",  # To be filled by user
            "bot_username": "",  # To be filled by user
            "allowed_users": [],  # Empty list means all users are allowed
            "admin_users": [],  # List of admin user IDs
            "disable_suspicious_commands": True,
            "max_message_length": 4096,
            "command_cooldown_seconds": 3,
            "welcome_message": "Welcome to the Hyperliquid Trading Bot! Use /agent to get started."
        },
        "agent_wallet": {
            "min_funding_amount": 10.0,  # Minimum USDC to fund
            "recommended_funding_amount": 50.0,
            "fund_notification_threshold": 0.01,  # Notify user when funds are detected
            "creation_timeout_seconds": 60,
            "agent_name_prefix": "tg_agent_",
            "allow_direct_wallet_connection": False  # Whether to allow users to connect with private keys
        },
        "trading": {
            "default_slippage_bps": 10,
            "default_order_size_usd": 50.0,
            "min_order_size_usd": 10.0,
            "max_order_size_usd": 1000.0,
            "default_leverage": 1.0,
            "max_leverage": 5.0,
            "grid_levels": 10,
            "grid_spacing_bps": 20
        },
        "risk_management": {
            "max_daily_loss_percentage": 5.0,  # Maximum daily loss as percentage of account
            "position_size_limit_percentage": 20.0,  # Maximum single position size as percentage of account
            "total_position_limit_percentage": 80.0,  # Maximum total positions as percentage of account
            "max_daily_trades": 100,  # Maximum number of trades per day
            "max_open_positions": 10,  # Maximum number of simultaneous open positions
            "min_account_balance_usd": 10.0,  # Minimum account balance to keep
            "stop_loss_percentage": 5.0,  # Default stop loss percentage
            "take_profit_percentage": 10.0,  # Default take profit percentage
            "enable_emergency_stop": True  # Enable emergency stop if daily loss limit reached
        },
        "strategies": {
            "grid_trading": {
                "enabled": True,
                "default_pairs": ["BTC", "ETH", "SOL", "ARB"],
                "min_spread_bps": 5,
                "max_spread_bps": 100,
                "order_count_per_side": 5,
                "capital_per_grid": 100.0,
                "auto_adjust_spacing": True,
                "min_order_lifetime_seconds": 300,
                "rebalance_interval_minutes": 60
            },
            "momentum": {
                "enabled": True,
                "lookback_periods": 3,
                "confirmation_threshold": 2,
                "signal_strength_threshold": 0.5,
                "max_trade_duration_hours": 24,
                "stop_loss_percentage": 3.0,
                "take_profit_percentage": 6.0
            },
            "maker_rebate": {
                "enabled": True,
                "target_coins": ["BTC", "ETH", "SOL", "ARB", "MATIC", "LINK", "DOGE"],
                "min_liquidity_usd": 500000,
                "min_spread_bps": 3,
                "max_spread_bps": 20,
                "order_refresh_seconds": 300,
                "max_capital_allocation_percentage": 30.0
            }
        },
        "user_preferences": {
            # Default user preferences, will be overridden by user-specific settings
            "default": {
                "notifications": {
                    "trade_executed": True,
                    "position_closed": True,
                    "stop_loss_hit": True,
                    "take_profit_hit": True,
                    "funding_received": True,
                    "low_balance": True,
                    "strategy_updates": False,
                    "price_alerts": False,
                    "vault_updates": False
                },
                "trading_interface": {
                    "default_order_size_usd": 20.0,
                    "favorite_pairs": ["BTC", "ETH", "SOL"],
                    "default_slippage_bps": 5,
                    "confirm_orders": True,
                    "show_advanced_options": False,
                    "default_timeframe": "4h",
                    "chart_indicators": ["MA", "RSI"]
                },
                "risk_settings": {
                    "max_position_size_percentage": 10.0,
                    "max_daily_loss_percentage": 3.0,
                    "auto_stop_loss": True,
                    "default_stop_loss_percentage": 5.0,
                    "default_take_profit_percentage": 10.0,
                    "disable_trading_after_loss": True
                },
                "strategies": {
                    "grid_trading_enabled": True,
                    "momentum_enabled": False,
                    "maker_rebate_enabled": True
                },
                "display": {
                    "currency": "USD",
                    "timezone": "UTC",
                    "compact_portfolio": False,
                    "show_pnl_percentage": True,
                    "show_realized_pnl": True
                }
            }
        }
    }
    
    def __init__(self, config_path: str = "bot_config.json", user_config_dir: str = "user_configs"):
        """
        Initialize the configuration manager
        
        Args:
            config_path: Path to the main configuration file
            user_config_dir: Directory to store user-specific configurations
        """
        self.config_path = config_path
        self.user_config_dir = user_config_dir
        self.config = self._load_config()
        self.user_configs = {}
        self._ensure_user_config_dir()
    
    def _ensure_user_config_dir(self):
        """Ensure user config directory exists"""
        os.makedirs(self.user_config_dir, exist_ok=True)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or create default"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                
                # Merge with default config to ensure all keys exist
                merged_config = self._deep_merge(copy.deepcopy(self.DEFAULT_CONFIG), config)
                
                # Set API URL based on environment if not explicitly set
                if merged_config["general"]["environment"] == "mainnet":
                    merged_config["general"]["api_url"] = "https://api.hyperliquid.xyz"
                elif merged_config["general"]["environment"] == "testnet":
                    merged_config["general"]["api_url"] = "https://api.hyperliquid-testnet.xyz"
                
                return merged_config
            else:
                logger.info(f"Config file {self.config_path} not found, creating default config")
                self.save_config(self.DEFAULT_CONFIG)
                return copy.deepcopy(self.DEFAULT_CONFIG)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return copy.deepcopy(self.DEFAULT_CONFIG)
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """
        Deep merge two dictionaries
        
        Args:
            base: Base dictionary
            override: Dictionary with values to override
            
        Returns:
            Merged dictionary
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def save_config(self, config: Dict = None):
        """
        Save configuration to file
        
        Args:
            config: Configuration to save, defaults to current config
        """
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config or self.config, f, indent=2)
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get(self, key_path: str, default=None):
        """
        Get configuration value by key path
        
        Args:
            key_path: Dot-separated path to configuration value
            default: Default value if key doesn't exist
            
        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path: str, value: Any, save: bool = True) -> bool:
        """
        Set configuration value by key path
        
        Args:
            key_path: Dot-separated path to configuration value
            value: Value to set
            save: Whether to save config after setting
            
        Returns:
            True if successful, False otherwise
        """
        try:
            keys = key_path.split('.')
            config = self.config
            
            # Navigate to the parent of the target key
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]
            
            # Set the value
            config[keys[-1]] = value
            
            # Save if requested
            if save:
                self.save_config()
                
            return True
        except Exception as e:
            logger.error(f"Error setting config value: {e}")
            return False
    
    def load_user_config(self, user_id: int) -> Dict[str, Any]:
        """
        Load user-specific configuration
        
        Args:
            user_id: User ID
            
        Returns:
            User configuration
        """
        # Return cached config if available
        if user_id in self.user_configs:
            return self.user_configs[user_id]
        
        user_config_path = os.path.join(self.user_config_dir, f"user_{user_id}.json")
        
        try:
            if os.path.exists(user_config_path):
                with open(user_config_path, 'r') as f:
                    user_config = json.load(f)
                
                # Cache the config
                self.user_configs[user_id] = user_config
                return user_config
            else:
                # Create default user config based on global defaults
                default_user_config = copy.deepcopy(self.config["user_preferences"]["default"])
                self.save_user_config(user_id, default_user_config)
                return default_user_config
        except Exception as e:
            logger.error(f"Error loading user config for {user_id}: {e}")
            # Return default user preferences
            return copy.deepcopy(self.config["user_preferences"]["default"])
    
    def save_user_config(self, user_id: int, user_config: Dict[str, Any]) -> bool:
        """
        Save user-specific configuration
        
        Args:
            user_id: User ID
            user_config: User configuration
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_config_path = os.path.join(self.user_config_dir, f"user_{user_id}.json")
            
            with open(user_config_path, 'w') as f:
                json.dump(user_config, f, indent=2)
            
            # Update cache
            self.user_configs[user_id] = user_config
            
            logger.info(f"User config for {user_id} saved")
            return True
        except Exception as e:
            logger.error(f"Error saving user config for {user_id}: {e}")
            return False
    
    def get_user_preference(self, user_id: int, key_path: str, default=None) -> Any:
        """
        Get user preference by key path
        
        Args:
            user_id: User ID
            key_path: Dot-separated path to preference
            default: Default value if key doesn't exist
            
        Returns:
            Preference value or default
        """
        user_config = self.load_user_config(user_id)
        
        keys = key_path.split('.')
        value = user_config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                # If not found in user config, check global default
                return self.get(f"user_preferences.default.{key_path}", default)
        
        return value
    
    def set_user_preference(self, user_id: int, key_path: str, value: Any, save: bool = True) -> bool:
        """
        Set user preference by key path
        
        Args:
            user_id: User ID
            key_path: Dot-separated path to preference
            value: Value to set
            save: Whether to save config after setting
            
        Returns:
            True if successful, False otherwise
        """
        try:
            user_config = self.load_user_config(user_id)
            
            keys = key_path.split('.')
            config = user_config
            
            # Navigate to the parent of the target key
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]
            
            # Set the value
            config[keys[-1]] = value
            
            # Save if requested
            if save:
                self.save_user_config(user_id, user_config)
                
            return True
        except Exception as e:
            logger.error(f"Error setting user preference: {e}")
            return False
    
    def get_strategy_parameters(self, strategy_name: str) -> Dict[str, Any]:
        """
        Get parameters for a specific strategy
        
        Args:
            strategy_name: Strategy name
            
        Returns:
            Strategy parameters
        """
        return self.get(f"strategies.{strategy_name}", {})
    
    def get_risk_limits(self) -> Dict[str, Any]:
        """
        Get risk management limits
        
        Returns:
            Risk management limits
        """
        return self.get("risk_management", {})
    
    def get_user_risk_limits(self, user_id: int) -> Dict[str, Any]:
        """
        Get user-specific risk limits, falling back to global if not set
        
        Args:
            user_id: User ID
            
        Returns:
            Risk limits
        """
        user_risk = self.get_user_preference(user_id, "risk_settings", {})
        global_risk = self.get_risk_limits()
        
        # Use user settings where available, otherwise fall back to global
        combined_risk = copy.deepcopy(global_risk)
        for key, value in user_risk.items():
            if key in combined_risk:
                combined_risk[key] = value
        
        return combined_risk
    
    def update_strategy_parameters(self, strategy_name: str, parameters: Dict[str, Any]) -> bool:
        """
        Update parameters for a specific strategy
        
        Args:
            strategy_name: Strategy name
            parameters: Strategy parameters
            
        Returns:
            True if successful, False otherwise
        """
        current_params = self.get(f"strategies.{strategy_name}", {})
        updated_params = {**current_params, **parameters}
        return self.set(f"strategies.{strategy_name}", updated_params)
    
    def export_config_summary(self) -> str:
        """
        Export a human-readable summary of the configuration
        
        Returns:
            Configuration summary
        """
        # Get important values to display
        env = self.get("general.environment", "testnet")
        api_url = self.get("general.api_url", "")
        admin_users = self.get("telegram_bot.admin_users", [])
        allowed_users = self.get("telegram_bot.allowed_users", [])
        min_funding = self.get("agent_wallet.min_funding_amount", 10.0)
        max_leverage = self.get("risk_management.max_leverage", 5.0)
        
        enabled_strategies = []
        for strat, params in self.get("strategies", {}).items():
            if params.get("enabled", False):
                enabled_strategies.append(strat)
        
        # Build summary
        summary = [
            "📊 Configuration Summary",
            "------------------------",
            f"Environment: {env.upper()}",
            f"API URL: {api_url}",
            f"Admin Users: {len(admin_users)}",
            f"Allowed Users: {'All' if not allowed_users else len(allowed_users)}",
            f"Min Funding: {min_funding} USDC",
            f"Max Leverage: {max_leverage}x",
            f"Enabled Strategies: {', '.join(enabled_strategies)}",
            "",
            "Risk Management:",
            f"- Max Daily Loss: {self.get('risk_management.max_daily_loss_percentage', 5.0)}%",
            f"- Position Limit: {self.get('risk_management.position_size_limit_percentage', 20.0)}%",
            f"- Max Positions: {self.get('risk_management.max_open_positions', 10)}",
            f"- Stop Loss: {self.get('risk_management.stop_loss_percentage', 5.0)}%",
            f"- Take Profit: {self.get('risk_management.take_profit_percentage', 10.0)}%"
        ]
        
        return "\n".join(summary)

# Create a global instance for easy import
config_manager = ConfigManager()

# Helper functions for easy access
def get_config(key_path: str, default=None) -> Any:
    """Get configuration value by key path"""
    return config_manager.get(key_path, default)

def set_config(key_path: str, value: Any, save: bool = True) -> bool:
    """Set configuration value by key path"""
    return config_manager.set(key_path, value, save)

def get_user_config(user_id: int) -> Dict[str, Any]:
    """Get user-specific configuration"""
    return config_manager.load_user_config(user_id)

def set_user_preference(user_id: int, key_path: str, value: Any) -> bool:
    """Set user preference by key path"""
    return config_manager.set_user_preference(user_id, key_path, value)

def get_user_preference(user_id: int, key_path: str, default=None) -> Any:
    """Get user preference by key path"""
    return config_manager.get_user_preference(user_id, key_path, default)

def get_strategy_parameters(strategy_name: str) -> Dict[str, Any]:
    """Get parameters for a specific strategy"""
    return config_manager.get_strategy_parameters(strategy_name)

def get_risk_limits() -> Dict[str, Any]:
    """Get risk management limits"""
    return config_manager.get_risk_limits()

def get_api_url() -> str:
    """Get API URL based on environment"""
    return config_manager.get("general.api_url")

def is_mainnet() -> bool:
    """Check if running on mainnet"""
    return config_manager.get("general.environment") == "mainnet"

def get_telegram_bot_token() -> str:
    """Get Telegram bot token"""
    return config_manager.get("telegram_bot.bot_token", "")

def is_user_allowed(user_id: int) -> bool:
    """Check if user is allowed to use the bot"""
    allowed_users = config_manager.get("telegram_bot.allowed_users", [])
    # If allowed_users is empty, all users are allowed
    return len(allowed_users) == 0 or user_id in allowed_users

def is_admin_user(user_id: int) -> bool:
    """Check if user is an admin"""
    admin_users = config_manager.get("telegram_bot.admin_users", [])
    return user_id in admin_users

# Only execute if run directly
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Initialize config manager
    cm = ConfigManager()
    
    # Save default config
    cm.save_config()
    
    # Test user config
    test_user_id = 123456
    test_user_config = cm.load_user_config(test_user_id)
    print(f"User config: {test_user_config}")
    
    # Test getting values
    print(f"Environment: {cm.get('general.environment')}")
    print(f"API URL: {cm.get('general.api_url')}")
    print(f"Grid levels: {cm.get('strategies.grid_trading.order_count_per_side')}")
    
    # Print config summary
    print("\n" + cm.export_config_summary())
