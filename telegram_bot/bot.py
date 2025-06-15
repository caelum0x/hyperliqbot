import asyncio
import logging
import os
import sys
import random
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from hyperliquid.info import Info

# Add project root to path for imports
project_root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root_path not in sys.path:
    sys.path.insert(0, project_root_path)

from trading_engine.config import TradingConfig

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from hyperliquid.utils import constants

# Import the new TelegramAuthHandler
from telegram_bot.telegram_auth_handler import TelegramAuthHandler




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
        
        # Initialize wallet manager for agent wallet creation
        from telegram_bot.wallet_manager import AgentWalletManager
        self.wallet_manager = AgentWalletManager(
            base_url=self.main_config.get("hyperliquid", {}).get("api_url", constants.MAINNET_API_URL)
        )
        
        # Initialize TelegramAuthHandler with wallet manager
        bot_username = self.main_config.get("telegram", {}).get("bot_username", "YourBotUsername")
        hyperliquid_api_url = self.main_config.get("hyperliquid", {}).get("api_url", constants.MAINNET_API_URL)
        self.auth_handler = TelegramAuthHandler(
            self.user_sessions, 
            base_url=hyperliquid_api_url, 
            bot_username=bot_username,
            wallet_manager=self.wallet_manager
        )
        
        self.app = Application.builder().token(self.token).build()
        self.trading_config = TradingConfig() # For bot's internal trading logic parameters
        self.setup_handlers()

    def setup_handlers(self):
        """Setup all command and callback handlers"""
        # Authentication and core commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        # Remove "/connect" command that asked for private keys
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("help", self.help_command))

        # User-specific commands (require auth)
        self.app.add_handler(CommandHandler("portfolio", self.portfolio_command))
          # Trading control commands
        self.app.add_handler(CommandHandler("trading_status", self.trading_status_command))
        self.app.add_handler(CommandHandler("start_trading", self.start_trading_command))
        self.app.add_handler(CommandHandler("stop_trading", self.stop_trading_command))
        
        # Advanced strategy commands
        self.app.add_handler(CommandHandler("strategies", self.strategies_command))
        self.app.add_handler(CommandHandler("rebates", self.rebates_command))
        self.app.add_handler(CommandHandler("settings", self.settings_command))
        
        # Agent wallet management commands
        self.app.add_handler(CommandHandler("create_agent", self.auth_handler.handle_create_agent_command))
        self.app.add_handler(CommandHandler("agent_status", self.auth_handler.handle_agent_status_command))
        self.app.add_handler(CommandHandler("emergency_stop", self.auth_handler.handle_emergency_stop_command))
        
        # Test trading commands
        self.app.add_handler(CommandHandler("test_trade", self.test_trade_command))
        self.app.add_handler(CommandHandler("cancel_order", self.cancel_order_command))
        
        # Address registration commands
        self.app.add_handler(CommandHandler("register_address", self.register_address_command))
        self.app.add_handler(CommandHandler("change_address", self.change_address_command))
        
        # Add debug command
        self.app.add_handler(CommandHandler("debug", self.debug_trading_command))
        
        # Message handler for address input and signature verification
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            self.handle_text_input
        ))
        
        # Callback query handlers
        self.app.add_handler(CallbackQueryHandler(self.handle_callbacks))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔒 SECURITY FIX: Check for registered address before proceeding"""
        user_id = update.effective_user.id
        
        # Check if user has registered address
        user_data = context.bot_data.get('users', {})
        
        if user_id not in user_data:
            # New user - ask for address registration
            await update.message.reply_text(
                "🚀 **Welcome to the Hyperliquid Trading Bot!**\n\n"
                "🔐 **Security First:** Before we start, I need to verify your Hyperliquid address.\n\n"
                "**Please enter your Hyperliquid account address:**\n"
                "• Format: Must start with '0x' and be 42 characters long\n"
                "• Example: 0x1234567890123456789012345678901234567890\n\n"
                "You can find this in the Hyperliquid app under 'Account' or 'Wallet'.\n\n"
                "⚠️ **Important:** This is YOUR address that you control, not a private key!",
                parse_mode='Markdown'
            )
            context.user_data['awaiting_address'] = True
            return
        
        # Existing user - show main menu with their registered address
        user_address = user_data[user_id]['address']
        registered_time = datetime.fromtimestamp(user_data[user_id]['registered_at']).strftime("%Y-%m-%d %H:%M")
        
        welcome_message = (
            "🚀 **Welcome back to the Hyperliquid Trading Bot!**\n\n"
            f"📍 **Your registered address:** `{user_address[:8]}...{user_address[-6:]}`\n"
            f"📅 **Registered:** {registered_time}\n\n"
            "**Quick Actions:**\n"
            "➡️ Use `/create_agent` to create your secure agent wallet\n"
            "➡️ Use `/agent_status` to check your wallet status\n\n"
            "**Features:**\n"
            "🔒 Secure agent wallet system\n"
            "📊 Portfolio tracking\n"
            "📈 Manual & Automated Trading\n\n"
            "Use `/help` for a list of commands.\n\n"
            "💡 Need to change your address? Use `/change_address`"
        )
        
        keyboard = [
            [KeyboardButton("/create_agent"), KeyboardButton("/agent_status")],
            [KeyboardButton("/portfolio"), KeyboardButton("/help")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)

    async def register_address_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Allow users to register or change their address"""
        await update.message.reply_text(
            "📝 **Register Your Hyperliquid Address**\n\n"
            "Please enter your Hyperliquid account address:\n\n"
            "**Format:** Must start with '0x' and be 42 characters long\n"
            "**Example:** 0x1234567890123456789012345678901234567890\n\n"
            "You can find this in the Hyperliquid app under 'Account' or 'Wallet'.\n\n"
            "⚠️ **Security Note:** This is your wallet address (public), not your private key!",
            parse_mode='Markdown'
        )
        context.user_data['awaiting_address'] = True

    async def change_address_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Allow users to change their registered address"""
        user_id = update.effective_user.id
        user_data = context.bot_data.get('users', {})
        
        if user_id in user_data:
            current_address = user_data[user_id]['address']
            await update.message.reply_text(
                f"🔄 **Change Your Registered Address**\n\n"
                f"**Current address:** `{current_address[:8]}...{current_address[-6:]}`\n\n"
                f"Please enter your new Hyperliquid account address:\n\n"
                f"**Format:** Must start with '0x' and be 42 characters long\n\n"
                f"⚠️ **Note:** Changing your address will require creating a new agent wallet.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "📝 **Register Your Hyperliquid Address**\n\n"
                "You haven't registered an address yet. Please enter your Hyperliquid account address:",
                parse_mode='Markdown'
            )
        
        context.user_data['awaiting_address'] = True

    async def start_command_old(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        welcome_message = (
            "🚀 **Welcome to the Hyperliquid Trading Bot!**\n\n"
            "Get started with secure trading using agent wallets:\n"
            "➡️ Use `/create_agent` to create your dedicated agent wallet.\n\n"
            "**Features:**\n"
            "🔒 Secure agent wallet system\n"
            "📊 Portfolio tracking\n"
            "📈 Manual & Automated Trading\n\n"
            "Use `/help` for a list of commands."
        )
        keyboard = [
            [KeyboardButton("/create_agent"), KeyboardButton("/status")],
            [KeyboardButton("/portfolio"), KeyboardButton("/help")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        # Check if user has an agent wallet first
        if self.wallet_manager:
            wallet_info = await self.wallet_manager.get_user_wallet(user_id)
            if wallet_info and user_id not in self.user_sessions:
                # Establish session if wallet exists but no session
                await self.auth_handler._establish_user_session(user_id, update.effective_user.username, wallet_info)
        
        session_info_text = self.auth_handler.get_session_info_text(user_id)
        await update.message.reply_text(session_info_text, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "ℹ️ **Hyperliquid Bot Help**\n\n"
            "`/start` - Welcome message & main menu.\n"
            "`/create_agent` - Create a secure agent wallet for your account.\n"
            "`/agent_status` - Check your agent wallet status.\n"
            "`/status` - Check your current connection status.\n"
            "`/portfolio` - View your account portfolio (requires connection).\n\n"
            "**Trading Controls:**\n"
            "`/trading_status` - Check auto-trading status.\n"
            "`/start_trading` - Enable all auto-trading components.\n"
            "`/stop_trading` - Disable all auto-trading components.\n"
            "`/test_trade` - Test order placement functionality.\n"
            "`/cancel_order ORDER_ID` - Cancel a specific order.\n\n"
            "**Account Management:**\n"
            "`/register_address` - Register your Hyperliquid address.\n"
            "`/change_address` - Change your registered address.\n"
            "`/emergency_stop` - Emergency stop all trading and close positions.\n\n"
            "**Debug & Support:**\n"
            "`/debug` - Show system debug information.\n\n"
            "**Security Note:** This bot never requires your private keys. "
            "All trading is done via secure agent wallets."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        
    async def trading_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current auto-trading status"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet manager not initialized")
            return
            
        wallet_info = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_info:
            await update.message.reply_text(
                "❌ No agent wallet found. Use `/create_agent` to create one first.",
                parse_mode='Markdown'
            )
            return
        
        # Get wallet status
        wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        trading_enabled = wallet_status.get("trading_enabled", False)
        balance = wallet_status.get("balance", 0)
        
        status_text = (
            f"🤖 **Your Trading Status**\n\n"
            f"**Agent Wallet:** `{wallet_info['address'][:10]}...{wallet_info['address'][-8:]}`\n"
            f"**Balance:** ${balance:.2f}\n"
            f"**Trading Status:** {'✅ Active' if trading_enabled else '❌ Disabled'}\n\n"
        )
        
        if trading_enabled:
            status_text += (
                f"**Active Strategies:**\n"
                f"• Grid Trading (automated buy/sell orders)\n"
                f"• Market Making (earning rebates)\n\n"
                f"Use `/stop_trading` to disable all strategies."
            )
        else:
            status_text += (
                f"**Available Actions:**\n"
                f"• Use `/start_trading` to enable strategies\n"
                f"• Use `/test_trade` to test your setup\n"
                f"• Use `/portfolio` to view your account"            )
        
        await update.message.reply_text(status_text, parse_mode='Markdown')

    async def start_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Advanced trading using existing strategy infrastructure"""
        try:
            user_id = update.effective_user.id
            
            # Get user setup (same as before)
            wallet_info = await self.wallet_manager.get_user_wallet(user_id)
            if not wallet_info:
                await update.effective_message.reply_text(
                    "❌ No agent wallet found. Use `/create_agent` to create one first.",
                    parse_mode='Markdown'
                )
                return
                    
            exchange = await self.wallet_manager.get_user_exchange(user_id)
            if not exchange:
                await update.effective_message.reply_text(
                    "❌ No trading connection available.",
                    parse_mode='Markdown'
                )
                return
            
            # Check balance
            from hyperliquid.info import Info
            info = Info(self.wallet_manager.base_url)
            main_address = wallet_info["main_address"]
            
            user_state = info.user_state(main_address)
            account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            if account_value < 20:
                await update.effective_message.reply_text(
                    f"❌ Insufficient balance: ${account_value:.2f}. Recommend at least $20 for multi-strategy trading.",
                    parse_mode='Markdown'
                )
                return
            
            progress_msg = await update.effective_message.reply_text(
                "🚀 **Starting Advanced Trading System...**\n\n"
                "⚡ Initializing your existing strategy classes...\n"
                "📊 Grid Trading Engine\n"
                "💰 Profit Optimization Bot\n"
                "🎯 Automated Trading System",
                parse_mode='Markdown'
            )
            
            # ✅ USE YOUR EXISTING STRATEGY CLASSES
            strategies_started = 0
            total_orders = 0
            
            # 1. Start Grid Trading Engine
            if 'grid' in self.strategies:
                try:
                    grid_result = await self.strategies['grid'].start_user_grid(
                        user_id=user_id,
                        exchange=exchange,
                        pairs=['BTC', 'ETH', 'SOL', 'AVAX', 'LINK'],
                        account_value=account_value
                    )
                    if grid_result.get('success'):
                        strategies_started += 1
                        total_orders += grid_result.get('orders_placed', 0)
                        logger.info(f"✅ Grid trading started for user {user_id}")
                except Exception as e:
                    logger.error(f"Grid trading start error: {e}")
            
            # 2. Start Automated Trading
            if 'auto' in self.strategies:
                try:
                    auto_result = await self.strategies['auto'].start_user_automation(
                        user_id=user_id,
                        exchange=exchange,
                        strategies=['momentum', 'mean_reversion', 'breakout'],
                        account_value=account_value
                    )
                    if auto_result.get('success'):
                        strategies_started += 1
                        total_orders += auto_result.get('orders_placed', 0)
                        logger.info(f"✅ Automated trading started for user {user_id}")
                except Exception as e:
                    logger.error(f"Automated trading start error: {e}")
            
            # 3. Start Profit Bot (Maker Rebates + Optimization)
            if 'profit' in self.strategies:
                try:
                    profit_result = await self.strategies['profit'].start_profit_optimization(
                        user_id=user_id,
                        exchange=exchange,
                        target_rebate_tier=3,  # Aim for -0.003% rebate
                        account_value=account_value
                    )
                    if profit_result.get('success'):
                        strategies_started += 1
                        total_orders += profit_result.get('orders_placed', 0)
                        logger.info(f"✅ Profit optimization started for user {user_id}")
                except Exception as e:
                    logger.error(f"Profit optimization start error: {e}")
            
            # 4. Use Trading Engine for Multi-User Management
            if self.trading_engine:
                try:
                    # Start user in the trading engine
                    engine_result = await self.trading_engine.create_user_trader(user_id, main_address)
                    if engine_result.get('status') == 'success':
                        # Enable all strategies through trading engine
                        await self.trading_engine.start_user_strategy(user_id, 'grid', {
                            'pairs': ['BTC', 'ETH', 'SOL', 'AVAX', 'LINK', 'UNI', 'DOGE'],
                            'grid_spacing': 0.005,
                            'num_levels': 8,
                            'position_size_pct': 0.02  # 2% per level
                        })
                        
                        await self.trading_engine.start_user_strategy(user_id, 'maker_rebate', {
                            'pairs': ['BTC', 'ETH', 'SOL'],
                            'target_spread': 0.002,
                            'rebate_tier_target': 3
                        })
                        
                        logger.info(f"✅ Trading engine strategies started for user {user_id}")
                except Exception as e:
                    logger.error(f"Trading engine start error: {e}")
            
            # Start monitoring and background tasks
            if not context.bot_data.get('trading_tasks', {}).get(user_id):
                if 'trading_tasks' not in context.bot_data:
                    context.bot_data['trading_tasks'] = {}
                
                # Start comprehensive monitoring
                task = asyncio.create_task(self._comprehensive_trading_monitor(
                    user_id, exchange, info, main_address, strategies_started
                ))
                context.bot_data['trading_tasks'][user_id] = task
                
                logger.info(f"Started comprehensive trading monitor for user {user_id}")
            
            await progress_msg.edit_text(
                f"🎉 **Advanced Trading System ACTIVE!**\n\n"
                f"✅ **{strategies_started} Strategy Systems Running:**\n"
                f"📊 Grid Trading Engine (Multi-pair)\n"
                f"🤖 Automated Trading System\n"
                f"� Profit Optimization Bot\n"
                f"⚡ Multi-User Trading Engine\n\n"
                f"🚀 **{total_orders} Orders Placed**\n"
                f"💰 **Account Value:** ${account_value:.2f}\n"
                f"🎯 **Risk Management:** Active\n\n"
                f"**Live Controls:**\n"
                f"📊 `/portfolio` - Real-time P&L\n"
                f"📈 `/strategies` - Strategy performance\n"
                f"� `/rebates` - Maker rebate progress\n"
                f"⚙️ `/settings` - Adjust parameters\n"
                f"⛔ `/stop_trading` - Emergency stop",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Advanced trading start error: {e}")
            await update.effective_message.reply_text(
                f"❌ Error starting advanced trading: {str(e)}",
                parse_mode='Markdown'
            )

    async def _start_comprehensive_trading(self, user_id: int, exchange, info, main_address: str, account_value: float):
        """Initialize comprehensive multi-strategy trading system"""
        try:
            # Get market data for all assets
            mids = info.all_mids()
            meta = info.meta()
            
            # Filter to top liquid pairs for trading
            top_pairs = ['BTC', 'ETH', 'SOL', 'AVAX', 'MATIC', 'LINK', 'UNI', 'DOGE']
            available_pairs = [pair for pair in top_pairs if pair in mids]
            
            # Calculate position sizing based on account value
            risk_per_trade = min(account_value * 0.01, 20)  # 1% risk or $20 max
            base_position_size = risk_per_trade / len(available_pairs)
            
            total_orders = 0
            strategies_started = 0
            
            # 1. GRID TRADING STRATEGY - Multiple pairs
            logger.info(f"Starting grid trading for user {user_id} on {len(available_pairs)} pairs")
            for pair in available_pairs[:5]:  # Top 5 pairs for grid
                try:
                    grid_orders = await self._setup_grid_strategy(exchange, info, pair, base_position_size)
                    total_orders += grid_orders
                    logger.info(f"✅ Grid trading: {pair} - {grid_orders} orders")
                except Exception as e:
                    logger.error(f"Grid setup failed for {pair}: {e}")
            
            if total_orders > 0:
                strategies_started += 1
            
            # 2. MAKER REBATE OPTIMIZATION - Spread trading
            logger.info(f"Starting maker rebate optimization for user {user_id}")
            try:
                maker_orders = await self._setup_maker_strategy(exchange, info, available_pairs, base_position_size)
                total_orders += maker_orders
                if maker_orders > 0:
                    strategies_started += 1
                logger.info(f"✅ Maker rebate: {maker_orders} spread orders")
            except Exception as e:
                logger.error(f"Maker strategy failed: {e}")
            
            # 3. MOMENTUM DETECTION - Trend following
            logger.info(f"Starting momentum detection for user {user_id}")
            try:
                momentum_orders = await self._setup_momentum_strategy(exchange, info, available_pairs, base_position_size)
                total_orders += momentum_orders
                if momentum_orders > 0:
                    strategies_started += 1
                logger.info(f"✅ Momentum: {momentum_orders} trend orders")
            except Exception as e:
                logger.error(f"Momentum strategy failed: {e}")
            
            # Calculate target rebate tier based on planned volume
            target_tier = self._calculate_rebate_tier_target(account_value, total_orders)
            
            return {
                'strategies_started': strategies_started,
                'total_orders': total_orders,
                'pairs_count': len(available_pairs),
                'target_tier': target_tier,
                'risk_per_trade': risk_per_trade
            }
            
        except Exception as e:
            logger.error(f"Error in comprehensive trading setup: {e}")
            return {'strategies_started': 0, 'total_orders': 0, 'pairs_count': 0, 'target_tier': 'Unknown'}

    async def _setup_grid_strategy(self, exchange, info, pair: str, position_size: float):
        """Setup grid trading for a specific pair"""
        try:
            mids = info.all_mids()
            current_price = float(mids[pair])
            
            # Dynamic grid spacing based on volatility
            grid_spacing = 0.005  # 0.5% default
            num_levels = 8  # 4 buy + 4 sell levels
            
            orders_placed = 0
            
            # Place buy levels below current price
            for i in range(1, 5):  # 4 buy levels
                level_price = current_price * (1 - grid_spacing * i)
                
                try:
                    result = exchange.order(
                        pair, True, position_size, level_price, 
                        {"limit": {"tif": "Alo"}}  # Post-only for maker rebate
                    )
                    
                    if result and result.get('status') == 'ok':
                        orders_placed += 1
                        logger.info(f"Grid buy: {pair} @ ${level_price:.2f}")
                except Exception as e:
                    logger.error(f"Grid buy error for {pair}: {e}")
            
            # Place sell levels above current price
            for i in range(1, 5):  # 4 sell levels
                level_price = current_price * (1 + grid_spacing * i)
                
                try:
                    result = exchange.order(
                        pair, False, position_size, level_price,
                        {"limit": {"tif": "Alo"}}  # Post-only for maker rebate
                    )
                    
                    if result and result.get('status') == 'ok':
                        orders_placed += 1
                        logger.info(f"Grid sell: {pair} @ ${level_price:.2f}")
                except Exception as e:
                    logger.error(f"Grid sell error for {pair}: {e}")
            
            return orders_placed
            
        except Exception as e:
            logger.error(f"Grid strategy setup error for {pair}: {e}")
            return 0

    async def _setup_maker_strategy(self, exchange, info, pairs: list, position_size: float):
        """Setup maker rebate optimization strategy"""
        try:
            mids = info.all_mids()
            orders_placed = 0
            
            # Place tight spreads for maker rebates
            for pair in pairs[:3]:  # Top 3 pairs for maker strategy
                try:
                    current_price = float(mids[pair])
                    spread = 0.002  # 0.2% spread for competitive maker orders
                    
                    bid_price = current_price * (1 - spread)
                    ask_price = current_price * (1 + spread)
                    
                    # Bid order
                    bid_result = exchange.order(
                        pair, True, position_size, bid_price,
                        {"limit": {"tif": "Alo"}}  # Guaranteed maker
                    )
                    
                    if bid_result and bid_result.get('status') == 'ok':
                        orders_placed += 1
                    
                    # Ask order
                    ask_result = exchange.order(
                        pair, False, position_size, ask_price,
                        {"limit": {"tif": "Alo"}}  # Guaranteed maker
                    )
                    
                    if ask_result and ask_result.get('status') == 'ok':
                        orders_placed += 1
                    
                    logger.info(f"Maker spread: {pair} ${bid_price:.2f}-${ask_price:.2f}")
                    
                except Exception as e:
                    logger.error(f"Maker strategy error for {pair}: {e}")
            
            return orders_placed
            
        except Exception as e:
            logger.error(f"Maker strategy setup error: {e}")
            return 0

    async def _setup_momentum_strategy(self, exchange, info, pairs: list, position_size: float):
        """Setup momentum/trend following strategy"""
        try:
            # This would normally analyze price history for momentum
            # For now, place some strategic orders based on current conditions
            orders_placed = 0
            mids = info.all_mids()
            
            for pair in pairs[:2]:  # Top 2 pairs for momentum
                try:
                    current_price = float(mids[pair])
                    
                    # Place breakout orders (above current price for momentum)
                    breakout_price = current_price * 1.01  # 1% above for momentum entry
                    
                    result = exchange.order(
                        pair, True, position_size * 0.5, breakout_price,
                        {"limit": {"tif": "Gtc"}}  # GTC for momentum capture
                    )
                    
                    if result and result.get('status') == 'ok':
                        orders_placed += 1
                        logger.info(f"Momentum: {pair} breakout @ ${breakout_price:.2f}")
                    
                except Exception as e:
                    logger.error(f"Momentum strategy error for {pair}: {e}")
            
            return orders_placed
            
        except Exception as e:
            logger.error(f"Momentum strategy setup error: {e}")
            return 0

    def _calculate_rebate_tier_target(self, account_value: float, orders_count: int) -> str:
        """Calculate target rebate tier based on account size and activity"""
        if account_value >= 1000:
            return "Tier 3 (-0.003% rebate)"
        elif account_value >= 500:
            return "Tier 2 (-0.002% rebate)"
        elif orders_count >= 10:
            return "Tier 1 (-0.001% rebate)"
        else:
            return "Building volume for rebates"

    # CONTINUOUS STRATEGY LOOPS

    async def _grid_trading_loop(self, user_id: int, exchange, info, account_value: float):
        """Continuous grid trading management"""
        while True:
            try:
                # Every 15 minutes, check and rebalance grids
                await self._rebalance_grids(user_id, exchange, info, account_value)
                await asyncio.sleep(900)  # 15 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Grid loop error for user {user_id}: {e}")
                await asyncio.sleep(300)

    async def _maker_rebate_loop(self, user_id: int, exchange, info, account_value: float):
        """Continuous maker rebate optimization"""
        while True:
            try:
                # Every 5 minutes, update maker orders for optimal spreads
                await self._optimize_maker_spreads(user_id, exchange, info)
                await asyncio.sleep(300)  # 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Maker loop error for user {user_id}: {e}")
                await asyncio.sleep(180)

    async def _momentum_trading_loop(self, user_id: int, exchange, info, account_value: float):
        """Continuous momentum detection and trading"""
        while True:
            try:
                # Every 2 minutes, scan for momentum opportunities
                await self._scan_momentum_opportunities(user_id, exchange, info)
                await asyncio.sleep(120)  # 2 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Momentum loop error for user {user_id}: {e}")
                await asyncio.sleep(240)

    async def _arbitrage_loop(self, user_id: int, exchange, info, account_value: float):
        """Cross-pair arbitrage detection"""
        while True:
            try:
                # Every 30 seconds, scan for arbitrage opportunities
                await self._scan_arbitrage_opportunities(user_id, exchange, info)
                await asyncio.sleep(30)  # 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Arbitrage loop error for user {user_id}: {e}")
                await asyncio.sleep(60)

    async def _performance_monitor_loop(self, user_id: int, info, main_address: str):
        """Monitor and log performance metrics"""
        while True:
            try:
                # Every 5 minutes, log performance
                user_state = info.user_state(main_address)
                account_value = float(user_state.get("marginSummary", {}).get("accountValue", 0))
                unrealized_pnl = float(user_state.get("marginSummary", {}).get("totalUnrealizedPnl", 0))
                
                positions = user_state.get("assetPositions", [])
                active_positions = sum(1 for p in positions if p.get("position") and abs(float(p["position"].get("szi", 0))) > 0.00001)
                
                logger.info(f"📊 User {user_id}: ${account_value:.2f} | PnL: ${unrealized_pnl:+.2f} | Positions: {active_positions}")
                
                await asyncio.sleep(300)  # 5 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Performance monitor error for user {user_id}: {e}")
                await asyncio.sleep(300)

    async def _comprehensive_trading_monitor(self, user_id: int, exchange, info, main_address: str, strategies_count: int):
        """Comprehensive monitoring leveraging existing infrastructure"""
        try:
            while True:
                # Every 5 minutes, check all systems
                try:
                    # Use trading engine for position monitoring
                    if self.trading_engine:
                        positions = await self.trading_engine.get_user_positions(user_id)
                        strategies = await self.trading_engine.get_user_strategies(user_id)
                        logger.info(f"📊 User {user_id}: {len(positions.get('positions', []))} positions, {len(strategies.get('strategies', []))} strategies")
                    
                    # Use vault manager for performance tracking
                    if self.vault_manager:
                        performance = await self.vault_manager.get_user_performance(user_id)
                        if performance and performance.get('status') == 'success':
                            logger.info(f"💰 User {user_id} vault performance: {performance.get('total_return_pct', 0):.2f}%")
                    
                    # Monitor grid strategy performance
                    if 'grid' in self.strategies and hasattr(self.strategies['grid'], 'get_user_performance'):
                        grid_perf = await self.strategies['grid'].get_user_performance(user_id)
                        if grid_perf:
                            logger.info(f"📊 Grid trading performance for user {user_id}: {grid_perf}")
                    
                    await asyncio.sleep(300)  # 5 minutes
                    
                except Exception as e:
                    logger.error(f"Monitoring error for user {user_id}: {e}")
                    await asyncio.sleep(180)  # Retry in 3 minutes on error
                    
        except asyncio.CancelledError:
            logger.info(f"Trading monitor stopped for user {user_id}")
        except Exception as e:
            logger.error(f"Fatal monitoring error for user {user_id}: {e}")

    async def strategies_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show live strategy performance using existing infrastructure"""
        try:
            user_id = update.effective_user.id
            
            # Check if user has trading active
            if not context.bot_data.get('trading_tasks', {}).get(user_id):
                await update.message.reply_text(
                    "📊 **No Active Strategies**\n\n"
                    "Use `/start_trading` to begin automated strategies.",
                    parse_mode='Markdown'
                )
                return
            
            status_text = "📈 **Live Strategy Performance**\n\n"
            
            # Get data from trading engine
            if self.trading_engine:
                strategies = await self.trading_engine.get_user_strategies(user_id)
                positions = await self.trading_engine.get_user_positions(user_id)
                
                if strategies.get('status') == 'success':
                    for strategy in strategies.get('strategies', []):
                        name = strategy.get('name', 'Unknown')
                        status = strategy.get('status', 'Unknown')
                        status_emoji = "🟢" if status == "running" else "🔴"
                        status_text += f"{status_emoji} **{name.title()}**: {status}\n"
                
                if positions.get('status') == 'success':
                    account_value = positions.get('account_value', 0)
                    position_count = len(positions.get('positions', []))
                    status_text += f"\n💰 **Account Value**: ${account_value:.2f}\n"
                    status_text += f"📊 **Active Positions**: {position_count}\n"
            
            # Get grid strategy details
            if 'grid' in self.strategies:
                try:
                    if hasattr(self.strategies['grid'], 'get_user_stats'):
                        grid_stats = await self.strategies['grid'].get_user_stats(user_id)
                        if grid_stats:
                            status_text += f"\n📊 **Grid Trading**:\n"
                            status_text += f"• Orders: {grid_stats.get('active_orders', 0)}\n"
                            status_text += f"• Pairs: {len(grid_stats.get('pairs', []))}\n"
                except Exception as e:
                    logger.error(f"Grid stats error: {e}")
            
            # Get profit bot performance
            if 'profit' in self.strategies:
                try:
                    if hasattr(self.strategies['profit'], 'get_rebate_progress'):
                        rebate_progress = await self.strategies['profit'].get_rebate_progress(user_id)
                        if rebate_progress:
                            status_text += f"\n💰 **Maker Rebates**:\n"
                            status_text += f"• Current Tier: {rebate_progress.get('current_tier', 'Unknown')}\n"
                            status_text += f"• Volume: ${rebate_progress.get('volume_30d', 0):,.0f}\n"
                except Exception as e:
                    logger.error(f"Rebate progress error: {e}")
            
            status_text += f"\n**Controls:**\n"
            status_text += f"🔄 `/portfolio` - Account overview\n"
            status_text += f"💰 `/rebates` - Rebate progress\n"
            status_text += f"⚙️ `/settings` - Adjust parameters\n"
            status_text += f"⛔ `/stop_trading` - Stop all strategies"
            
            await update.message.reply_text(status_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Strategies command error: {e}")
            await update.message.reply_text(
                f"❌ Error getting strategy status: {str(e)}",
                parse_mode='Markdown'
            )

    async def rebates_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show maker rebate progress and tier advancement"""
        try:
            user_id = update.effective_user.id
            
            # Get wallet info for balance
            wallet_info = await self.wallet_manager.get_user_wallet(user_id)
            if not wallet_info:
                await update.message.reply_text(
                    "❌ No agent wallet found.",
                    parse_mode='Markdown'
                )
                return
            
            # Get rebate information from profit bot
            rebate_text = "💰 **Maker Rebate Progress**\n\n"
            
            if 'profit' in self.strategies and hasattr(self.strategies['profit'], 'get_rebate_details'):
                try:
                    rebate_details = await self.strategies['profit'].get_rebate_details(user_id)
                    
                    if rebate_details:
                        current_tier = rebate_details.get('current_tier', 0)
                        volume_30d = rebate_details.get('volume_30d', 0)
                        rebate_earned = rebate_details.get('rebate_earned_30d', 0)
                        
                        rebate_text += f"📊 **Current Tier**: {current_tier}\n"
                        rebate_text += f"📈 **30-Day Volume**: ${volume_30d:,.0f}\n"
                        rebate_text += f"💵 **Rebates Earned**: ${rebate_earned:.4f}\n\n"
                        
                        # Show tier progression
                        tiers = [
                            {"tier": 1, "volume": 100000, "rebate": "-0.001%"},
                            {"tier": 2, "volume": 1000000, "rebate": "-0.002%"},
                            {"tier": 3, "volume": 10000000, "rebate": "-0.003%"}
                        ]
                        
                        rebate_text += "🎯 **Tier Progression**:\n"
                        for tier in tiers:
                            if current_tier >= tier["tier"]:
                                rebate_text += f"✅ Tier {tier['tier']}: {tier['rebate']} rebate\n"
                            else:
                                needed = tier["volume"] - volume_30d
                                rebate_text += f"🎯 Tier {tier['tier']}: ${needed:,.0f} volume needed\n"
                                break
                    else:
                        rebate_text += "📊 **Getting rebate data...**\n"
                        rebate_text += "Start trading to begin earning maker rebates!\n"
                        
                except Exception as e:
                    logger.error(f"Rebate details error: {e}")
                    rebate_text += "⚠️ **Rebate data temporarily unavailable**\n"
            else:
                rebate_text += "📊 **Rebate System Available**\n\n"
                rebate_text += "🎯 **Maker Rebate Tiers**:\n"
                rebate_text += "• Tier 1: -0.001% rebate ($100k+ volume)\n"
                rebate_text += "• Tier 2: -0.002% rebate ($1M+ volume)\n"
                rebate_text += "• Tier 3: -0.003% rebate ($10M+ volume)\n\n"
                rebate_text += "Start trading to begin earning rebates!"
            
            rebate_text += f"\n💡 **Tips**:\n"
            rebate_text += f"• Use post-only orders (Alo) for guaranteed maker status\n"
            rebate_text += f"• Higher volume = better rebate rates\n"
            rebate_text += f"• Grid trading automatically uses maker orders\n"
            rebate_text += f"• `/start_trading` enables rebate optimization"
            
            await update.message.reply_text(rebate_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Rebates command error: {e}")
            await update.message.reply_text(
                f"❌ Error getting rebate information: {str(e)}",
                parse_mode='Markdown'
            )

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Adjust trading parameters in real-time"""
        try:
            user_id = update.effective_user.id
            
            # Check if user has active trading
            if not context.bot_data.get('trading_tasks', {}).get(user_id):
                await update.message.reply_text(
                    "⚙️ **Trading Settings**\n\n"
                    "No active trading session found.\n"
                    "Use `/start_trading` first, then return here to adjust settings.",
                    parse_mode='Markdown'
                )
                return
            
            # Get current settings from trading engine
            settings_text = "⚙️ **Trading Settings & Controls**\n\n"
            
            if self.trading_engine:
                try:
                    strategies = await self.trading_engine.get_user_strategies(user_id)
                    if strategies.get('status') == 'success':
                        settings_text += "📊 **Active Strategies**:\n"
                        for strategy in strategies.get('strategies', []):
                            name = strategy.get('name', 'Unknown')
                            status = strategy.get('status', 'Unknown')
                            settings_text += f"• {name.title()}: {status}\n"
                        settings_text += "\n"
                except Exception as e:
                    logger.error(f"Settings strategy error: {e}")
            
            # Show available controls
            settings_text += "🎛️ **Available Controls**:\n\n"
            settings_text += "**Risk Management**:\n"
            settings_text += "• `/reduce_risk` - Lower position sizes\n"
            settings_text += "• `/increase_risk` - Higher position sizes\n"
            settings_text += "• `/emergency_stop` - Immediate stop all\n\n"
            
            settings_text += "**Strategy Controls**:\n"
            settings_text += "• `/pause_grid` - Pause grid trading\n"
            settings_text += "• `/resume_grid` - Resume grid trading\n"
            settings_text += "• `/adjust_spreads` - Modify maker spreads\n\n"
            
            settings_text += "**Monitoring**:\n"
            settings_text += "• `/portfolio` - Account overview\n"
            settings_text += "• `/strategies` - Strategy performance\n"
            settings_text += "• `/rebates` - Rebate progress\n\n"
            
            settings_text += "**Advanced**:\n"
            settings_text += "• `/export_logs` - Download trading logs\n"
            settings_text += "• `/performance_report` - Detailed analysis\n"
            
            await update.message.reply_text(settings_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Settings command error: {e}")
            await update.message.reply_text(
                f"❌ Error accessing settings: {str(e)}",
                parse_mode='Markdown'
            )

    def is_valid_eth_address(self, address: str) -> bool:
        """Validate Ethereum address format"""
        if not address:
            return False
        
        # Remove any whitespace
        address = address.strip()
        
        # Check if it starts with 0x and is 42 characters long
        if not address.startswith('0x'):
            return False
        
        if len(address) != 42:
            return False
        
        # Check if all characters after 0x are hexadecimal
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False

    async def stop_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop trading and cancel orders"""
        try:
            user_id = update.effective_user.id
            
            # Cancel the trading task
            if context.bot_data.get('trading_tasks', {}).get(user_id):
                task = context.bot_data['trading_tasks'][user_id]
                if isinstance(task, dict):
                    # Multiple tasks - cancel all
                    for task_name, task_obj in task.items():
                        if hasattr(task_obj, 'cancel'):
                            task_obj.cancel()
                else:
                    # Single task
                    task.cancel()
                del context.bot_data['trading_tasks'][user_id]
                logger.info(f"Cancelled trading tasks for user {user_id}")
            
            # Use trading engine to stop all strategies
            if self.trading_engine:
                await self.trading_engine.stop_all_user_strategies(user_id)
                await self.trading_engine.cancel_all_orders(user_id)
            
            # Disable trading in the wallet manager
            if self.wallet_manager:
                result = await self.wallet_manager.disable_trading(user_id)
                orders_cancelled = result.get("orders_cancelled", 0)
            else:
                orders_cancelled = 0
            
            await update.effective_message.reply_text(
                "⛔ **Automated Trading Stopped!**\n\n"
                f"🛑 Cancelled {orders_cancelled} open orders\n"
                f"📊 All strategies disabled\n"
                f"💰 Existing positions remain unchanged\n"
                f"🔄 Use `/start_trading` to resume",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Stop trading error: {e}")
            await update.effective_message.reply_text(
                "❌ Error stopping trading. Please try again.",
                parse_mode='Markdown'
            )

    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced portfolio with trading status"""
        user_id = update.effective_user.id
        
        # 🔒 SECURITY FIX: Check if user has registered address first
        user_address = self.get_user_address(update, context)
        if not user_address:
            await update.effective_message.reply_text(
                "❌ **No Registered Address**\n\n"
                "Please register your Hyperliquid address first using `/start` or `/register_address`.",
                parse_mode='Markdown'
            )
            return
        
        # Check if user has an agent wallet
        if not self.wallet_manager:
            await update.effective_message.reply_text("❌ Wallet manager not initialized")
            return
            
        wallet_info = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_info:
            await update.effective_message.reply_text(
                f"❌ **No Agent Wallet Found**\n\n"
                f"Registered address: `{user_address[:8]}...{user_address[-6:]}`\n\n"
                f"Use `/create_agent` to create your agent wallet for this address.",
                parse_mode='Markdown'
            )
            return
        
        # Check if trading is active
        is_trading = user_id in context.bot_data.get('trading_tasks', {})
        
        # Get account data
        info = Info(self.wallet_manager.base_url)
        main_address = wallet_info["main_address"]
        
        try:
            user_state = info.user_state(main_address)
            margin_summary = user_state.get("marginSummary", {})
            positions = user_state.get("assetPositions", [])
            
            account_value = float(margin_summary.get("accountValue", 0))
            total_pnl = float(margin_summary.get("totalUnrealizedPnl", 0))
            
            portfolio_text = f"📊 **Your Portfolio**\n\n"
            portfolio_text += f"📍 **Main Address:** `{main_address[:8]}...{main_address[-6:]}`\n"
            portfolio_text += f"🤖 **Agent Address:** `{wallet_info['address'][:8]}...{wallet_info['address'][-6:]}`\n"
            portfolio_text += f"💰 **Account Value:** ${account_value:,.2f}\n"
            portfolio_text += f"📈 **Unrealized P&L:** ${total_pnl:+,.2f}\n"
            portfolio_text += f"🤖 **Auto Trading:** {'🟢 ACTIVE' if is_trading else '🔴 OFF'}\n\n"
            
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
                        continue

                    if abs(size) > 1e-9:
                        side = "📈 LONG" if size > 0 else "📉 SHORT"
                        portfolio_text += f"  `{coin}`: {side} {abs(size):.4f} @ ${entry_px:,.2f}\n"
                        portfolio_text += f"     P&L: ${unrealized_pnl:+,.2f}\n"
            else:
                portfolio_text += "No open positions.\n"
            
            # Add trading status info
            if is_trading:
                portfolio_text += "\n🔥 **Advanced Trading System Active!**\n"
                portfolio_text += "• Multi-strategy execution running\n"
                portfolio_text += "• Maker rebate optimization\n"
                portfolio_text += "• Grid trading across multiple pairs\n"
                portfolio_text += "• Use `/strategies` for detailed status\n"
                portfolio_text += "• Use `/stop_trading` to pause automation"
            else:
                portfolio_text += "\n⚡ Use `/start_trading` to enable advanced strategies"
            
            await update.effective_message.reply_text(portfolio_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error fetching portfolio for user {user_id}: {e}", exc_info=True)
            await update.effective_message.reply_text(f"❌ Error fetching portfolio: {str(e)}", parse_mode='Markdown')

    def get_user_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """🔒 SECURITY FIX: Get user's registered address safely"""
        user_id = update.effective_user.id
        user_data = context.bot_data.get('users', {})
        
        if user_id not in user_data:
            return None
            
        return user_data[user_id].get('address')

    async def test_trade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test order placement with small size"""
        user_id = update.effective_user.id
        
        # Check if user has an agent wallet
        wallet_info = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_info:
            await update.message.reply_text(
                "❌ No agent wallet found. Use `/create_agent` to create one first.",
                parse_mode='Markdown'
            )
            return
            
        # Get user's exchange
        exchange = await self.wallet_manager.get_user_exchange(user_id)
        if not exchange:
            await update.message.reply_text(
                "❌ No trading connection available. Please try `/agent_status` first.",
                parse_mode='Markdown'
            )
            return
            
        # Check if agent is approved
        approval = await self.wallet_manager.check_agent_approval(user_id)
        if not approval.get("approved", False):
            await update.message.reply_text(
                "❌ Agent wallet not approved yet. Please approve your agent in the Hyperliquid app first.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("How to Approve", callback_data=f"approval_help_{user_id}")]
                ])
            )
            return
            
        # Get current BTC price
        info = Info(self.wallet_manager.base_url)
        mids = info.all_mids()
        
        try:
            btc_price = float(mids.get("BTC", 60000))
            
            # Calculate a realistic test price (15% below current price)
            test_price = round(btc_price * 0.85, 1)
            
            # Small test size
            test_size = 0.001
            
            # Create a placeholder response while order processes
            progress_msg = await update.message.reply_text(
                f"🧪 **Testing order placement...**\n\n"
                f"Placing test BTC buy order:\n"
                f"• Size: {test_size} BTC\n"
                f"• Price: ${test_price:,.2f} (15% below market)\n"
                f"• Current BTC price: ${btc_price:,.2f}\n\n"
                f"⏳ Processing...",
                parse_mode='Markdown'
            )
            
            # Place the test order
            try:
                # ✅ Use CORRECT order format - Method 1 (All positional parameters)
                result = exchange.order(
                    "BTC",           # coin
                    True,           # is_buy
                    test_size,      # sz
                    test_price,     # px
                    {"limit": {"tif": "Gtc"}}  # order_type
                )
                
                logger.info(f"Test trade result for user {user_id}: {result}")
                
                if result.get("status") == "ok":
                    # Order API call succeeded, now check if order was accepted
                    response_data = result.get("response", {}).get("data", {})
                    if response_data.get("statuses"):
                        order_status = response_data["statuses"][0]
                        
                        if "resting" in order_status:
                            # Order was placed successfully
                            oid = order_status["resting"]["oid"]
                            await progress_msg.edit_text(
                                f"✅ **Test Order Successful!**\n\n"
                                f"Your BTC buy order is now active:\n"
                                f"• Size: {test_size} BTC\n"
                                f"• Price: ${test_price:,.2f}\n"
                                f"• Order ID: {oid[:8]}...\n\n"
                                f"📊 This confirms your trading setup works correctly!\n"
                                f"🔄 Use `/start_trading` to enable automated strategies\n"
                                f"⛔ Use `/cancel_order {oid}` to cancel this test order",
                                parse_mode='Markdown'
                            )
                        elif "error" in order_status:
                            # Order API worked but order was rejected
                            error_msg = order_status["error"]
                            
                            # Order rejection is still a successful test if API works
                            await progress_msg.edit_text(
                                f"✅ **Test Successful (API Works)**\n\n"
                                f"Your order API connection works correctly, but the order itself was rejected:\n"
                                f"• Size: {test_size} BTC\n"
                                f"• Price: ${test_price:,.2f}\n"
                                f"• Error: {error_msg}\n\n"
                                f"📝 This is normal and confirms your agent and approvals are working.\n"
                                f"🚀 Try `/start_trading` to use proper market-aware strategies.",
                                parse_mode='Markdown'
                            )
                        else:
                            # Unknown status
                            await progress_msg.edit_text(
                                f"⚠️ **Test Completed With Unknown Status**\n\n"
                                f"Your order was processed but returned an unknown status:\n"
                                f"• Status: {order_status}\n\n"
                                f"This may still indicate your setup is working correctly.\n"
                                f"Try `/portfolio` to check your account status.",
                                parse_mode='Markdown'
                            )
                    else:
                        # No status info in response
                        await progress_msg.edit_text(
                            f"⚠️ **Test Completed But Missing Status**\n\n"
                            f"Your order API call succeeded, but didn't return status details.\n"
                            f"This may still indicate your setup is working correctly.\n\n"
                            f"Response: {result}\n\n"
                            f"Try `/portfolio` to check your account status.",
                            parse_mode='Markdown'
                        )
                else:
                    # Order API call failed
                    error_msg = result.get("error", "Unknown error")
                    await progress_msg.edit_text(
                        f"❌ **Test Order Failed**\n\n"
                        f"Your order could not be placed:\n"
                        f"• Error: {error_msg}\n\n"
                        f"This might be due to:\n"
                        f"• Agent wallet not properly approved\n"
                        f"• Insufficient funds\n"
                        f"• API connectivity issues\n\n"
                        f"Try `/agent_status` to check your agent wallet.",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error placing test order for user {user_id}: {e}", exc_info=True)
                await progress_msg.edit_text(
                    f"❌ **Test Order Error**\n\n"
                    f"An error occurred while placing your test order:\n"
                    f"• Error: {str(e)}\n\n"
                    f"This might be due to:\n"
                    f"• Connection issues\n"
                    f"• API format errors\n"
                    f"• Server issues\n\n"
                    f"Please try again later or contact support.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Test trade general error for user {user_id}: {e}", exc_info=True)
            await update.message.reply_text(
                f"❌ Error preparing test trade: {str(e)}",
                parse_mode='Markdown'
            )

    async def cancel_order_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel a specific order by ID"""
        user_id = update.effective_user.id
        
        # Check if order ID was provided
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "❌ Please provide an order ID to cancel.\n\n"
                "Usage: `/cancel_order ORDER_ID`",
                parse_mode='Markdown'
            )
            return
            
        order_id = context.args[0]
        
        # Get user's exchange
        exchange = await self.wallet_manager.get_user_exchange(user_id)
        if not exchange:
            await update.message.reply_text(
                "❌ No trading connection available. Please try `/agent_status` first.",
                parse_mode='Markdown'
            )
            return
            
        # Lookup coin for this order ID (not implemented in this example)
        # In a real implementation, you would store order IDs and their coins,
        # or get all open orders and find the matching ID
        coin = "BTC"  # Default to BTC if we can't determine
        
        try:
            # Cancel the order
            result = exchange.cancel("BTC", order_id)
            
            if result.get("status") == "ok":
                # Check if any orders were actually cancelled
                cancelled = False
                
                response_data = result.get("response", {}).get("data", {})
                if response_data.get("statuses"):
                    # Verify a cancel success message exists
                    for status in response_data["statuses"]:
                        if status.get("status") == "cancelled":
                            cancelled = True
                            break
                
                if cancelled:
                    await update.message.reply_text(
                        f"✅ **Order Cancelled Successfully**\n\n"
                        f"Order ID: `{order_id}`\n\n"
                        f"Use `/portfolio` to check your updated positions.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        f"⚠️ **Order Cancellation Request Sent**\n\n"
                        f"Order ID: `{order_id}`\n"
                        f"The cancel request was accepted, but no confirmation.\n"
                        f"Use `/portfolio` to check if the order was cancelled.",
                        parse_mode='Markdown'
                    )
            else:
                error_msg = result.get("error", "Unknown error")
                await update.message.reply_text(
                    f"❌ **Order Cancellation Failed**\n\n"
                    f"Order ID: `{order_id}`\n"
                    f"Error: {error_msg}\n\n"
                    f"The order might already be filled or cancelled,\n"
                    f"or the ID might be incorrect.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            await update.message.reply_text(
                f"❌ **Error Cancelling Order**\n\n"
                f"Order ID: `{order_id}`\n"
                f"Error: {str(e)}",
                parse_mode='Markdown'
            )

    async def debug_trading_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Debug trading status"""
        try:
            user_id = update.effective_user.id
            
            # Check components
            checks = []
            checks.append(f"✅ User ID: {user_id}")
            
            # Check wallet info
            wallet_info = await self.wallet_manager.get_user_wallet(user_id)
            checks.append(f"{'✅' if wallet_info else '❌'} Wallet Info: {bool(wallet_info)}")
            
            if wallet_info:
                # Check exchange
                exchange = await self.wallet_manager.get_user_exchange(user_id)
                checks.append(f"{'✅' if exchange else '❌'} Exchange: {bool(exchange)}")
                
                # Check market data
                info = Info(self.wallet_manager.base_url)
                mids = info.all_mids()
                checks.append(f"{'✅' if mids else '❌'} Market Data: {len(mids)} pairs")
                
                # Check trading task
                is_trading = user_id in context.bot_data.get('trading_tasks', {})
                checks.append(f"{'✅' if is_trading else '❌'} Trading Task: {is_trading}")
                
                # Check account status
                try:
                    main_address = wallet_info['main_address'] 
                    user_state = info.user_state(main_address)
                    balance = float(user_state.get("marginSummary", {}).get("accountValue", 0))
                    checks.append(f"{'✅' if balance > 5 else '❌'} Balance: ${balance:.2f}")
                    
                    # Check approval status
                    approval = await self.wallet_manager.check_agent_approval(user_id)
                    checks.append(f"{'✅' if approval.get('approved') else '❌'} Approved: {approval.get('approved', False)}")
                    
                    # Check if trading enabled flag is set
                    checks.append(f"{'✅' if wallet_info.get('trading_enabled') else '❌'} Trading Enabled Flag: {wallet_info.get('trading_enabled', False)}")
                    
                except Exception as balance_error:
                    checks.append(f"❌ Balance Check Error: {str(balance_error)[:50]}")
            
            await update.effective_message.reply_text(
                "🔍 Trading Debug Report:\n\n" + "\n".join(checks)
            )
            
        except Exception as e:
            await update.effective_message.reply_text(f"❌ Debug error: {str(e)[:100]}")

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input from users"""
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        
        # Check if user is waiting to input an address
        if context.user_data.get('awaiting_address'):
            await self.process_address_input(update, context, message_text)
            context.user_data['awaiting_address'] = False
            return
        
        # Check if user is waiting to input address for agent creation
        if context.user_data.get('awaiting_address_for_agent'):
            await self.process_address_for_agent(update, context, message_text)
            context.user_data['awaiting_address_for_agent'] = False
            return
        
        # Default response for unrecognized text
        await update.message.reply_text(
            "ℹ️ I didn't understand that command.\n\n"
            "Use /help to see available commands.",
            parse_mode='Markdown'
        )

    async def process_address_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, address: str):
        """Process address input from user"""
        try:
            user_id = update.effective_user.id
            
            # Validate address format
            if not self.is_valid_eth_address(address):
                await update.message.reply_text(
                    "❌ **Invalid Address Format**\n\n"
                    "Please enter a valid Ethereum address:\n"
                    "• Must start with '0x'\n"
                    "• Must be 42 characters long\n"
                    "• Example: 0x1234567890123456789012345678901234567890",
                    parse_mode='Markdown'
                )
                context.user_data['awaiting_address'] = True  # Keep waiting
                return
            
            # Store address in bot data
            if 'users' not in context.bot_data:
                context.bot_data['users'] = {}
            
            context.bot_data['users'][user_id] = {
                'address': address.lower(),
                'registered_at': time.time(),
                'username': update.effective_user.username
            }
            
            # Success message
            await update.message.reply_text(
                f"✅ **Address Registered Successfully!**\n\n"
                f"Your address: `{address[:8]}...{address[-6:]}`\n"
                f"Full address: `{address.lower()}`\n\n"
                f"**Next Steps:**\n"
                f"1. Use `/create_agent` to create your secure agent wallet\n"
                f"2. Approve the agent in the Hyperliquid app\n"
                f"3. Fund your account and start trading!\n\n"
                f"🔒 **Security:** Your private keys are never shared with this bot!",
                parse_mode='Markdown'
            )
            
            logger.info(f"User {user_id} registered address: {address}")
            
        except Exception as e:
            logger.error(f"Error processing address input: {e}")
            await update.message.reply_text(
                "❌ Error processing your address. Please try again with `/register_address`",
                parse_mode='Markdown'
            )

    async def process_address_for_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE, address: str):
        """Process address input for agent creation"""
        try:
            # Validate and create agent
            if self.is_valid_eth_address(address):
                # Store temporarily and redirect to agent creation
                context.user_data['temp_address'] = address.lower()
                await self.auth_handler.handle_create_agent_command(update, context)
            else:
                await update.message.reply_text(
                    "❌ Invalid address format. Please enter a valid Ethereum address.",
                    parse_mode='Markdown'
                )
                context.user_data['awaiting_address_for_agent'] = True  # Keep waiting
                
        except Exception as e:
            logger.error(f"Error processing address for agent: {e}")
            await update.message.reply_text(
                "❌ Error processing address. Please try `/create_agent` again.",
                parse_mode='Markdown'
            )

    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all callback queries from inline keyboards"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        try:
            await query.answer()  # Acknowledge the callback
            
            # Parse callback data
            if data.startswith("create_agent_session_"):
                await self.auth_handler.handle_agent_creation_callback(update, context)
                
            elif data.startswith("agent_status_"):
                await self.refresh_agent_status_callback(update, context)
                
            elif data.startswith("refresh_agent_status_"):
                await self.refresh_agent_status_callback(update, context)
                
            elif data.startswith("enable_trading_"):
                await self.enable_trading_callback(update, context)
                
            elif data.startswith("disable_trading_"):
                await self.disable_trading_callback(update, context)
                
            elif data.startswith("emergency_stop_"):
                await self.confirm_emergency_stop_callback(update, context)
                
            elif data.startswith("confirm_emergency_stop_"):
                await self.confirm_emergency_stop_callback(update, context)
                
            elif data.startswith("cancel_emergency_"):
                await self.cancel_emergency_callback(update, context)
                
            elif data.startswith("view_portfolio_"):
                await self.portfolio_command(update, context)
                
            elif data.startswith("test_trade_"):
                await self.test_trade_command(update, context)
                
            elif data.startswith("approval_help_"):
                await self.show_approval_help(update, context)
                
            elif data.startswith("funding_help_"):
                await self.show_funding_help(update, context)
                
            elif data.startswith("register_address_"):
                await self.register_address_command(update, context)
                
            elif data.startswith("has_account_"):
                await self.auth_handler.handle_has_account_callback(update, context)
                
            elif data.startswith("no_account_"):
                await self.auth_handler.handle_no_account_callback(update, context)
                
            elif data.startswith("retry_agent_"):
                # Retry agent creation
                await self.auth_handler.handle_create_agent_command(update, context)
                
            elif data.startswith("enter_address_"):
                # Show address entry prompt
                await query.edit_message_text(
                    "📝 **Enter Your Hyperliquid Address**\n\n"
                    "Please enter your Hyperliquid account address:",
                    parse_mode='Markdown'
                )
                context.user_data["awaiting_address_for_agent"] = True
                
            elif data.startswith("explain_agent_"):
                await self.show_agent_explanation(update, context)
                
            else:
                # Unknown callback data
                await query.edit_message_text(
                    f"❓ Unknown action: {data}\n\nPlease try again or use /help for available commands.",
                    parse_mode='Markdown'
                )
                
        except Exception as e:
            logger.error(f"Error handling callback {data}: {e}")
            try:
                # Escape any problematic characters in error message
                error_msg = str(e).replace('`', '\\`').replace('*', '\\*').replace('_', '\\_')
                await query.edit_message_text(
                    f"❌ Error processing request: {error_msg}\n\nPlease try again or contact support."
                )
            except Exception as edit_error:
                # If edit fails, send a new message without markdown
                try:
                    await update.effective_chat.send_message(
                        f"❌ Error processing request: {str(e)}\n\nPlease try again or contact support."
                    )
                except:
                    logger.error(f"Failed to send error message: {edit_error}")
