import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)

class StrategyHandler:
    def __init__(self, wallet_manager, trading_engine, grid_engine, config):
        self.wallet_manager = wallet_manager
        self.trading_engine = trading_engine # For momentum, manual trades
        self.grid_engine = grid_engine # For grid trading
        self.config = config
        # In-memory store for active strategies per user
        # Example: {user_id: {"grid_BTC": {"coin": "BTC", ...}, "maker_ETH": {}}}
        self.active_strategies = {}

    async def start_strategy_command(self, update: Update, context: CallbackContext):
        """Handles /start_trading [strategy_name] [params...]"""
        user_id = update.effective_user.id
        args = context.args

        if not await self._check_wallet_and_trading_enabled(user_id, update):
            return

        if not args:
            await update.message.reply_text(
                "Please specify a strategy. Usage: /start_trading <strategy_name> [params...]\n"
                "Available strategies: grid, momentum, maker_rebate (more soon)"
            )
            return

        strategy_name = args[0].lower()
        strategy_params = args[1:]

        if strategy_name == "grid":
            await self.handle_grid_trading_command(update, context, params=strategy_params, start=True)
        elif strategy_name == "momentum":
            await self.handle_momentum_trading_command(update, context, params=strategy_params, start=True)
        # Add more strategies like maker_rebate
        else:
            await update.message.reply_text(f"Unknown strategy: {strategy_name}. Available: grid, momentum.")

    async def stop_strategy_command(self, update: Update, context: CallbackContext):
        """Handles /stop_trading [strategy_name] or all strategies for a user"""
        user_id = update.effective_user.id
        args = context.args

        if not self.wallet_manager or not await self.wallet_manager.get_user_wallet(user_id):
            await update.message.reply_text("❌ No agent wallet found. Use /agent to create one.")
            return

        if not args: # Stop all strategies for the user
            stopped_count = 0
            user_strats = self.active_strategies.get(user_id, {})
            strategies_to_stop = list(user_strats.keys()) # Avoid issues if dict changes during iteration

            for strat_id in strategies_to_stop:
                # This is a simplified stop. Real implementation would call specific stop methods.
                if strat_id.startswith("grid_"):
                    coin = user_strats[strat_id]['coin']
                    if hasattr(self.grid_engine, 'stop_grid'):
                         # Assuming stop_grid takes coin and user_id (or agent_address)
                        await self.grid_engine.stop_grid(coin, user_id=user_id) # Adapt as per grid_engine
                # Add logic for other strategy types
                
                del self.active_strategies[user_id][strat_id]
                stopped_count +=1
            
            if self.active_strategies.get(user_id) == {}:
                del self.active_strategies[user_id]

            if stopped_count > 0:
                await update.message.reply_text(f"✅ Stopped {stopped_count} active strategies for you.")
            else:
                await update.message.reply_text("ℹ️ No active strategies found for you to stop.")
            # Also disable general trading on the agent wallet
            await self.wallet_manager.disable_trading(user_id)
            await update.message.reply_text("ℹ️ General trading for your agent wallet has been disabled.")

        else: # Stop a specific strategy
            strategy_name_or_id = args[0]
            # This part needs more robust ID management for strategies
            # For now, let's assume strategy_name_or_id can be like "grid_BTC"
            user_strats = self.active_strategies.get(user_id, {})
            if strategy_name_or_id in user_strats:
                # Simplified stop
                del self.active_strategies[user_id][strategy_name_or_id]
                await update.message.reply_text(f"✅ Strategy {strategy_name_or_id} stopped.")
                if not self.active_strategies[user_id]: # if no strategies left, disable trading
                     await self.wallet_manager.disable_trading(user_id)
                     await update.message.reply_text("ℹ️ All strategies stopped. General trading for your agent wallet has been disabled.")

            else:
                await update.message.reply_text(f"❌ Strategy {strategy_name_or_id} not found or not active for you.")


    async def _check_wallet_and_trading_enabled(self, user_id: int, update: Update) -> bool:
        """Helper to check for agent wallet and if trading is generally enabled."""
        if not self.wallet_manager:
            await update.message.reply_text("❌ Wallet management not available.")
            return False

        user_wallet = await self.wallet_manager.get_user_wallet(user_id)
        if not user_wallet:
            await update.message.reply_text("❌ No agent wallet found. Use /agent to create one.")
            return False

        status = await self.wallet_manager.get_wallet_status(user_id)
        if not status['funded']:
            await update.message.reply_text("❌ Your agent wallet is not funded. Please use /fund.")
            return False
        
        if not await self.wallet_manager.is_trading_enabled(user_id):
            # If not enabled, enable it now.
            await self.wallet_manager.enable_trading(user_id)
            await update.message.reply_text("ℹ️ General trading for your agent wallet has been enabled.")
        return True

    async def handle_grid_trading_command(self, update: Update, context: CallbackContext, params: list, start: bool):
        user_id = update.effective_user.id
        if start:
            if not params:
                await update.message.reply_text("Usage: /start_trading grid <COIN> [levels] [spacing]\nExample: /start_trading grid BTC 10 0.002")
                return
            
            coin = params[0].upper()
            levels = int(params[1]) if len(params) > 1 else 10
            spacing = float(params[2]) if len(params) > 2 else 0.002
            
            if not self.grid_engine:
                await update.message.reply_text("❌ Grid Trading Engine not available.")
                return

            # Ensure user_id has an entry in active_strategies
            if user_id not in self.active_strategies:
                self.active_strategies[user_id] = {}

            # Check if grid for this coin is already active for the user
            grid_id = f"grid_{coin}"
            if grid_id in self.active_strategies.get(user_id, {}):
                await update.message.reply_text(f"ℹ️ Grid trading for {coin} is already active.")
                return

            # Start grid using GridTradingEngine (adapt call as per actual GridTradingEngine)
            # This is a placeholder call, actual implementation depends on GridTradingEngine
            # It should use the user's agent wallet context (e.g. agent_address or agent_exchange)
            agent_wallet = await self.wallet_manager.get_user_wallet(user_id)
            result = await self.grid_engine.start_grid(
                coin=coin, 
                levels=levels, 
                spacing=spacing, 
                user_id=user_id, # Pass user_id for context
                agent_address=agent_wallet['address'] # Pass agent_address
            ) 
            
            if result.get('status') == 'success':
                self.active_strategies[user_id][grid_id] = {"coin": coin, "levels": levels, "spacing": spacing, "details": result}
                await update.message.reply_text(
                    f"✅ Grid trading for {coin} started.\n"
                    f"Range: {result.get('grid_range', 'N/A')}, Orders: {result.get('orders_placed', 'N/A')}"
                )
            else:
                await update.message.reply_text(f"❌ Failed to start grid for {coin}: {result.get('message', 'Unknown error')}")
        else: # Stop grid
            # Implement stop logic, similar to stop_strategy_command
            await update.message.reply_text("🛑 Grid stop functionality to be implemented via /stop_trading grid <COIN>")


    async def handle_momentum_trading_command(self, update: Update, context: CallbackContext, params: list, start: bool):
        user_id = update.effective_user.id
        if start:
            if not params:
                await update.message.reply_text("Usage: /start_trading momentum <COIN>\nExample: /start_trading momentum ETH")
                return
            
            coin = params[0].upper()
            
            if not self.trading_engine or not hasattr(self.trading_engine, 'momentum_strategy'):
                await update.message.reply_text("❌ Momentum Trading Engine not available.")
                return

            if user_id not in self.active_strategies:
                self.active_strategies[user_id] = {}
            
            momentum_id = f"momentum_{coin}"
            if momentum_id in self.active_strategies.get(user_id, {}):
                await update.message.reply_text(f"ℹ️ Momentum trading for {coin} is already considered active (or last signal processed).")
                return

            agent_wallet = await self.wallet_manager.get_user_wallet(user_id)
            # The trading_engine.momentum_strategy needs to be adapted to take user_id/agent_address
            # and use the agent's exchange context.
            result = await self.trading_engine.momentum_strategy(
                coin=coin,
                user_id=user_id, # Pass user_id for context
                agent_address=agent_wallet['address'] # Pass agent_address
            )
            
            if result.get('status') == 'success':
                # Momentum might be a one-off signal rather than a continuous strategy state
                # self.active_strategies[user_id][momentum_id] = {"coin": coin, "details": result}
                await update.message.reply_text(
                    f"📈 Momentum signal for {coin} processed.\n"
                    f"Action: {result.get('action', 'N/A')}, Entry: ${result.get('entry_price', 0):.2f}"
                )
            else:
                await update.message.reply_text(f"ℹ️ Momentum signal for {coin}: {result.get('message', 'No signal or error')}")
        else:
            await update.message.reply_text("🛑 Momentum stop functionality to be implemented via /stop_trading momentum <COIN>")

    async def handle_manual_trade_command(self, update: Update, context: CallbackContext):
        # Placeholder for manual trading via commands
        await update.message.reply_text("🛠️ Manual trading feature coming soon! (e.g., /buy BTC 0.1 limit 60000)")

    async def handle_strategy_config_command(self, update: Update, context: CallbackContext):
        # Placeholder for configuring strategies
        await update.message.reply_text("⚙️ Strategy configuration feature coming soon!")

    async def handle_risk_management_command(self, update: Update, context: CallbackContext):
        # Placeholder for risk management settings
        await update.message.reply_text("🛡️ Risk management settings feature coming soon!")

    def get_active_strategies_for_user(self, user_id: int) -> dict:
        return self.active_strategies.get(user_id, {})

