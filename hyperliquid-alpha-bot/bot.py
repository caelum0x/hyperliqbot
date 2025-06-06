#!/usr/bin/env python3
"""
HYPERLIQUID ALPHA BOT - Simple Telegram Interface
Focus: Make money from Hyperliquid incentives, not users
"""

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from strategies import AlphaStrategies
from wallet_manager import WalletManager
from hyperliquid_api import HyperliquidAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HyperliquidAlphaBot:
    def __init__(self, telegram_token: str, referral_code: str = "ALPHABOT"):
        self.app = Application.builder().token(telegram_token).build()
        self.referral_code = referral_code
        
        # Core components
        self.api = HyperliquidAPI()
        self.wallet_manager = WalletManager(self.api)
        self.strategies = AlphaStrategies(self.api, self.wallet_manager)
        
        # Setup handlers
        self.setup_commands()
        
    def setup_commands(self):
        """Setup simple command handlers"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("farm", self.farm))
        self.app.add_handler(CommandHandler("stats", self.stats))
        self.app.add_handler(CommandHandler("compete", self.compete))
        self.app.add_handler(CommandHandler("connect", self.connect))
        self.app.add_handler(CommandHandler("vault", self.vault))
        self.app.add_handler(CallbackQueryHandler(self.handle_callbacks))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command - explain the alpha"""
        user_id = update.effective_user.id
        
        welcome = f"""
🏆 **HYPERLIQUID ALPHA BOT**

💰 **WE MAKE MONEY FROM HYPERLIQUID, NOT YOU**

🎯 **ACTIVE INCENTIVES:**
• Volume Competitions: $50K+ prizes monthly
• Builder Grants: Up to $100K for ecosystem tools
• Maker Rebates: -0.003% on every trade
• Referral Program: 10% of all user fees

🚀 **ALPHA STRATEGIES:**
• HyperEVM Daily Farming (launch protocols)
• Seedify IMC Participation (guaranteed allocations)
• NFT Mint Sniping (Abstract/HyperEVM)
• Volume Generation (competition farming)

💡 **CONNECT YOUR WALLET (2 OPTIONS):**

**Option 1: API Wallet (RECOMMENDED)**
1. Go to app.hyperliquid.xyz/API
2. Create API wallet (keeps main wallet safe)
3. /connect <api_private_key>

**Option 2: Deposit to Vault**
1. /vault - Get vault address
2. Deposit USDC to collective vault
3. Get proportional profits

🔗 **START WITH 4% FEE DISCOUNT:**
https://app.hyperliquid.xyz/join/{self.referral_code}

Ready to farm alpha?
        """
        
        keyboard = [
            [InlineKeyboardButton("🔗 Connect API Wallet", callback_data="connect_api")],
            [InlineKeyboardButton("🏦 Use Vault", callback_data="use_vault")],
            [InlineKeyboardButton("🏆 View Competitions", callback_data="competitions")],
            [InlineKeyboardButton("🚀 Start Farming", callback_data="start_farming")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome, parse_mode='Markdown', reply_markup=reply_markup)
        
    async def connect(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Connect API wallet"""
        user_id = update.effective_user.id
        
        if not context.args:
            await update.message.reply_text(
                "🔐 **Connect Your API Wallet**\n\n"
                "1. Go to https://app.hyperliquid.xyz/API\n"
                "2. Click 'Create API Wallet'\n"
                "3. Copy the private key\n"
                "4. Send: `/connect <your_api_private_key>`\n\n"
                "⚠️ **API Wallet Benefits:**\n"
                "• Keeps main wallet secure\n"
                "• Bot can trade for you\n"
                "• You maintain full control\n"
                "• Delete message after connecting",
                parse_mode='Markdown'
            )
            return
        
        try:
            api_key = context.args[0]
            
            # Connect user wallet
            result = await self.wallet_manager.connect_user(user_id, api_key)
            
            if result['success']:
                # Auto-delete the message with private key
                try:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=update.message.message_id
                    )
                except:
                    pass
                
                user_info = result['user_info']
                
                await update.message.reply_text(
                    f"✅ **API Wallet Connected!**\n\n"
                    f"📍 Address: `{user_info['address'][:8]}...{user_info['address'][-6:]}`\n"
                    f"💰 Balance: ${user_info['balance']:,.2f}\n"
                    f"🎯 Status: Ready for alpha strategies\n\n"
                    f"Use /farm to start earning!",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(f"❌ Connection failed: {result['error']}")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def farm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start farming alpha strategies"""
        user_id = update.effective_user.id
        
        if not await self.wallet_manager.is_user_connected(user_id):
            await update.message.reply_text("❌ Connect your wallet first: /connect")
            return
        
        # Start all alpha strategies
        await update.message.reply_text("🚀 Starting alpha farming strategies...")
        
        try:
            results = await self.strategies.start_all_strategies(user_id)
            
            status_msg = "✅ **ALPHA FARMING ACTIVE**\n\n"
            
            for strategy, result in results.items():
                if result['success']:
                    status_msg += f"🟢 {strategy}: {result['message']}\n"
                else:
                    status_msg += f"🔴 {strategy}: {result['error']}\n"
            
            status_msg += "\n📊 Use /stats to track earnings"
            
            keyboard = [
                [InlineKeyboardButton("📊 View Stats", callback_data="view_stats")],
                [InlineKeyboardButton("⏹️ Stop Farming", callback_data="stop_farming")],
                [InlineKeyboardButton("🔄 Restart", callback_data="restart_farming")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(status_msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Farming failed: {str(e)}")
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show earnings and performance"""
        user_id = update.effective_user.id
        
        if not await self.wallet_manager.is_user_connected(user_id):
            await update.message.reply_text("❌ Connect your wallet first: /connect")
            return
        
        try:
            # Get user stats from all strategies
            user_stats = await self.strategies.get_user_stats(user_id)
            competition_stats = await self.api.get_competition_status()
            
            stats_msg = f"""
📊 **YOUR ALPHA EARNINGS**

💰 **Total Profits:** ${user_stats['total_profit']:+,.2f}

🎯 **Strategy Performance:**
• Volume Farming: ${user_stats['volume_earnings']:+,.2f}
• Maker Rebates: ${user_stats['rebate_earnings']:+,.2f}
• HyperEVM Farming: ${user_stats['hyperevm_earnings']:+,.2f}
• Seedify Profits: ${user_stats['seedify_earnings']:+,.2f}

🏆 **Competition Status:**
• Current Volume: ${user_stats['daily_volume']:,.2f}
• Leaderboard Position: #{competition_stats.get('rank', 'N/A')}
• Est. Prize: ${competition_stats.get('estimated_prize', 0):,.2f}

📈 **24h Performance:**
• Trades Executed: {user_stats['trades_24h']}
• Rebates Earned: ${user_stats['rebates_24h']:,.4f}
• P&L: ${user_stats['pnl_24h']:+,.2f}

⚡ **Active Now:**
{', '.join(user_stats['active_strategies'])}
            """
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")],
                [InlineKeyboardButton("💰 Optimize", callback_data="optimize_farming")],
                [InlineKeyboardButton("🏆 Competition Details", callback_data="competition_details")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(stats_msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error fetching stats: {str(e)}")
    
    async def compete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Join volume competitions"""
        user_id = update.effective_user.id
        
        try:
            # Get active competitions
            competitions = await self.api.get_active_competitions()
            
            compete_msg = "🏆 **HYPERLIQUID COMPETITIONS**\n\n"
            
            for comp in competitions:
                compete_msg += f"**{comp['name']}**\n"
                compete_msg += f"• Prize Pool: ${comp['prize_pool']:,.0f}\n"
                compete_msg += f"• Ends: {comp['end_date']}\n"
                compete_msg += f"• Your Volume: ${comp['user_volume']:,.0f}\n"
                compete_msg += f"• Rank: #{comp['user_rank']}\n\n"
            
            compete_msg += "💡 **Auto-Competition Mode:**\n"
            compete_msg += "Bot automatically optimizes volume for max prizes"
            
            keyboard = [
                [InlineKeyboardButton("🚀 Join All Competitions", callback_data="join_competitions")],
                [InlineKeyboardButton("📊 Leaderboard", callback_data="view_leaderboard")],
                [InlineKeyboardButton("⚙️ Competition Settings", callback_data="comp_settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(compete_msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error loading competitions: {str(e)}")
    
    async def vault(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show vault information"""
        try:
            vault_info = await self.wallet_manager.get_vault_info()
            
            vault_msg = f"""
🏦 **COLLECTIVE ALPHA VAULT**

💰 **Vault Stats:**
• Total Value: ${vault_info['total_value']:,.2f}
• Users: {vault_info['user_count']}
• Daily Return: {vault_info['daily_return']:.2%}
• Total Profit: ${vault_info['total_profit']:+,.2f}

🎯 **Active Strategies:**
• Volume Competition Farming
• Maker Rebate Mining
• HyperEVM Protocol Farming
• Seedify IMC Participation

📋 **Deposit Address:**
```
{vault_info['vault_address']}
```

💡 **How It Works:**
1. Deposit USDC to vault address
2. Bot farms alpha strategies with pooled funds
3. You get proportional share of profits
4. No performance fees - we profit from incentives

**Minimum Deposit:** $50 USDC
            """
            
            keyboard = [
                [InlineKeyboardButton("💰 Deposit to Vault", callback_data="deposit_vault")],
                [InlineKeyboardButton("📊 Vault Performance", callback_data="vault_performance")],
                [InlineKeyboardButton("💸 Request Withdrawal", callback_data="request_withdrawal")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(vault_msg, parse_mode='Markdown', reply_markup=reply_markup)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error loading vault: {str(e)}")
    
    async def handle_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = query.from_user.id
        
        try:
            if data == "connect_api":
                await query.edit_message_text(
                    "🔗 **Connect API Wallet**\n\n"
                    "1. Visit: https://app.hyperliquid.xyz/API\n"
                    "2. Create new API wallet\n"
                    "3. Copy private key\n"
                    "4. Send: `/connect <private_key>`\n\n"
                    "This keeps your main wallet safe!"
                )
            
            elif data == "use_vault":
                await self.vault(update, context)
            
            elif data == "competitions":
                await self.compete(update, context)
            
            elif data == "start_farming":
                await self.farm(update, context)
            
            elif data == "view_stats":
                await self.stats(update, context)
            
            elif data == "join_competitions":
                await query.edit_message_text("🚀 Joining all active competitions...")
                result = await self.strategies.enable_competition_mode(user_id)
                
                if result['success']:
                    await query.edit_message_text(
                        f"✅ Competition mode enabled!\n\n"
                        f"Targeting: {', '.join(result['competitions'])}\n"
                        f"Estimated daily volume: ${result['target_volume']:,.0f}"
                    )
                else:
                    await query.edit_message_text(f"❌ Failed: {result['error']}")
            
            elif data == "optimize_farming":
                await query.edit_message_text("⚙️ Optimizing farming strategies...")
                result = await self.strategies.optimize_for_user(user_id)
                await query.edit_message_text(f"✅ Optimization complete: {result['message']}")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)}")
    
    async def run(self):
        """Start the bot"""
        logger.info("🚀 Starting Hyperliquid Alpha Bot...")
        
        # Start background strategies
        asyncio.create_task(self.strategies.run_background_farming())
        
        # Start bot
        await self.app.initialize()
        await self.app.start()
        logger.info("✅ Bot running - ready to farm alpha!")
        await self.app.run_polling()

# Run the bot
if __name__ == "__main__":
    import json
    
    with open("config.json", "r") as f:
        config = json.load(f)
    
    bot = HyperliquidAlphaBot(
        telegram_token=config["telegram_token"],
        referral_code=config.get("referral_code", "ALPHABOT")
    )
    
    asyncio.run(bot.run())
