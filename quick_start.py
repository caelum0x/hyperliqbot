"""
Quick start script for Hyperliquid Alpha Bot
Guides users through initial setup
"""

import json
import os
import sys

def print_banner():
    """Print welcome banner"""
    print("🚀" + "="*50 + "🚀")
    print("   HYPERLIQUID ALPHA BOT - QUICK START")
    print("🚀" + "="*50 + "🚀")
    print()

def check_dependencies():
    """Check if required dependencies are installed"""
    print("📦 Checking dependencies...")
    
    missing = []
    
    try:
        import telegram
        print("✅ python-telegram-bot")
    except ImportError:
        print("❌ python-telegram-bot")
        missing.append("python-telegram-bot")
    
    try:
        import web3
        print("✅ web3")
    except ImportError:
        print("❌ web3")
        missing.append("web3")
    
    try:
        from hyperliquid.info import Info
        print("✅ hyperliquid-python-sdk")
    except ImportError:
        print("❌ hyperliquid-python-sdk")
        missing.append("hyperliquid-python-sdk")
    
    if missing:
        print(f"\n⚠️ Missing dependencies: {', '.join(missing)}")
        print("Run: pip install " + " ".join(missing))
        return False
    
    print("\n✅ All dependencies installed!")
    return True

def setup_bot_token():
    """Guide user through bot token setup"""
    print("\n🤖 TELEGRAM BOT SETUP")
    print("=" * 30)
    print("1. Open Telegram and message @BotFather")
    print("2. Send /newbot")
    print("3. Choose a name for your bot (e.g., 'My HyperLiquid Bot')")
    print("4. Choose a username (e.g., 'my_hyperliquid_bot')")
    print("5. Copy the token that BotFather gives you")
    print()
    
    while True:
        token = input("📝 Paste your bot token here: ").strip()
        if token and len(token) > 40 and ':' in token:
            break
        print("❌ Invalid token format. Please try again.")
    
    return token

def update_config(bot_token):
    """Update config.json with bot token"""
    config = {
        "telegram": {
            "bot_token": bot_token
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
    
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)
    
    print("✅ Config file updated!")

def main():
    """Main setup function"""
    print_banner()
    
    # Step 1: Check dependencies
    if not check_dependencies():
        print("\n❌ Please install missing dependencies first.")
        print("Run: python fix_pip_and_setup.py")
        return
    
    # Step 2: Setup bot token
    if not os.path.exists("config.json") or input("\n🔧 Setup bot token? (y/n): ").lower() == 'y':
        bot_token = setup_bot_token()
        update_config(bot_token)
    
    # Step 3: Final instructions
    print("\n🎉 SETUP COMPLETE!")
    print("=" * 20)
    print("Next steps:")
    print("1. Run: python main.py")
    print("2. Open Telegram and find your bot")
    print("3. Send /start to begin trading!")
    print()
    print("📚 Need help? Check the README.md file")
    print("💬 Join our community: @hyperliquid")

if __name__ == "__main__":
    main()
