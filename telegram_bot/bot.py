import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import BotConfig
from .user_manager import UserManager
from .handlers import TradingHandlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class HyperliquidTradingBot:
    def __init__(self, config_path: str = "telegram_bot/bot_config.json"):
        self.config = BotConfig(config_path)
        self.user_manager = UserManager()
        self.handlers = TradingHandlers(self.user_manager, self.config)
        self.application = None
    
    def setup_handlers(self):
        """Setup command handlers"""
        if not self.application:
            return
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.handlers.start))
        self.application.add_handler(CommandHandler("help", self.handlers.help_command))
        self.application.add_handler(CommandHandler("register", self.handlers.register))
        self.application.add_handler(CommandHandler("balance", self.handlers.balance))
        self.application.add_handler(CommandHandler("positions", self.handlers.positions))
        self.application.add_handler(CommandHandler("orders", self.handlers.orders))
        self.application.add_handler(CommandHandler("buy", self.handlers.buy_order))
        self.application.add_handler(CommandHandler("sell", self.handlers.sell_order))
        self.application.add_handler(CommandHandler("market_buy", self.handlers.market_buy))
        self.application.add_handler(CommandHandler("market_sell", self.handlers.market_sell))
        self.application.add_handler(CommandHandler("cancel", self.handlers.cancel_order))
    
    async def cleanup_sessions(self):
        """Periodic cleanup of expired sessions"""
        while True:
            try:
                timeout = self.config.get("security.session_timeout", 3600)
                self.user_manager.cleanup_expired_sessions(timeout)
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
                await asyncio.sleep(300)
    
    def run(self):
        """Run the bot"""
        bot_token = self.config.get("telegram.bot_token")
        if not bot_token:
            logger.error("Bot token not found in configuration!")
            return
        
        # Create application
        self.application = Application.builder().token(bot_token).build()
        
        # Setup handlers
        self.setup_handlers()
        
        # Start cleanup task
        asyncio.create_task(self.cleanup_sessions())
        
        # Run the bot
        logger.info("Starting Hyperliquid Trading Bot...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = HyperliquidTradingBot()
    bot.run()
