import json
import os
from typing import Dict, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class BotConfig:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self._load_config()
        self._load_env_overrides()
    
    def _load_config(self) -> Dict:
        """Load configuration from JSON file (Hyperliquid SDK format)"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                # Ensure we have the required Hyperliquid SDK structure
                return self._ensure_hyperliquid_format(config)
        except FileNotFoundError:
            return self._create_hyperliquid_config()
    
    def _ensure_hyperliquid_format(self, config: Dict) -> Dict:
        """Ensure config follows Hyperliquid SDK format"""
        # Start with Hyperliquid SDK format
        hyperliquid_config = {
            "account_address": config.get("account_address", ""),
            "secret_key": config.get("secret_key", ""),
            "mainnet": config.get("mainnet", False)
        }
        
        # Add our bot-specific extensions
        bot_config = {
            "vault_address": config.get("vault_address", ""),
            "referral_code": config.get("referral_code", "HYPERBOT"),
            "telegram": {
                "bot_token": config.get("telegram", {}).get("bot_token", ""),
                "allowed_users": config.get("telegram", {}).get("allowed_users", []),
                "admin_users": config.get("telegram", {}).get("admin_users", [])
            },
            "database": {
                "file": config.get("database", {}).get("file", "bot_data.json"),
                "backup_interval": config.get("database", {}).get("backup_interval", 3600)
            },
            "hyperevm": {
                "network": config.get("hyperevm", {}).get("network", "testnet"),
                "rpc_url": config.get("hyperevm", {}).get("rpc_url", "https://rpc.hyperliquid-testnet.xyz/evm"),
                "chain_id": config.get("hyperevm", {}).get("chain_id", 998)
            },
            "vault_system": {
                "minimum_deposit": config.get("vault_system", {}).get("minimum_deposit", 50),
                "performance_fee": config.get("vault_system", {}).get("performance_fee", 0.10),
                "withdrawal_lockup_days": config.get("vault_system", {}).get("withdrawal_lockup_days", 1),
                "strategies": config.get("vault_system", {}).get("strategies", [
                    "maker_rebate_mining",
                    "grid_trading",
                    "hlp_staking",
                    "arbitrage_scanning"
                ])
            },
            "trading": {
                "max_position_size": config.get("trading", {}).get("max_position_size", 10000),
                "default_grid_spread": config.get("trading", {}).get("default_grid_spread", 0.002),
                "profit_threshold": config.get("trading", {}).get("profit_threshold", 0.001),
                "stop_loss_pct": config.get("trading", {}).get("stop_loss_pct", 0.01)
            },
            "risk_management": {
                "max_leverage": config.get("risk_management", {}).get("max_leverage", 10),
                "position_size_limit": config.get("risk_management", {}).get("position_size_limit", 0.1),
                "daily_loss_limit": config.get("risk_management", {}).get("daily_loss_limit", 1000)
            }
        }
        
        # Merge Hyperliquid format with bot extensions
        return {**hyperliquid_config, **bot_config}
    
    def _create_hyperliquid_config(self) -> Dict:
        """Create default configuration in Hyperliquid SDK format"""
        default_config = {
            # Core Hyperliquid SDK configuration
            "account_address": "",
            "secret_key": "",
            "mainnet": False,
            
            # Bot extensions
            "vault_address": "",
            "referral_code": "HYPERBOT",
            "telegram": {
                "bot_token": "",
                "allowed_users": [],
                "admin_users": []
            },
            "database": {
                "file": "bot_data.json",
                "backup_interval": 3600
            },
            "hyperevm": {
                "network": "testnet",
                "rpc_url": "https://rpc.hyperliquid-testnet.xyz/evm",
                "chain_id": 998
            },
            "vault_system": {
                "minimum_deposit": 50,
                "performance_fee": 0.10,
                "withdrawal_lockup_days": 1,
                "strategies": [
                    "maker_rebate_mining",
                    "grid_trading", 
                    "hlp_staking",
                    "arbitrage_scanning"
                ]
            },
            "trading": {
                "max_position_size": 10000,
                "default_grid_spread": 0.002,
                "profit_threshold": 0.001,
                "stop_loss_pct": 0.01
            },
            "risk_management": {
                "max_leverage": 10,
                "position_size_limit": 0.1,
                "daily_loss_limit": 1000
            }
        }
        
        # Save default config
        with open(self.config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        
        return default_config
    
    def _load_env_overrides(self):
        """Override config with environment variables"""
        # Hyperliquid SDK core values
        if os.getenv("HL_ACCOUNT_ADDRESS"):
            self.config["account_address"] = os.getenv("HL_ACCOUNT_ADDRESS")
        if os.getenv("HL_SECRET_KEY"):
            self.config["secret_key"] = os.getenv("HL_SECRET_KEY")
        if os.getenv("HL_MAINNET"):
            self.config["mainnet"] = os.getenv("HL_MAINNET", "false").lower() == "true"
        
        # Bot-specific overrides
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            self.config["telegram"]["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN")
        if os.getenv("VAULT_ADDRESS"):
            self.config["vault_address"] = os.getenv("VAULT_ADDRESS")
        if os.getenv("VAULT_PRIVATE_KEY"):
            self.config["vault_private_key"] = os.getenv("VAULT_PRIVATE_KEY")
        if os.getenv("REFERRAL_CODE"):
            self.config["referral_code"] = os.getenv("REFERRAL_CODE")
        if os.getenv("DATABASE_FILE"):
            self.config["database"]["file"] = os.getenv("DATABASE_FILE")
    
    # Hyperliquid SDK compatible methods
    def get_account_address(self) -> str:
        """Get account address for Hyperliquid SDK"""
        return self.config.get("account_address", "")
    
    def get_secret_key(self) -> str:
        """Get secret key for Hyperliquid SDK"""
        return self.config.get("secret_key", "")
    
    def is_mainnet(self) -> bool:
        """Check if using mainnet"""
        return self.config.get("mainnet", False)
    
    def get_api_url(self) -> str:
        """Get API URL based on network"""
        if self.is_mainnet():
            return "https://api.hyperliquid.xyz"
        else:
            return "https://api.hyperliquid-testnet.xyz"
    
    # Bot-specific methods
    def get_telegram_token(self) -> str:
        """Get Telegram bot token"""
        return self.config.get("telegram", {}).get("bot_token", "")
    
    def get_vault_address(self) -> str:
        """Get vault address"""
        return self.config.get("vault_address", "")
    
    def get_vault_private_key(self) -> str:
        """Get vault private key"""
        return self.config.get("vault_private_key", "")
    
    def get_referral_code(self) -> str:
        """Get referral code"""
        return self.config.get("referral_code", "HYPERBOT")
    
    def get_database_file(self) -> str:
        """Get database file path"""
        return self.config.get("database", {}).get("file", "bot_data.json")
    
    def get_minimum_deposit(self) -> float:
        """Get minimum vault deposit"""
        return self.config.get("vault_system", {}).get("minimum_deposit", 50)
    
    def get_performance_fee(self) -> float:
        """Get vault performance fee"""
        return self.config.get("vault_system", {}).get("performance_fee", 0.10)
    
    def get_trading_config(self) -> Dict:
        """Get trading configuration"""
        return self.config.get("trading", {})
    
    def get_risk_config(self) -> Dict:
        """Get risk management configuration"""
        return self.config.get("risk_management", {})
    
    def get_hyperevm_config(self) -> Dict:
        """Get HyperEVM configuration"""
        return self.config.get("hyperevm", {})
    
    def get_vault_strategies(self) -> list:
        """Get enabled vault strategies"""
        return self.config.get("vault_system", {}).get("strategies", [])
    
    def is_strategy_enabled(self, strategy: str) -> bool:
        """Check if a strategy is enabled"""
        return strategy in self.get_vault_strategies()
    
    def validate_hyperliquid_config(self) -> Dict[str, bool]:
        """Validate Hyperliquid SDK configuration"""
        return {
            "account_address_set": bool(self.get_account_address()),
            "secret_key_set": bool(self.get_secret_key()),
            "network_configured": True,
            "telegram_token_set": bool(self.get_telegram_token()),
            "vault_address_set": bool(self.get_vault_address()),
            "referral_code_set": bool(self.get_referral_code())
        }
    
    def get_hyperliquid_sdk_config(self) -> Dict:
        """Get configuration in Hyperliquid SDK format"""
        return {
            "account_address": self.get_account_address(),
            "secret_key": self.get_secret_key(),
            "mainnet": self.is_mainnet()
        }
    
    def save_config(self):
        """Save current configuration"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def get(self, key: str, default=None):
        """Get configuration value with dot notation"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value):
        """Set configuration value with dot notation"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    def generate_config_summary(self) -> str:
        """Generate configuration summary"""
        validation = self.validate_hyperliquid_config()
        
        return f"""
🔧 **Hyperliquid Bot Configuration**

📡 **Network Settings:**
• Environment: {'Mainnet' if self.is_mainnet() else 'Testnet'}
• API URL: {self.get_api_url()}

🔐 **Authentication:**
• Account Address: {'✅ Set' if validation['account_address_set'] else '❌ Not Set'}
• Secret Key: {'✅ Set' if validation['secret_key_set'] else '❌ Not Set'}

🤖 **Bot Settings:**
• Telegram Token: {'✅ Set' if validation['telegram_token_set'] else '❌ Not Set'}
• Vault Address: {'✅ Set' if validation['vault_address_set'] else '❌ Not Set'}
• Referral Code: {self.get_referral_code()}

💰 **Vault Configuration:**
• Minimum Deposit: ${self.get_minimum_deposit()}
• Performance Fee: {self.get_performance_fee() * 100}%
• Strategies: {len(self.get_vault_strategies())} enabled

⚠️ **Risk Management:**
• Max Leverage: {self.get('risk_management.max_leverage', 10)}x
• Position Limit: {self.get('risk_management.position_size_limit', 0.1) * 100}%
• Daily Loss Limit: ${self.get('risk_management.daily_loss_limit', 1000)}

🌐 **HyperEVM:**
• Network: {self.get('hyperevm.network', 'testnet')}
• Chain ID: {self.get('hyperevm.chain_id', 998)}
        """.strip()

# Create global config instance
config = BotConfig()

# Convenience functions for backward compatibility
def get_hyperliquid_config() -> Dict:
    """Get Hyperliquid SDK configuration"""
    return config.get_hyperliquid_sdk_config()

def get_telegram_token() -> str:
    """Get Telegram token"""
    return config.get_telegram_token()

def get_vault_address() -> str:
    """Get vault address"""
    return config.get_vault_address()

def is_mainnet() -> bool:
    """Check if using mainnet"""
    return config.is_mainnet()
