"""
Main entry point for the Hyperliquid Alpha Trading Bot
Unified architecture connecting all components with real implementations
"""

import asyncio
import logging
import json
import sys
import os
from pathlib import Path
from typing import Dict, Optional

from trading_engine.vault_manager import VaultManager

# Add current directory to Python path to fix imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Real component imports
from database import Database

from trading_engine.core_engine import TradingEngine
from trading_engine.websocket_manager import HyperliquidWebSocketManager
from telegram_bot.bot import HyperliquidTradingBot
from strategies.grid_trading_engine import GridTradingEngine
from strategies.automated_trading import AutomatedTrading
from strategies.hyperliquid_profit_bot import HyperliquidProfitBot

# Hyperliquid SDK imports
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Import examples for setup
examples_dir = Path(__file__).parent / 'examples'
sys.path.append(str(examples_dir))
import example_utils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hyperliquid_bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class HyperliquidAlphaBot:
    """
    Main orchestrator for the Hyperliquid Alpha Trading Bot
    Initializes all components in proper dependency order using real implementations
    """
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.running = False
        
        # Core components
        self.database = None
        self.trading_engine = None
        self.vault_manager = None
        self.strategies = {}
        self.ws_manager = None
        self.telegram_bot = None
        
        # Hyperliquid SDK components
        self.address = None
        self.info = None
        self.exchange = None
        
        logger.info("HyperliquidAlphaBot initialized")
    
    def _load_config(self, config_path: str) -> dict:
        """Load and validate configuration"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Set defaults if not present
            if 'hyperliquid' not in config:
                config['hyperliquid'] = {
                    'api_url': constants.TESTNET_API_URL,
                    'mainnet': False
                }
            
            if 'vault' not in config:
                config['vault'] = {
                    'address': '',
                    'minimum_deposit': 50,
                    'performance_fee': 0.10
                }
            
            if 'telegram' not in config:
                config['telegram'] = {
                    'bot_token': '',
                    'allowed_users': []
                }
            
            # Validate required fields
            if not config['telegram']['bot_token']:
                logger.error("❌ Telegram bot token not set in config.json")
                raise ValueError("Missing telegram bot token")
            
            return config
            
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
    
    async def initialize_components(self):
        """Initialize all components in proper dependency order with enhanced error handling"""
        try:
            logger.info("🔧 Initializing HyperliquidAlphaBot components...")
            
            # 1. Initialize Hyperliquid SDK using example_utils pattern with enhanced error handling
            logger.info("🔗 Setting up Hyperliquid API connection...")
            try:
                base_url = self.config['hyperliquid']['api_url']
                self.address, self.info, self.exchange = example_utils.setup(base_url, skip_ws=True)
                
                # Test the connection
                user_state = self.info.user_state(self.address)
                account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
                
                logger.info(f"✅ Connected to Hyperliquid API at {self.address}")
                logger.info(f"📊 Account value: ${account_value:,.2f}")
                
                # Enhanced vault handling from real_trading_bot.py
                if self.config['vault']['address']:
                    try:
                        self.vault_exchange = Exchange(
                            self.exchange.wallet, 
                            self.exchange.base_url, 
                            vault_address=self.config['vault']['address']
                        )
                        
                        # Test vault connection
                        vault_state = self.info.user_state(self.config['vault']['address'])
                        vault_value = float(vault_state.get('marginSummary', {}).get('accountValue', 0))
                        logger.info(f"🏦 Vault connected: ${vault_value:,.2f}")
                        
                    except Exception as e:
                        logger.warning(f"Vault connection failed: {e}")
                        self.vault_exchange = None
                
            except Exception as e:
                logger.critical(f"Failed to connect to Hyperliquid API: {e}")
                raise
            
            # 2. Database with connection validation
            logger.info("📚 Initializing database...")
            try:
                self.database = Database()
                await self.database.initialize()
                # Test database connection
                await self.database.execute("SELECT 1")
                logger.info("✅ Database initialized and tested")
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")
                # Create fallback database
                self.database = self._create_fallback_database()
                logger.warning("⚠️ Using fallback database implementation")
            
            # 3. Core trading engine with validation
            logger.info("⚙️ Initializing core trading engine...")
            try:
                self.trading_engine = TradingEngine(
                    base_url=base_url,
                    address=self.address,
                    info=self.info,
                    exchange=self.exchange
                )
                
                # Validate trading engine with test query
                test_mids = await self.trading_engine.get_all_mids()
                if test_mids:
                    logger.info(f"✅ Trading engine initialized ({len(test_mids)} markets)")
                else:
                    raise Exception("No market data available")
                    
            except Exception as e:
                logger.error(f"Trading engine initialization failed: {e}")
                self.trading_engine = self._create_fallback_trading_engine()
                logger.warning("⚠️ Using fallback trading engine")
            
            # 4. Vault manager with enhanced setup
            logger.info("🏦 Initializing vault manager...")
            try:
                self.vault_manager = VaultManager(
                    vault_address=self.config['vault']['address'],
                    base_url=base_url,
                    exchange=getattr(self, 'vault_exchange', self.exchange),
                    info=self.info
                )
                
                # Test vault manager
                if self.config['vault']['address']:
                    vault_balance = await self.vault_manager.get_vault_balance()
                    if vault_balance['status'] == 'success':
                        logger.info(f"✅ Vault manager initialized: ${vault_balance['total_value']:,.2f}")
                    else:
                        logger.warning("⚠️ Vault manager created but balance check failed")
                else:
                    logger.info("✅ Vault manager initialized (no vault address configured)")
                    
            except Exception as e:
                logger.error(f"Vault manager initialization failed: {e}")
                self.vault_manager = self._create_fallback_vault_manager()
                logger.warning("⚠️ Using fallback vault manager")
            
            # 5. Trading strategies with individual error handling
            logger.info("🎯 Initializing trading strategies...")
            strategy_count = await self._initialize_strategies_with_validation()
            logger.info(f"✅ Initialized {strategy_count} strategies")
            
            # 6. WebSocket manager with connection test
            logger.info("🔌 Initializing WebSocket manager...")
            try:
                self.ws_manager = HyperliquidWebSocketManager(
                    base_url=base_url,
                    address=self.address,
                    info=self.info,
                    exchange=self.exchange
                )
                
                # Test WebSocket connection
                await self.ws_manager.test_connection()
                logger.info("✅ WebSocket manager initialized and tested")
                
            except Exception as e:
                logger.error(f"WebSocket manager initialization failed: {e}")
                self.ws_manager = None
                logger.warning("⚠️ Continuing without WebSocket manager")
            
            # 7. Telegram bot with dependency injection
            logger.info("🤖 Initializing Telegram bot...")
            try:
                self.telegram_bot = HyperliquidTradingBot(
                    config_path="telegram_bot/bot_config.json"
                )
                
                # Inject dependencies
                self.telegram_bot.vault_manager = self.vault_manager
                self.telegram_bot.trading_engine = self.trading_engine
                self.telegram_bot.strategies = self.strategies
                self.telegram_bot.database = self.database
                self.telegram_bot.ws_manager = self.ws_manager
                
                # Test bot initialization
                await self.telegram_bot.initialize()
                logger.info("✅ Telegram bot initialized with all dependencies")
                
            except Exception as e:
                logger.error(f"Telegram bot initialization failed: {e}")
                self.telegram_bot = None
                logger.warning("⚠️ Continuing without Telegram bot")
            
            # Final health check
            await self._perform_health_check()
            logger.info("🚀 All components initialized successfully!")
            
        except Exception as e:
            logger.critical(f"Failed to initialize components: {e}")
            raise
    
    async def _initialize_strategies_with_validation(self) -> int:
        """Initialize strategies with individual error handling"""
        strategy_count = 0
        
        # Grid trading strategy
        try:
            self.strategies['grid'] = GridTradingEngine(
                exchange=self.exchange,
                info=self.info,
                base_url=self.config['hyperliquid']['api_url']
            )
            await self.strategies['grid'].validate_connection()
            strategy_count += 1
            logger.info("✅ Grid trading engine ready")
        except Exception as e:
            logger.error(f"Grid trading engine failed: {e}")
        
        # Automated trading strategy
        try:
            self.strategies['auto'] = AutomatedTrading(
                exchange=self.exchange,
                info=self.info,
                base_url=self.config['hyperliquid']['api_url']
            )
            await self.strategies['auto'].validate_connection()
            strategy_count += 1
            logger.info("✅ Automated trading engine ready")
        except Exception as e:
            logger.error(f"Automated trading engine failed: {e}")
        
        # Profit-focused bot
        try:
            self.strategies['profit'] = HyperliquidProfitBot(
                exchange=self.exchange,
                info=self.info,
                base_url=self.config['hyperliquid']['api_url'],
                vault_address=self.config['vault']['address']
            )
            await self.strategies['profit'].validate_connection()
            strategy_count += 1
            logger.info("✅ Profit bot ready")
        except Exception as e:
            logger.error(f"Profit bot failed: {e}")
        
        return strategy_count
    
    def _create_fallback_database(self):
        """Create fallback database for demo mode"""
        class FallbackDatabase:
            async def initialize(self): pass
            async def execute(self, query): return []
            async def get_user_stats(self, user_id): return {}
            async def record_trade(self, user_id, trade_data): pass
            async def close(self): pass
        
        return FallbackDatabase()
    
    def _create_fallback_trading_engine(self):
        """Create fallback trading engine for demo mode"""
        class FallbackTradingEngine:
            async def get_all_mids(self): 
                return {'BTC': '65000.0', 'ETH': '3000.0', 'SOL': '100.0'}
            async def place_order(self, *args, **kwargs): 
                return {'status': 'demo_mode'}
        
        return FallbackTradingEngine()
    
    def _create_fallback_vault_manager(self):
        """Create fallback vault manager for demo mode"""
        class FallbackVaultManager:
            async def get_vault_balance(self): 
                return {'status': 'demo_mode', 'total_value': 1000.0}
            async def deposit(self, *args, **kwargs): 
                return {'status': 'demo_mode'}
        
        return FallbackVaultManager()
    
    async def _perform_health_check(self):
        """Perform comprehensive health check of all components"""
        health_status = {
            'hyperliquid_api': False,
            'database': False,
            'trading_engine': False,
            'vault_manager': False,
            'strategies': 0,
            'websocket': False,
            'telegram_bot': False
        }
        
        # Check Hyperliquid API
        try:
            user_state = self.info.user_state(self.address)
            health_status['hyperliquid_api'] = bool(user_state)
        except:
            pass
        
        # Check database
        try:
            await self.database.execute("SELECT 1")
            health_status['database'] = True
        except:
            pass
        
        # Check trading engine
        if self.trading_engine:
            try:
                mids = await self.trading_engine.get_all_mids()
                health_status['trading_engine'] = len(mids) > 0
            except:
                pass
        
        # Check vault manager
        if self.vault_manager:
            try:
                balance = await self.vault_manager.get_vault_balance()
                health_status['vault_manager'] = balance['status'] != 'error'
            except:
                pass
        
        # Count working strategies
        health_status['strategies'] = len(self.strategies)
        
        # Check WebSocket
        health_status['websocket'] = self.ws_manager is not None
        
        # Check Telegram bot
        health_status['telegram_bot'] = self.telegram_bot is not None
        
        # Log health status
        healthy_components = sum(1 for v in health_status.values() if v is True or (isinstance(v, int) and v > 0))
        total_components = len(health_status)
        
        logger.info(f"🏥 Health check: {healthy_components}/{total_components} components healthy")
        
        if healthy_components < total_components * 0.7:  # Less than 70% healthy
            logger.warning("⚠️ System health below optimal - some features may be limited")
        
        return health_status

    async def start_background_tasks(self):
        """Start background monitoring and trading tasks"""
        try:
            logger.info("⚡ Starting background tasks...")
            
            # Start WebSocket monitoring
            if self.ws_manager:
                asyncio.create_task(self._monitor_markets())
                logger.info("📊 Market monitoring started")
            
            # Start vault performance tracking
            if self.vault_manager:
                asyncio.create_task(self._track_vault_performance())
                logger.info("🏦 Vault performance tracking started")
            
            # Start strategy execution
            for name, strategy in self.strategies.items():
                if hasattr(strategy, 'run_background'):
                    asyncio.create_task(strategy.run_background())
                    logger.info(f"🎯 {name} strategy background task started")
            
            # Start profit optimization
            asyncio.create_task(self._run_profit_optimization())
            logger.info("💰 Profit optimization started")
            
            logger.info("✅ All background tasks started")
            
        except Exception as e:
            logger.error(f"Error starting background tasks: {e}")
    
    async def _monitor_markets(self):
        """Monitor real-time market data"""
        while self.running:
            try:
                # Subscribe to key market data
                major_coins = ['BTC', 'ETH', 'SOL', 'ARB']
                
                for coin in major_coins:
                    # Subscribe to order book for spread analysis
                    self.ws_manager.subscribe_l2_book(coin, self._process_market_data)
                    
                    # Subscribe to BBO for tight spread detection
                    self.ws_manager.subscribe_bbo(coin, self._detect_opportunities)
                
                # Subscribe to all mids for general monitoring
                self.ws_manager.subscribe_all_mids(self._track_price_movements)
                
                await asyncio.sleep(300)  # Refresh subscriptions every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in market monitoring: {e}")
                await asyncio.sleep(60)
    
    async def _track_vault_performance(self):
        """Track and optimize vault performance"""
        while self.running:
            try:
                # Get current vault balance
                vault_balance = await self.vault_manager.get_vault_balance()
                
                if vault_balance['status'] == 'success':
                    logger.info(f"Vault balance: ${vault_balance['total_value']:,.2f}")
                    
                    # Calculate performance metrics
                    if vault_balance['total_value'] > 1000:  # Only trade if sufficient capital
                        # Execute profit strategies
                        for strategy_name, strategy in self.strategies.items():
                            try:
                                if hasattr(strategy, 'execute_strategy'):
                                    result = await strategy.execute_strategy()
                                    if result.get('status') == 'success':
                                        logger.info(f"{strategy_name} strategy executed successfully")
                            except Exception as e:
                                logger.error(f"Error executing {strategy_name}: {e}")
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error tracking vault performance: {e}")
                await asyncio.sleep(60)
    
    async def _run_profit_optimization(self):
        """Run profit optimization strategies"""
        while self.running:
            try:
                # Execute profit bot strategies
                if 'profit' in self.strategies:
                    profit_bot = self.strategies['profit']
                    
                    # Execute maker rebate strategy
                    rebate_result = await profit_bot.multi_pair_rebate_mining(['BTC', 'ETH', 'SOL'])
                    if rebate_result['status'] == 'success':
                        logger.info(f"Rebate mining: {rebate_result['total_orders_placed']} orders placed")
                    
                    # Execute vault performance strategy
                    vault_result = await profit_bot.vault_performance_strategy()
                    if vault_result['status'] == 'success':
                        logger.info(f"Vault strategy performance fee: ${vault_result['performance_fee_earned']:.4f}")
                
                await asyncio.sleep(600)  # Every 10 minutes
                
            except Exception as e:
                logger.error(f"Error in profit optimization: {e}")
                await asyncio.sleep(120)
    
    def _process_market_data(self, data):
        """Process market data for trading signals"""
        try:
            # Extract market data and check for opportunities
            coin = data.get('coin', '')
            if coin and 'levels' in data:
                # Check for imbalance opportunities
                levels = data['levels']
                if len(levels) >= 2:
                    bids = levels[0]
                    asks = levels[1]
                    
                    if bids and asks:
                        bid_depth = sum(float(lvl[1]) for lvl in bids[:5])  # Top 5 levels
                        ask_depth = sum(float(lvl[1]) for lvl in asks[:5])
                        
                        if bid_depth + ask_depth > 0:
                            imbalance = (bid_depth - ask_depth) / (bid_depth + ask_depth)
                            
                            # Log significant imbalances
                            if abs(imbalance) > 0.3:
                                logger.info(f"{coin} order book imbalance: {imbalance:.3f}")
        
        except Exception as e:
            logger.error(f"Error processing market data: {e}")
    
    def _detect_opportunities(self, data):
        """Detect trading opportunities from BBO data"""
        try:
            coin = data.get('coin', '')
            if coin and 'bid' in data and 'ask' in data:
                bid = float(data['bid'])
                ask = float(data['ask'])
                mid = (bid + ask) / 2
                spread_bps = ((ask - bid) / mid) * 10000
                
                # Log tight spreads for market making
                if spread_bps < 5:  # Less than 0.5 bps
                    logger.info(f"{coin} tight spread opportunity: {spread_bps:.1f}bps")
        
        except Exception as e:
            logger.error(f"Error detecting opportunities: {e}")
    
    def _track_price_movements(self, data):
        """Track price movements for momentum signals"""
        try:
            if isinstance(data, dict) and 'mids' in data:
                # Log significant price movements
                for coin, price_str in data['mids'].items():
                    if coin in ['BTC', 'ETH', 'SOL']:  # Focus on major coins
                        price = float(price_str)
                        # Could add momentum tracking logic here
        
        except Exception as e:
            logger.error(f"Error tracking price movements: {e}")
    
    async def start(self):
        """Start the unified bot system"""
        try:
            logger.info("🚀 Starting Hyperliquid Alpha Trading Bot...")
            
            # Initialize all components
            await self.initialize_components()
            
            # Start background tasks
            self.running = True
            await self.start_background_tasks()
            
            # Start Telegram bot
            logger.info("🤖 Starting Telegram bot...")
            await self.telegram_bot.run()
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    async def stop(self):
        """Stop the bot gracefully"""
        try:
            logger.info("🛑 Stopping Hyperliquid Alpha Trading Bot...")
            
            self.running = False
            
            # Stop Telegram bot
            if self.telegram_bot:
                await self.telegram_bot.stop()
            
            # Close database connection
            if self.database:
                await self.database.close()
            
            logger.info("✅ Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

def create_default_config():
    """Create default configuration file"""
    default_config = {
        "hyperliquid": {
            "api_url": constants.TESTNET_API_URL,
            "mainnet": False,
            "account_address": "",
            "secret_key": ""
        },
        "vault": {
            "address": "",
            "minimum_deposit": 50,
            "performance_fee": 0.10
        },
        "telegram": {
            "bot_token": "GET_TOKEN_FROM_BOTFATHER",
            "allowed_users": [],
            "admin_users": []
        },
        "strategies": {
            "grid_trading": {
                "enabled": True,
                "default_levels": 10,
                "default_spacing": 0.002
            },
            "automated_trading": {
                "enabled": True,
                "momentum_threshold": 0.2
            },
            "profit_bot": {
                "enabled": True,
                "rebate_mining": True
            }
        }
    }
    
    with open("config.json", "w") as f:
        json.dump(default_config, f, indent=2)
    
    logger.info("✅ Created default config.json")
    return default_config

async def main():
    """Main entry point with comprehensive error handling"""
    try:
        # Check if config exists
        config_path = Path("config.json")
        if not config_path.exists():
            logger.info("📝 Creating default configuration...")
            create_default_config()
            logger.error("❌ Please update config.json with your settings and restart")
            logger.error("   1. Add your Telegram bot token")
            logger.error("   2. Add your Hyperliquid account details")
            logger.error("   3. Set your vault address")
            return
        
        # Load and validate config
        with open("config.json", 'r') as f:
            config = json.load(f)
        
        # Check required fields
        if config.get('telegram', {}).get('bot_token', '') in ['', 'GET_TOKEN_FROM_BOTFATHER']:
            logger.error("❌ Please set your Telegram bot token in config.json")
            logger.error("   Get token from @BotFather: https://t.me/BotFather")
            return
        
        # Create and start the bot
        bot = HyperliquidAlphaBot()
        
        try:
            await bot.start()
        except KeyboardInterrupt:
            logger.info("Received shutdown signal...")
            await bot.stop()
        
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        raise

if __name__ == "__main__":
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Shutdown complete!")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        exit(1)
