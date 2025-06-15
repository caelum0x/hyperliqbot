"""
State manager for Telegram bot user flows
Handles user state transitions and corresponding UI
"""
import logging
import asyncio
import time
import re
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackContext

logger = logging.getLogger(__name__)

class UserState:
    """User states in the onboarding and trading flow"""
    UNREGISTERED = "unregistered"
    PENDING_APPROVAL = "pending_approval" 
    APPROVED = "approved"
    FUNDED = "funded"
    TRADING = "trading"

class StateManager:
    """
    Manages user flow states and UI transitions
    Handles all state-specific logic for the Telegram bot
    """
    
    def __init__(self, user_manager=None, trading_engine=None):
        """Initialize with core components"""
        self.user_manager = user_manager
        self.trading_engine = trading_engine
        self.wallet_manager = None
        
        # State tracking for text input expectations
        self.user_input_state: Dict[int, str] = {}  # user_id -> expected_input_type
        
        # Temporary storage for inputs in multi-step flows
        self.temp_data: Dict[int, Dict[str, Any]] = {}  # user_id -> {key: value}
        
        # Strategy configuration storage
        self.strategy_configs: Dict[int, Dict[str, Any]] = {}  # user_id -> {strategy: config}
        
        logger.info("StateManager initialized")
    
    def set_wallet_manager(self, wallet_manager):
        """Set wallet manager after initialization"""
        self.wallet_manager = wallet_manager
        logger.info("WalletManager set in StateManager")
    
    async def get_user_state(self, user_id: int) -> str:
        """
        Determine the current state of a user 
        based on their wallet and trading status
        """
        if not self.user_manager:
            # Fallback if user_manager not available
            return UserState.UNREGISTERED
        
        try:
            # Get user data from user_manager
            user_data = await self.user_manager.get_user(user_id)
            if not user_data or not user_data.get("hyperliquid_main_address"):
                return UserState.UNREGISTERED
            
            # Check wallet status
            wallet = await self.user_manager.get_user_wallet(user_id)
            if not wallet:
                # User registered but no agent wallet
                return UserState.UNREGISTERED
            
            # Check the status from the wallet
            status = wallet.get("status", "pending_approval")
            
            # Map the database status to our UserState enum values
            if status == "pending_approval":
                return UserState.PENDING_APPROVAL
            elif status == "approved":
                # Check if funded
                if wallet.get("balance", 0) > 0 or wallet.get("funded", False):
                    return UserState.FUNDED
                return UserState.APPROVED
            elif status == "funded":
                return UserState.FUNDED
            elif status == "trading":
                return UserState.TRADING
            
            # Default fallback
            return UserState.UNREGISTERED
            
        except Exception as e:
            logger.error(f"Error getting user state: {e}")
            return UserState.UNREGISTERED
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /start command based on user's current state
        """
        user_id = update.effective_user.id
        user_state = await self.get_user_state(user_id)
        
        if user_state == UserState.UNREGISTERED:
            await self.request_hyperliquid_address(update, context)
        elif user_state == UserState.PENDING_APPROVAL:
            await self.show_approval_instructions(update, context)
        elif user_state == UserState.APPROVED:
            await self.show_funding_instructions(update, context)
        elif user_state == UserState.FUNDED:
            await self.show_strategy_selection(update, context)
        else:
            await self.show_main_menu(update, context)
    
    async def request_hyperliquid_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask the user for their Hyperliquid address"""
        user_id = update.effective_user.id
        
        # Set user input state to expect an address
        self.user_input_state[user_id] = "awaiting_hyperliquid_address"
        
        welcome_msg = (
            "🎉 **Welcome to Hyperliquid Alpha Bot!**\n\n"
            "Please provide your Hyperliquid account address:"
        )
        
        keyboard = [
            [InlineKeyboardButton("What's Hyperliquid?", url="https://app.hyperliquid.xyz")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def show_approval_instructions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show approval instructions for a pending agent wallet"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet system not available. Please try again later.")
            return
            
        # Get wallet info
        wallet = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet:
            # No wallet found, restart the flow
            await self.request_hyperliquid_address(update, context)
            return
        
        agent_address = wallet.get("address", "Unknown")
        main_address = wallet.get("main_address", "Unknown")
        
        approval_message = (
            "✅ **Agent created!**\n\n"
            f"Please approve this agent wallet at Hyperliquid:\n"
            f"[Open Approval Page](https://app.hyperliquid.xyz/agent)\n\n"
            f"Agent Address: `{agent_address}`\n\n"
            f"After approval, I'll notify you to fund the wallet."
        )
        
        keyboard = [
            [InlineKeyboardButton("Approval Instructions", callback_data="show_approval_instructions")],
            [InlineKeyboardButton("Check Approval Status", callback_data="check_approval_status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Use effective_message to support both direct messages and callbacks
        message = update.effective_message
        await message.reply_text(approval_message, parse_mode='Markdown', 
                               disable_web_page_preview=False,
                               reply_markup=reply_markup)
    
    async def show_funding_instructions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show funding instructions for an approved agent wallet"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet system not available. Please try again later.")
            return
            
        # Get wallet info
        wallet = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet:
            # No wallet found, restart the flow
            await self.request_hyperliquid_address(update, context)
            return
        
        agent_address = wallet.get("address", "Unknown")
        
        funding_msg = (
            "✅ **Approved!**\n\n"
            f"Fund your agent wallet: `{agent_address}`\n\n"
            f"Network: **Arbitrum One**\n"
            f"Token: **USDC**\n"
            f"Min Recommended: **$10 USDC**\n\n"
            f"I'll notify you when funds arrive."
        )
        
        keyboard = [
            [InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_address_{agent_address}")],
            [InlineKeyboardButton("Check Funding", callback_data="check_funding")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Use effective_message to support both direct messages and callbacks
        message = update.effective_message
        await message.reply_text(funding_msg, parse_mode='Markdown', 
                               reply_markup=reply_markup)
    
    async def show_strategy_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available trading strategies for a funded agent wallet"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet system not available. Please try again later.")
            return
            
        # Get wallet info for balance
        wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        balance = wallet_status.get("balance", 0)
        
        strategy_msg = (
            f"✅ **Funded with ${balance:.2f}!**\n\n"
            f"Choose a strategy:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🌟 HyperEVM", callback_data="strategy_hyperevm")],
            [InlineKeyboardButton("📊 Grid Trading", callback_data="strategy_grid")],
            [InlineKeyboardButton("💰 Profit Optimization", callback_data="strategy_profit")],
            [InlineKeyboardButton("📂 View Portfolio", callback_data="view_portfolio")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Use effective_message to support both direct messages and callbacks
        message = update.effective_message
        await message.reply_text(strategy_msg, parse_mode='Markdown', 
                               reply_markup=reply_markup)
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu for users already in trading state"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet system not available. Please try again later.")
            return
            
        # Get wallet info and active strategy
        wallet = await self.wallet_manager.get_user_wallet(user_id)
        wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        
        # Get active strategy if any
        active_strategy = self.strategy_configs.get(user_id, {}).get("active_strategy")
        
        # Fetch wallet balance
        balance = wallet_status.get("balance", 0)
        
        main_msg = (
            "🤖 **Hyperliquid Alpha Bot**\n\n"
            f"**Balance:** ${balance:,.2f}\n"
        )
        
        # Add active strategy info if available
        if active_strategy:
            strategy_name = active_strategy.get("name", "Unknown")
            emoji = "🌟" if strategy_name == "hyperevm" else "📊" if strategy_name == "grid" else "💰"
            main_msg += f"**Active Strategy:** {emoji} {strategy_name.capitalize()}\n\n"
        else:
            main_msg += "**Status:** Ready to trade\n\n"
            
        main_msg += "What would you like to do?"
        
        keyboard = [
            [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
            [InlineKeyboardButton("🎯 Choose Strategy", callback_data="choose_strategy")]
        ]
        
        # Add different buttons based on whether a strategy is active
        if active_strategy:
            keyboard.append([InlineKeyboardButton("⏹️ Stop Strategy", callback_data="stop_strategy")])
        
        keyboard.append([InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Use effective_message to support both direct messages and callbacks
        message = update.effective_message
        await message.reply_text(main_msg, parse_mode='Markdown', 
                               reply_markup=reply_markup)
    
    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input based on current user state"""
        user_id = update.effective_user.id
        text = update.message.text
        
        # Check what kind of input we're expecting
        expected_input = self.user_input_state.get(user_id)
        
        if expected_input == "awaiting_hyperliquid_address":
            await self._handle_address_input(update, context, text)
        else:
            # No special input expected, show help
            await update.message.reply_text(
                "I'm not sure what you want to do. Try using one of the commands:\n"
                "/start - Begin setup process\n"
                "/status - Check your wallet status\n"
                "/help - Show all available commands"
            )
    
    async def _handle_address_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Handle Hyperliquid address input"""
        user_id = update.effective_user.id
        
        # Clear expected input state
        self.user_input_state.pop(user_id, None)
        
        # Basic address validation (starts with 0x, has 42 characters)
        if not text.startswith("0x") or len(text) != 42:
            await update.message.reply_text(
                "❌ **Invalid Ethereum Address**\n\n"
                "Please provide a valid Ethereum address starting with '0x' and containing 42 characters.\n\n"
                "Try again or use `/start` to restart.",
                parse_mode='Markdown'
            )
            return
            
        # Store address in temp data
        if user_id not in self.temp_data:
            self.temp_data[user_id] = {}
        self.temp_data[user_id]['hyperliquid_address'] = text
        
        # Show loading message
        loading_message = await update.message.reply_text(
            "🔄 Creating agent wallet for your account...",
            parse_mode='Markdown'
        )
        
        # Register user with address
        if self.user_manager:
            result = await self.user_manager.register_user(
                user_id,
                text,
                update.effective_user.username
            )
        else:
            result = {"status": "error", "message": "User manager not available"}
            
        # Handle registration result
        if result['status'] == 'success':
            # Create agent wallet
            if self.wallet_manager:
                wallet_result = await self.wallet_manager.create_agent_wallet(
                    user_id,
                    update.effective_user.username,
                    text
                )
                
                if wallet_result['status'] in ['success', 'exists']:
                    # Show approval instructions
                    await loading_message.delete()
                    await self.show_approval_instructions(update, context)
                    
                    # Start monitoring approval status
                    asyncio.create_task(self._monitor_approval_status(user_id))
                    return
                else:
                    # Error creating wallet
                    await loading_message.edit_text(
                        f"❌ **Error Creating Agent Wallet**\n\n"
                        f"{wallet_result.get('message', 'Unknown error')}\n\n"
                        f"Please try again with `/start`.",
                        parse_mode='Markdown'
                    )
                    return
            else:
                await loading_message.edit_text(
                    "❌ **Error Creating Agent Wallet**\n\n"
                    "Wallet system not available. Please try again later.",
                    parse_mode='Markdown'
                )
                return
        else:
            # Registration failed
            await loading_message.edit_text(
                f"❌ **Error Registering Address**\n\n"
                f"{result.get('message', 'Unknown error')}\n\n"
                f"Please check that your address is correct and try again with `/start`.",
                parse_mode='Markdown'
            )
    
    async def _monitor_approval_status(self, user_id: int):
        """Background task to monitor agent wallet approval status"""
        try:
            check_interval = 60  # Check every minute
            max_checks = 60  # Maximum 60 checks (1 hour total)
            
            for i in range(max_checks):
                # Wait between checks
                await asyncio.sleep(check_interval)
                
                # Skip if user manager not available
                if not self.user_manager:
                    continue
                
                # Check approval status
                wallet = await self.user_manager.get_user_wallet(user_id)
                if not wallet:
                    continue
                    
                if wallet.get("status") == "approved":
                    logger.info(f"Agent wallet approved for user {user_id}")
                    
                    # Show funding instructions as a direct message
                    try:
                        # TODO: Get bot instance from context and send message to user
                        # This will need to be implemented when properly integrating with bot
                        pass
                    except Exception as e:
                        logger.error(f"Failed to notify user {user_id} about approval: {e}")
                    
                    # Start monitoring funding
                    asyncio.create_task(self._monitor_funding_status(user_id))
                    return
                    
            logger.info(f"Approval monitoring timed out for user {user_id}")
        except Exception as e:
            logger.error(f"Error monitoring approval status for user {user_id}: {e}")
    
    async def _monitor_funding_status(self, user_id: int):
        """Background task to monitor agent wallet funding status"""
        try:
            check_interval = 60  # Check every minute
            max_checks = 120  # Maximum 120 checks (2 hours total)
            
            for i in range(max_checks):
                # Wait between checks
                await asyncio.sleep(check_interval)
                
                # Skip if wallet manager not available
                if not self.wallet_manager:
                    continue
                
                # Check funding status
                wallet_status = await self.wallet_manager.get_wallet_status(user_id)
                if not wallet_status:
                    continue
                    
                if wallet_status.get("funded"):
                    logger.info(f"Agent wallet funded for user {user_id}: ${wallet_status.get('balance', 0)}")
                    
                    # Show strategy selection as a direct message
                    try:
                        # TODO: Get bot instance from context and send message to user
                        # This will need to be implemented when properly integrating with bot
                        pass
                    except Exception as e:
                        logger.error(f"Failed to notify user {user_id} about funding: {e}")
                    
                    return
                    
            logger.info(f"Funding monitoring timed out for user {user_id}")
        except Exception as e:
            logger.error(f"Error monitoring funding status for user {user_id}: {e}")
    
    async def handle_strategy_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, strategy_type: str):
        """Handle selection of a trading strategy"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Check if user is in correct state
        user_state = await self.get_user_state(user_id)
        if user_state not in [UserState.FUNDED, UserState.TRADING]:
            await query.edit_message_text(
                "❌ You need a funded wallet before selecting a strategy.\n\n"
                "Use `/status` to check your wallet status.",
                parse_mode='Markdown'
            )
            return
            
        # Prepare for strategy configuration
        if user_id not in self.strategy_configs:
            self.strategy_configs[user_id] = {}
            
        # Store selected strategy type
        self.strategy_configs[user_id]["selected_strategy"] = strategy_type
        
        # Show strategy-specific configuration options
        if strategy_type == "hyperevm":
            await self._configure_hyperevm_strategy(update, context)
        elif strategy_type == "grid":
            await self._configure_grid_strategy(update, context)
        elif strategy_type == "profit":
            await self._configure_profit_strategy(update, context)
        else:
            await query.edit_message_text(
                f"❌ Unknown strategy type: {strategy_type}\n\n"
                "Please select a valid strategy.",
                parse_mode='Markdown'
            )
    
    async def _configure_hyperevm_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configure HyperEVM strategy"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get wallet status for balance
        wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        balance = wallet_status.get("balance", 0)
        
        # Calculate recommended allocation (20% of balance, min $10, max $100)
        recommended_allocation = min(max(balance * 0.2, 10), 100)
        
        # Store default configuration
        self.strategy_configs[user_id]["hyperevm"] = {
            "max_allocation": recommended_allocation,
            "auto_take_profit": True,
            "take_profit_percentage": 100,  # 100% (double investment)
            "stop_loss_percentage": 50      # 50% (half investment)
        }
        
        config_msg = (
            "🌟 **HyperEVM Mode Configuration**\n\n"
            f"Balance: ${balance:.2f}\n\n"
            f"Max allocation per launch: ${recommended_allocation:.2f}\n\n"
            "This strategy automatically participates in HyperEVM token launches with your specified allocation."
        )
        
        keyboard = [
            [InlineKeyboardButton(f"Set Max: ${recommended_allocation:.2f}", callback_data="confirm_hyperevm_default")],
            [InlineKeyboardButton("Customize Allocation", callback_data="customize_hyperevm_allocation")],
            [InlineKeyboardButton("↩️ Back", callback_data="choose_strategy")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(config_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _configure_grid_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configure Grid Trading strategy"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get wallet status for balance
        wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        balance = wallet_status.get("balance", 0)
        
        # Store default configuration
        self.strategy_configs[user_id]["grid"] = {
            "pair": "BTC",
            "levels": 10,
            "grid_width_percent": 4.0,  # 4% range around current price
            "allocation_percentage": 50,  # 50% of balance
            "allocation_value": min(balance * 0.5, balance - 5)  # Leave at least $5 as buffer
        }
        
        config_msg = (
            "📊 **Grid Trading Configuration**\n\n"
            f"Balance: ${balance:.2f}\n\n"
            "Default settings:\n"
            "• Pair: BTC-USDC\n"
            "• Grid Levels: 10\n"
            "• Grid Width: 4%\n"
            f"• Allocation: ${self.strategy_configs[user_id]['grid']['allocation_value']:.2f}\n\n"
            "Grid trading places multiple orders around the current price, buying low and selling high as price moves."
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Use Default Settings", callback_data="confirm_grid_default")],
            [InlineKeyboardButton("🔄 Change Pair", callback_data="grid_change_pair")],
            [InlineKeyboardButton("⚙️ Advanced Settings", callback_data="grid_advanced_settings")],
            [InlineKeyboardButton("↩️ Back", callback_data="choose_strategy")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(config_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _configure_profit_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configure Profit Optimization strategy"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get wallet status for balance
        wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        balance = wallet_status.get("balance", 0)
        
        # Store default configuration
        self.strategy_configs[user_id]["profit"] = {
            "pairs": ["BTC", "ETH", "SOL"],
            "allocation_percentage": 90,  # 90% of balance
            "allocation_value": min(balance * 0.9, balance - 5),  # Leave at least $5 as buffer
            "maker_rebate": True,
            "funding_rate": True
        }
        
        config_msg = (
            "💰 **Profit Optimization Configuration**\n\n"
            f"Balance: ${balance:.2f}\n\n"
            "Default settings:\n"
            "• Trading Pairs: BTC, ETH, SOL\n"
            "• Strategies: Maker Rebate Mining, Funding Rate Arbitrage\n"
            f"• Allocation: ${self.strategy_configs[user_id]['profit']['allocation_value']:.2f}\n\n"
            "This strategy focuses on low-risk income generation through maker rebates and funding rate optimization."
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Use Default Settings", callback_data="confirm_profit_default")],
            [InlineKeyboardButton("🔄 Change Pairs", callback_data="profit_change_pairs")],
            [InlineKeyboardButton("⚙️ Advanced Settings", callback_data="profit_advanced_settings")],
            [InlineKeyboardButton("↩️ Back", callback_data="choose_strategy")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(config_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def activate_hyperevm_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Activate HyperEVM strategy with configured settings"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get configuration
        config = self.strategy_configs[user_id].get("hyperevm", {})
        
        # Mark as active strategy
        self.strategy_configs[user_id]["active_strategy"] = {
            "name": "hyperevm",
            "config": config,
            "activated_at": datetime.now().isoformat()
        }
        
        # Start the strategy in trading engine
        if self.trading_engine:
            try:
                result = await self.trading_engine.start_user_strategy(
                    user_id, "hyperevm", config
                )
                
                if result.get("status") != "success":
                    await query.edit_message_text(
                        f"❌ Error starting strategy: {result.get('message', 'Unknown error')}\n\n"
                        "Please try again later.",
                        parse_mode='Markdown'
                    )
                    return
            except Exception as e:
                logger.error(f"Error starting HyperEVM strategy for user {user_id}: {e}")
        
        confirmation_msg = (
            "🌟 **HyperEVM Mode Activated**\n\n"
            f"Max allocation: ${config['max_allocation']:.2f} per launch\n\n"
            "I'll notify you when new launches are detected and automatically participate according to your settings.\n\n"
            "Use `/portfolio` to check your positions at any time."
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
            [InlineKeyboardButton("⏹️ Stop Strategy", callback_data="stop_strategy")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(confirmation_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _simulate_hyperevm_launch(self, user_id: int):
        """Simulate a HyperEVM launch notification (for demonstration)"""
        try:
            # Wait 15 seconds
            await asyncio.sleep(15)
            
            # Get bot from trading engine
            if not hasattr(self.trading_engine, "telegram_bot") or not self.trading_engine.telegram_bot:
                return
                
            bot = self.trading_engine.telegram_bot.app.bot
            
            # Get config
            config = self.strategy_configs[user_id].get("hyperevm", {})
            allocation = config.get("max_allocation", 100)
            
            # Send launch notification
            launch_msg = (
                "🚀 **New launch detected: TOKEN_X**\n\n"
                f"Auto-buying ${allocation:.2f} worth..."
            )
            
            message = await bot.send_message(
                chat_id=user_id,
                text=launch_msg,
                parse_mode='Markdown'
            )
            
            # Wait 5 seconds
            await asyncio.sleep(5)
            
            # Send confirmation
            buy_price = 0.50
            quantity = allocation / buy_price
            
            confirmation_msg = (
                "✅ **Position opened**\n\n"
                f"Token: TOKEN_X\n"
                f"Amount: {quantity:.2f} tokens\n"
                f"Price: ${buy_price:.2f} per token\n"
                f"Total: ${allocation:.2f}"
            )
            
            await bot.send_message(
                chat_id=user_id,
                text=confirmation_msg,
                parse_mode='Markdown'
            )
            
            # Wait 20 seconds
            await asyncio.sleep(20)
            
            # Send price update
            new_price = 1.20
            pnl_pct = ((new_price / buy_price) - 1) * 100
            pnl_value = allocation * (new_price / buy_price - 1)
            
            update_msg = (
                "📈 **TOKEN_X Update**\n\n"
                f"Current price: ${new_price:.2f} (+{pnl_pct:.0f}%)\n"
                f"💰 Unrealized P&L: +${pnl_value:.2f}"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh Price", callback_data="refresh_token_price")],
                [InlineKeyboardButton("💰 Take Profit", callback_data="take_profit_token")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await bot.send_message(
                chat_id=user_id,
                text=update_msg,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in HyperEVM simulation for user {user_id}: {e}")
    
    async def activate_grid_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Activate Grid Trading strategy with configured settings"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get configuration
        config = self.strategy_configs[user_id].get("grid", {})
        
        # Mark as active strategy
        self.strategy_configs[user_id]["active_strategy"] = {
            "name": "grid",
            "config": config,
            "activated_at": datetime.now().isoformat()
        }
        
        # Start the strategy in trading engine
        if self.trading_engine:
            try:
                result = await self.trading_engine.start_user_strategy(
                    user_id, "grid", config
                )
                
                if result.get("status") != "success":
                    await query.edit_message_text(
                        f"❌ Error starting strategy: {result.get('message', 'Unknown error')}\n\n"
                        "Please try again later.",
                        parse_mode='Markdown'
                    )
                    return
            except Exception as e:
                logger.error(f"Error starting Grid strategy for user {user_id}: {e}")
        
        confirmation_msg = (
            "📊 **Grid Trading Activated**\n\n"
            f"Pair: {config['pair']}-USDC\n"
            f"Grid Levels: {config['levels']}\n"
            f"Grid Width: {config['grid_width_percent']}%\n"
            f"Allocation: ${config['allocation_value']:.2f}\n\n"
            "I'll place grid orders and notify you when trades are executed.\n\n"
            "Use `/portfolio` to check your positions at any time."
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
            [InlineKeyboardButton("⏹️ Stop Strategy", callback_data="stop_strategy")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(confirmation_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def activate_profit_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Activate Profit Optimization strategy with configured settings"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get configuration
        config = self.strategy_configs[user_id].get("profit", {})
        
        # Mark as active strategy
        self.strategy_configs[user_id]["active_strategy"] = {
            "name": "profit",
            "config": config,
            "activated_at": datetime.now().isoformat()
        }
        
        # Start the strategy in trading engine
        if self.trading_engine:
            try:
                result = await self.trading_engine.start_user_strategy(
                    user_id, "maker_rebate", config
                )
                
                if result.get("status") != "success":
                    await query.edit_message_text(
                        f"❌ Error starting strategy: {result.get('message', 'Unknown error')}\n\n"
                        "Please try again later.",
                        parse_mode='Markdown'
                    )
                    return
            except Exception as e:
                logger.error(f"Error starting Profit strategy for user {user_id}: {e}")
        
        pairs_str = ", ".join(config["pairs"])
        strategies_str = []
        if config.get("maker_rebate"):
            strategies_str.append("Maker Rebate Mining")
        if config.get("funding_rate"):
            strategies_str.append("Funding Rate Arbitrage")
            
        strategies_txt = ", ".join(strategies_str)
        
        confirmation_msg = (
            "💰 **Profit Optimization Activated**\n\n"
            f"Pairs: {pairs_str}\n"
            f"Strategies: {strategies_txt}\n"
            f"Allocation: ${config['allocation_value']:.2f}\n\n"
            "I'll optimize your positions to generate passive income and notify you of profits.\n\n"
            "Use `/portfolio` to check your positions at any time."
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
            [InlineKeyboardButton("⏹️ Stop Strategy", callback_data="stop_strategy")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(confirmation_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def stop_active_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop the currently active strategy"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Check if user has an active strategy
        active_strategy = self.strategy_configs.get(user_id, {}).get("active_strategy")
        if not active_strategy:
            await query.edit_message_text(
                "❌ No active strategy to stop.\n\n"
                "Use `/strategies` to start a strategy.",
                parse_mode='Markdown'
            )
            return
        
        strategy_name = active_strategy.get("name", "unknown")
        
        # Stop the strategy in trading engine
        if self.trading_engine:
            try:
                result = await self.trading_engine.stop_user_strategy(
                    user_id, strategy_name
                )
                
                if result.get("status") != "success":
                    await query.edit_message_text(
                        f"❌ Error stopping strategy: {result.get('message', 'Unknown error')}\n\n"
                        "Please try again later.",
                        parse_mode='Markdown'
                    )
                    return
            except Exception as e:
                logger.error(f"Error stopping strategy for user {user_id}: {e}")
        
        # Clear active strategy
        self.strategy_configs[user_id]["active_strategy"] = None
        
        confirmation_msg = (
            "✅ **Strategy Stopped**\n\n"
            f"Your {strategy_name.capitalize()} strategy has been stopped.\n\n"
            "Use `/strategies` to start a new strategy."
        )
        
        keyboard = [
            [InlineKeyboardButton("🎯 Choose Strategy", callback_data="choose_strategy")],
            [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(confirmation_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def handle_callback(self, update: Update, context: CallbackContext):
        """Handle callback queries from all interactive buttons"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        # Common callbacks
        if data == "check_approval_status":
            await self.show_agent_status(update, context)
        elif data == "help_approval":
            await self._show_approval_help(update, context)
        elif data == "check_funding" or data == "check_balance":
            await self._check_wallet_balance(update, context)
        elif data.startswith("copy_address_"):
            address = data.replace("copy_address_", "")
            await query.answer(f"Address copied: {address}")
            # No message change needed
        elif data == "choose_strategy":
            await self.show_strategy_selection(update, context)
        elif data == "view_portfolio" or data == "refresh_portfolio":
            # This would normally be handled by the portfolio command
            await query.edit_message_text("Portfolio view will be implemented in the bot")
        elif data == "stop_strategy":
            await self.stop_active_strategy(update, context)
        elif data == "back_to_main":
            await self.show_main_menu(update, context)
        elif data == "restart_setup":
            await self.request_hyperliquid_address(update, context)
        elif data == "show_settings":
            await self._show_settings(update, context)
        elif data == "explain_agent_wallet":
            await self._explain_agent_wallet(update, context)
        elif data.startswith("strategy_"):
            strategy_type = data.replace("strategy_", "")
            await self.handle_strategy_selection(update, context, strategy_type)
        elif data == "confirm_hyperevm_default":
            await self.activate_hyperevm_strategy(update, context)
        elif data == "confirm_grid_default":
            await self.activate_grid_strategy(update, context)
        elif data == "confirm_profit_default":
            await self.activate_profit_strategy(update, context)
        elif data == "refresh_token_price":
            # Simulate refreshing price
            await self._simulate_price_refresh(update, context)
        elif data == "take_profit_token":
            # Simulate taking profit
            await self._simulate_take_profit(update, context)
        else:
            # Unhandled callback
            await query.answer("This option is not available yet")
            
    async def _simulate_price_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Simulate refreshing token price"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Updated price and profit
        new_price = 1.45
        buy_price = 0.50
        allocation = self.strategy_configs[user_id].get("hyperevm", {}).get("max_allocation", 100)
        pnl_pct = ((new_price / buy_price) - 1) * 100
        pnl_value = allocation * (new_price / buy_price - 1)
        
        update_msg = (
            "📈 **TOKEN_X Update**\n\n"
            f"Current price: ${new_price:.2f} (+{pnl_pct:.0f}%)\n"
            f"💰 Unrealized P&L: +${pnl_value:.2f}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Price", callback_data="refresh_token_price")],
            [InlineKeyboardButton("💰 Take Profit", callback_data="take_profit_token")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(update_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _simulate_take_profit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Simulate taking profit on a token"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Profit details
        sell_price = 1.45
        buy_price = 0.50
        allocation = self.strategy_configs[user_id].get("hyperevm", {}).get("max_allocation", 100)
        pnl_pct = ((sell_price / buy_price) - 1) * 100
        pnl_value = allocation * (sell_price / buy_price - 1)
        total_value = allocation + pnl_value
        
        profit_msg = (
            "✅ **Profit Taken Successfully!**\n\n"
            f"Token: TOKEN_X\n"
            f"Sell Price: ${sell_price:.2f}\n"
            f"Profit: +${pnl_value:.2f} (+{pnl_pct:.0f}%)\n\n"
            f"Total value returned: ${total_value:.2f}"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
            [InlineKeyboardButton("↩️ Back to Main Menu", callback_data="back_to_main")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(profit_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_approval_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed help for agent wallet approval"""
        query = update.callback_query
        
        help_msg = (
            "🔑 **How to Approve Your Agent Wallet**\n\n"
            "1. Go to [Hyperliquid App](https://app.hyperliquid.xyz/agent)\n"
            "2. Connect your wallet (must be the same as registered)\n"
            "3. Find your agent in the list or search by address\n"
            "4. Click 'Approve' button\n"
            "5. Sign the transaction in your wallet\n\n"
            "After approval, use `/status` to check if your agent is ready."
        )
        
        keyboard = [
            [InlineKeyboardButton("Go to Hyperliquid App", url="https://app.hyperliquid.xyz/agent")],
            [InlineKeyboardButton("🔄 Check Status", callback_data="check_approval_status")],
            [InlineKeyboardButton("↩️ Back", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_msg, parse_mode='Markdown',
                                    disable_web_page_preview=True,
                                    reply_markup=reply_markup)
    
    async def _check_wallet_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check and display wallet balance"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.edit_message_text(
            "🔄 Checking your wallet balance...",
            parse_mode='Markdown'
        )
        
        if not self.wallet_manager:
            await query.edit_message_text(
                "❌ Wallet system not available. Please try again later.",
                parse_mode='Markdown'
            )
            return
            
        # Refresh wallet status
        if hasattr(self.wallet_manager, 'refresh_wallet_status'):
            wallet_status = await self.wallet_manager.refresh_wallet_status(user_id)
        elif hasattr(self.wallet_manager, 'get_wallet_status'):
            wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        else:
            wallet_status = {
                "status": "error",
                "message": "Balance check not available"
            }
        
        # Show appropriate message based on funding status
        if wallet_status.get('funded', False):
            balance = wallet_status.get('balance', 0)
            
            funded_msg = (
                f"✅ **Funded with ${balance:.2f}!**\n\n"
                f"Your agent wallet is ready for trading.\n\n"
                f"Choose your trading strategy to get started:"
            )
            
            keyboard = [
                [InlineKeyboardButton("🚀 Choose Strategy", callback_data="choose_strategy")],
                [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(funded_msg, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            wallet_data = await self.wallet_manager.get_user_wallet(user_id)
            if not wallet_data:
                await query.edit_message_text(
                    "❌ Wallet data not available. Please try again later.",
                    parse_mode='Markdown'
                )
                return
                
            agent_address = wallet_data.get("address", "Unknown")
            balance = wallet_status.get('balance', 0)
            
            unfunded_msg = (
                "⏳ **Waiting for funding...**\n\n"
                f"Network: **Arbitrum One**\n"
                f"Agent Address: `{agent_address}`\n"
                f"Current Balance: ${balance:.2f} USDC\n\n"
                "Fund with USDC to start trading."
            )
            
            keyboard = [
                [InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_address_{agent_address}")],
                [InlineKeyboardButton("🔄 Check Again", callback_data="check_balance")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(unfunded_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _explain_agent_wallet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Explain what an agent wallet is"""
        query = update.callback_query
        
        explanation = (
            "🤖 **What is an Agent Wallet?**\n\n"
            "An agent wallet is a secure way to trade on Hyperliquid without exposing your private keys.\n\n"
            "**How it works:**\n"
            "1. We create an agent wallet linked to your main account\n"
            "2. You approve the agent in your Hyperliquid settings\n"
            "3. You fund the agent wallet\n"
            "4. The agent can now trade on your behalf\n\n"
            "**Benefits:**\n"
            "• Your main private key is never shared\n"
            "• You maintain full control\n"
            "• You can revoke access anytime\n"
            "• More secure than giving API keys"
        )
        
        keyboard = [
            [InlineKeyboardButton("👍 Got it!", callback_data="restart_setup")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(explanation, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def show_agent_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed agent wallet status"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet system not available. Please try again later.")
            return
            
        # Get wallet info
        wallet_data = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_data:
            await update.message.reply_text(
                "❌ You don't have an agent wallet yet.\n\n"
                "Use `/start` to set one up.",
                parse_mode='Markdown'
            )
            return
        
        # Get wallet status
        if hasattr(self.wallet_manager, 'get_wallet_status'):
            wallet_status = await self.wallet_manager.get_wallet_status(user_id)
        else:
            wallet_status = {
                "status": wallet_data.get("status", "unknown"),
                "status_emoji": "❓",
                "balance": wallet_data.get("balance", 0),
                "funded": wallet_data.get("balance", 0) > 0,
                "trading_enabled": wallet_data.get("trading_enabled", False)
            }
        
        status_msg = (
            f"{wallet_status.get('status_emoji', '📊')} **Agent Wallet Status**\n\n"
            f"**Status:** {wallet_status.get('status', 'Unknown')}\n"
            f"**Balance:** ${wallet_status.get('balance', 0):,.2f}\n"
            f"**Main Address:** `{wallet_data.get('main_address', 'Unknown')}`\n"
            f"**Agent Address:** `{wallet_data.get('address', 'Unknown')}`\n\n"
        )
        
        # Add different instructions based on wallet status
        user_state = await self.get_user_state(user_id)
        
        if user_state == UserState.PENDING_APPROVAL:
            status_msg += (
                "⏳ **Your agent wallet needs approval**\n\n"
                "Please approve your agent wallet in the Hyperliquid app to continue."
            )
            keyboard = [
                [InlineKeyboardButton("🔄 Check Again", callback_data="check_approval_status")],
                [InlineKeyboardButton("ℹ️ How to Approve", callback_data="help_approval")]
            ]
        elif user_state == UserState.APPROVED:
            status_msg += (
                "💰 **Your agent wallet needs funding**\n\n"
                "Send USDC to your agent address to start trading."
            )
            keyboard = [
                [InlineKeyboardButton("📋 Copy Address", callback_data=f"copy_address_{wallet_data.get('address')}")],
                [InlineKeyboardButton("🔄 Check Balance", callback_data="check_balance")]
            ]
        elif user_state in [UserState.FUNDED, UserState.TRADING]:
            active_strategy = self.strategy_configs.get(user_id, {}).get("active_strategy")
            
            if active_strategy:
                strategy_name = active_strategy.get("name", "Unknown")
                status_msg += (
                    f"✅ **Your wallet is active with {strategy_name.capitalize()} strategy**\n\n"
                    f"Your strategy is running as configured."
                )
                keyboard = [
                    [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
                    [InlineKeyboardButton("⏹️ Stop Strategy", callback_data="stop_strategy")]
                ]
            else:
                status_msg += (
                    "✅ **Your agent wallet is funded and ready**\n\n"
                    "Select a trading strategy to begin."
                )
                keyboard = [
                    [InlineKeyboardButton("🚀 Choose Strategy", callback_data="choose_strategy")],
                    [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")]
                ]
        else:
            status_msg += (
                "❓ **Unknown wallet status**\n\n"
                "Please restart the setup process."
            )
            keyboard = [
                [InlineKeyboardButton("🔄 Restart Setup", callback_data="restart_setup")]
            ]
        
        # Use effective_message to support both direct commands and callbacks
        effective_message = update.effective_message
        if effective_message:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await effective_message.reply_text(status_msg, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user settings menu"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Get user state to determine available settings
        user_state = await self.get_user_state(user_id)
        
        settings_msg = (
            "⚙️ **User Settings**\n\n"
            "Configure your preferences:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔔 Notifications", callback_data="settings_notifications")],
            [InlineKeyboardButton("💰 Risk Level", callback_data="settings_risk_level")]
        ]
        
        # Add state-specific options
        active_strategy = self.strategy_configs.get(user_id, {}).get("active_strategy")
        if active_strategy:
            keyboard.append([InlineKeyboardButton("⚙️ Strategy Settings", callback_data="settings_strategy")])
            keyboard.append([InlineKeyboardButton("⏹️ Stop Strategy", callback_data="stop_strategy")])
        
        keyboard.append([InlineKeyboardButton("↩️ Back", callback_data="back_to_main")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(settings_msg, parse_mode='Markdown', reply_markup=reply_markup)
