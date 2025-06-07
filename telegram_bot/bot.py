import logging
import asyncio
import sys
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Import real Hyperliquid components
from hyperliquid.utils import constants

# Import actual examples
examples_dir = os.path.join(os.path.dirname(__file__), '..', 'examples')
sys.path.append(examples_dir)

import example_utils

from .config import BotConfig
from .user_manager import UserManager
from .handlers import TradingHandlers

# Import real vault and trading components
from ..trading_engine.vault_manager import VaultManager
from ..strategies.automated_trading import AutomatedTrading
from ..strategies.grid_trading_engine import GridTradingEngine

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class HyperliquidTradingBot:
    """
    Main Telegram bot using real Hyperliquid API patterns
    No placeholder messages - only real functionality
    """
    
    def __init__(self, config_path: str = "telegram_bot/bot_config.json"):
        self.config = BotConfig(config_path)
        
        # Initialize real Hyperliquid components
        base_url = constants.TESTNET_API_URL if not self.config.is_mainnet() else constants.MAINNET_API_URL
        
        # Setup using example_utils pattern
        self.address, self.info, self.exchange = example_utils.setup(base_url, skip_ws=True)
        
        # Initialize real managers with actual Hyperliquid integration
        self.vault_manager = VaultManager(
            vault_address=self.config.get_vault_address(),
            base_url=base_url
        )
        
        self.trading_engine = AutomatedTrading(
            exchange=self.exchange,
            info=self.info,
            base_url=base_url
        )
        
        self.grid_engine = GridTradingEngine(
            exchange=self.exchange,
            info=self.info,
            base_url=base_url
        )
        
        self.user_manager = UserManager(
            vault_manager=self.vault_manager,
            exchange=self.exchange,
            info=self.info
        )
        
        self.handlers = TradingHandlers(
            user_manager=self.user_manager,
            vault_manager=self.vault_manager,
            trading_engine=self.trading_engine,
            grid_engine=self.grid_engine,
            config=self.config
        )
        
        self.application = None
        logger.info("HyperliquidTradingBot initialized with real API components")
    
    def setup_handlers(self):
        """Setup command handlers with real functionality only"""
        if not self.application:
            return
        
        # Core commands
        self.application.add_handler(CommandHandler("start", self.handlers.start_command))
        self.application.add_handler(CommandHandler("help", self.handlers.help_command))
        
        # Account management (real implementations)
        self.application.add_handler(CommandHandler("balance", self.handlers.balance_command))
        self.application.add_handler(CommandHandler("positions", self.handlers.positions_command))
        self.application.add_handler(CommandHandler("deposits", self.handlers.deposits_command))
        
        # Vault operations (real API calls)
        self.application.add_handler(CommandHandler("vault", self.handlers.vault_command))
        self.application.add_handler(CommandHandler("deposit", self.handlers.deposit_command))
        self.application.add_handler(CommandHandler("withdraw", self.handlers.withdraw_command))
        
        # Trading operations (real market data)
        self.application.add_handler(CommandHandler("price", self.handlers.price_command))
        self.application.add_handler(CommandHandler("orders", self.handlers.orders_command))
        self.application.add_handler(CommandHandler("buy", self.handlers.buy_command))
        self.application.add_handler(CommandHandler("sell", self.handlers.sell_command))
        
        # Strategy management (real trading)
        self.application.add_handler(CommandHandler("grid", self.handlers.grid_command))
        self.application.add_handler(CommandHandler("momentum", self.handlers.momentum_command))
        self.application.add_handler(CommandHandler("stop", self.handlers.stop_strategy_command))
        
        # Performance tracking (real data)
        self.application.add_handler(CommandHandler("stats", self.handlers.stats_command))
        self.application.add_handler(CommandHandler("fills", self.handlers.fills_command))
    
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
    
    async def update_vault_balances(self):
        """Periodic update of vault balances using real API"""
        while True:
            try:
                # Update vault balance using real Hyperliquid API
                vault_balance = await self.vault_manager.get_vault_balance()
                if vault_balance['status'] == 'success':
                    logger.info(f"Vault balance updated: ${vault_balance['total_value']:.2f}")
                
                await asyncio.sleep(60)  # Update every minute
            except Exception as e:
                logger.error(f"Error updating vault balances: {e}")
                await asyncio.sleep(60)
    
    async def monitor_trading_signals(self):
        """Monitor real trading signals"""
        while True:
            try:
                # Get real market data
                all_mids = self.info.all_mids()
                
                # Check for momentum signals on major pairs
                for coin in ['BTC', 'ETH', 'SOL']:
                    if coin in all_mids:
                        signal_result = await self.trading_engine.momentum_strategy(coin, 0.05)
                        if signal_result.get('status') == 'success':
                            logger.info(f"Momentum signal executed for {coin}")
                
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Error monitoring signals: {e}")
                await asyncio.sleep(30)
    
    def run(self):
        """Run the bot with real functionality"""
        bot_token = self.config.get_telegram_token()
        if not bot_token:
            logger.error("Bot token not found in configuration!")
            return
        
        # Validate Hyperliquid configuration
        validation = self.config.validate_hyperliquid_config()
        if not all(validation.values()):
            logger.error(f"Configuration validation failed: {validation}")
            return
        
        # Create application
        self.application = Application.builder().token(bot_token).build()
        
        # Setup handlers
        self.setup_handlers()
        
        # Start background tasks
        asyncio.create_task(self.cleanup_sessions())
        asyncio.create_task(self.update_vault_balances())
        asyncio.create_task(self.monitor_trading_signals())
        
        # Run the bot
        logger.info("Starting Hyperliquid Trading Bot with real API integration...")
        logger.info(f"Vault address: {self.config.get_vault_address()}")
        logger.info(f"Account address: {self.address}")
        logger.info(f"Network: {'mainnet' if self.config.is_mainnet() else 'testnet'}")
        
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = HyperliquidTradingBot()
    bot.run()
