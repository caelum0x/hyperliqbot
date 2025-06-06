"""
Setup script to install and configure all dependencies
Run this before starting the bot
"""

import subprocess
import sys
import os

def install_requirements():
    """Install all required packages"""
    try:
        print("📦 Installing required packages...")
        
        # Install from requirements.txt
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        
        print("✅ All packages installed successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing packages: {e}")
        return False
    
    return True

def check_config():
    """Check if config.json exists and has required fields"""
    if not os.path.exists("config.json"):
        print("📝 Creating default config.json...")
        
        default_config = {
            "telegram": {
                "bot_token": "YOUR_BOT_TOKEN_HERE"
            },
            "base_url": "https://api.hyperliquid-testnet.xyz",
            "referral_code": "HYPERBOT",
            "hyperevm": {
                "network": "testnet",
                "rpc_url": "https://api.hyperliquid-testnet-evm.xyz/rpc"
            },
            "trading": {
                "max_position_size": 10000,
                "default_slippage": 0.005,
                "risk_level": "medium"
            },
            "vault": {
                "minimum_deposit": 100,
                "profit_share": 0.10,
                "lockup_days": 1
            },
            "ai": {
                "model_retrain_hours": 24,
                "confidence_threshold": 0.7,
                "max_signals_per_hour": 10
            }
        }
        
        import json
        with open("config.json", "w") as f:
            json.dump(default_config, f, indent=2)
        
        print("✅ Created config.json")
        print("⚠️  Please update config.json with your Telegram bot token!")
        return False
    
    return True

def main():
    """Main setup function"""
    print("🚀 Setting up HyperLiquid Alpha Bot dependencies...")
    
    # Install packages
    if not install_requirements():
        return
    
    # Check config
    config_ready = check_config()
    
    print("\n" + "="*50)
    if config_ready:
        print("✅ Setup complete! You can now run the bot:")
        print("   python main.py")
    else:
        print("⚠️  Setup partially complete!")
        print("   1. Update config.json with your bot token")
        print("   2. Run: python main.py")
    print("="*50)

if __name__ == "__main__":
    main()
