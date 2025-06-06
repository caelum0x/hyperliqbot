import logging
from typing import Dict, Any

from telegram import Update
from telegram.ext import ContextTypes

from hyperliquid.utils.types import Cloid
from .user_manager import UserManager
from .config import BotConfig
from .utils import format_number, parse_order_params, validate_user_access

logger = logging.getLogger(__name__)


class TradingHandlers:
    def __init__(self, user_manager: UserManager, config: BotConfig):
        self.user_manager = user_manager
        self.config = config
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        await update.message.reply_text(
            "🚀 Welcome to Hyperliquid Trading Bot!\n\n"
            "Commands:\n"
            "/register - Register your wallet\n"
            "/balance - Check account balance\n"
            "/positions - View open positions\n"
            "/orders - View open orders\n"
            "/buy - Place buy order\n"
            "/sell - Place sell order\n"
            "/market_buy - Place market buy order\n"
            "/market_sell - Place market sell order\n"
            "/cancel - Cancel order\n"
            "/help - Show this help message"
        )
    
    async def register(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Register user wallet"""
        if not validate_user_access(update.effective_user.id, self.config):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        if len(context.args) < 1:
            await update.message.reply_text(
                "Please provide your private key:\n"
                "/register <private_key> [account_address]"
            )
            return
        
        private_key = context.args[0]
        account_address = context.args[1] if len(context.args) > 1 else ""
        
        if self.user_manager.register_user(update.effective_user.id, private_key, account_address):
            await update.message.reply_text("✅ Wallet registered successfully!")
            # Delete the message containing the private key
            await update.message.delete()
        else:
            await update.message.reply_text("❌ Invalid private key provided.")
    
    async def balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check account balance"""
        session = self.user_manager.get_session(update.effective_user.id)
        if not session:
            session = self.user_manager.authenticate_user(update.effective_user.id)
            if not session:
                await update.message.reply_text("❌ Please register first using /register")
                return
        
        try:
            base_url = self.config.get("hyperliquid.base_url")
            info = session.get_info(base_url)
            
            # Get user state
            user_state = info.user_state(session.account_address)
            spot_state = info.spot_user_state(session.account_address)
            
            # Format balance message
            margin_summary = user_state["marginSummary"]
            account_value = float(margin_summary["accountValue"])
            withdrawable = float(user_state["withdrawable"])
            
            message = f"💰 **Account Balance**\n\n"
            message += f"Account Value: ${format_number(account_value)}\n"
            message += f"Withdrawable: ${format_number(withdrawable)}\n"
            
            # Add spot balances
            if spot_state["balances"]:
                message += "\n**Spot Balances:**\n"
                for balance in spot_state["balances"]:
                    if float(balance["total"]) > 0:
                        message += f"{balance['coin']}: {format_number(float(balance['total']))}\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            session.update_activity()
            
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            await update.message.reply_text("❌ Error retrieving balance.")
    
    async def positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View open positions"""
        session = self.user_manager.get_session(update.effective_user.id)
        if not session:
            await update.message.reply_text("❌ Please register first using /register")
            return
        
        try:
            base_url = self.config.get("hyperliquid.base_url")
            info = session.get_info(base_url)
            
            user_state = info.user_state(session.account_address)
            positions = user_state["assetPositions"]
            
            if not positions:
                await update.message.reply_text("📊 No open positions.")
                return
            
            message = "📊 **Open Positions**\n\n"
            for pos in positions:
                position = pos["position"]
                coin = position["coin"]
                size = float(position["szi"])
                if size != 0:
                    entry_px = position.get("entryPx", "N/A")
                    unrealized_pnl = float(position["unrealizedPnl"])
                    
                    side = "LONG" if size > 0 else "SHORT"
                    message += f"**{coin}** - {side}\n"
                    message += f"Size: {format_number(abs(size))}\n"
                    message += f"Entry: ${entry_px}\n"
                    message += f"PnL: ${format_number(unrealized_pnl)}\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            session.update_activity()
            
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            await update.message.reply_text("❌ Error retrieving positions.")
    
    async def orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """View open orders"""
        session = self.user_manager.get_session(update.effective_user.id)
        if not session:
            await update.message.reply_text("❌ Please register first using /register")
            return
        
        try:
            base_url = self.config.get("hyperliquid.base_url")
            info = session.get_info(base_url)
            
            open_orders = info.open_orders(session.account_address)
            
            if not open_orders:
                await update.message.reply_text("📋 No open orders.")
                return
            
            message = "📋 **Open Orders**\n\n"
            for order in open_orders:
                coin = order["coin"]
                side = "BUY" if order["side"] == "A" else "SELL"
                size = order["sz"]
                price = order["limitPx"]
                oid = order["oid"]
                
                message += f"**{coin}** - {side}\n"
                message += f"Size: {size}\n"
                message += f"Price: ${price}\n"
                message += f"Order ID: {oid}\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            session.update_activity()
            
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            await update.message.reply_text("❌ Error retrieving orders.")
    
    async def buy_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Place buy limit order"""
        await self._place_order(update, context, is_buy=True, is_market=False)
    
    async def sell_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Place sell limit order"""
        await self._place_order(update, context, is_buy=False, is_market=False)
    
    async def market_buy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Place market buy order"""
        await self._place_order(update, context, is_buy=True, is_market=True)
    
    async def market_sell(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Place market sell order"""
        await self._place_order(update, context, is_buy=False, is_market=True)
    
    async def _place_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE, is_buy: bool, is_market: bool):
        """Place order helper function"""
        session = self.user_manager.get_session(update.effective_user.id)
        if not session:
            await update.message.reply_text("❌ Please register first using /register")
            return
        
        # Parse order parameters
        order_params = parse_order_params(context.args, is_market)
        if not order_params:
            if is_market:
                await update.message.reply_text(
                    f"Usage: /{'market_buy' if is_buy else 'market_sell'} <coin> <size> [slippage]"
                )
            else:
                await update.message.reply_text(
                    f"Usage: /{'buy' if is_buy else 'sell'} <coin> <size> <price>"
                )
            return
        
        try:
            base_url = self.config.get("hyperliquid.base_url")
            exchange = session.get_exchange(base_url)
            
            coin = order_params["coin"].upper()
            size = order_params["size"]
            
            if is_market:
                slippage = order_params.get("slippage", self.config.get("hyperliquid.default_slippage"))
                if is_buy:
                    result = exchange.market_open(coin, True, size, slippage=slippage)
                else:
                    result = exchange.market_open(coin, False, size, slippage=slippage)
            else:
                price = order_params["price"]
                order_type = {"limit": {"tif": "Gtc"}}
                result = exchange.order(coin, is_buy, size, price, order_type)
            
            if result.get("status") == "ok":
                action = "Market Buy" if is_market and is_buy else "Market Sell" if is_market else "Buy" if is_buy else "Sell"
                message = f"✅ **{action} Order Placed**\n\n"
                message += f"Coin: {coin}\n"
                message += f"Size: {size}\n"
                if not is_market:
                    message += f"Price: ${price}\n"
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ Order failed: {result}")
            
            session.update_activity()
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            await update.message.reply_text("❌ Error placing order.")
    
    async def cancel_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel order by ID"""
        session = self.user_manager.get_session(update.effective_user.id)
        if not session:
            await update.message.reply_text("❌ Please register first using /register")
            return
        
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /cancel <coin> <order_id>")
            return
        
        try:
            coin = context.args[0].upper()
            order_id = int(context.args[1])
            
            base_url = self.config.get("hyperliquid.base_url")
            exchange = session.get_exchange(base_url)
            
            result = exchange.cancel(coin, order_id)
            
            if result.get("status") == "ok":
                await update.message.reply_text(f"✅ Order {order_id} for {coin} cancelled successfully.")
            else:
                await update.message.reply_text(f"❌ Cancel failed: {result}")
            
            session.update_activity()
            
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            await update.message.reply_text("❌ Error cancelling order.")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message"""
        help_text = """
🤖 **Hyperliquid Trading Bot Commands**

**Setup:**
/register <private_key> [account_address] - Register wallet
/balance - Check account balance

**Information:**
/positions - View open positions
/orders - View open orders

**Trading:**
/buy <coin> <size> <price> - Place buy limit order
/sell <coin> <size> <price> - Place sell limit order
/market_buy <coin> <size> [slippage] - Market buy order
/market_sell <coin> <size> [slippage] - Market sell order
/cancel <coin> <order_id> - Cancel order

**Examples:**
`/buy BTC 0.1 45000` - Buy 0.1 BTC at $45,000
`/market_sell ETH 1` - Market sell 1 ETH
`/cancel BTC 123456` - Cancel BTC order ID 123456

⚠️ **Security Notice:** This bot handles your private keys. Use only in secure environments.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
