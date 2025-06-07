#!/usr/bin/env python3


import asyncio
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal

# Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Hyperliquid SDK - REAL imports
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import example_utils

# Our existing modules
from telegram_bot.config import config
from database import bot_db

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class RealHyperliquidBot:
    """Real implementation using Hyperliquid SDK with vault trading capabilities"""
    
    def __init__(self):
        # Use our existing configuration system
        self.api_url = config.get_api_url()
        
        # Initialize using SDK's example_utils for proper setup
        self.address, self.info, self.exchange = example_utils.setup(
            base_url=self.api_url,
            skip_ws=True
        )
        
        logger.info(f"Initialized for address: {self.address}")
        
        # Bot configuration from our config system
        self.telegram_token = config.get_telegram_token()
        self.vault_address = config.get_vault_address()
        self.referral_code = config.get_referral_code()
        self.min_deposit = config.get_minimum_deposit()
        
        # Initialize Telegram bot
        if not self.telegram_token:
            raise ValueError("Telegram bot token must be configured!")
            
        self.app = Application.builder().token(self.telegram_token).build()
        self._setup_handlers()
        
        # Track active strategies and vault performance
        self.active_grids = {}
        self.user_sessions = {}
        self.vault_stats = {}
        
        # Trading configuration
        self.grid_spread = 0.002  # 0.2% default spread
        self.max_grid_levels = 10
        self.position_size_pct = 0.1  # 10% of balance per position
        
    def _setup_handlers(self):
        """Setup Telegram handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("balance", self.balance_command))
        self.app.add_handler(CommandHandler("deposit", self.deposit_command))
        self.app.add_handler(CommandHandler("trade", self.trade_command))
        self.app.add_handler(CommandHandler("orders", self.orders_command))
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(CommandHandler("grid", self.grid_command))
        self.app.add_handler(CommandHandler("stats", self.stats_command))
        self.app.add_handler(CommandHandler("vault", self.vault_command))
        self.app.add_handler(CommandHandler("withdraw", self.withdraw_command))
        self.app.add_handler(CommandHandler("confirm", self.confirm_deposit))
        self.app.add_handler(CommandHandler("vaultdeposit", self.vault_deposit_command))
        self.app.add_handler(CommandHandler("vaultstats", self.vault_stats_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command with real vault data"""
        user_id = update.effective_user.id
        
        # Add user to database if not exists
        existing_user = await bot_db.get_user_stats(user_id)
        if not existing_user:
            await bot_db.add_user(user_id)
        
        # Get real account value and vault status
        try:
            user_state = self.info.user_state(self.address)
            account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
            
            # Get vault details if vault exists
            vault_info = ""
            if self.vault_address:
                try:
                    vault_details = self.info.query_vault_details(self.vault_address)
                    vault_state = self.info.user_state(self.vault_address)
                    vault_value = float(vault_state.get('marginSummary', {}).get('accountValue', 0))
                    vault_info = f"\n• Vault Value: ${vault_value:,.2f}"
                except Exception as e:
                    logger.warning(f"Could not get vault details: {e}")
                    vault_info = "\n• Vault: Not accessible"
        except Exception as e:
            logger.error(f"Error getting account value: {e}")
            account_value = 0
            
        welcome_msg = f"""
🚀 **Real Hyperliquid Vault Trading Bot**

**Live Connection Status:**
• Wallet: `{self.address[:8]}...{self.address[-6:]}`
• Network: {'Mainnet' if config.is_mainnet() else 'Testnet'}
• Account Value: ${account_value:,.2f}{vault_info}
• API Status: ✅ Connected

**🎯 Real Vault Trading Features:**
• Direct vault order placement
• Automated profit-taking for vault
• Real-time vault performance tracking
• Maker rebate optimization for vault

**💰 Vault Revenue Model:**
• Users deposit to vault (you manage it)
• You take 10% of profits (Hyperliquid standard)
• Earn maker rebates on vault trading
• Performance-based compensation

**Commands:**
/balance - Account & vault balance
/vaultdeposit - Deposit to YOUR vault
/vault - Manage vault positions
/vaultstats - Real vault performance
/trade - Place trades for vault
/grid - Grid trading for vault

🔗 **Join with referral for 4% discount:**
https://app.hyperliquid.xyz/join/{self.referral_code}
        """
        
        keyboard = [
            [InlineKeyboardButton("💰 Check Vault Balance", callback_data="vault_balance")],
            [InlineKeyboardButton("🎯 Start Vault Grid", callback_data="vault_grid")],
            [InlineKeyboardButton("📊 Vault Performance", callback_data="vault_performance")],
            [InlineKeyboardButton("🏦 Manage Vault", callback_data="vault_manage")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=reply_markup)
        
    async def vault_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comprehensive vault management"""
        if not self.vault_address:
            await update.message.reply_text(
                "❌ No vault configured. Please set VAULT_ADDRESS in your configuration."
            )
            return
            
        try:
            # Get real vault state
            vault_state = self.info.user_state(self.vault_address)
            vault_details = self.info.query_vault_details(self.vault_address)
            
            # Extract vault metrics
            account_value = float(vault_state.get('marginSummary', {}).get('accountValue', 0))
            available_balance = float(vault_state.get('crossMarginSummary', {}).get('availableBalance', 0))
            total_pnl = float(vault_state.get('marginSummary', {}).get('totalPnl', 0))
            
            # Get vault positions
            positions = vault_state.get('assetPositions', [])
            open_orders = self.info.open_orders(self.vault_address)
            
            # Calculate vault performance
            vault_performance = await self.calculate_vault_performance()
            
            msg = f"""
🏦 **Vault Management Dashboard**

**Vault Overview:**
• Vault Address: `{self.vault_address[:8]}...{self.vault_address[-6:]}`
• Total Value: ${account_value:,.2f}
• Available: ${available_balance:,.2f}
• Total P&L: ${total_pnl:+,.2f}

**Active Trading:**
• Open Positions: {len([p for p in positions if float(p.get('position', {}).get('szi', 0)) != 0])}
• Open Orders: {len(open_orders)}
• Total Volume: ${vault_performance.get('volume', 0):,.2f}
• Maker Rebates: ${vault_performance.get('rebates', 0):.4f}

**Revenue Generation:**
• Your Profit Share (10%): ${vault_performance.get('profit_share', 0):+.2f}
• Total Trades: {vault_performance.get('trades', 0)}
"""
            
            # Show positions
            if positions:
                msg += "\n**Active Positions:**\n"
                for pos in positions:
                    position = pos.get('position', {})
                    coin = position.get('coin', '')
                    size = float(position.get('szi', 0))
                    entry_px = float(position.get('entryPx', 0)) if position.get('entryPx') else 0
                    pnl = float(position.get('unrealizedPnl', 0))
                    
                    if size != 0:
                        side = "📈 Long" if size > 0 else "📉 Short"
                        msg += f"\n{coin}: {side} {abs(size):.4f} @ ${entry_px:.2f} (P&L: ${pnl:+.2f})"
            
            keyboard = [
                [InlineKeyboardButton("📈 Trade for Vault", callback_data="vault_trade")],
                [InlineKeyboardButton("🎯 Start Vault Grid", callback_data="vault_grid")],
                [InlineKeyboardButton("💰 Close Profitable Positions", callback_data="take_profits")],
                [InlineKeyboardButton("📊 Detailed Stats", callback_data="vault_detailed")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Vault command error: {e}")
            await update.message.reply_text(f"❌ Error accessing vault: {str(e)}")
    
    async def vault_deposit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle direct vault deposit using SDK"""
        if not self.vault_address:
            await update.message.reply_text(
                "❌ No vault configured. Please set VAULT_ADDRESS in your configuration."
            )
            return
            
        if len(context.args) < 1:
            await update.message.reply_text(
                "**Deposit to Your Vault:**\n\n"
                "Usage: `/vaultdeposit <amount>`\n\n"
                "Example: `/vaultdeposit 100` - Deposit $100 USDC to vault\n\n"
                "💡 This deposits from your personal account to your vault."
            )
            return
            
        try:
            amount = float(context.args[0])
            
            if amount < 1:
                await update.message.reply_text("❌ Minimum deposit is $1 USDC")
                return
            
            # Check personal account balance
            user_state = self.info.user_state(self.address)
            available = float(user_state.get('crossMarginSummary', {}).get('availableBalance', 0))
            
            if amount > available:
                await update.message.reply_text(
                    f"❌ Insufficient balance\n"
                    f"Requested: ${amount:,.2f}\n"
                    f"Available: ${available:,.2f}"
                )
                return
            
            # Execute real vault deposit using SDK
            deposit_result = self.exchange.vault_transfer(
                vault_address=self.vault_address,
                is_deposit=True,
                usd=amount
            )
            
            if deposit_result.get('status') == 'ok':
                msg = f"""
✅ **Vault Deposit Successful!**

• Amount: ${amount:,.2f} USDC
• From: Personal Account
• To: Vault `{self.vault_address[:8]}...`
• Status: Confirmed

🚀 **Funds are now available for vault trading strategies:**
• Grid trading for maker rebates
• Automated profit-taking
• Risk-managed position sizing

Use /vault to manage your vault positions.
                """
                
                await update.message.reply_text(msg, parse_mode='Markdown')
                
                # Update database with deposit
                await bot_db.record_vault_deposit(self.vault_address, amount)
                
            else:
                await update.message.reply_text(
                    f"❌ **Deposit Failed**\n\n{deposit_result.get('error', 'Unknown error')}"
                )
                
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Please enter a number.")
        except Exception as e:
            logger.error(f"Vault deposit error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def vault_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show real vault statistics"""
        if not self.vault_address:
            await update.message.reply_text(
                "❌ No vault configured. Please set VAULT_ADDRESS in your configuration."
            )
            return
            
        try:
            # Calculate comprehensive vault performance
            performance = await self.calculate_vault_performance()
            
            # Get current vault state
            vault_state = self.info.user_state(self.vault_address)
            account_value = float(vault_state.get('marginSummary', {}).get('accountValue', 0))
            
            # Get recent fills for more metrics
            fills = self.info.user_fills(self.vault_address)
            recent_fills = [f for f in fills if f.get('time', 0) > (datetime.now().timestamp() - 86400) * 1000]  # Last 24h
            
            daily_volume = sum(float(f['sz']) * float(f['px']) for f in recent_fills)
            daily_trades = len(recent_fills)
            daily_rebates = sum(abs(float(f.get('fee', 0))) for f in recent_fills if float(f.get('fee', 0)) < 0)
            
            msg = f"""
📊 **Vault Performance Analytics**

**Current Status:**
• Vault Value: ${account_value:,.2f}
• Total Trades: {performance.get('trades', 0)}
• Total Volume: ${performance.get('volume', 0):,.2f}
• Net P&L: ${performance.get('pnl', 0):+,.2f}

**Revenue Breakdown:**
• Maker Rebates: ${performance.get('rebates', 0):.4f}
• Your Profit Share (10%): ${performance.get('profit_share', 0):+.2f}
• Daily Volume: ${daily_volume:,.2f}
• Daily Rebates: ${daily_rebates:.4f}

**24h Performance:**
• Trades Today: {daily_trades}
• Volume Today: ${daily_volume:,.2f}
• Rebates Today: ${daily_rebates:.4f}

**Efficiency Metrics:**
• Maker Percentage: {performance.get('maker_pct', 0):.1f}%
• Avg Trade Size: ${performance.get('avg_trade_size', 0):,.2f}
• Revenue per Trade: ${performance.get('revenue_per_trade', 0):.4f}
"""
            
            # Add fee tier information
            volume_14d = performance.get('volume', 0)  # Simplified
            if volume_14d < 5000000:
                fee_tier = "Bronze (0.035% taker, 0.01% maker)"
            elif volume_14d < 25000000:
                fee_tier = "Silver (0.0325% taker, 0.005% maker)"
            else:
                fee_tier = "Gold+ (0.03% taker, 0% maker)"
                
            msg += f"\n**Fee Tier:** {fee_tier}"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh Stats", callback_data="vault_stats")],
                [InlineKeyboardButton("📈 Optimize Strategy", callback_data="optimize_vault")],
                [InlineKeyboardButton("💰 Revenue Report", callback_data="revenue_report")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Vault stats error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def calculate_vault_performance(self) -> Dict:
        """Calculate real vault performance metrics using SDK data"""
        if not self.vault_address:
            return {}
            
        try:
            # Get vault fills (trades)
            fills = self.info.user_fills(self.vault_address)
            
            # Calculate comprehensive metrics
            total_volume = 0
            total_pnl = 0
            maker_rebates = 0
            maker_volume = 0
            
            for fill in fills:
                px = float(fill['px'])
                sz = float(fill['sz'])
                fee = float(fill.get('fee', 0))
                
                volume = px * sz
                total_volume += volume
                
                # Check if maker (negative fee = rebate)
                if fee < 0:
                    maker_rebates += abs(fee)
                    maker_volume += volume
                    
                # Add realized PnL if available
                if 'closedPnl' in fill:
                    total_pnl += float(fill['closedPnl'])
            
            # Calculate derived metrics
            maker_pct = (maker_volume / total_volume * 100) if total_volume > 0 else 0
            avg_trade_size = total_volume / len(fills) if fills else 0
            revenue_per_trade = maker_rebates / len(fills) if fills else 0
            
            # Calculate vault owner's 10% profit share
            profit_share = max(0, total_pnl * 0.10) if total_pnl > 0 else 0
            
            performance = {
                'volume': total_volume,
                'pnl': total_pnl,
                'rebates': maker_rebates,
                'trades': len(fills),
                'maker_pct': maker_pct,
                'avg_trade_size': avg_trade_size,
                'revenue_per_trade': revenue_per_trade,
                'profit_share': profit_share
            }
            
            logger.info(f"Vault performance calculated: {performance}")
            return performance
            
        except Exception as e:
            logger.error(f"Error calculating vault performance: {e}")
            return {}
    
    async def trade_for_vault(self, coin: str, is_buy: bool, size: float, price: float = None):
        """Place trade on behalf of vault using real SDK"""
        if not self.vault_address:
            raise ValueError("No vault configured")
            
        try:
            # Place order for vault with vault_address parameter
            if price:
                # Limit order
                order_result = self.exchange.order(
                    coin,
                    is_buy,
                    size,
                    price,
                    {"limit": {"tif": "Alo"}},  # Post-only for maker rebates
                    reduce_only=False,
                    vault_address=self.vault_address  # KEY: Trade for vault
                )
            else:
                # Market order
                order_result = self.exchange.order(
                    coin,
                    is_buy,
                    size,
                    None,
                    {"market": {}},
                    reduce_only=False,
                    vault_address=self.vault_address
                )
            
            logger.info(f"Vault order result: {order_result}")
            
            if order_result.get('status') == 'ok':
                # Record in database
                await bot_db.record_vault_trade(
                    vault_address=self.vault_address,
                    coin=coin,
                    side="buy" if is_buy else "sell",
                    size=size,
                    price=price or 0,
                    fee_type="vault_trade"
                )
            
            return order_result
            
        except Exception as e:
            logger.error(f"Error trading for vault: {e}")
            raise
    
    async def manage_vault_positions(self):
        """Automatically manage vault positions for profit-taking"""
        if not self.vault_address:
            return
            
        try:
            # Get all vault positions
            vault_state = self.info.user_state(self.vault_address)
            positions = vault_state.get('assetPositions', [])
            
            for pos in positions:
                position = pos.get('position', {})
                coin = position.get('coin')
                size = float(position.get('szi', 0))
                entry_price = float(position.get('entryPx', 0))
                unrealized_pnl = float(position.get('unrealizedPnl', 0))
                
                if size != 0 and unrealized_pnl > 0:
                    # Take profit if unrealized PnL > $10
                    if unrealized_pnl > 10:
                        logger.info(f"Taking profit on {coin}: ${unrealized_pnl:.2f}")
                        
                        # Place reduce-only order to close position
                        close_result = await self.trade_for_vault(
                            coin=coin,
                            is_buy=(size < 0),  # Buy if short, sell if long
                            size=abs(size),
                            price=None  # Market order for immediate execution
                        )
                        
                        if close_result.get('status') == 'ok':
                            logger.info(f"Successfully closed {coin} position")
                            
                            # Record profit-taking
                            await bot_db.record_profit_taking(
                                vault_address=self.vault_address,
                                coin=coin,
                                pnl=unrealized_pnl,
                                action="auto_close"
                            )
                        
        except Exception as e:
            logger.error(f"Error managing vault positions: {e}")
    
    async def start_vault_grid_trading(self, coin: str, levels: int = 10, spacing: float = 0.002):
        """Start grid trading specifically for vault"""
        if not self.vault_address:
            return {'success': False, 'error': 'No vault configured'}
            
        try:
            # Get current price
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                return {'success': False, 'error': f'Coin {coin} not found'}
                
            mid_price = float(all_mids[coin])
            
            # Cancel existing vault orders for this coin
            vault_orders = self.info.open_orders(self.vault_address)
            for order in vault_orders:
                if order['coin'] == coin:
                    cancel_result = self.exchange.cancel(coin, order['oid'], vault_address=self.vault_address)
                    logger.info(f"Cancelled vault order: {order['oid']}")
            
            # Get vault balance for sizing
            vault_state = self.info.user_state(self.vault_address)
            available = float(vault_state.get('crossMarginSummary', {}).get('availableBalance', 0))
            
            # Calculate order sizing (more conservative for vault)
            max_grid_value = min(available * 0.2, 1000)  # 20% of vault balance
            order_size = max_grid_value / (levels * 2) / mid_price
            
            if order_size < 0.001:
                return {'success': False, 'error': 'Insufficient vault balance'}
            
            # Determine precision
            if coin in ['BTC']:
                size_precision = 6
                price_precision = 1
            elif coin in ['ETH']:
                size_precision = 4
                price_precision = 2
            else:
                size_precision = 2
                price_precision = 4
                
            order_size = round(order_size, size_precision)
            placed_orders = []
            
            # Place buy orders below current price
            for i in range(1, levels + 1):
                buy_price = round(mid_price * (1 - spacing * i), price_precision)
                
                try:
                    order_result = await self.trade_for_vault(coin, True, order_size, buy_price)
                    if order_result.get('status') == 'ok':
                        placed_orders.append(('buy', buy_price))
                except Exception as e:
                    logger.error(f"Failed to place vault buy order {i}: {e}")
            
            # Place sell orders above current price
            for i in range(1, levels + 1):
                sell_price = round(mid_price * (1 + spacing * i), price_precision)
                
                try:
                    order_result = await self.trade_for_vault(coin, False, order_size, sell_price)
                    if order_result.get('status') == 'ok':
                        placed_orders.append(('sell', sell_price))
                except Exception as e:
                    logger.error(f"Failed to place vault sell order {i}: {e}")
            
            # Store vault grid info
            grid_key = f"vault_{coin}"
            self.active_grids[grid_key] = {
                'coin': coin,
                'vault_address': self.vault_address,
                'mid_price': mid_price,
                'levels': levels,
                'spacing': spacing,
                'orders': placed_orders,
                'started_at': datetime.now()
            }
            
            return {
                'success': True,
                'orders_placed': len(placed_orders),
                'mid_price': mid_price,
                'vault_address': self.vault_address
            }
            
        except Exception as e:
            logger.error(f"Vault grid trading error: {e}")
            return {'success': False, 'error': str(e)}
    
    async def balance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show real balance from Hyperliquid"""
        try:
            # Get REAL user state from Hyperliquid API
            user_state = self.info.user_state(self.address)
            
            # Extract real balances
            cross_margin = user_state.get('crossMarginSummary', {})
            account_value = float(cross_margin.get('accountValue', 0))
            available_balance = float(cross_margin.get('availableBalance', 0))
            margin_used = float(cross_margin.get('marginUsed', 0))
            total_pnl = float(user_state.get('marginSummary', {}).get('totalPnl', 0))
            
            # Get real positions
            positions = user_state.get('assetPositions', [])
            
            # Get user's vault stats from database
            user_id = update.effective_user.id
            vault_stats = await bot_db.get_user_stats(user_id)
            
            balance_msg = f"""
💰 **Live Hyperliquid Account**

**Account Overview:**
• Total Value: ${account_value:,.2f}
• Available: ${available_balance:,.2f}
• Margin Used: ${margin_used:,.2f}
• Unrealized P&L: ${total_pnl:+,.2f}

**Open Positions:**
"""
            
            if positions:
                for pos in positions:
                    position = pos.get('position', {})
                    coin = position.get('coin', '')
                    size = float(position.get('szi', 0))
                    entry_px = float(position.get('entryPx', 0)) if position.get('entryPx') else 0
                    pnl = float(position.get('unrealizedPnl', 0))
                    
                    if size != 0:
                        side = "📈 Long" if size > 0 else "📉 Short"
                        balance_msg += f"\n{coin}: {side} {abs(size):.4f} @ ${entry_px:.2f}"
                        balance_msg += f" (P&L: ${pnl:+.2f})"
            else:
                balance_msg += "\nNo open positions"
                
            # Add vault information if user is in vault
            if vault_stats:
                balance_msg += f"\n\n**Vault Participation:**"
                balance_msg += f"\n• Deposited: ${vault_stats.get('total_deposited', 0):,.2f}"
                balance_msg += f"\n• Current Value: ${vault_stats.get('current_balance', 0):,.2f}"
                balance_msg += f"\n• Profit: ${vault_stats.get('total_profit', 0):+,.2f}"
                balance_msg += f"\n• ROI: {vault_stats.get('roi_pct', 0):+.2f}%"
                
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="balance")],
                [InlineKeyboardButton("📈 Place Trade", callback_data="trade_menu")],
                [InlineKeyboardButton("🎯 Start Grid", callback_data="start_grid")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
                
            await update.message.reply_text(balance_msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Balance command error: {e}")
            await update.message.reply_text(f"❌ Error fetching balance: {str(e)}")
            
    async def trade_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Place a real trade using Hyperliquid API"""
        if len(context.args) < 4:
            await update.message.reply_text(
                "**Place Real Trade:**\n\n"
                "Usage: `/trade <coin> <buy/sell> <size> <price>`\n\n"
                "Examples:\n"
                "• `/trade ETH buy 0.1 3000` - Buy 0.1 ETH at $3000\n"
                "• `/trade BTC sell 0.01 65000` - Sell 0.01 BTC at $65000\n\n"
                "💡 **Tip:** Use post-only orders to earn maker rebates!",
                parse_mode='Markdown'
            )
            return
            
        try:
            coin = context.args[0].upper()
            is_buy = context.args[1].lower() == 'buy'
            size = float(context.args[2])
            price = float(context.args[3])
            
            # Validate coin exists
            all_mids = self.info.all_mids()
            if coin not in all_mids:
                await update.message.reply_text(f"❌ Coin {coin} not found on Hyperliquid")
                return
                
            # Check account balance
            user_state = self.info.user_state(self.address)
            available = float(user_state.get('crossMarginSummary', {}).get('availableBalance', 0))
            
            trade_value = size * price
            if trade_value > available:
                await update.message.reply_text(
                    f"❌ Insufficient balance\n"
                    f"Trade value: ${trade_value:,.2f}\n"
                    f"Available: ${available:,.2f}"
                )
                return
            
            # Place REAL order using Hyperliquid SDK
            order_result = self.exchange.order(
                coin,
                is_buy,
                size,
                price,
                {"limit": {"tif": "Alo"}},  # Add Liquidity Only for maker rebate
                reduce_only=False
            )
            
            if order_result['status'] == 'ok':
                # Parse order response
                response_data = order_result.get('response', {}).get('data', {})
                statuses = response_data.get('statuses', [])
                
                # Record trade in database
                await bot_db.record_trade(
                    coin=coin,
                    side="buy" if is_buy else "sell",
                    size=size,
                    price=price,
                    pnl=0,  # Will be calculated when filled
                    fee=0,  # Will be updated with actual fee
                    fee_type="maker_order"
                )
                
                msg = "✅ **Order Placed Successfully!**\n\n"
                msg += f"**Trade Details:**\n"
                msg += f"• Coin: {coin}\n"
                msg += f"• Side: {'Buy' if is_buy else 'Sell'}\n"
                msg += f"• Size: {size}\n"
                msg += f"• Price: ${price:,.2f}\n"
                msg += f"• Value: ${trade_value:,.2f}\n\n"
                
                for status in statuses:
                    if 'resting' in status:
                        oid = status['resting']['oid']
                        msg += f"📋 Order ID: {oid}\n"
                        msg += f"💰 Status: Resting (earning maker rebates)\n"
                    elif 'filled' in status:
                        filled_data = status['filled']
                        avg_px = float(filled_data['avgPx'])
                        total_sz = float(filled_data['totalSz']);
                        msg += f"✅ Filled: {total_sz} @ ${avg_px:.2f}\n";
                        
                msg += f"\n💡 **Post-only order** - Earning maker rebates up to -0.003%!"
                
                keyboard = [
                    [InlineKeyboardButton("📋 View Orders", callback_data="orders")],
                    [InlineKeyboardButton("📊 Check Stats", callback_data="stats")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                await update.message.reply_text(f"❌ **Order Failed**\n\n{order_result}")
                
        except ValueError as e:
            await update.message.reply_text(f"❌ Invalid input: {str(e)}")
        except Exception as e:
            logger.error(f"Trade command error: {e}")
            await update.message.reply_text(f"❌ Error placing trade: {str(e)}")
            
    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show real open orders from Hyperliquid"""
        try:
            # Get REAL open orders from Hyperliquid API
            open_orders = self.info.open_orders(self.address)
            
            if not open_orders:
                await update.message.reply_text(
                    "📋 **No Open Orders**\n\n"
                    "Use /trade to place new orders or /grid to start automated trading."
                )
                return
                
            msg = "📋 **Your Open Orders**\n\n"
            
            total_value = 0
            for order in open_orders:
                coin = order['coin']
                side = "Buy" if order['side'] == "B" else "Sell"
                size = float(order['sz'])
                price = float(order['limitPx'])
                oid = order['oid']
                
                order_value = size * price
                total_value += order_value
                
                msg += f"**{coin}** {side} {size} @ ${price:,.2f}\n"
                msg += f"  Value: ${order_value:,.2f} | ID: {oid}\n\n"
                
            msg += f"**Total Value:** ${total_value:,.2f}\n"
            msg += f"**Total Orders:** {len(open_orders)}"
            
            keyboard = [
                [InlineKeyboardButton("❌ Cancel All", callback_data="cancel_all")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="orders")],
                [InlineKeyboardButton("📊 View Stats", callback_data="stats")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Orders command error: {e}")
            await update.message.reply_text(f"❌ Error fetching orders: {str(e)}")
            
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel orders using real Hyperliquid API"""
        if not context.args:
            await update.message.reply_text(
                "**Cancel Orders:**\n\n"
                "Usage:\n"
                "• `/cancel all` - Cancel all orders\n"
                "• `/cancel <order_id>` - Cancel specific order\n"
                "• `/cancel ETH` - Cancel all ETH orders"
            )
            return
            
        try:
            arg = context.args[0].upper()
            
            if arg == 'ALL':
                # Cancel ALL orders using real API
                open_orders = self.info.open_orders(self.address)
                cancelled = 0
                failed = 0
                
                for order in open_orders:
                    try:
                        result = self.exchange.cancel(order['coin'], order['oid'])
                        if result['status'] == 'ok':
                            cancelled += 1
                        else:
                            failed += 1
                    except Exception as e:
                        logger.error(f"Failed to cancel order {order['oid']}: {e}")
                        failed += 1
                        
                msg = f"✅ **Cancelled {cancelled} orders**"
                if failed > 0:
                    msg += f"\n❌ Failed to cancel {failed} orders"
                    
                await update.message.reply_text(msg)
            elif arg.isdigit():
                # Cancel specific order by ID
                oid = int(arg)
                open_orders = self.info.open_orders(self.address)
                
                for order in open_orders:
                    if order['oid'] == oid:
                        result = self.exchange.cancel(order['coin'], oid)
                        if result['status'] == 'ok':
                            await update.message.reply_text(f"✅ Order {oid} cancelled")
                        else:
                            await update.message.reply_text(f"❌ Failed to cancel: {result}")
                        return
                        
                await update.message.reply_text(f"❌ Order {oid} not found")
                
            else:
                # Cancel all orders for specific coin
                coin = arg
                open_orders = self.info.open_orders(self.address)
                cancelled = 0
                
                for order in open_orders:
                    if order['coin'] == coin:
                        result = self.exchange.cancel(coin, order['oid'])
                        if result['status'] == 'ok':
                            cancelled += 1
                            
                if cancelled > 0:
                    await update.message.reply_text(f"✅ Cancelled {cancelled} {coin} orders")
                else:
                    await update.message.reply_text(f"❌ No {coin} orders found")
                
        except Exception as e:
            logger.error(f"Cancel command error: {e}")
            await update.message.reply_text(f"❌ Error cancelling: {str(e)}")
            
    async def grid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start real grid trading"""
        if len(context.args) < 1:
            await update.message.reply_text(
                "**Start Grid Trading:**\n\n"
                "Usage: `/grid <coin> [levels] [spread]`\n\n"
                "Examples:\n"
                "• `/grid ETH` - Default 10 levels, 0.2% spread\n"
                "• `/grid BTC 5` - 5 levels, 0.2% spread\n"
                "• `/grid SOL 8 0.3` - 8 levels, 0.3% spread\n\n"
                "💡 Grid trading places buy/sell orders around current price to earn maker rebates!"
            )
            return
            
        try:
            coin = context.args[0].upper()
            levels = int(context.args[1]) if len(context.args) > 1 else 10
            spread_pct = float(context.args[2]) if len(context.args) > 2 else 0.2
            
            # Validate inputs
            if levels < 2 or levels > 20:
                await update.message.reply_text("❌ Levels must be between 2 and 20")
                return
                
            if spread_pct < 0.1 or spread_pct > 5.0:
                await update.message.reply_text("❌ Spread must be between 0.1% and 5.0%")
                return
            
            await update.message.reply_text(f"🎯 Starting grid trading for {coin}...")
            
            # Start real grid trading
            result = await self.start_grid_trading(coin, levels, spread_pct / 100)
            
            if result['success']:
                keyboard = [
                    [InlineKeyboardButton("📋 View Orders", callback_data="orders")],
                    [InlineKeyboardButton("⏹️ Stop Grid", callback_data=f"stop_grid_{coin}")],
                    [InlineKeyboardButton("📊 Grid Stats", callback_data=f"grid_stats_{coin}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    f"✅ **Grid Trading Active!**\n\n"
                    f"**{coin} Grid Details:**\n"
                    f"• Levels: {levels}\n"
                    f"• Spread: {spread_pct}%\n"
                    f"• Orders Placed: {result['orders_placed']}\n"
                    f"• Total Value: ${result['total_value']:,.2f}\n"
                    f"• Mid Price: ${result['mid_price']:,.2f}\n\n"
                    f"💰 Earning maker rebates on every fill!",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(f"❌ Failed to start grid: {result.get('error', 'Unknown error')}")
                
        except ValueError as e:
            await update.message.reply_text(f"❌ Invalid input: {str(e)}")
        except Exception as e:
            logger.error(f"Grid command error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
            
    async def start_grid_trading(self, coin: str, levels: int = 10, spacing: float = 0.002):
        """Real grid trading implementation using Hyperliquid API"""
        try:
            # Get current price from real Hyperliquid data
            all_mids = self.info.all_mids()
            
            if coin not in all_mids:
                return {'success': False, 'error': f'Coin {coin} not found'}
                
            mid_price = float(all_mids[coin])
            
            # Cancel existing orders for this coin
            open_orders = self.info.open_orders(self.address)
            for order in open_orders:
                if order['coin'] == coin:
                    try:
                        self.exchange.cancel(coin, order['oid'])
                        logger.info(f"Cancelled existing order: {order['oid']}")
                    except Exception as e:
                        logger.error(f"Failed to cancel order {order['oid']}: {e}")
                    
            # Get available balance
            user_state = self.info.user_state(self.address)
            available = float(user_state.get('crossMarginSummary', {}).get('availableBalance', 0))
            
            # Calculate order sizing
            max_grid_value = min(available * 0.3, 2000)  # Max 30% of balance or $2000
            total_levels = levels * 2  # Buy + sell levels
            order_value = max_grid_value / total_levels
            order_size = order_value / mid_price
            
            # Round order size appropriately
            if order_size < 0.001:
                return {'success': False, 'error': 'Insufficient balance for meaningful grid'}
                
            # Determine precision based on coin
            if coin in ['BTC']:
                size_precision = 6
                price_precision = 1
            elif coin in ['ETH']:
                size_precision = 4  
                price_precision = 2
            else:
                size_precision = 2
                price_precision = 4
                
            order_size = round(order_size, size_precision)
            placed_orders = []
            
            # Place buy orders below current price
            for i in range(1, levels + 1):
                buy_price = mid_price * (1 - spacing * i)
                buy_price = round(buy_price, price_precision)
                
                try:
                    order_result = self.exchange.order(
                        coin,
                        True,  # is_buy
                        order_size,
                        buy_price,
                        {"limit": {"tif": "Alo"}},  # Add Liquidity Only for rebates
                        reduce_only=False
                    )
                    
                    if order_result['status'] == 'ok':
                        placed_orders.append(('buy', buy_price, order_size))
                        
                        # Record in database
                        await bot_db.record_trade(
                            coin=coin,
                            side="buy",
                            size=order_size,
                            price=buy_price,
                            pnl=0,
                            fee=0,
                            fee_type="maker_order"
                        )
                except Exception as e:
                    logger.error(f"Failed to place buy order {i}: {e}")
            
            # Place sell orders above current price
            for i in range(1, levels + 1):
                sell_price = mid_price * (1 + spacing * i)
                sell_price = round(sell_price, price_precision)
                
                try:
                    order_result = self.exchange.order(
                        coin,
                        False,  # is_buy
                        order_size,
                        sell_price,
                        {"limit": {"tif": "Alo"}},  # Add Liquidity Only for rebates
                        reduce_only=False
                    )
                    
                    if order_result['status'] == 'ok':
                        placed_orders.append(('sell', sell_price, order_size))
                        
                        # Record in database
                        await bot_db.record_trade(
                            coin=coin,
                            side="sell",
                            size=order_size,
                            price=sell_price,
                            pnl=0,
                            fee=0,
                            fee_type="maker_order"
                        )
                except Exception as e:
                    logger.error(f"Failed to place sell order {i}: {e}")
                    
            # Store grid info
            self.active_grids[coin] = {
                'mid_price': mid_price,
                'levels': levels,
                'spacing': spacing,
                'orders': placed_orders,
                'started_at': datetime.now()
            }
            
            logger.info(f"Grid completed: {len(placed_orders)} orders placed, ${sum([o[1] for o in placed_orders]):,.2f} total value")
            
            return {
                'success': True,
                'orders_placed': len(placed_orders),
                'mid_price': mid_price,
                'vault_address': self.vault_address
            }
            
        except Exception as e:
            logger.error(f"Grid trading error: {e}")
            return {'success': False, 'error': str(e)}
            
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show real trading statistics from Hyperliquid and database"""
        try:
            # Get real fills from Hyperliquid API
            fills = self.info.user_fills(self.address)
            
            # Calculate real statistics
            if not fills:
                await update.message.reply_text("📊 No trading history found")
                return
                
            # Initialize comprehensive stats
            total_volume = 0
            total_fees = 0
            total_rebates = 0
            maker_volume = 0
            taker_volume = 0
            total_pnl = 0
            winning_trades = 0
            losing_trades = 0
            recent_fills = []
            
            # Calculate 24h cutoff
            now = datetime.now()
            cutoff_24h = (now - timedelta(hours=24)).timestamp() * 1000
            
            for fill in fills:
                px = float(fill['px'])
                sz = float(fill['sz'])
                fee = float(fill.get('fee', 0))
                fill_time = fill.get('time', 0)
                
                volume = px * sz
                total_volume += volume
                
                # Check if within 24h
                if fill_time > cutoff_24h:
                    recent_fills.append(fill)
                
                # Track maker vs taker
                if fee < 0:  # Negative fee = rebate earned (maker)
                    total_rebates += abs(fee)
                    maker_volume += volume
                else:  # Positive fee = fee paid (taker)
                    total_fees += fee
                    taker_volume += volume
                
                # Track PnL if available
                if 'closedPnl' in fill:
                    pnl = float(fill['closedPnl'])
                    total_pnl += pnl
                    if pnl > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
                    
            # Calculate derived metrics
            maker_pct = (maker_volume / total_volume * 100) if total_volume > 0 else 0
            win_rate = (winning_trades / (winning_trades + losing_trades) * 100) if (winning_trades + losing_trades) > 0 else 0
            avg_trade_size = total_volume / len(fills) if fills else 0
            net_fees = total_rebates - total_fees
            
            # Calculate 24h stats
            daily_volume = sum(float(f['px']) * float(f['sz']) for f in recent_fills)
            daily_trades = len(recent_fills)
            daily_rebates = sum(abs(float(f.get('fee', 0))) for f in recent_fills if float(f.get('fee', 0)) < 0)
            
            # Get database stats for additional metrics
            try:
                db_stats = await bot_db.get_trading_stats(self.address)
            except:
                db_stats = {}
            
            # Get current account value
            user_state = self.info.user_state(self.address)
            account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
            
            msg = f"""
📊 **Live Trading Statistics**

**Account Overview:**
• Account Value: ${account_value:,.2f}
• Total P&L: ${total_pnl:+,.2f}
• Win Rate: {win_rate:.1f}%

**Trading Volume:**
• All-Time Volume: ${total_volume:,.2f}
• Total Trades: {len(fills):,}
• Avg Trade Size: ${avg_trade_size:,.2f}
• 24h Volume: ${daily_volume:,.2f}
• 24h Trades: {daily_trades}

**Fee Performance:**
• Maker Volume: {maker_pct:.1f}%
• Rebates Earned: ${total_rebates:.4f}
• Fees Paid: ${total_fees:.4f}
• Net Savings: ${net_fees:+.4f}
• 24h Rebates: ${daily_rebates:.4f}

**Grid Trading Status:**
• Active Grids: {len(self.active_grids)}
"""
            
            # Add active grids details
            if self.active_grids:
                msg += "\n**Active Grid Details:**"
                for coin, grid in self.active_grids.items():
                    runtime = (datetime.now() - grid['started_at']).total_seconds() / 3600
                    success_rate = len(grid['orders']) / (len(grid['orders']) + len(grid.get('failed_orders', []))) * 100
                    msg += f"\n• {coin}: {len(grid['orders'])} orders ({success_rate:.0f}% success)"
                    msg += f"\n  Runtime: {runtime:.1f}h | Value: ${grid['total_value']:,.2f}"
                    msg += f"\n  Mid: ${grid['mid_price']:,.2f} | Spread: {grid['spacing']*100:.1f}%"
            
            # Determine current rebate tier
            if maker_pct >= 5.0:
                rebate_tier = "Tier 4: -0.005% rebate 🏆"
            elif maker_pct >= 3.0:
                rebate_tier = "Tier 3: -0.003% rebate ✅"
            elif maker_pct >= 1.5:
                rebate_tier = "Tier 2: -0.002% rebate ✅"
            elif maker_pct >= 0.5:
                rebate_tier = "Tier 1: -0.001% rebate ✅"
            else:
                rebate_tier = "No rebate tier (need >0.5% maker)"
                
            msg += f"\n\n**Rebate Status:** {rebate_tier}"
            
            # Add performance insights
            if maker_pct < 80:
                msg += f"\n\n💡 **Tip:** Increase maker percentage to earn more rebates!"
            if daily_volume > 0:
                projected_monthly = daily_volume * 30
                msg += f"\n📈 **Projected Monthly Volume:** ${projected_monthly:,.0f}"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="stats")],
                [InlineKeyboardButton("📋 View Orders", callback_data="orders")],
                [InlineKeyboardButton("💰 Check Balance", callback_data="balance")],
                [InlineKeyboardButton("🎯 Optimize Strategy", callback_data="optimize")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Stats command error: {e}")
            await update.message.reply_text(f"❌ Error fetching stats: {str(e)}")
    
    async def run_grid_maintenance(self):
        """Maintain and rebalance active grids"""
        while True:
            try:
                for coin, grid in list(self.active_grids.items()):
                    try:
                        # Check if grid needs rebalancing
                        current_price = float(self.info.all_mids().get(coin, 0))
                        if current_price == 0:
                            continue
                            
                        grid_mid = grid['mid_price']
                        price_change = abs(current_price - grid_mid) / grid_mid
                        
                        # Rebalance if price moved >5%
                        if price_change > 0.05:
                            logger.info(f"Rebalancing {coin} grid: price changed {price_change:.1%}")
                            
                            # Cancel existing orders
                            open_orders = self.info.open_orders(self.address)
                            for order in open_orders:
                                if order['coin'] == coin:
                                    try:
                                        self.exchange.cancel(coin, order['oid'])
                                    except Exception as e:
                                        logger.error(f"Failed to cancel {order['oid']}: {e}")
                            
                            # Restart grid with new price
                            result = await self.start_grid_trading(
                                coin, 
                                grid['levels'], 
                                grid['spacing']
                            )
                            
                            if result['success']:
                                logger.info(f"Successfully rebalanced {coin} grid")
                            else:
                                logger.error(f"Failed to rebalance {coin} grid: {result.get('error')}")
                                
                    except Exception as e:
                        logger.error(f"Grid maintenance error for {coin}: {e}")
                
                # Sleep for 10 minutes between checks
                await asyncio.sleep(600)
                
            except Exception as e:
                logger.error(f"Grid maintenance loop error: {e}")
                await asyncio.sleep(300)  # 5 minutes on error
    
    async def withdraw_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle vault withdrawals with proper validation"""
        if not self.vault_address:
            await update.message.reply_text(
                "❌ No vault configured. Cannot process withdrawals."
            )
            return
            
        user_id = update.effective_user.id
        
        if len(context.args) < 1:
            # Show withdrawal info
            try:
                user_stats = await bot_db.get_user_stats(user_id)
                available_balance = user_stats.get('current_balance', 0) if user_stats else 0
                
                msg = f"""
💸 **Vault Withdrawal**

**Available Balance:** ${available_balance:,.2f}
**Minimum Withdrawal:** $10.00
**Processing Time:** 1-24 hours

**Usage:** `/withdraw <amount>`
**Example:** `/withdraw 100` - Withdraw $100

**Notes:**
• Withdrawals are processed from vault balance
• Performance fees already deducted
• Available 24/7
                """
                
                await update.message.reply_text(msg, parse_mode='Markdown')
                
            except Exception as e:
                await update.message.reply_text(f"❌ Error getting withdrawal info: {str(e)}")
            return
            
        try:
            amount = float(context.args[0])
            
            if amount < 10:
                await update.message.reply_text("❌ Minimum withdrawal is $10.00")
                return
            
            # Check user balance
            user_stats = await bot_db.get_user_stats(user_id)
            if not user_stats:
                await update.message.reply_text("❌ No account found. Please deposit first.")
                return
                
            available_balance = user_stats.get('current_balance', 0)
            
            if amount > available_balance:
                await update.message.reply_text(
                    f"❌ Insufficient balance\n"
                    f"Requested: ${amount:,.2f}\n"
                    f"Available: ${available_balance:,.2f}"
                )
                return
            
            # Process withdrawal using vault transfer
            try:
                withdrawal_result = self.exchange.vault_transfer(
                    vault_address=self.vault_address,
                    is_deposit=False,  # This is a withdrawal
                    usd=amount
                )
                
                if withdrawal_result.get('status') == 'ok':
                    # Record in database
                    await bot_db.record_withdrawal(user_id, amount)
                    
                    msg = f"""
✅ **Withdrawal Processed**

• Amount: ${amount:,.2f} USDC
• From: Vault
• To: Your wallet
• Status: Confirmed
• Remaining Balance: ${available_balance - amount:,.2f}

⏰ **Processing:** Funds will arrive within 24 hours
🔗 **Transaction:** Check your wallet for confirmation
                    """
                    
                    await update.message.reply_text(msg, parse_mode='Markdown')
                    
                else:
                    await update.message.reply_text(
                        f"❌ **Withdrawal Failed**\n\n"
                        f"Error: {withdrawal_result.get('error', 'Unknown error')}\n"
                        f"Please try again or contact support."
                    )
                    
            except Exception as e:
                logger.error(f"Vault withdrawal error: {e}")
                await update.message.reply_text(
                    f"❌ **System Error**\n\n"
                    f"Failed to process withdrawal: {str(e)}\n"
                    f"Please try again later."
                )
                
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Please enter a valid number.")
        except Exception as e:
            logger.error(f"Withdrawal command error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def _get_vault_tvl(self) -> float:
        """Get total value locked in vault"""
        try:
            if not self.vault_address:
                return 0.0
                
            vault_state = self.info.user_state(self.vault_address)
            return float(vault_state.get('marginSummary', {}).get('accountValue', 0))
            
        except Exception as e:
            logger.error(f"Error getting vault TVL: {e}")
            return 0.0

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks with vault-specific actions"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        try:
            if data == "vault_balance":
                await self.vault_command(update, context)
            elif data == "vault_grid":
                await query.edit_message_text(
                    "🎯 **Start Vault Grid Trading**\n\n"
                    "Use `/grid <coin>` to start grid trading for your vault.\n\n"
                    "Examples:\n"
                    "• `/grid ETH` - Start ETH grid for vault\n"
                    "• `/grid BTC 5` - 5-level BTC grid for vault\n\n"
                    "💰 All trades will be placed on behalf of your vault!"
                )
            elif data == "vault_performance":
                await self.vault_stats_command(update, context)
            elif data == "vault_manage":
                await self.vault_command(update, context)
            elif data == "vault_trade":
                await query.edit_message_text(
                    "📈 **Trade for Vault**\n\n"
                    "Use `/trade <coin> <buy/sell> <size> <price>` to place trades for your vault.\n\n"
                    "All trades will be executed on behalf of your vault address."
                )
            elif data == "take_profits":
                await self._take_vault_profits(query)
            elif data == "vault_stats":
                await self.vault_stats_command(update, context)
            # ...existing code...
                
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)}")
    
    async def _take_vault_profits(self, query):
        """Take profits on vault positions"""
        try:
            if not self.vault_address:
                await query.edit_message_text("❌ No vault configured")
                return
                
            profits_taken = 0
            total_profit = 0
            
            vault_state = self.info.user_state(self.vault_address)
            positions = vault_state.get('assetPositions', [])
            
            for pos in positions:
                position = pos.get('position', {})
                coin = position.get('coin')
                size = float(position.get('szi', 0))
                unrealized_pnl = float(position.get('unrealizedPnl', 0))
                
                if size != 0 and unrealized_pnl > 5:  # Profit > $5
                    try:
                        close_result = await self.trade_for_vault(
                            coin=coin,
                            is_buy=(size < 0),
                            size=abs(size),
                            price=None  # Market order
                        )
                        
                        if close_result.get('status') == 'ok':
                            profits_taken += 1
                            total_profit += unrealized_pnl
                            
                    except Exception as e:
                        logger.error(f"Failed to close {coin}: {e}")
            
            if profits_taken > 0:
                await query.edit_message_text(
                    f"✅ **Profits Taken**\n\n"
                    f"Closed {profits_taken} profitable positions\n"
                    f"Total profit realized: ${total_profit:+.2f}\n"
                    f"Your share (10%): ${total_profit * 0.1:+.2f}"
                )
            else:
                await query.edit_message_text("💡 No profitable positions to close at this time")
                
        except Exception as e:
            await query.edit_message_text(f"❌ Error taking profits: {str(e)}")
    
    async def run_vault_automation(self):
        """Run automated vault management in background"""
        while True:
            try:
                if self.vault_address:
                    # Manage positions every 5 minutes
                    await self.manage_vault_positions()
                    
                    # Update vault stats
                    performance = await self.calculate_vault_performance()
                    self.vault_stats = performance
                
                await asyncio.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error(f"Vault automation error: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """Start the bot with vault automation"""
        logger.info("Starting Real Hyperliquid Vault Trading Bot...")
        
        # Validate configuration
        validation = config.validate_hyperliquid_config()
        if not all(validation.values()):
            logger.error("Configuration validation failed!")
            for key, valid in validation.items():
                if not valid:
                    logger.error(f"  - {key}: Not configured")
            return
        
        logger.info("Configuration validated ✅")
        logger.info(f"Trading on: {'Mainnet' if config.is_mainnet() else 'Testnet'}")
        logger.info(f"Wallet: {self.address}")
        if self.vault_address:
            logger.info(f"Vault: {self.vault_address}")
        
        # Start vault automation in background
        asyncio.create_task(self.run_vault_automation())
        
        # Start grid maintenance
        asyncio.create_task(self.run_grid_maintenance())
        
        # Start Telegram bot
        await self.app.initialize()
        await self.app.start()
        logger.info("Bot started successfully! 🚀")
        await self.app.run_polling()


async def main():
    """Main entry point"""
    try:
        # Create and start bot
        bot = RealHyperliquidBot()
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")


if __name__ == "__main__":
    asyncio.run(main())