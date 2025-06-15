"""
Quick start script for the Hyperliquid Trading Bot
This script ensures everything is properly configured and starts the bot
"""

import asyncio
import json
import os
import sys
from pathlib import Path

async def main():
    """Main startup with all checks"""
    print("🚀 HYPERLIQUID TRADING BOT STARTUP")
    print("=" * 50)
    
    # Check configuration
    config_path = Path("config.json")
    if not config_path.exists():
        print("❌ config.json not found!")
        print("💡 Run 'python main.py' first to create default configuration")
        return
    
    # Load and check config
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Check Telegram token
    bot_token = config.get('telegram', {}).get('bot_token', '')
    if bot_token in ['', 'GET_TOKEN_FROM_BOTFATHER']:
        print("❌ Telegram bot token not configured!")
        print("💡 Get token from @BotFather and update config.json")
        return
    
    # Check Hyperliquid configuration
    examples_config = Path("examples/config.json")
    env_key = os.environ.get('HYPERLIQUID_PRIVATE_KEY')
    
    if not env_key and not examples_config.exists():
        print("❌ Hyperliquid authentication not configured!")
        print("💡 Set HYPERLIQUID_PRIVATE_KEY environment variable")
        print("   OR create examples/config.json with your secret_key")
        return
    
    print("✅ Configuration checks passed")
    print("\n🔧 Starting diagnostic checks...")
    
    # Run diagnostics
    try:
        from diagnose_agent_issue import main as diagnose_main
        diagnose_main()
    except Exception as e:
        print(f"⚠️ Diagnostic check failed: {e}")
    
    print("\n🧪 Running agent trading test...")
    
    # Run trading test
    try:
        from test_agent_trading import main as test_main
        await test_main()
    except Exception as e:
        print(f"⚠️ Trading test failed: {e}")
    
    print("\n🚀 Starting main bot...")
    
    # Start the main bot
    try:
        from main import main as bot_main
        await bot_main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot startup failed: {e}")
        print("💡 Check the error messages above and ensure all configuration is correct")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutdown complete")
    except Exception as e:
        print(f"💥 Critical error: {e}")
        sys.exit(1)
