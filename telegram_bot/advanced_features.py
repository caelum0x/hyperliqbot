import logging
import json
import csv
import io
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Document
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)

class AdvancedFeaturesHandler:
    """
    Advanced features for power users:
    - Referral system management
    - Vault creation and management
    - Analytics dashboard
    - Performance reports
    - Export trade data
    """

    def __init__(self, wallet_manager, vault_manager, database, trading_engine):
        self.wallet_manager = wallet_manager
        self.vault_manager = vault_manager
        self.database = database
        self.trading_engine = trading_engine
        
        # In-memory referral tracking
        self.referral_codes = {}
        self.referral_stats = {}

    async def show_analytics_dashboard(self, update: Update, context: CallbackContext):
        """Display comprehensive analytics dashboard"""
        user_id = update.effective_user.id
        
        if not self.wallet_manager:
            await update.message.reply_text("❌ Analytics not available (wallet manager missing)")
            return

        user_wallet = await self.wallet_manager.get_user_wallet(user_id)
        if not user_wallet:
            await update.message.reply_text("❌ No agent wallet found. Use /agent to create one.")
            return

        # Show loading message
        loading_msg = await update.message.reply_text("📊 Loading analytics dashboard...")

        try:
            # Get portfolio data
            portfolio_data = await self.wallet_manager.get_user_portfolio(user_id)
            
            # Calculate performance metrics
            performance_stats = await self._calculate_performance_stats(user_id)
            
            # Get trading statistics
            trading_stats = await self._get_trading_statistics(user_id)
            
            # Generate dashboard
            dashboard_msg = f"""
📊 **Analytics Dashboard**

**📈 Portfolio Overview**
• Account Value: ${portfolio_data.get('account_value', 0):,.2f}
• Available Balance: ${portfolio_data.get('available_balance', 0):,.2f}
• Unrealized P&L: ${portfolio_data.get('unrealized_pnl', 0):+,.2f}
• Open Positions: {len(portfolio_data.get('positions', []))}

**📋 Performance Metrics (30 Days)**
• Total P&L: ${performance_stats.get('total_pnl', 0):+,.2f}
• Win Rate: {performance_stats.get('win_rate', 0):.1f}%
• Best Trade: ${performance_stats.get('best_trade', 0):+,.2f}
• Worst Trade: ${performance_stats.get('worst_trade', 0):+,.2f}
• Average Trade: ${performance_stats.get('avg_trade', 0):+,.2f}

**🔄 Trading Statistics**
• Total Trades: {trading_stats.get('total_trades', 0)}
• Total Volume: ${trading_stats.get('total_volume', 0):,.2f}
• Total Fees Paid: ${trading_stats.get('total_fees', 0):,.2f}
• Active Strategies: {trading_stats.get('active_strategies', 0)}

**📅 Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """

            keyboard = [
                [InlineKeyboardButton("📈 Performance Report", callback_data="perf_report"),
                 InlineKeyboardButton("📊 Export Data", callback_data="export_data")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_analytics"),
                 InlineKeyboardButton("📋 Detailed Stats", callback_data="detailed_stats")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await loading_msg.edit_text(dashboard_msg, parse_mode='Markdown', reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error generating analytics dashboard: {e}")
            await loading_msg.edit_text(f"❌ Error loading dashboard: {str(e)}")

    async def generate_performance_report(self, update: Update, context: CallbackContext):
        """Generate detailed performance report"""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer("Generating performance report...")
        await query.edit_message_text("📊 Generating detailed performance report...")

        try:
            # Get comprehensive performance data
            report_data = await self._generate_comprehensive_report(user_id)
            
            report_msg = f"""
📊 **Detailed Performance Report**

**🎯 Strategy Performance**
            """
            
            for strategy, stats in report_data.get('strategy_stats', {}).items():
                report_msg += f"""
• **{strategy.title()}:**
  P&L: ${stats.get('pnl', 0):+,.2f}
  Trades: {stats.get('trades', 0)}
  Win Rate: {stats.get('win_rate', 0):.1f}%
                """

            report_msg += f"""

**📈 Monthly Breakdown**
            """
            
            for month, data in report_data.get('monthly_stats', {}).items():
                report_msg += f"""
• **{month}:** ${data.get('pnl', 0):+,.2f} ({data.get('trades', 0)} trades)
                """

            report_msg += f"""

**🏆 Key Achievements**
• Best Day: ${report_data.get('best_day', 0):+,.2f}
• Longest Win Streak: {report_data.get('win_streak', 0)} trades
• Max Drawdown: ${report_data.get('max_drawdown', 0):+,.2f}
• Sharpe Ratio: {report_data.get('sharpe_ratio', 0):.2f}
            """

            keyboard = [
                [InlineKeyboardButton("📄 Export Report", callback_data="export_report"),
                 InlineKeyboardButton("← Back", callback_data="refresh_analytics")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(report_msg, parse_mode='Markdown', reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            await query.edit_message_text(f"❌ Error generating report: {str(e)}")

    async def export_trade_data(self, update: Update, context: CallbackContext):
        """Export trade data as CSV"""
        query = update.callback_query
        user_id = query.from_user.id

        await query.answer("Preparing data export...")
        await query.edit_message_text("📤 Preparing trade data export...")

        try:
            # Get all trade data for user
            trade_data = await self._get_all_trade_data(user_id)
            
            if not trade_data:
                await query.edit_message_text("ℹ️ No trade data found to export.")
                return

            # Create CSV in memory
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            
            # Write headers
            csv_writer.writerow([
                'Date', 'Time', 'Coin', 'Side', 'Size', 'Price', 
                'Fee', 'P&L', 'Strategy', 'Order ID'
            ])
            
            # Write trade data
            for trade in trade_data:
                csv_writer.writerow([
                    trade.get('date', ''),
                    trade.get('time', ''),
                    trade.get('coin', ''),
                    trade.get('side', ''),
                    trade.get('size', 0),
                    trade.get('price', 0),
                    trade.get('fee', 0),
                    trade.get('pnl', 0),
                    trade.get('strategy', ''),
                    trade.get('order_id', '')
                ])

            # Convert to bytes
            csv_bytes = csv_buffer.getvalue().encode('utf-8')
            csv_file = io.BytesIO(csv_bytes)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"hyperliquid_trades_{timestamp}.csv"

            # Send file
            await query.message.reply_document(
                document=csv_file,
                filename=filename,
                caption=f"📊 Trade data export\n"
                       f"Period: {trade_data[0].get('date')} to {trade_data[-1].get('date')}\n"
                       f"Total trades: {len(trade_data)}"
            )

            await query.edit_message_text("✅ Trade data exported successfully!")

        except Exception as e:
            logger.error(f"Error exporting trade data: {e}")
            await query.edit_message_text(f"❌ Error exporting data: {str(e)}")

    async def manage_referrals(self, update: Update, context: CallbackContext):
        """Manage referral system"""
        user_id = update.effective_user.id
        
        # Get user's referral stats
        referral_stats = await self._get_referral_stats(user_id)
        
        referral_msg = f"""
🤝 **Referral System**

**Your Referral Code:** `{referral_stats.get('code', 'Not generated')}`
**Total Referrals:** {referral_stats.get('total_referrals', 0)}
**Active Referrals:** {referral_stats.get('active_referrals', 0)}
**Commission Earned:** ${referral_stats.get('commission_earned', 0):,.2f}

**Recent Referrals:**
        """
        
        for referral in referral_stats.get('recent_referrals', [])[:5]:
            join_date = datetime.fromtimestamp(referral.get('join_date', 0)).strftime('%Y-%m-%d')
            referral_msg += f"• User {referral.get('user_id', 'Unknown')} - {join_date}\n"
        
        if not referral_stats.get('recent_referrals'):
            referral_msg += "• No referrals yet\n"

        referral_msg += f"""
**How it works:**
• Share your referral code with friends
• Earn 10% of their trading fees as commission
• They get 5% discount on trading fees
• Commission paid weekly to your agent wallet
        """

        keyboard = [
            [InlineKeyboardButton("🔗 Generate Code", callback_data="generate_referral"),
             InlineKeyboardButton("📊 Detailed Stats", callback_data="referral_stats")],
            [InlineKeyboardButton("💰 Withdraw Commission", callback_data="withdraw_commission"),
             InlineKeyboardButton("📋 Referral History", callback_data="referral_history")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(referral_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def vault_management(self, update: Update, context: CallbackContext):
        """Advanced vault creation and management"""
        user_id = update.effective_user.id
        
        if not self.vault_manager:
            await update.message.reply_text("❌ Vault management not available")
            return

        vault_msg = f"""
🏦 **Vault Management**

**Create Your Own Vault:**
• Launch a managed trading vault
• Set your own strategy and fees
• Attract other investors
• Earn management fees

**Current Vault Status:**
• Personal Vault: Not created
• Minimum Capital Required: $1,000 USDC
• Management Fee: 2% annually
• Performance Fee: 20%

**Features:**
• Professional dashboard
• Investor reporting
• Automated fee collection
• Risk management tools
        """

        keyboard = [
            [InlineKeyboardButton("🚀 Create Vault", callback_data="create_vault"),
             InlineKeyboardButton("📊 Vault Templates", callback_data="vault_templates")],
            [InlineKeyboardButton("⚙️ Vault Settings", callback_data="vault_settings"),
             InlineKeyboardButton("📈 Performance Tracking", callback_data="vault_performance")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(vault_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def handle_advanced_callbacks(self, update: Update, context: CallbackContext):
        """Handle callbacks for advanced features"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id

        if data == "perf_report":
            await self.generate_performance_report(update, context)
        elif data == "export_data":
            await self.export_trade_data(update, context)
        elif data == "refresh_analytics":
            await self._refresh_analytics_dashboard(query, context)
        elif data == "detailed_stats":
            await self._show_detailed_statistics(query, context)
        elif data == "generate_referral":
            await self._generate_referral_code(query, context)
        elif data == "referral_stats":
            await self._show_referral_statistics(query, context)
        elif data == "create_vault":
            await self._initiate_vault_creation(query, context)
        elif data == "vault_templates":
            await self._show_vault_templates(query, context)
        else:
            await query.answer("Feature coming soon!")

    # Helper methods

    async def _calculate_performance_stats(self, user_id: int) -> Dict:
        """Calculate performance statistics for a user"""
        try:
            # Get trade history from last 30 days
            trades = await self._get_recent_trades(user_id, days=30)
            
            if not trades:
                return {
                    'total_pnl': 0,
                    'win_rate': 0,
                    'best_trade': 0,
                    'worst_trade': 0,
                    'avg_trade': 0
                }

            total_pnl = sum(trade.get('pnl', 0) for trade in trades)
            winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
            win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
            
            pnls = [trade.get('pnl', 0) for trade in trades]
            best_trade = max(pnls) if pnls else 0
            worst_trade = min(pnls) if pnls else 0
            avg_trade = total_pnl / len(trades) if trades else 0

            return {
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'best_trade': best_trade,
                'worst_trade': worst_trade,
                'avg_trade': avg_trade
            }

        except Exception as e:
            logger.error(f"Error calculating performance stats: {e}")
            return {}

    async def _get_trading_statistics(self, user_id: int) -> Dict:
        """Get trading statistics for a user"""
        try:
            # This would typically query your database
            # For now, using mock data
            return {
                'total_trades': 156,
                'total_volume': 50000,
                'total_fees': 125.50,
                'active_strategies': 2
            }

        except Exception as e:
            logger.error(f"Error getting trading statistics: {e}")
            return {}

    async def _generate_comprehensive_report(self, user_id: int) -> Dict:
        """Generate comprehensive performance report"""
        try:
            # Mock comprehensive report data
            return {
                'strategy_stats': {
                    'grid_trading': {
                        'pnl': 1250.50,
                        'trades': 89,
                        'win_rate': 72.5
                    },
                    'momentum': {
                        'pnl': -125.25,
                        'trades': 23,
                        'win_rate': 65.2
                    }
                },
                'monthly_stats': {
                    'January': {'pnl': 850.25, 'trades': 45},
                    'February': {'pnl': 275.00, 'trades': 67}
                },
                'best_day': 425.75,
                'win_streak': 12,
                'max_drawdown': -85.50,
                'sharpe_ratio': 1.45
            }

        except Exception as e:
            logger.error(f"Error generating comprehensive report: {e}")
            return {}

    async def _get_all_trade_data(self, user_id: int) -> List[Dict]:
        """Get all trade data for export"""
        try:
            # Mock trade data for export
            trades = []
            for i in range(50):  # Generate 50 mock trades
                trade_date = datetime.now() - timedelta(days=i)
                trades.append({
                    'date': trade_date.strftime('%Y-%m-%d'),
                    'time': trade_date.strftime('%H:%M:%S'),
                    'coin': 'BTC' if i % 3 == 0 else 'ETH' if i % 3 == 1 else 'SOL',
                    'side': 'BUY' if i % 2 == 0 else 'SELL',
                    'size': round(0.1 + (i * 0.01), 4),
                    'price': 65000 + (i * 10),
                    'fee': round(2.5 + (i * 0.1), 2),
                    'pnl': round((i - 25) * 5.5, 2),
                    'strategy': 'grid' if i % 4 == 0 else 'momentum',
                    'order_id': f"order_{1000 + i}"
                })
            
            return trades

        except Exception as e:
            logger.error(f"Error getting trade data: {e}")
            return []

    async def _get_recent_trades(self, user_id: int, days: int = 30) -> List[Dict]:
        """Get recent trades for a user"""
        try:
            # Mock recent trades
            trades = []
            for i in range(20):
                trades.append({
                    'pnl': (i - 10) * 12.5,
                    'coin': 'BTC',
                    'size': 0.1,
                    'timestamp': datetime.now() - timedelta(days=i)
                })
            return trades

        except Exception as e:
            logger.error(f"Error getting recent trades: {e}")
            return []

    async def _get_referral_stats(self, user_id: int) -> Dict:
        """Get referral statistics for a user"""
        try:
            # Mock referral stats
            return {
                'code': f"REF{user_id}",
                'total_referrals': 5,
                'active_referrals': 3,
                'commission_earned': 125.50,
                'recent_referrals': [
                    {'user_id': 'USER123', 'join_date': datetime.now().timestamp()},
                    {'user_id': 'USER456', 'join_date': (datetime.now() - timedelta(days=5)).timestamp()}
                ]
            }

        except Exception as e:
            logger.error(f"Error getting referral stats: {e}")
            return {}

    async def _refresh_analytics_dashboard(self, query, context):
        """Refresh the analytics dashboard"""
        await query.answer("Refreshing dashboard...")
        # Re-create the dashboard by calling show_analytics_dashboard logic
        # For callback context, we need to simulate the update object
        class MockUpdate:
            def __init__(self, query):
                self.callback_query = query
                self.message = query.message
        
        mock_update = MockUpdate(query)
        await self.show_analytics_dashboard(mock_update, context)

    async def _show_detailed_statistics(self, query, context):
        """Show detailed trading statistics"""
        await query.answer("Loading detailed stats...")
        
        detailed_msg = """
📊 **Detailed Trading Statistics**

**Asset Breakdown:**
• BTC: 45 trades, $1,250 P&L
• ETH: 67 trades, $890 P&L  
• SOL: 23 trades, -$125 P&L

**Time Analysis:**
• Best Hour: 14:00-15:00 UTC
• Worst Hour: 22:00-23:00 UTC
• Most Active Day: Tuesday

**Risk Metrics:**
• Max Daily Loss: $85
• Average Position Size: 0.15
• Risk/Reward Ratio: 1.8:1
        """
        
        keyboard = [
            [InlineKeyboardButton("← Back to Dashboard", callback_data="refresh_analytics")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(detailed_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _generate_referral_code(self, query, context):
        """Generate or show referral code"""
        user_id = query.from_user.id
        referral_code = f"HYPER{user_id}"
        
        await query.answer("Referral code generated!")
        
        code_msg = f"""
🔗 **Your Referral Code Generated!**

**Code:** `{referral_code}`

**Share this link:**
`https://t.me/YourBotUsername?start={referral_code}`

**Benefits:**
• You earn 10% commission on referral trading fees
• Your referrals get 5% discount on trading fees
• Commission paid weekly to your agent wallet
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 View Stats", callback_data="referral_stats"),
             InlineKeyboardButton("← Back", callback_data="refresh_analytics")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(code_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_referral_statistics(self, query, context):
        """Show detailed referral statistics"""
        await query.answer("Loading referral stats...")
        
        stats_msg = """
📊 **Detailed Referral Statistics**

**This Month:**
• New Referrals: 3
• Commission Earned: $45.50
• Total Volume from Referrals: $12,500

**All Time:**
• Total Referrals: 15
• Total Commission: $425.75
• Active Referrals: 8

**Top Performing Referrals:**
• User REF001: $125 commission
• User REF005: $89 commission
• User REF012: $67 commission
        """
        
        keyboard = [
            [InlineKeyboardButton("💰 Withdraw", callback_data="withdraw_commission"),
             InlineKeyboardButton("← Back", callback_data="referral_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(stats_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _initiate_vault_creation(self, query, context):
        """Initiate vault creation process"""
        await query.answer("Starting vault creation...")
        
        creation_msg = """
🚀 **Create Your Trading Vault**

**Step 1: Choose Vault Type**
• Conservative: Lower risk, steady returns
• Aggressive: Higher risk, higher potential returns
• Balanced: Mix of conservative and aggressive strategies

**Requirements:**
• Minimum Capital: $1,000 USDC
• Initial Deposit: $500 USDC (as vault manager)
• Management Experience: Recommended

**Next Steps:**
1. Select vault strategy template
2. Set fee structure
3. Configure risk parameters
4. Deploy vault contract
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 Conservative", callback_data="vault_conservative"),
             InlineKeyboardButton("🚀 Aggressive", callback_data="vault_aggressive")],
            [InlineKeyboardButton("⚖️ Balanced", callback_data="vault_balanced"),
             InlineKeyboardButton("← Back", callback_data="vault_management")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(creation_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_vault_templates(self, query, context):
        """Show available vault templates"""
        await query.answer("Loading vault templates...")
        
        templates_msg = """
📋 **Vault Strategy Templates**

**Grid Trading Vault**
• Strategy: Multi-pair grid trading
• Risk Level: Medium
• Expected Return: 15-25% annually
• Management Fee: 2%

**Momentum Trading Vault**
• Strategy: Trend-following algorithms
• Risk Level: High
• Expected Return: 25-40% annually
• Management Fee: 2.5%

**Market Making Vault**
• Strategy: Liquidity provision + rebate capture
• Risk Level: Low-Medium
• Expected Return: 10-20% annually
• Management Fee: 1.5%
        """
        
        keyboard = [
            [InlineKeyboardButton("📊 Grid Template", callback_data="template_grid"),
             InlineKeyboardButton("📈 Momentum Template", callback_data="template_momentum")],
            [InlineKeyboardButton("💧 Market Making", callback_data="template_market_making"),
             InlineKeyboardButton("← Back", callback_data="vault_management")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(templates_msg, parse_mode='Markdown', reply_markup=reply_markup)
