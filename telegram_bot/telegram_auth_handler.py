"""
Secure authentication handler for Telegram bot users
"""
import logging
import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import aiosqlite
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from telegram_bot.address_verification import AddressVerificationManager

logger = logging.getLogger(__name__)

# Define conversation states
ADDRESS_COLLECTION = 1
AGENT_CREATION = 2
APPROVAL_WAITING = 3
FUNDING_WAIT = 4

class TelegramAuthHandler:
    """Handles secure user authentication for Telegram bot using agent wallets"""
    
    def __init__(self, user_sessions: Dict[int, Dict[str, Any]], base_url=None, 
                 bot_username: str = "YourDefaultBotUsername", wallet_manager=None):
        self.user_sessions = user_sessions
        self.base_url = base_url or constants.MAINNET_API_URL
        self.bot_username = bot_username
        self.wallet_manager = wallet_manager
        # Track users in authentication flow
        self.user_flow_state = {}
        
        # ✅ SECURITY: Initialize address verification system
        self.address_verifier = AddressVerificationManager(self.base_url)
        
        # Start cleanup task for address verification
        asyncio.create_task(self.address_verifier.start_cleanup_task())

    async def handle_connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /connect command - redirects to agent wallet flow"""
        user_id = update.effective_user.id
        
        # Check if message is in private chat
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "⚠️ For security, please send this command in a private chat with the bot.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Message Privately", url=f"https://t.me/{self.bot_username}")
                ]])
            )
            return
        
        # Inform about the new authentication system
        await update.message.reply_text(
            "🔐 **Secure Agent Wallet System**\n\n"
            "Our bot uses a secure agent wallet system that doesn't require your private key.\n\n"
            "To get started, use the `/create_agent` command to set up your agent wallet.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Create Agent Wallet", callback_data=f"create_agent_session_{user_id}")
            ]])
        )
    
    async def handle_create_agent_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        """Handle /create_agent command - start the onboarding flow"""
        user_id = update.effective_user.id
        username = update.effective_user.username
        
        # Check if message is in private chat
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "⚠️ For security, please send this command in a private chat with the bot.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Message Privately", url=f"https://t.me/{self.bot_username}")]
                ])
            )
            return
        
        # 🔒 SECURITY FIX: Check if user has registered address first
        user_data = context.bot_data.get('users', {})
        if user_id not in user_data:
            await update.message.reply_text(
                "❌ **No Registered Address Found**\n\n"
                "Please register your Hyperliquid address first using `/start` or `/register_address`.\n\n"
                "This is required for security - we need to know which address to create an agent wallet for.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Register Address", callback_data=f"register_address_{user_id}")]
                ])
            )
            return
        
        user_address = user_data[user_id]['address']
        
        # Check if wallet manager is properly initialized
        if not self.wallet_manager:
            await update.message.reply_text(
                "❌ Error: Wallet manager not initialized. Please contact support."
            )
            return
        
        # Check if user already has an agent wallet
        wallet_info = await self.wallet_manager.get_user_wallet(user_id)
        if wallet_info:
            # User already has a wallet - establish session and show status
            await self._establish_user_session(user_id, username, wallet_info)
            await self.handle_agent_status_command(update, context)
            return
        
        # Initialize wallet manager if needed
        if not hasattr(self.wallet_manager, 'db_initialized') or not self.wallet_manager.db_initialized:
            await self.wallet_manager.initialize()
        
        # Start agent creation with registered address
        await self._start_agent_creation_with_address(update, context, user_address)
        return ADDRESS_COLLECTION

    async def _start_agent_creation_with_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_address: str):
        """🔒 SECURITY FIX: Start agent creation with registered address"""
        user_id = update.effective_user.id
        
        # Save user in flow state
        self.user_flow_state[user_id] = {
            "state": AGENT_CREATION,
            "timestamp": datetime.now(),
            "hl_address": user_address
        }
        
        creating_message = await update.message.reply_text(
            f"🔄 **Creating Agent Wallet**\n\n"
            f"**Your registered address:** `{user_address[:8]}...{user_address[-6:]}`\n\n"
            f"Creating secure agent wallet for this address...\n"
            f"This will take a few seconds.",
            parse_mode='Markdown'
        )
        
        # Create agent wallet with registered address
        result = await self.wallet_manager.create_agent_wallet(
            user_id, 
            update.effective_user.username,
            main_address=user_address
        )
        
        if result["status"] == "success":
            # Success - show detailed approval instructions
            approval_message = (
                f"✅ **Agent Wallet Created Successfully!**\n\n"
                f"**Your Details:**\n"
                f"• Main Address: `{user_address[:8]}...{user_address[-6:]}`\n"
                f"• Agent Address: `{result['address'][:8]}...{result['address'][-6:]}`\n"
                f"• Agent Name: `{result['agent_name']}`\n\n"
                f"🔐 **IMPORTANT: Agent Approval Required**\n\n"
                f"**Step 1:** Visit [app.hyperliquid.xyz](https://app.hyperliquid.xyz)\n"
                f"**Step 2:** Connect with your main wallet\n"
                f"**Step 3:** Go to 'Settings' → 'Agent Wallets'\n"
                f"**Step 4:** Find and approve agent: `{result['agent_name']}`\n\n"
                f"⚠️ **Without approval, the agent cannot trade on your behalf.**\n\n"
                f"After approval, use `/agent_status` to check your setup."
            )
            
            await creating_message.edit_text(
                approval_message,
                parse_mode='Markdown',
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Check Status", callback_data=f"agent_status_{user_id}")],
                    [InlineKeyboardButton("How to Approve?", callback_data=f"approval_help_{user_id}")]
                ])
            )
            
            # Update flow state to waiting for approval
            self.user_flow_state[user_id]["state"] = APPROVAL_WAITING
            self.user_flow_state[user_id]["agent_address"] = result["address"]
            self.user_flow_state[user_id]["agent_name"] = result["agent_name"]
            
        elif result["status"] == "exists":
            await creating_message.edit_text(
                f"ℹ️ **Agent Wallet Already Exists**\n\n"
                f"You already have an agent wallet: `{result['address'][:8]}...{result['address'][-6:]}`\n\n"
                f"Use `/agent_status` to check your wallet status and see next steps.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Check Status", callback_data=f"agent_status_{user_id}")]
                ])
            )
        else:
            # Error handling
            error_message = result.get('message', 'Unknown error')
            
            await creating_message.edit_text(
                f"❌ **Agent Wallet Creation Failed**\n\n"
                f"Error: {error_message}\n\n"
                f"**Your registered address:** `{user_address[:8]}...{user_address[-6:]}`\n\n"
                f"Please try again or contact support if this persists.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Try Again", callback_data=f"retry_agent_{user_id}")],
                    [InlineKeyboardButton("Contact Support", url="https://t.me/hyperliquid_support")]
                ])
            )

    async def handle_address_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user providing their Hyperliquid address with verification"""
        user_id = update.effective_user.id
        
        # Check if we're awaiting an address
        if not context.user_data.get("awaiting_address", False):
            return
        
        # Get the address from message
        address = update.message.text.strip()
        
        # Start address verification process
        verification_result = await self.address_verifier.start_address_verification(user_id, address)
        
        if verification_result["status"] == "success":
            # Store that we're now awaiting signature
            context.user_data["awaiting_address"] = False
            context.user_data["awaiting_signature"] = True
            context.user_data["claimed_address"] = address
            
            await update.message.reply_text(
                f"✅ **Address Format Valid**\n\n"
                f"**Address:** `{address}`\n"
                f"**Status:** Found on Hyperliquid ✅\n\n"
                f"🔐 **Ownership Verification Required**\n\n"
                f"**Message to Sign:**\n"
                f"```\n{verification_result['message_to_sign']}\n```\n\n"
                f"**Instructions:**\n"
                f"{verification_result['instructions']}\n\n"
                f"⏱️ **You have {verification_result['expiry_minutes']} minutes to complete verification.**\n\n"
                f"Please sign the message above and send the signature back.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ **Address Verification Failed**\n\n"
                f"Error: {verification_result['message']}\n\n"
                f"Please provide a valid Hyperliquid address.",
                parse_mode='Markdown'
            )

    async def handle_signature_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle signature verification"""
        user_id = update.effective_user.id
        
        # Check if we're awaiting a signature
        if not context.user_data.get("awaiting_signature", False):
            return
        
        signature = update.message.text.strip()
        
        # Verify the signature
        verification_result = await self.address_verifier.verify_signature(user_id, signature)
        
        if verification_result["status"] == "success":
            # Signature verified - proceed with agent creation
            verified_address = verification_result["verified_address"]
            
            context.user_data["awaiting_signature"] = False
            self.user_flow_state[user_id]["state"] = AGENT_CREATION
            self.user_flow_state[user_id]["hl_address"] = verified_address
            
            creating_message = await update.message.reply_text(
                f"✅ **Address Ownership Verified!**\n\n"
                f"Verified address: `{verified_address}`\n\n"
                f"🔄 Creating secure agent wallet...\n"
                f"This will take a few seconds.",
                parse_mode='Markdown'
            )
            
            # Create agent wallet with verified address
            result = await self.wallet_manager.create_agent_wallet(
                user_id, 
                update.effective_user.username,
                main_address=verified_address
            )
            
            if result["status"] == "success":
                # Success - show detailed approval instructions
                approval_message = (
                    f"✅ **Agent Wallet Created Successfully!**\n\n"
                    f"**Your Details:**\n"
                    f"• Main Address: `{verified_address}`\n"
                    f"• Agent Address: `{result['address']}`\n"
                    f"• Agent Name: `{result['agent_name']}`\n\n"
                    f"🔐 **IMPORTANT: Agent Approval Required**\n\n"
                    f"**Step 1:** Visit [app.hyperliquid.xyz](https://app.hyperliquid.xyz)\n"
                    f"**Step 2:** Connect with your main wallet\n"
                    f"**Step 3:** Go to 'Settings' → 'Agent Wallets'\n"
                    f"**Step 4:** Find and approve agent: `{result['agent_name']}`\n\n"
                    f"⚠️ **Without approval, the agent cannot trade on your behalf.**\n\n"
                    f"After approval, use `/agent_status` to check your setup."
                )
                
                await creating_message.edit_text(
                    approval_message,
                    parse_mode='Markdown',
                    disable_web_page_preview=True,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Check Status", callback_data=f"agent_status_{user_id}")],
                        [InlineKeyboardButton("How to Approve?", callback_data=f"approval_help_{user_id}")]
                    ])
                )
                
                # Update flow state to waiting for approval
                self.user_flow_state[user_id]["state"] = APPROVAL_WAITING
                self.user_flow_state[user_id]["agent_address"] = result["address"]
                self.user_flow_state[user_id]["agent_name"] = result["agent_name"]
                
            elif result["status"] == "exists":
                await creating_message.edit_text(
                    f"ℹ️ **Agent Wallet Already Exists**\n\n"
                    f"You already have an agent wallet: `{result['address']}`\n\n"
                    f"Use `/agent_status` to check your wallet status and see next steps.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Check Status", callback_data=f"agent_status_{user_id}")]
                    ])
                )
            else:
                # Enhanced error handling with specific guidance
                error_message = result.get('message', 'Unknown error')
                
                if "fund" in error_message.lower() or "deposit" in error_message.lower():
                    await creating_message.edit_text(
                        f"❌ **Service Temporarily Unavailable**\n\n"
                        f"Our master wallet needs funding to create new agent wallets.\n"
                        f"We've notified our administrators.\n\n"
                        f"**What you can do:**\n"
                        f"• Try again in a few hours\n"
                        f"• Contact support if urgent\n"
                        f"• Your address `{verified_address}` has been saved for retry",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Try Again", callback_data=f"retry_agent_{user_id}")],
                            [InlineKeyboardButton("Contact Support", url="https://t.me/hyperliquid_support")]
                        ])
                    )
                elif "permission" in error_message.lower():
                    await creating_message.edit_text(
                        f"❌ **Address Verification Failed**\n\n"
                        f"The address `{verified_address}` could not be verified.\n\n"
                        f"**Please check:**\n"
                        f"• Is this your correct Hyperliquid address?\n"
                        f"• Do you have an active account on Hyperliquid?\n"
                        f"• Have you made at least one transaction?\n\n"
                        f"Try entering your address again.",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Enter Address Again", callback_data=f"enter_address_{user_id}")]
                        ])
                    )
                else:
                    await creating_message.edit_text(
                        f"❌ **Agent Wallet Creation Failed**\n\n"
                        f"Error: {error_message}\n\n"
                        f"**Troubleshooting:**\n"
                        f"• Ensure your Hyperliquid address is correct\n"
                        f"• Make sure you have an active account\n"
                        f"• Try again in a few minutes\n\n"
                        f"Contact support if this persists.",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("Try Again", callback_data=f"retry_agent_{user_id}")],
                            [InlineKeyboardButton("Contact Support", url="https://t.me/hyperliquid_support")]
                        ])
                    )
        else:
            await update.message.reply_text(
                f"❌ **Signature Verification Failed**\n\n"
                f"Error: {verification_result['message']}\n\n"
                f"Please try signing the message again, or restart the process with `/create_agent`.",
                parse_mode='Markdown'
            )

    async def handle_agent_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Enhanced agent status command with proper state management"""
        user_id = update.effective_user.id
        
        # Check if wallet manager is properly initialized
        if not self.wallet_manager:
            await update.effective_message.reply_text(
                "❌ Error: Wallet manager not initialized. Please contact support."
            )
            return
        
        # Check if user has an agent wallet
        wallet_info = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_info:
            # User doesn't have agent wallet - guide them through creation
            await update.effective_message.reply_text(
                "❌ **No Agent Wallet Found**\n\n"
                "You don't have an agent wallet yet. Let's create one!\n\n"
                "**What you'll need:**\n"
                "• Your Hyperliquid account address\n"
                "• Access to approve the agent in Hyperliquid app\n\n"
                "Ready to start?",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Create Agent Wallet", callback_data=f"create_agent_session_{user_id}")],
                    [InlineKeyboardButton("❓ What's an Agent Wallet?", callback_data=f"explain_agent_{user_id}")]
                ])
            )
            return
        
        # Establish session if not already established
        if user_id not in self.user_sessions:
            await self._establish_user_session(user_id, update.effective_user.username, wallet_info)
        
        # Get comprehensive wallet status
        status_loading = await update.effective_message.reply_text("🔄 Checking your agent wallet status...")
        
        try:
            wallet_status = await self.wallet_manager.get_wallet_status(user_id)
            approval_result = await self.wallet_manager.check_agent_approval(user_id)
            
            # Build detailed status message
            status_message = self._build_status_message(wallet_info, wallet_status, approval_result)
            buttons = self._build_status_buttons(user_id, wallet_status, approval_result)
            
            await status_loading.edit_text(
                status_message,
                parse_mode='Markdown',
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        except Exception as e:
            logger.error(f"Error getting agent wallet status for user {user_id}: {e}")
            await status_loading.edit_text(
                f"❌ **Error Getting Status**\n\n"
                f"Error: {str(e)}\n\n"
                f"**Troubleshooting:**\n"
                f"• Check your internet connection\n"
                f"• Try again in a moment\n"
                f"• Contact support if error persists",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Try Again", callback_data=f"refresh_agent_status_{user_id}")],
                    [InlineKeyboardButton("Contact Support", url="https://t.me/hyperliquid_support")]
                ])
            )

    def _build_status_message(self, wallet_info: Dict, wallet_status: Dict, approval_result: Dict) -> str:
        """Build comprehensive status message"""
        status_emoji = wallet_status.get('status_emoji', '❓')
        status_text = wallet_status.get('status', 'Unknown')
        balance = wallet_status.get('balance', 0)
        funded = wallet_status.get('funded', False)
        trading_enabled = wallet_status.get('trading_enabled', False)
        approved = approval_result.get('approved', False)
        
        message = (
            f"{status_emoji} **Agent Wallet Status: {status_text}**\n\n"
            f"**📋 Wallet Details:**\n"
            f"• Main Address: `{wallet_info['main_address']}`\n"
            f"• Agent Address: `{wallet_info['address']}`\n"
            f"• Created: {wallet_info['created_at']}\n\n"
            f"**💰 Account Status:**\n"
            f"• Balance: ${balance:.2f}\n"
            f"• Funded: {'✅ Yes' if funded else '❌ No'}\n"
            f"• Approved: {'✅ Yes' if approved else '❌ Pending'}\n"
            f"• Trading: {'✅ Enabled' if trading_enabled else '❌ Disabled'}\n\n"
        )
        
        # Add specific guidance based on current state
        if not approved:
            message += (
                f"🔐 **Next Step: Approve Agent Wallet**\n\n"
                f"Your agent wallet needs approval to trade on your behalf.\n\n"
                f"**How to approve:**\n"
                f"1. Visit [app.hyperliquid.xyz](https://app.hyperliquid.xyz)\n"
                f"2. Connect your main wallet\n"
                f"3. Go to Settings → Agent Wallets\n"
                f"4. Find and approve: `{wallet_info.get('agent_name', 'your agent')}`\n\n"
                f"⚠️ Without approval, trading cannot be enabled."
            )
        elif not funded:
            message += (
                f"💳 **Next Step: Fund Your Account**\n\n"
                f"Your agent is approved but needs funding to start trading.\n\n"
                f"**How to fund:**\n"
                f"1. Send USDC to your main address: `{wallet_info['main_address']}`\n"
                f"2. Minimum recommended: $10 USDC\n"
                f"3. Funds will appear in your agent wallet automatically\n\n"
                f"💡 You can trade with any amount, but $10+ is recommended for grid strategies."
            )
        elif not trading_enabled:
            message += (
                f"🚀 **Ready to Trade!**\n\n"
                f"Your agent wallet is approved and funded.\n"
                f"You can now enable trading to start automated strategies.\n\n"
                f"**Available strategies:**\n"
                f"• Grid Trading (buy low, sell high automatically)\n"
                f"• Market Making (earn rebates)\n"
                f"• Test trades (manual order placement)\n\n"
                f"Click 'Enable Trading' below to start!"
            )
        else:
            message += (
                f"✅ **Trading Active!**\n\n"
                f"Your agent wallet is fully operational and trading.\n\n"
                f"**Active features:**\n"
                f"• Automated grid trading\n"
                f"• Real-time order management\n"
                f"• Portfolio monitoring\n\n"
                f"Use the buttons below to manage your trading."
            )
        
        return message

    def _build_status_buttons(self, user_id: int, wallet_status: Dict, approval_result: Dict) -> List[List[InlineKeyboardButton]]:
        """Build appropriate action buttons based on wallet state"""
        buttons = []
        
        approved = approval_result.get('approved', False)
        funded = wallet_status.get('funded', False)
        trading_enabled = wallet_status.get('trading_enabled', False)
        
        if not approved:
            buttons.extend([
                [InlineKeyboardButton("🔄 Check Approval Status", callback_data=f"refresh_agent_status_{user_id}")],
                [InlineKeyboardButton("❓ How to Approve?", callback_data=f"approval_help_{user_id}")]
            ])
        elif not funded:
            buttons.extend([
                [InlineKeyboardButton("🔄 Check Balance", callback_data=f"refresh_agent_status_{user_id}")],
                [InlineKeyboardButton("💡 Funding Guide", callback_data=f"funding_help_{user_id}")]
            ])
        else:
            # Wallet is approved and funded
            if trading_enabled:
                buttons.extend([
                    [InlineKeyboardButton("📊 View Portfolio", callback_data=f"view_portfolio_{user_id}")],
                    [InlineKeyboardButton("🛑 Stop Trading", callback_data=f"disable_trading_{user_id}")],
                    [InlineKeyboardButton("🚨 Emergency Stop", callback_data=f"emergency_stop_{user_id}")],
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_agent_status_{user_id}")]
                ])
            else:
                buttons.extend([
                    [InlineKeyboardButton("🚀 Enable Trading", callback_data=f"enable_trading_{user_id}")],
                    [InlineKeyboardButton("🧪 Test Trade", callback_data=f"test_trade_{user_id}")],
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_agent_status_{user_id}")]
                ])
        
        return buttons

    async def handle_agent_creation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle agent wallet creation callback"""
        query = update.callback_query
        await query.answer("Starting agent wallet setup...")
        
        # Start the onboarding flow
        await query.edit_message_text(
            "🤖 **Welcome to the Hyperliquid Trading Bot Setup!**\n\n"
            "Do you have an existing Hyperliquid account?",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes, I have an account", callback_data=f"has_account_{query.from_user.id}")],
                [InlineKeyboardButton("No, I don't have one yet", callback_data=f"no_account_{query.from_user.id}")]
            ])
        )
    
    async def handle_agent_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /agent_status command"""
        user_id = update.effective_user.id
        
        # Check if wallet manager is properly initialized
        if not self.wallet_manager:
            await update.effective_message.reply_text(
                "❌ Error: Wallet manager not initialized. Please contact support."
            )
            return
        
        # Check if user has an agent wallet
        wallet_info = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_info:
            await update.effective_message.reply_text(
                "❌ You don't have an agent wallet yet.\n\n"
                "Use `/create_agent` to create one.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Create Agent Wallet", callback_data=f"create_agent_session_{user_id}")]
                ])
            )
            return
        
        # Get wallet status
        status_loading = await update.effective_message.reply_text("🔄 Fetching your wallet status...")
        
        try:
            wallet_status = await self.wallet_manager.get_wallet_status(user_id)
            
            # Format status message
            status_message = (
                f"{wallet_status['status_emoji']} **Agent Wallet Status: {wallet_status['status']}**\n\n"
                f"Main Address: `{wallet_info['main_address']}`\n"
                f"Agent Address: `{wallet_info['address']}`\n"
                f"Balance: ${wallet_status['balance']:.2f}\n"
                f"Created: {wallet_info['created_at']}\n"
                f"Trading Enabled: {'✅ Yes' if wallet_status['trading_enabled'] else '❌ No'}\n"
                f"Approval Status: {'✅ Approved' if wallet_status['approved'] else '❌ Pending'}\n\n"
            )
            
            # Determine current state and appropriate next actions
            user_state = self.user_flow_state.get(user_id, {}).get("state", "unknown")
            
            # Add appropriate instructions based on state
            buttons = []
            
            if user_state == APPROVAL_WAITING:
                status_message += (
                    "⏳ **Waiting for Approval**\n\n"
                    "Your agent wallet needs to be approved in your Hyperliquid account settings.\n\n"
                    "Please visit [Hyperliquid app](https://app.hyperliquid.xyz) and approve this agent in your account settings."
                )
                buttons = [
                    [InlineKeyboardButton("Refresh Status", callback_data=f"refresh_agent_status_{user_id}")]
                ]
            elif not wallet_status['funded']:
                status_message += (
                    "⚠️ **Your account needs funding to start trading**\n\n"
                    "To fund your account, send USDC to your main Hyperliquid address shown above.\n"
                    "Minimum recommended amount: $10 USDC\n\n"
                    "After funding, use `/agent_status` to verify your balance."
                )
                buttons = [
                    [InlineKeyboardButton("Refresh Status", callback_data=f"refresh_agent_status_{user_id}")]
                ]
            else:
                # Account is funded
                status_message += (
                    "✅ **Your account is funded and ready for trading!**\n\n"
                    "You can now start trading using the available commands."
                )
                
                if wallet_status['trading_enabled']:
                    buttons = [
                        [InlineKeyboardButton("📊 View Portfolio", callback_data=f"view_portfolio_{user_id}")],
                        [InlineKeyboardButton("Stop Trading", callback_data=f"disable_trading_{user_id}")],
                        [InlineKeyboardButton("Emergency Stop", callback_data=f"emergency_stop_{user_id}")]
                    ]
                else:
                    buttons = [
                        [InlineKeyboardButton("Enable Trading", callback_data=f"enable_trading_{user_id}")],
                        [InlineKeyboardButton("Refresh Status", callback_data=f"refresh_agent_status_{user_id}")]
                    ]
            
            await status_loading.edit_text(
                status_message,
                parse_mode='Markdown',
                disable_web_page_preview=True,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            
        except Exception as e:
            logger.error(f"Error getting agent wallet status for user {user_id}: {e}")
            await status_loading.edit_text(
                f"❌ Error getting wallet status: {str(e)}\n\n"
                f"Please try again later.",
                parse_mode='Markdown'
            )
    
    async def handle_emergency_stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle emergency stop command"""
        user_id = update.effective_user.id
        
        # Check if user has an agent wallet
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet manager not initialized. Please contact support.")
            return
            
        wallet_info = await self.wallet_manager.get_user_wallet(user_id)
        if not wallet_info:
            await update.message.reply_text(
                "❌ You don't have an agent wallet. Use `/create_agent` to set one up.",
                parse_mode='Markdown'
            )
            return
        
        # Show confirmation message
        await update.message.reply_text(
            "⚠️ **EMERGENCY STOP REQUESTED**\n\n"
            "This will:\n"
            "- Cancel all open orders\n"
            "- Close all positions\n"
            "- Disable automated trading\n\n"
            "Are you sure you want to proceed?",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⚠️ YES, EMERGENCY STOP", callback_data=f"confirm_emergency_stop_{user_id}")],
                [InlineKeyboardButton("No, cancel", callback_data=f"cancel_emergency_{user_id}")]
            ])
        )
    
    async def _establish_user_session(self, user_id: int, username: str, wallet_info: Dict):
        """
        Establish a user session based on existing agent wallet
        
        Args:
            user_id: Telegram user ID
            username: Telegram username
            wallet_info: User's wallet information
        """
        try:
            # Create Info instance for the session
            info = Info(self.base_url)
            
            # Create session data
            session_data = {
                'user_id': user_id,
                'username': username,
                'address': wallet_info.get('main_address'),
                'agent_address': wallet_info.get('address'),
                'auth_method': 'agent',
                'connected_at': datetime.now(),
                'last_activity': time.time(),
                'info': info,
                'wallet_info': wallet_info
            }
            
            # Store session
            self.user_sessions[user_id] = session_data
            
            logger.info(f"Established session for user {user_id} with existing agent wallet")
            
        except Exception as e:
            logger.error(f"Error establishing user session for {user_id}: {e}")

    async def handle_has_account_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user confirming they have a Hyperliquid account"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Update user flow state
        if user_id in self.user_flow_state:
            self.user_flow_state[user_id]["has_account"] = True
        
        await query.answer()
        
        # Ask for their Hyperliquid address
        address_prompt = (
            "📝 **Enter Your Hyperliquid Account Address**\n\n"
            "Please enter your Hyperliquid account address (starting with '0x').\n\n"
            "I'll create a secure agent wallet that can trade on behalf of your account."
        )
        
        await query.edit_message_text(
            address_prompt,
            parse_mode='Markdown'
        )
        
        # Store that we're awaiting an address
        context.user_data["awaiting_address"] = True
    
    async def handle_no_account_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user confirming they don't have a Hyperliquid account"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Update user flow state
        if user_id in self.user_flow_state:
            self.user_flow_state[user_id]["has_account"] = False
        
        await query.answer()
        
        # Provide instructions to create an account first
        no_account_message = (
            "❗ **Hyperliquid Account Required**\n\n"
            "You need to create a Hyperliquid account first before using this bot.\n\n"
            "Please visit [app.hyperliquid.xyz](https://app.hyperliquid.xyz) to create your account, then come back and use `/create_agent` again.\n\n"
            "If you need help creating your account, visit the [Hyperliquid documentation](https://hyperliquid.xyz/docs)."
        )
        
        await query.edit_message_text(
            no_account_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

    def validate_session(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Validate if user session is valid and active"""
        if user_id not in self.user_sessions:
            return False, "You're not connected. Use `/create_agent` to create a secure agent wallet."
        
        session = self.user_sessions[user_id]
        current_time = time.time()
        last_activity = session.get('last_activity', 0)
        
        # Agent sessions last up to 24 hours
        timeout_hours = 24
        timeout_seconds = timeout_hours * 3600
        
        if current_time - last_activity > timeout_seconds:
            self.user_sessions.pop(user_id, None) # Remove expired session
            logger.info(f"Session timed out for user {user_id} (method: {session.get('auth_method')}).")
            return False, f"Your session has expired due to inactivity ({timeout_hours}h). Please use /create_agent to reconnect."
        
        session['last_activity'] = current_time # Update activity time
        return True, None

    def get_session_info_text(self, user_id: int) -> str:
        """Get formatted session info string for display"""
        if user_id not in self.user_sessions:
            return "Status: Disconnected 🔴\n\nUse `/create_agent` to create a secure agent wallet."
        
        session = self.user_sessions[user_id]
        now = datetime.now()
        connected_at_dt = session.get('connected_at', now) # Fallback to now if not set
        time_connected_delta = now - connected_at_dt
        
        hours_conn = int(time_connected_delta.total_seconds() // 3600)
        minutes_conn = int((time_connected_delta.total_seconds() % 3600) // 60)
        
        current_time = time.time()
        last_activity = session.get('last_activity', 0)
        timeout_hours = 24
        timeout_seconds = timeout_hours * 3600
        
        timeout_remaining_seconds = max(0, timeout_seconds - (current_time - last_activity))
        hours_rem = int(timeout_remaining_seconds // 3600)
        minutes_rem = int((timeout_remaining_seconds % 3600) // 60)
        
        # Get agent wallet status if available
        balance = 0.0
        trading_status = "Not enabled"
        if self.wallet_manager:
            try:
                # Use asyncio to run the coroutine in sync context
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, create a task
                    task = asyncio.create_task(self.wallet_manager.get_wallet_status(user_id))
                    # Don't await here since this is a sync method
                    wallet_status = None
                else:
                    wallet_status = asyncio.run(self.wallet_manager.get_wallet_status(user_id))
                
                if wallet_status:
                    balance = wallet_status.get('balance', 0.0)
                    trading_status = "Active" if wallet_status.get('trading_enabled', False) else "Not enabled"
            except Exception as e:
                logger.error(f"Error getting wallet status in session info: {e}")
        
        # Escape markdown characters to prevent parsing errors
        address = session.get('address', 'N/A')
        agent_address = session.get('agent_address', 'N/A')
        
        info_text = f"Status: Connected 🟢 (Agent Wallet)\n"
        info_text += f"Main Address: `{address}`\n"
        info_text += f"Agent Address: `{agent_address}`\n"
        info_text += f"Connected for: {hours_conn}h {minutes_conn}m\n"
        info_text += f"Session expires in: {hours_rem}h {minutes_rem}m (approx)\n"
        info_text += f"Account Value: ${balance:,.2f}\n"
        info_text += f"Trading Status: {trading_status}"
        
        return info_text

