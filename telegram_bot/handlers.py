from typing import Dict, Any, List, Set
from datetime import datetime
import logging
import asyncio
import time
import json
from uuid import uuid4

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CallbackContext, CommandHandler, MessageHandler, filters

# Import the new state manager
from telegram_bot.state_manager import StateManager, UserState

logger = logging.getLogger(__name__)

# Global allowed users cache
ALLOWED_USERS: Set[int] = set()
ADMIN_USERS: Set[int] = set()

async def is_user_authorized(user_id: int, bot) -> bool:
    """Check if the user is authorized to use the bot"""
    global ALLOWED_USERS
    
    # Always allow admin users
    if await is_admin_user(user_id, bot):
        return True
        
    # Check if user is in allowed users cache
    if user_id in ALLOWED_USERS:
        return True
    
    # Check from config
    try:
        # Check if bot has a config attribute
        if hasattr(bot, 'config') and isinstance(bot.config, dict):
            allowed_users = bot.config.get('telegram', {}).get('allowed_users', [])
            if user_id in allowed_users:
                # Add to cache for future checks
                ALLOWED_USERS.add(user_id)
                return True
                
        # For development/testing, allow all users
        return True
    except Exception as e:
        logger.error(f"Error checking user authorization: {e}")
        return False

async def is_admin_user(user_id: int, bot) -> bool:
    """Check if the user is an admin"""
    global ADMIN_USERS
    
    # Check if user is in admin cache
    if user_id in ADMIN_USERS:
        return True
    
    # Check from config
    try:
        if hasattr(bot, 'config') and isinstance(bot.config, dict):
            admin_users = bot.config.get('telegram', {}).get('admin_users', [])
            if user_id in admin_users:
                # Add to cache for future checks
                ADMIN_USERS.add(user_id)
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

class TradingHandlers:
    """Real Telegram handlers with actual Hyperliquid API integration"""
    
    def __init__(self, user_manager, vault_manager, trading_engine, grid_engine, config):
        self.user_manager = user_manager
        self.vault_manager = vault_manager
        self.trading_engine = trading_engine
        self.grid_engine = grid_engine
        self.config = config
        self.wallet_manager = None
        
        # Initialize state manager
        self.state_manager = StateManager(user_manager, trading_engine)
    
    def set_wallet_manager(self, wallet_manager):
        self.wallet_manager = wallet_manager
        # Pass wallet manager to state manager
        if hasattr(self.state_manager, 'set_wallet_manager'):
            self.state_manager.set_wallet_manager(wallet_manager)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Enhanced start command - entry point for user interaction
        Delegates to state manager for state-based handling
        """
        user_id = update.effective_user.id
        username = update.effective_user.username
        
        # Check authorization
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        # Let state manager handle the flow based on user state
        await self.state_manager.handle_start(update, context)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show agent wallet status & funding"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        await self.state_manager.show_agent_status(update, context)
    
    async def fund_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show funding instructions"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        await self.state_manager.show_funding_instructions(update, context)
    
    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show personal positions & P&L"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        await self.state_manager.show_portfolio(update, context)
    
    async def strategies_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List available strategies"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        await self.state_manager.show_strategy_selection(update, context)
    
    async def trade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start specific strategy"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        # Check if a strategy name was provided
        if context.args:
            strategy_name = context.args[0].lower()
            await self.state_manager.handle_strategy_selection(update, context, strategy_name)
        else:
            await self.strategies_command(update, context)
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop all trading"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        await self.state_manager.stop_trading(update, context)
    
    async def hyperevm_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """HyperEVM opportunities"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        await update.message.reply_text(
            "🚀 **HyperEVM Opportunities**\n\n"
            "HyperEVM trading opportunities will be coming soon!\n\n"
            "Stay tuned for updates on this exciting new feature.",
            parse_mode='Markdown'
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User configuration"""
        user_id = update.effective_user.id
        
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
            
        await self.state_manager.show_settings(update, context)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information"""
        help_msg = """
🤖 **Hyperliquid Alpha Bot Commands**

**Getting Started:**
• `/start` - Register and begin setup process
• `/status` - Check wallet status and balance
• `/fund` - Show funding instructions

**Trading:**
• `/portfolio` - View your positions and P&L
• `/strategies` - List available trading strategies
• `/trade [strategy]` - Start specific strategy
• `/stop` - Stop all trading activities

**Advanced:**
• `/hyperevm` - HyperEVM opportunities
• `/settings` - Adjust your preferences

**Support:**
• Contact support for assistance
• All trades executed via secure agent wallets
        """
        await update.message.reply_text(help_msg, parse_mode='Markdown')
    
    async def price_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current prices"""
        if self.trading_engine:
            try:
                mids = await self.trading_engine.get_all_mids()
                if mids:
                    price_msg = "💰 **Current Prices:**\n\n"
                    for coin, price in list(mids.items())[:10]:  # Show top 10
                        price_msg += f"• {coin}: ${float(price):,.2f}\n"
                    await update.message.reply_text(price_msg, parse_mode='Markdown')
                else:
                    await update.message.reply_text("❌ Unable to fetch prices")
            except Exception as e:
                await update.message.reply_text(f"❌ Error fetching prices: {e}")
        else:
            await update.message.reply_text("❌ Trading engine not available")
    
    # Text input handlers
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command text messages"""
        user_id = update.effective_user.id
        message_text = update.message.text
        
        # Check authorization
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        # Let the state manager handle text input based on user state
        await self.state_manager.handle_text_input(update, context)
    
    # Callback handlers for interactive buttons
    async def handle_callbacks(self, update: Update, context: CallbackContext) -> None:
        """Handle callback queries"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        # Check authorization
        if not await is_user_authorized(user_id, context.bot):
            await query.answer("❌ You are not authorized to use this bot.")
            return
            
        await query.answer()
        
        # Forward all callbacks to state manager
        await self.state_manager.handle_callback(update, context)
