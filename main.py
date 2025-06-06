"""
Main entry point for the Hyperliquid Alpha Trading Bot
Connects all components into a unified system
"""

import asyncio
import logging
import json
import sys
import os
from pathlib import Path

# Add current directory to Python path to fix imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Import components with proper error handling
try:
    from trading_engine.main_bot import TelegramTradingBot
    BOT_IMPORTED = True
except ImportError as e:
    print(f"❌ Error importing TelegramTradingBot: {e}")
    BOT_IMPORTED = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class HyperliquidAlphaBot:
    """
    Main application class that orchestrates all components
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.components = {}
        self.running = False
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                
            # Check if bot token needs to be set
            bot_token = config.get('telegram', {}).get('bot_token', '')
            if bot_token in ['YOUR_BOT_TOKEN_HERE', 'GET_TOKEN_FROM_BOTFATHER', '']:
                logger.error("❌ Please set your Telegram bot token in config.json")
                logger.error("1. Message @BotFather on Telegram")
                logger.error("2. Send /newbot and follow instructions")
                logger.error("3. Copy the token to config.json")
                return {}
                
            return config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    async def initialize_components(self):
        """Initialize all bot components"""
        try:
            logger.info("Initializing Hyperliquid Alpha Bot components...")
            
            if not BOT_IMPORTED:
                raise ImportError("TelegramTradingBot could not be imported")
            
            # Initialize Telegram bot with working components
            telegram_token = self.config.get('telegram', {}).get('bot_token')
            if not telegram_token:
                raise ValueError("Telegram bot token not found in config")
            
            self.components['telegram_bot'] = TelegramTradingBot(telegram_token, self.config)
            logger.info("✅ Telegram Bot initialized with REAL Hyperliquid integration")
            
            logger.info("🚀 All components initialized successfully!")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    async def start(self):
        """Start the bot"""
        try:
            if not self.config:
                logger.error("❌ Cannot start bot without valid configuration")
                return
                
            await self.initialize_components()
            
            logger.info("🤖 Starting Hyperliquid Alpha Bot...")
            
            # Start Telegram bot
            telegram_bot = self.components['telegram_bot']
            
            # Start polling
            await telegram_bot.app.initialize()
            await telegram_bot.app.start()
            await telegram_bot.app.updater.start_polling()
            
            self.running = True
            logger.info("✅ Bot is running! Send /start in Telegram to begin.")
            logger.info("💡 Connect your wallet with /connect YOUR_PRIVATE_KEY")
            logger.info("📊 View portfolio with /portfolio")
            logger.info("🎯 Start trading with /trade")
            
            # Keep running
            try:
                while self.running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received shutdown signal...")
                await self.stop()
                
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    async def stop(self):
        """Stop the bot gracefully"""
        try:
            logger.info("🛑 Stopping Hyperliquid Alpha Bot...")
            
            self.running = False
            
            # Stop Telegram bot
            if 'telegram_bot' in self.components:
                telegram_bot = self.components['telegram_bot']
                await telegram_bot.app.updater.stop()
                await telegram_bot.app.stop()
                await telegram_bot.app.shutdown()
            
            logger.info("✅ Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

async def main():
    """Main entry point"""
    try:
        # Check dependencies
        logger.info("🔍 Checking dependencies...")
        
        try:
            import telegram
            logger.info("✅ telegram module available")
        except ImportError:
            logger.error("❌ telegram module missing - install with: pip install python-telegram-bot")
            return
        
        try:
            from hyperliquid.info import Info
            logger.info("✅ hyperliquid module available")
        except ImportError:
            logger.error("❌ hyperliquid module missing")
            logger.error("   Install with: pip install git+https://github.com/hyperliquid-dex/hyperliquid-python-sdk.git")
            return
        
        # Create and start the bot
        bot = HyperliquidAlphaBot()
        await bot.start()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    # Check if config file exists
    if not Path("config.json").exists():
        logger.error("❌ config.json not found! Please create it with your settings.")
        logger.info("Creating default config.json...")
        
        default_config = {
            "telegram": {
                "bot_token": "GET_TOKEN_FROM_BOTFATHER"
            },
            "base_url": "https://api.hyperliquid-testnet.xyz",
            "referral_code": "HYPERBOT"
        }
        
        with open("config.json", "w") as f:
            json.dump(default_config, f, indent=2)
        
        logger.info("✅ Created default config.json - please add your bot token!")
        exit(1)
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Goodbye!")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        exit(1)
