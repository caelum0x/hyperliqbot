import asyncio
import logging
import os
import sys
from datetime import datetime
import time # For agent name timestamp
from typing import Dict, Any, List, Optional 

# Add project root to path for imports
project_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root_path not in sys.path:
    sys.path.insert(0, project_root_path)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from hyperliquid.utils import constants

# Import the new TelegramAuthHandler
from telegram_bot.telegram_auth_handler import TelegramAuthHandler

# Import other necessary components (adjust paths as needed)
# from trading_engine.base_trader import ProfitOptimizedTrader # If used
from trading_engine.config import TradingConfig 

logger = logging.getLogger(__name__)

class TelegramTradingBot:
    """
    Advanced Telegram trading bot integrating the new authentication system.
    """
    
    def __init__(self, token: str, config: Dict, 
                 vault_manager=None, trading_engine=None, 
                 database=None, user_manager=None, 
                 strategies=None, ws_manager=None): # Added strategies, ws_manager
        self.token = token
        self.main_config = config # Store the main application config
        
        self.vault_manager = vault_manager
        self.trading_engine = trading_engine
        self.database = database
        self.user_manager = user_manager
        self.strategies = strategies if strategies is not None else {}
        self.ws_manager = ws_manager
        
        self.user_sessions: Dict[int, Dict[str, Any]] = {}
        
        # Initialize TelegramAuthHandler
        bot_username = self.main_config.get("telegram", {}).get("bot_username", "YourBotUsername")
        hyperliquid_api_url = self.main_config.get("hyperliquid", {}).get("api_url", constants.MAINNET_API_URL)
        self.auth_handler = TelegramAuthHandler(self.user_sessions, base_url=hyperliquid_api_url, bot_username=bot_username)
        
        self.app = Application.builder().token(self.token).build()
        self.trading_config = TradingConfig() # For bot's internal trading logic parameters
        self.setup_handlers()

    def setup_handlers(self):
        """Setup all command and callback handlers"""
        # Authentication and core commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("connect", self.auth_handler.handle_connect_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("help", self.help_command))

        # User-specific commands (require auth)
        self.app.add_handler(CommandHandler("portfolio", self.portfolio_command))
        # Add other command handlers for trading, strategies, etc.

        # Callback query handlers
        self.app.add_handler(CallbackQueryHandler(self.handle_callbacks))
        # self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_messages)) # If needed

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        welcome_message = (
            "🚀 **Welcome to the Hyperliquid Trading Bot!**\n\n"
            "Securely connect your wallet to access trading features:\n"
            "➡️ Use `/connect YOUR_ETHEREUM_PRIVATE_KEY` in a private chat with me.\n\n"
            "**Features:**\n"
            "🔒 Secure agent wallet system\n"
            "📊 Portfolio tracking\n"
            "📈 Manual & Automated Trading (coming soon)\n\n"
            "Use `/help` for a list of commands."
        )
        keyboard = [
            [KeyboardButton("/connect"), KeyboardButton("/status")],
            [KeyboardButton("/portfolio"), KeyboardButton("/help")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        session_info_text = self.auth_handler.get_session_info_text(user_id)
        await update.message.reply_text(session_info_text, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "ℹ️ **Hyperliquid Bot Help**\n\n"
            "`/start` - Welcome message & main menu.\n"
            "`/connect YOUR_KEY` - Securely connect your wallet (DM only).\n"
            "`/status` - Check your current connection status.\n"
            "`/portfolio` - View your account portfolio (requires connection).\n"
            # Add more commands as they are implemented
            "`/help` - Show this help message.\n\n"
            "**Security Note:** Always send `/connect` with your private key in a direct message to the bot. "
            "The bot will delete your message containing the key for security."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        is_valid, error_message = self.auth_handler.validate_session(user_id)
        if not is_valid:
            await update.message.reply_text(error_message)
            return

        session = self.user_sessions[user_id]
        info_client = session['info']
        main_address = session['address'] # This is always the main address

        try:
            user_state = info_client.user_state(main_address)
            margin_summary = user_state.get("marginSummary", {})
            positions = user_state.get("assetPositions", [])
            
            account_value = float(margin_summary.get("accountValue", 0))
            total_pnl = float(margin_summary.get("totalUnrealizedPnl", 0)) # Using totalUnrealizedPnl
            
            portfolio_text = f"📊 **Your Portfolio (Main Address: `{main_address}`)\n\n"
            if session.get('auth_method') == 'agent':
                portfolio_text += f"🤖 Agent Address: `{session.get('agent_address')}` (Active)\n"
            portfolio_text += f"💰 Account Value: ${account_value:,.2f}\n"
            portfolio_text += f"📈 Total Unrealized P&L: ${total_pnl:+,.2f}\n\n"
            
            if positions:
                portfolio_text += "**Open Positions:**\n"
                for asset_pos_data in positions:
                    pos = asset_pos_data.get("position", {})
                    coin = pos.get("coin", "N/A")
                    size_str = pos.get("szi", "0")
                    entry_px_str = pos.get("entryPx", "0")
                    unrealized_pnl_str = pos.get("unrealizedPnl", "0")

                    try:
                        size = float(size_str)
                        entry_px = float(entry_px_str) if entry_px_str else 0.0
                        unrealized_pnl = float(unrealized_pnl_str)
                    except ValueError:
                        logger.warning(f"Could not parse position data for {coin}: size={size_str}, entryPx={entry_px_str}, pnl={unrealized_pnl_str}")
                        continue # Skip this position if data is malformed

                    if abs(size) > 1e-9: # Check if position is effectively non-zero
                        side = "📈 LONG" if size > 0 else "📉 SHORT"
                        portfolio_text += f"  `{coin}`: {side} {abs(size):.4f} @ ${entry_px:,.4f}\n"
                        portfolio_text += f"     Unrealized P&L: ${unrealized_pnl:+,.2f}\n"
            else:
                portfolio_text += "No open positions.\n"
            
            await update.message.reply_text(portfolio_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error fetching portfolio for user {user_id}: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error fetching portfolio: {str(e)}")


    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id # Get user_id from query
        data = query.data

        # Route callbacks to TelegramAuthHandler methods
        if data == f"create_agent_session_{user_id}":
            await self.auth_handler.handle_create_agent_session_callback(update, context)
        elif data == f"direct_key_session_{user_id}":
            await self.auth_handler.handle_direct_key_session_callback(update, context)
        else:
            # Handle other callbacks or acknowledge if not recognized
            await query.answer("Callback received.") 
            logger.info(f"Received unhandled callback: {data} from user {user_id}")
            # await query.edit_message_text(f"Received: {data}") # Example response

    async def run(self):
        logger.info("Telegram bot polling started...")
        self.app.run_polling()

    async def stop(self):
        logger.info("Stopping Telegram bot...")
        # Application.stop() is not an async method and is meant for specific contexts.
        # For run_polling, it's usually stopped by KeyboardInterrupt or by stopping the event loop.
        # If using run_webhook, then app.stop() would be relevant.
        # For now, logging is sufficient as the main loop will handle shutdown.
        pass
