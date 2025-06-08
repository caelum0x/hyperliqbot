from typing import Dict, Any, List, Set
from datetime import datetime
import logging
import asyncio
import time
import json
from uuid import uuid4

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CallbackContext, CommandHandler, MessageHandler, filters

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
        # For now, allow all users during development
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
        # Define admin users here or load from config
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
    
    def set_wallet_manager(self, wallet_manager):
        self.wallet_manager = wallet_manager
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Enhanced start command with automatic wallet creation"""
        user_id = update.effective_user.id
        username = update.effective_user.username
        
        # Check authorization
        if not await is_user_authorized(user_id, context.bot):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        # Create or get user session
        if self.user_manager:
            session = self.user_manager.create_user_session(user_id, username)
            onboarding_state = self.user_manager.get_onboarding_state(user_id)
        else:
            onboarding_state = None
        
        # Automatically create agent wallet for new users
        if self.wallet_manager and (not onboarding_state or onboarding_state.value == 'new'):
            wallet_result = await self.wallet_manager.create_agent_wallet(user_id)
            
            if wallet_result['status'] in ['created', 'exists']:
                # Update onboarding state
                if self.user_manager:
                    from telegram_bot.user_manager import OnboardingState
                    self.user_manager.update_onboarding_state(user_id, OnboardingState.WALLET_CREATED)
                
                welcome_msg = f"""
🎉 **Welcome to Hyperliquid Alpha Bot!**

✅ **Your trading wallet is ready:**
`{wallet_result['address']}`

💰 **Next step: Fund your wallet**
• Send USDC to the address above
• Minimum: 10 USDC
• Network: **Arbitrum One**
• The bot will notify you when funds arrive

📊 **Current balance:** ${wallet_result.get('balance', 0):.2f}
                """
                
                # Create keyboard based on funding status
                if wallet_result.get('funded', False):
                    keyboard = [
                        [InlineKeyboardButton("🚀 Choose Strategy", callback_data="choose_strategy")],
                        [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
                        [InlineKeyboardButton("💰 Check Balance", callback_data="check_balance")]
                    ]
                else:
                    keyboard = [
                        [InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_address_{wallet_result['address']}")],
                        [InlineKeyboardButton("🔄 Check Funding", callback_data="check_funding")],
                        [InlineKeyboardButton("❓ Help", callback_data="show_help")]
                    ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Send QR code if available
                if 'qr_code_url' in wallet_result:
                    try:
                        await update.message.reply_photo(
                            photo=wallet_result['qr_code_url'],
                            caption=welcome_msg,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                    except:
                        # Fallback to text message
                        await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=reply_markup)
                    
            else:
                await update.message.reply_text(f"❌ Error creating wallet: {wallet_result.get('message', 'Unknown error')}")
        else:
            # Fallback message if wallet manager not available
            welcome_msg = """
🎉 **Welcome to Hyperliquid Alpha Bot!**

Please use the following commands:
• `/connect` - Connect your wallet
• `/help` - Show all commands
• `/status` - Check bot status
            """
            await update.message.reply_text(welcome_msg, parse_mode='Markdown')

    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check wallet balance"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet manager not available")
            return
            
        wallet_data = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_data:
            await update.message.reply_text("❌ No wallet found. Use /start to create one.")
            return
            
        balance = wallet_data.get('balance', 0)
        funded = wallet_data.get('funded', False)
        
        balance_msg = f"""
💰 **Wallet Balance**

**Address:** `{wallet_data['address']}`
**Balance:** ${balance:.2f} USDC
**Status:** {'✅ Funded' if funded else '⚠️ Needs funding'}

{'Ready for trading!' if funded else 'Send USDC to start trading'}
        """
        
        keyboard = []
        if funded:
            keyboard.append([InlineKeyboardButton("🚀 Start Trading", callback_data="choose_strategy")])
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="check_balance")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(balance_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def deposit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show deposit instructions"""
        await update.message.reply_text("Use /start to get your wallet address for deposits")
    
    async def withdraw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle withdrawals"""
        await update.message.reply_text("Withdrawal feature coming soon")
    
    async def vault_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show vault information"""
        await update.message.reply_text("Vault features coming soon")
    
    async def grid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start grid trading"""
        await update.message.reply_text("Use /start and select Grid Trading strategy")
    
    async def momentum_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start momentum trading"""
        await update.message.reply_text("Momentum trading feature coming soon")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trading statistics"""
        await update.message.reply_text("Use the View Portfolio button for statistics")
    
    async def fills_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show trade fills"""
        await update.message.reply_text("Trade fills feature coming soon")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information"""
        help_msg = """
🤖 **Hyperliquid Alpha Bot Commands**

**Getting Started:**
• `/start` - Create wallet and start trading
• `/balance` - Check wallet balance
• `/portfolio` - View your positions

**Trading:**
• Choose strategies through interactive menus
• Monitor performance in real-time
• Automated execution and management

**Support:**
• Contact support for assistance
• All trades are executed securely
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
    
    async def agent_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show agent wallet information"""
        await self.balance_command(update, context)
    
    async def fund_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show funding instructions"""
        await self.balance_command(update, context)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show bot status"""
        user_id = update.effective_user.id
        
        status_msg = "🤖 **Bot Status**\n\n"
        
        # Check wallet
        if self.wallet_manager:
            wallet_data = await self.wallet_manager.get_user_wallet(user_id)
            if wallet_data:
                status_msg += f"✅ Wallet: {wallet_data['address'][:10]}...\n"
                status_msg += f"💰 Balance: ${wallet_data.get('balance', 0):.2f}\n"
            else:
                status_msg += "❌ No wallet found\n"
        
        # Check strategy
        if self.trading_engine:
            strategy = self.trading_engine.get_user_strategy(user_id)
            if strategy and strategy.get('active'):
                status_msg += f"🎯 Strategy: {strategy['type']} (Active)\n"
            else:
                status_msg += "⏸️ No active strategy\n"
        
        status_msg += "\n📊 All systems operational"
        
        await update.message.reply_text(status_msg, parse_mode='Markdown')
    
    # Callback handlers for agent wallet system
    
    async def handle_callbacks(self, update: Update, context: CallbackContext) -> None:
        """Handle callback queries"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        await query.answer()
        
        if data == "choose_strategy":
            await self._show_strategy_selection(update, context)
        elif data == "check_funding":
            await self._check_wallet_funding(update, context)
        elif data == "check_balance":
            await self._check_balance_callback(update, context)
        elif data.startswith("strategy_"):
            strategy_type = data.replace("strategy_", "")
            await self._handle_strategy_selection(update, context, strategy_type)
        elif data.startswith("confirm_strategy_"):
            strategy_data = data.replace("confirm_strategy_", "")
            await self._confirm_strategy_start(update, context, strategy_data)
        elif data == "view_portfolio":
            await self._show_portfolio(update, context)
        else:
            await query.edit_message_text("Feature coming soon!")

    async def _show_strategy_selection(self, update: Update, context: CallbackContext):
        """Show available trading strategies"""
        query = update.callback_query
        
        if not self.trading_engine:
            await query.edit_message_text("❌ Trading engine not available")
            return
            
        strategies = self.trading_engine.get_available_strategies()
        
        strategy_msg = """
🎯 **Choose Your Trading Strategy**

Select a strategy to start automated trading:
        """
        
        keyboard = []
        for strategy_id, description in strategies.items():
            emoji = "📊" if strategy_id == "grid" else "💰" if strategy_id == "maker_rebate" else "✋"
            keyboard.append([InlineKeyboardButton(f"{emoji} {description}", callback_data=f"strategy_{strategy_id}")])
        
        keyboard.append([InlineKeyboardButton("← Back", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(strategy_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _handle_strategy_selection(self, update: Update, context: CallbackContext, strategy_type: str):
        """Handle strategy selection and parameter input"""
        query = update.callback_query
        user_id = query.from_user.id
        
        if strategy_type == "grid":
            await self._setup_grid_strategy(update, context)
        elif strategy_type == "maker_rebate":
            await self._setup_maker_rebate_strategy(update, context)
        elif strategy_type == "manual":
            await self._setup_manual_strategy(update, context)

    async def _setup_grid_strategy(self, update: Update, context: CallbackContext):
        """Setup grid trading strategy with quick presets"""
        query = update.callback_query
        
        grid_msg = """
📊 **Grid Trading Setup**

Choose a preset or customize parameters:

**Conservative:** 20 levels, 0.1% spacing
**Balanced:** 10 levels, 0.2% spacing  
**Aggressive:** 5 levels, 0.5% spacing
        """
        
        keyboard = [
            [InlineKeyboardButton("🐌 Conservative (BTC)", callback_data="confirm_strategy_grid_btc_conservative")],
            [InlineKeyboardButton("⚖️ Balanced (BTC)", callback_data="confirm_strategy_grid_btc_balanced")],
            [InlineKeyboardButton("🚀 Aggressive (BTC)", callback_data="confirm_strategy_grid_btc_aggressive")],
            [InlineKeyboardButton("⚙️ Custom Setup", callback_data="custom_grid_setup")],
            [InlineKeyboardButton("← Back", callback_data="choose_strategy")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(grid_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _setup_maker_rebate_strategy(self, update: Update, context: CallbackContext):
        """Setup maker rebate mining strategy"""
        query = update.callback_query
        
        rebate_msg = """
💰 **Maker Rebate Mining**

Earn rebates by providing liquidity to the order book.

**Strategy:** Place orders near market price to earn trading rebates
**Risk:** Low (orders are close to market)
**Profit:** Steady rebate income + potential price movement gains
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Start Rebate Mining", callback_data="confirm_strategy_rebate_default")],
            [InlineKeyboardButton("⚙️ Configure Pairs", callback_data="configure_rebate_pairs")],
            [InlineKeyboardButton("← Back", callback_data="choose_strategy")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(rebate_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _setup_manual_strategy(self, update: Update, context: CallbackContext):
        """Setup manual trading assistance"""
        query = update.callback_query
        
        manual_msg = """
✋ **Manual Trading Mode**

Get assistance with manual trading:

• **Price Alerts** - Get notified of price movements
• **Market Analysis** - Real-time market insights  
• **Order Assistance** - Help with order placement
• **Risk Management** - Position size recommendations
        """
        
        keyboard = [
            [InlineKeyboardButton("✅ Activate Manual Mode", callback_data="confirm_strategy_manual_default")],
            [InlineKeyboardButton("← Back", callback_data="choose_strategy")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(manual_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _confirm_strategy_start(self, update: Update, context: CallbackContext, strategy_data: str):
        """Confirm and start the selected strategy"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Parse strategy data
        parts = strategy_data.split('_')
        strategy_type = parts[0]
        
        if not self.trading_engine:
            await query.edit_message_text("❌ Trading engine not available")
            return
        
        # Set default parameters based on selection
        parameters = {}
        if strategy_type == "grid":
            if "conservative" in strategy_data:
                parameters = {"coin": "BTC", "levels": 20, "spacing": 0.001, "size": 10}
            elif "balanced" in strategy_data:
                parameters = {"coin": "BTC", "levels": 10, "spacing": 0.002, "size": 10}
            elif "aggressive" in strategy_data:
                parameters = {"coin": "BTC", "levels": 5, "spacing": 0.005, "size": 10}
        elif strategy_type == "rebate":
            strategy_type = "maker_rebate"
            parameters = {"pairs": ["BTC", "ETH"], "spread": 0.0001}
        elif strategy_type == "manual":
            parameters = {}
        
        # Start the strategy
        result = await self.trading_engine.start_strategy(user_id, strategy_type, parameters)
        
        if result['status'] == 'success':
            # Update user state
            if self.user_manager:
                from telegram_bot.user_manager import OnboardingState
                self.user_manager.update_onboarding_state(user_id, OnboardingState.TRADING_ACTIVE)
            
            # Set strategy in wallet manager
            if self.wallet_manager:
                self.wallet_manager.set_user_strategy(user_id, strategy_type, parameters)
            
            success_msg = f"""
✅ **Strategy Started Successfully!**

**{result['message']}**

{self._format_strategy_details(result.get('details', {}))}

Your strategy is now running. Monitor your performance with:
• `/portfolio` - View positions
• `/status` - Check strategy status
• `/stop_trading` - Stop strategy
            """
            
            keyboard = [
                [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
                [InlineKeyboardButton("⚙️ Strategy Settings", callback_data="strategy_settings")],
                [InlineKeyboardButton("🛑 Stop Trading", callback_data="stop_trading")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(success_msg, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"❌ Error starting strategy: {result.get('message', 'Unknown error')}")

    def _format_strategy_details(self, details: Dict) -> str:
        """Format strategy details for display"""
        if not details:
            return ""
            
        formatted = "**Strategy Details:**\n"
        for key, value in details.items():
            if isinstance(value, list):
                value = ", ".join(value)
            formatted += f"• {key.replace('_', ' ').title()}: {value}\n"
        
        return formatted

    async def _check_wallet_funding(self, update: Update, context: CallbackContext):
        """Check wallet funding status"""
        query = update.callback_query
        user_id = query.from_user.id
        
        if not self.wallet_manager:
            await query.edit_message_text("❌ Wallet manager not available")
            return
            
        wallet_data = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_data:
            await query.edit_message_text("❌ No wallet found")
            return
            
        balance = wallet_data.get('balance', 0)
        funded = wallet_data.get('funded', False)
        
        if funded:
            # Update onboarding state
            if self.user_manager:
                from telegram_bot.user_manager import OnboardingState
                self.user_manager.update_onboarding_state(user_id, OnboardingState.FUNDED)
            
            funded_msg = f"""
🎉 **Wallet Funded Successfully!**

**Balance:** ${balance:.2f} USDC
**Status:** Ready for trading

Choose your trading strategy to get started:
            """
            
            keyboard = [
                [InlineKeyboardButton("🚀 Choose Strategy", callback_data="choose_strategy")],
                [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(funded_msg, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await query.edit_message_text(
                f"⏳ **Waiting for funding...**\n\n"
                f"**Address:** `{wallet_data['address']}`\n"
                f"**Current Balance:** ${balance:.2f} USDC\n\n"
                f"Send USDC to the address above and I'll notify you when it arrives!",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Check Again", callback_data="check_funding")]])
            )

    async def _check_balance_callback(self, update: Update, context: CallbackContext):
        """Handle balance check callback"""
        await self.balance_command(update, context)

    async def _show_portfolio(self, update: Update, context: CallbackContext):
        """Show user portfolio"""
        query = update.callback_query
        user_id = query.from_user.id
        
        if not self.wallet_manager:
            await query.edit_message_text("❌ Wallet manager not available")
            return
            
        portfolio = await self.wallet_manager.get_user_portfolio(user_id)
        
        if portfolio['status'] == 'success':
            portfolio_msg = f"""
📊 **Your Portfolio**

**Account Value:** ${portfolio['account_value']:,.2f}
**Available Balance:** ${portfolio['available_balance']:,.2f}
**Unrealized P&L:** ${portfolio['unrealized_pnl']:+,.2f}

**Positions:** {len(portfolio['positions'])}
            """
            
            if portfolio['positions']:
                portfolio_msg += "\n**Open Positions:**\n"
                for pos in portfolio['positions'][:5]:  # Show up to 5 positions
                    side = "LONG" if pos['size'] > 0 else "SHORT"
                    portfolio_msg += f"• {pos['coin']}: {side} {abs(pos['size']):.4f} @ ${pos['entry_price']:,.2f}\n"
                    portfolio_msg += f"  P&L: ${pos['unrealized_pnl']:+,.2f}\n"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="view_portfolio")],
                [InlineKeyboardButton("⚙️ Strategy Settings", callback_data="strategy_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(portfolio_msg, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await query.edit_message_text(f"❌ Error loading portfolio: {portfolio.get('message', 'Unknown error')}")
