import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)

class PortfolioHandler:
    def __init__(self, wallet_manager):
        self.wallet_manager = wallet_manager

    async def display_portfolio(self, update: Update, context: CallbackContext) -> None:
        """Display the user's agent wallet portfolio."""
        user_id = update.effective_user.id
        message_object = update.message or update.callback_query.message # Handle both command and callback

        if not self.wallet_manager:
            await message_object.reply_text("❌ Portfolio management not available (WalletManager missing).")
            return

        user_wallet = await self.wallet_manager.get_user_wallet(user_id)
        if not user_wallet:
            await message_object.reply_text(
                "❌ No agent wallet found. Use /agent to create one.",
                parse_mode='Markdown'
            )
            return

        # Show loading message if it's a command
        if update.message: # only send new message if it's a command
             await message_object.reply_text("🔄 Loading your portfolio... Please wait.")
        elif update.callback_query: # edit existing message if it's a callback
            await update.callback_query.edit_message_text("🔄 Loading your portfolio... Please wait.")


        portfolio_data = await self.wallet_manager.get_user_portfolio(user_id)

        if portfolio_data['status'] != 'success':
            await message_object.reply_text(
                f"❌ Error loading portfolio: {portfolio_data['message']}",
                parse_mode='Markdown'
            )
            return

        portfolio_msg = f"""
📊 **Your Agent Portfolio**
Agent Address: `{user_wallet['address']}`

**Account Value:** ${portfolio_data['account_value']:.2f} USDC
**Available Balance:** ${portfolio_data['available_balance']:.2f} USDC
**Unrealized PnL:** ${portfolio_data['unrealized_pnl']:.2f} USDC

**Positions: {len(portfolio_data['positions'])}**
        """

        if portfolio_data['positions']:
            for pos in portfolio_data['positions']:
                side = "📈 LONG" if pos['size'] > 0 else "📉 SHORT"
                portfolio_msg += f"\n• {pos['coin']}: {side} {abs(pos['size'])} @ ${pos['entry_price']:.4f}"
                portfolio_msg += f"\n  Unrealized PnL: ${pos['unrealized_pnl']:.2f}"
        else:
            portfolio_msg += "\n• No open positions."

        portfolio_msg += f"\n\n**Recent Trades: {len(portfolio_data['recent_trades'])}** (Max 10 shown)"
        if portfolio_data['recent_trades']:
            for trade in portfolio_data['recent_trades'][:10]: # Show up to 10 most recent
                trade_time = datetime.strptime(trade['time'], '%Y-%m-%d %H:%M:%S').strftime('%m-%d %H:%M')
                portfolio_msg += f"\n• {trade_time} {trade['coin']}: {trade['side']} {trade['size']} @ ${trade['price']:.2f} (Fee: ${trade['fee']:.4f})"
        else:
            portfolio_msg += "\n• No recent trades."

        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Portfolio", callback_data="portfolio_refresh")],
            # Add more buttons like "Manage Positions", "Trade History" later
            [InlineKeyboardButton("← Back to Wallet Status", callback_data="refresh_wallet_status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text(text=portfolio_msg, parse_mode='Markdown', reply_markup=reply_markup)
        else:
            await message_object.reply_text(text=portfolio_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_portfolio_refresh_callback(self, update: Update, context: CallbackContext):
        """Handles the refresh portfolio callback."""
        query = update.callback_query
        await query.answer("Refreshing portfolio...")
        await self.display_portfolio(update, context)

    # Placeholder for more detailed P&L tracking
    async def display_pnl_tracking(self, update: Update, context: CallbackContext):
        await update.message.reply_text("📈 P&L tracking feature coming soon!")

    # Placeholder for performance analytics
    async def display_performance_analytics(self, update: Update, context: CallbackContext):
        await update.message.reply_text("📉 Performance analytics feature coming soon!")
