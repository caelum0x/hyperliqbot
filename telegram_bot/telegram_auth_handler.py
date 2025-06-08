"""
Secure authentication handler for Telegram bot users
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

# Assuming ProfitOptimizedTrader might be used in session, adjust import as needed
# from trading_engine.base_trader import ProfitOptimizedTrader 

logger = logging.getLogger(__name__)

class TelegramAuthHandler:
    """Handles secure user authentication for Telegram bot"""
    
    def __init__(self, user_sessions: Dict[int, Dict[str, Any]], base_url=None, bot_username: str = "YourDefaultBotUsername"):
        self.user_sessions = user_sessions
        self.base_url = base_url or constants.MAINNET_API_URL # Default to mainnet
        self.bot_username = bot_username # Store bot_username
        
    async def handle_connect_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /connect command securely"""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id # Get chat_id for deleting message
        
        # Check if message is in private chat
        if update.effective_chat.type != "private":
            await update.message.reply_text(
                "⚠️ For security, please send this command in a private chat with the bot.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Message Privately", url=f"https://t.me/{self.bot_username}") # Use self.bot_username
                ]])
            )
            return
        
        if len(context.args) == 0:
            await update.message.reply_text(
                "🔐 **Connect Your Wallet**\n\n"
                "To connect your wallet, send your private key directly in the command:\n"
                "`/connect YOUR_ETHEREUM_PRIVATE_KEY`\n\n"
                "⚠️ **Security Note:** Your private key is used for this session only to interact with the Hyperliquid API. "
                "For added security, ensure this chat is private. The message containing your key will be deleted automatically.\n\n"
                "💡 **Recommended:** After connecting, use the 'Create Agent Wallet' button or `/create_agent` command for enhanced security.",
                parse_mode='Markdown'
            )
            return
        
        private_key_input = context.args[0]
        message_id_to_delete = update.message.message_id # Get message_id to delete

        # Attempt to delete the message containing the private key immediately
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id_to_delete)
            # Send confirmation as a new message, not a reply to the (now deleted) original
            await context.bot.send_message(chat_id=chat_id, 
                text="🔒 For security, I've deleted your message containing the private key.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Could not delete private key message {message_id_to_delete} for user {user_id}: {e}")
            await context.bot.send_message(chat_id=chat_id,
                text="⚠️ Please delete your message containing the private key manually for security.",
                parse_mode='Markdown'
            )
            
        try:
            # Validate private key format
            is_valid_format = (private_key_input.startswith("0x") and len(private_key_input) == 66) or \
                              (not private_key_input.startswith("0x") and len(private_key_input) == 64)
            if not is_valid_format:
                await context.bot.send_message(chat_id=chat_id,
                    text="❌ **Invalid Private Key Format**\n"
                         "Please provide a valid 64-character hex private key, optionally prefixed with '0x'.",
                    parse_mode='Markdown'
                )
                return
                
            private_key = private_key_input
            # Add 0x prefix if missing and length is 64
            if not private_key.startswith("0x") and len(private_key) == 64:
                private_key = "0x" + private_key
            
            # Initialize wallet
            user_account: LocalAccount = eth_account.Account.from_key(private_key)
            user_address = user_account.address
            
            # Initialize API clients
            user_info = Info(self.base_url, skip_ws=True)
            user_exchange = Exchange(wallet=user_account, base_url=self.base_url)
            
            # Test connection
            user_state_data = user_info.user_state(user_address)
            account_value = float(user_state_data.get('marginSummary', {}).get('accountValue', 0))
            
            # Create user session (initially direct)
            self.user_sessions[user_id] = {
                'exchange': user_exchange,
                'info': user_info,
                'address': user_address,
                'account': user_account, # Store the main LocalAccount object
                'balance': account_value,
                'connected_at': datetime.now(),
                'auth_method': 'direct', # Initially direct
                'last_activity': time.time(),
                # 'trader': ProfitOptimizedTrader(address=user_address, info=user_info, exchange=user_exchange) # If you have this class
            }
            
            logger.info(f"User {user_id} connected with direct wallet: {user_address}")
            
            # Offer agent wallet option
            keyboard = [
                [InlineKeyboardButton("🔐 Create Agent Wallet (Recommended)", callback_data="create_agent")], # Simple callback_data
                [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")] # Example action
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(chat_id=chat_id,
                text=f"✅ **Wallet Connected Successfully!**\n\n"
                     f"👤 Address: `{user_address}`\n" # Full address for clarity, or truncate
                     f"💰 Account Value: ${account_value:,.2f}\n\n"
                     f"⚠️ **Security Notice:** You're currently using direct wallet authentication.\n"
                     f"For enhanced security, we recommend creating an agent wallet.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except ValueError as ve: # More specific error for invalid key format during Account.from_key
            logger.error(f"Invalid private key format provided by user {user_id}: {ve}")
            await context.bot.send_message(chat_id=chat_id,
                text=f"❌ **Connection Failed**\n\nError: Invalid private key format. Please ensure it's a correct Ethereum private key.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Connection error for user {user_id}: {e}", exc_info=True)
            await context.bot.send_message(chat_id=chat_id,
                text=f"❌ **Connection Failed**\n\nAn unexpected error occurred: {str(e)}",
                parse_mode='Markdown'
            )
    
    async def create_agent_wallet_for_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: # Renamed for clarity
        """Create an agent wallet for the user, called via callback"""
        query = update.callback_query
        await query.answer() # Acknowledge callback
        user_id = query.from_user.id
        
        # Check if user is authenticated (should have a 'direct' session)
        if user_id not in self.user_sessions or self.user_sessions[user_id].get('auth_method') != 'direct':
            await query.edit_message_text(
                "❌ Please connect your wallet first using `/connect YOUR_PRIVATE_KEY` before creating an agent."
            )
            return
        
        session = self.user_sessions[user_id]
        
        # Get main account and exchange from the existing 'direct' session
        main_account = session.get('account') # This is the LocalAccount object for the main key
        main_address = session.get('address')
        # The exchange instance in a 'direct' session is already authenticated with the main key
        main_exchange_with_main_key = session.get('exchange') 
        
        if not all([main_account, main_address, main_exchange_with_main_key]):
            await query.edit_message_text(
                "❌ Authentication data is incomplete. Please reconnect using `/connect YOUR_PRIVATE_KEY`."
            )
            return
        
        try:
            await query.edit_message_text("🔄 Creating agent wallet. This may take a moment...")
            
            agent_name = f"telegram_user_{user_id}_{int(time.time())%10000}" # Unique agent name
            # Use the main_exchange_with_main_key to approve the agent
            approve_result, agent_key = main_exchange_with_main_key.approve_agent(agent_name) 
            
            if approve_result.get("status") != "ok":
                error_detail = approve_result.get("response", {}).get("error", str(approve_result))
                await query.edit_message_text(f"❌ Failed to create agent wallet: {error_detail}")
                return
            
            agent_account: LocalAccount = eth_account.Account.from_key(agent_key)
            agent_exchange = Exchange(
                wallet=agent_account, 
                base_url=main_exchange_with_main_key.base_url, # Use same base_url
                vault_address=main_address # Agent acts on behalf of main_address
            )
            
            # Update user session to use the agent
            self.user_sessions[user_id].update({
                'exchange': agent_exchange,  # Now use agent_exchange
                'agent_address': agent_account.address,
                'agent_name': agent_name,
                'auth_method': 'agent',      # Updated auth_method
                'last_activity': time.time() # Reset activity timer
                # 'trader': ProfitOptimizedTrader(address=main_address, info=session['info'], exchange=agent_exchange) # Update trader
            })
            # If ProfitOptimizedTrader was in session, update its exchange instance:
            if 'trader' in self.user_sessions[user_id] and hasattr(self.user_sessions[user_id]['trader'], 'exchange'):
                self.user_sessions[user_id]['trader'].exchange = agent_exchange


            logger.info(f"Created agent wallet for user {user_id}: {agent_account.address} (main: {main_address})")
            
            keyboard = [
                [InlineKeyboardButton("📊 View Portfolio", callback_data="view_portfolio")],
                # [InlineKeyboardButton("🚀 Start Trading", callback_data="start_trading")] # Example
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"✅ **Agent Wallet Created Successfully!**\n\n"
                f"👤 Main Address: `{main_address}`\n"
                f"🤖 Agent Address: `{agent_account.address}`\n\n"
                f"🛡️ **Enhanced Security Enabled!**\n"
                f"Your agent wallet has limited permissions (trade-only).\n"
                f"Your main private key is no longer directly used for trading by the bot for this session.",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error creating agent wallet for user {user_id}: {e}", exc_info=True)
            await query.edit_message_text(
                f"❌ **Agent Wallet Creation Failed**\n\nError: {str(e)}\n\n"
                f"You can continue using direct authentication for now.",
                parse_mode='Markdown'
            )
    
    def validate_session(self, user_id: int) -> Tuple[bool, Optional[str]]:
        """Validate if user session is valid and active"""
        if user_id not in self.user_sessions:
            return False, "You're not connected. Use `/connect YOUR_PRIVATE_KEY` to authenticate."
        
        session = self.user_sessions[user_id]
        current_time = time.time()
        last_activity = session.get('last_activity', 0)
        
        timeout_hours = 12 if session.get('auth_method') == 'agent' else 1 # Agent sessions last longer
        timeout_seconds = timeout_hours * 3600
        
        if current_time - last_activity > timeout_seconds:
            self.user_sessions.pop(user_id, None) # Remove expired session
            logger.info(f"Session timed out for user {user_id} (method: {session.get('auth_method')}).")
            return False, f"Your session has expired due to inactivity ({timeout_hours}h). Please /connect again."
        
        session['last_activity'] = current_time # Update activity time
        return True, None
    
    def get_session_info_text(self, user_id: int) -> str: # Renamed from get_session_info for clarity
        """Get formatted session info string for display"""
        if user_id not in self.user_sessions:
            return "Status: Disconnected 🔴"
        
        session = self.user_sessions[user_id]
        now = datetime.now()
        connected_at_dt = session.get('connected_at', now) # Fallback to now if not set
        time_connected_delta = now - connected_at_dt
        
        hours_conn = int(time_connected_delta.total_seconds() // 3600)
        minutes_conn = int((time_connected_delta.total_seconds() % 3600) // 60)
        
        current_time = time.time()
        last_activity = session.get('last_activity', 0)
        timeout_hours = 12 if session.get('auth_method') == 'agent' else 1
        timeout_seconds = timeout_hours * 3600
        
        timeout_remaining_seconds = max(0, timeout_seconds - (current_time - last_activity))
        hours_rem = int(timeout_remaining_seconds // 3600)
        minutes_rem = int((timeout_remaining_seconds % 3600) // 60)

        auth_method_display = "Agent Wallet (Enhanced Security)" if session.get('auth_method') == 'agent' else "Direct Key (Standard Security)"
        
        info_text = f"Status: Connected 🟢 ({auth_method_display})\n"
        info_text += f"Main Address: `{session.get('address', 'N/A')}`\n"
        if session.get('auth_method') == 'agent':
            info_text += f"Agent Address: `{session.get('agent_address', 'N/A')}`\n"
        info_text += f"Connected for: {hours_conn}h {minutes_conn}m\n"
        info_text += f"Session expires in: {hours_rem}h {minutes_rem}m (approx)\n"
        info_text += f"Account Value: ${session.get('balance', 0.0):,.2f}" # Assuming balance is updated
        return info_text

