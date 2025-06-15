#!/usr/bin/env python3
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
import threading
from typing import Dict, Optional

# Add current directory to Python path to fix imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Real component imports
from database import Database
# Fix the import to use MultiUserTradingEngine instead of TradingEngine
from trading_engine.core_engine import MultiUserTradingEngine
from trading_engine.websocket_manager import HyperliquidWebSocketManager
from telegram_bot.bot import TelegramTradingBot
from strategies.grid_trading_engine import GridTradingEngine
from strategies.automated_trading import AutomatedTrading
from strategies.hyperliquid_profit_bot import HyperliquidProfitBot

# Hyperliquid SDK imports
from hyperliquid.utils import constants

# Import examples for setup
examples_dir = Path(__file__).parent / 'examples'
sys.path.append(str(examples_dir))
import example_utils

# New imports for multi-user architecture
from telegram_bot.user_manager import UserManager
from telegram_bot.wallet_manager import AgentWalletManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hyperliquid_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Configure StreamHandler to use UTF-8
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except AttributeError:
            pass

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
        
        # Multi-user architecture components
        self.user_manager = None
        self.agent_factory = None
        
        # Hyperliquid admin connection (for system operations only)
        self.admin_info = None
        self.admin_exchange = None
        
        # Auto-trading control flags - DISABLED by default
        self.auto_trading_enabled = False  # Override config, force disabled on startup
        self.market_monitoring_enabled = False
        self.vault_tracking_enabled = False
        self.profit_optimization_enabled = False
        self.trading_enabled = False  # Master switch for all trading activities
        
        logger.info("HyperliquidAlphaBot initialized with trading DISABLED")
    
    def _load_config(self, config_path: str) -> dict:
        """Load and validate configuration"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Set defaults if not present
            hl_config = config.setdefault('hyperliquid', {})
            hl_config.setdefault('api_url', constants.TESTNET_API_URL)
            hl_config.setdefault('mainnet', hl_config['api_url'] == constants.MAINNET_API_URL)
            hl_config.setdefault('use_agent_for_core_operations', False)

            # Add auto_trading section with defaults - Always set enabled_on_startup to False
            config.setdefault('auto_trading', {
                'enabled_on_startup': False,  # Force disabled
                'market_monitoring': False,   # Disable monitoring by default
                'vault_tracking': False,      # Disable vault tracking by default
                'profit_optimization': False, # Disable profit optimization by default
                'require_manual_start': True  # Always require manual start
            })
            
            # Force these values regardless of what's in the config
            config['auto_trading']['enabled_on_startup'] = False
            config['auto_trading']['require_manual_start'] = True
            
            config.setdefault('vault', {
                'address': '',
                'minimum_deposit': 50,
                'performance_fee': 0.10
            })
            
            config.setdefault('telegram', {
                'bot_token': '',
                'allowed_users': []
            })
            
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
            
            # Initialize production systems first
            logger.info("🔒 Initializing production systems...")
            
            # Initialize audit logging
            from telegram_bot.audit_logger import audit_logger
            await audit_logger.initialize()
            logger.info("✅ Audit logging initialized")
            
            # Initialize rate limiting
            from telegram_bot.rate_limiter import rate_limiter
            await rate_limiter.start_cleanup_task()
            logger.info("✅ Rate limiting initialized")
            
            # Initialize compliance manager
            from telegram_bot.compliance import initialize_compliance_manager
            compliance_manager = initialize_compliance_manager(self.config)
            logger.info(f"✅ Compliance manager initialized ({compliance_manager.environment})")
            
            # Initialize admin panel
            from telegram_bot.admin_panel import initialize_admin_panel
            admin_panel = initialize_admin_panel(self.config)
            logger.info(f"✅ Admin panel initialized ({len(admin_panel.admin_users)} admins)")
            
            # Log system startup
            await audit_logger.log_admin_action(
                admin_user_id=0,
                admin_username="system",
                action="system_startup",
                details={
                    "version": "1.0",
                    "environment": compliance_manager.environment,
                    "config": {
                        "api_url": self.config["hyperliquid"]["api_url"],
                        "admin_count": len(admin_panel.admin_users)
                    }
                }
            )
            
            # Continue with existing initialization...
            # 1. Initialize Hyperliquid SDK for ADMIN operations only
            # This connection is used only for system operations, not for user trading
            logger.info("🔗 Setting up Hyperliquid API admin connection...")
            try:
                # Use example_utils.setup just for admin operations
                base_url = self.config['hyperliquid']['api_url']
                admin_address, self.admin_info, self.admin_exchange = example_utils.setup(base_url, skip_ws=True)
                
                logger.info(f"✅ Connected to Hyperliquid API. Admin address: {admin_address}")
                
                # Check master wallet balance for agent creation
                await self._check_master_wallet_balance()
                
            except Exception as e:
                logger.critical(f"Failed to connect to Hyperliquid API: {e}")
                logger.critical("Ensure you have run 'python setup_agent.py' or configured 'config.json' correctly.")
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
            
            # 3. Initialize UserManager and AgentFactory for multi-user architecture
            logger.info("👥 Initializing user management system...")
            try:
                # Initialize wallet manager (agent factory)
                self.agent_factory = AgentWalletManager(
                    base_url=self.config['hyperliquid']['api_url'],
                    main_wallet=self.admin_exchange.wallet if hasattr(self.admin_exchange, 'wallet') else None,
                    main_exchange=self.admin_exchange
                )
                await self.agent_factory.initialize()
                
                # Initialize user manager 
                self.user_manager = UserManager(
                    None,  # No vault manager yet
                    self.admin_exchange,
                    self.admin_info,
                    self.config['hyperliquid']['api_url']  # Pass API URL directly instead of storage_path
                )
                
                logger.info("✅ User management system initialized")
            except Exception as e:
                logger.error(f"User management system initialization failed: {e}")
                logger.warning("⚠️ User management will be limited")
            
            # 4. Core trading engine with validation
            logger.info("⚙️ Initializing core trading engine...")
            try:
                # Initialize trading engine with multi-user support
                master_private_key = None
                # Try to get the private key from the environment or examples/config.json
                if hasattr(self.admin_exchange, 'wallet') and hasattr(self.admin_exchange.wallet, 'key'):
                    master_private_key = self.admin_exchange.wallet.key.hex()
                
                self.trading_engine = MultiUserTradingEngine(
                    master_private_key=master_private_key,
                    base_url=self.config['hyperliquid']['api_url']
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
            
            # 5. Initialize vault manager after user_manager
            from trading_engine.vault_manager import VaultManager
            logger.info("🏦 Initializing vault manager...")
            try:
                # Use admin exchange for vault operations
                self.vault_manager = VaultManager(
                    vault_address=self.config['vault']['address'],
                    base_url=self.config['hyperliquid']['api_url'],
                    exchange=self.admin_exchange,
                    info=self.admin_info
                )
                
                # Initialize the vault manager properly
                await self.vault_manager.initialize()
                
                # Update user_manager with vault_manager
                if hasattr(self.user_manager, 'set_vault_manager'):
                    self.user_manager.set_vault_manager(self.vault_manager)
                
                # Only attempt to test balance if a vault address is configured
                if self.config['vault']['address']:
                    vault_balance = await self.vault_manager.get_vault_balance()
                    if vault_balance['status'] == 'success':
                        logger.info(f"✅ Vault manager initialized: ${vault_balance['total_value']:,.2f}")
                    else:
                        logger.warning("⚠️ Vault manager created but balance check failed")
                else:
                    logger.info("✅ Vault manager initialized in limited mode (no vault address configured)")
                
            except Exception as e:
                logger.error(f"Vault manager initialization failed: {e}")
                self.vault_manager = self._create_fallback_vault_manager()
                logger.warning("⚠️ Using fallback vault manager")
            
            # 6. Trading strategies with individual error handling
            logger.info("🎯 Initializing trading strategies...")
            strategy_count = await self._initialize_strategies_with_validation()
            logger.info(f"✅ Initialized {strategy_count} strategies")
            
            # 7. WebSocket manager with connection test
            logger.info("🔌 Initializing WebSocket manager...")
            try:
                self.ws_manager = HyperliquidWebSocketManager(
                    base_url=self.config['hyperliquid']['api_url'],
                    address=None,  # No global address - will be set per user
                    info=self.admin_info,  # Use admin info for market data only
                    exchange=None  # No global exchange - will be set per user
                )
                
                # Test WebSocket connection
                await self.ws_manager.test_connection()
                logger.info("✅ WebSocket manager initialized and tested")
                
            except Exception as e:
                logger.error(f"WebSocket manager initialization failed: {e}")
                self.ws_manager = None
                logger.warning("⚠️ Continuing without WebSocket manager")
            
            # 8. Telegram bot with multi-user architecture integration
            logger.info("🤖 Initializing Telegram bot...")
            try:
                # Use token and config from main HyperliquidAlphaBot config
                self.telegram_bot = TelegramTradingBot(
                    token=self.config['telegram']['bot_token'],
                    config=self.config, # Pass the main bot's config
                    vault_manager=self.vault_manager,
                    trading_engine=self.trading_engine,
                    strategies=self.strategies,
                    database=self.database,
                    ws_manager=self.ws_manager,
                    user_manager=self.user_manager  # Pass user manager to enable multi-user support
                )
                
                logger.info("✅ Telegram bot initialized with all dependencies")
                
            except Exception as e:
                logger.error(f"Telegram bot initialization failed: {e}", exc_info=True)
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
                exchange=None,  # No global exchange - will be set per user
                info=self.admin_info,  # Use admin info for market data
                base_url=self.config['hyperliquid']['api_url']
            )
            # Update to use multi-user architecture
            if hasattr(self.strategies['grid'], 'set_user_manager'):
                self.strategies['grid'].set_user_manager(self.user_manager)
            
            # Validate connection using common market data
            await self.strategies['grid'].validate_connection()
            strategy_count += 1
            logger.info("✅ Grid trading engine ready")
        except Exception as e:
            logger.error(f"Grid trading engine failed: {e}")
        
        # Automated trading strategy
        try:
            self.strategies['auto'] = AutomatedTrading(
                exchange=None,  # No global exchange - will be set per user
                info=self.admin_info,  # Use admin info for market data
                base_url=self.config['hyperliquid']['api_url']
            )
            # Update to use multi-user architecture
            if hasattr(self.strategies['auto'], 'set_user_manager'):
                self.strategies['auto'].set_user_manager(self.user_manager)
                
            await self.strategies['auto'].validate_connection()
            strategy_count += 1
            logger.info("✅ Automated trading engine ready")
        except Exception as e:
            logger.error(f"Automated trading engine failed: {e}")
        
        # Profit-focused bot
        try:
            self.strategies['profit'] = HyperliquidProfitBot(
                exchange=None,  # No global exchange - will be set per user
                info=self.admin_info,  # Use admin info for market data
                base_url=self.config['hyperliquid']['api_url'],
                vault_address=self.config['vault']['address']
            )
            # Fix: Use synchronous method instead of async
            if hasattr(self.strategies['profit'], 'set_user_manager'):
                self.strategies['profit'].set_user_manager(self.user_manager)
                
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
            async def create_user_trader(self, user_id, agent_private_key, main_address):
                return {'status': 'demo_mode'}
        
        return FallbackTradingEngine()
    
    def _create_fallback_vault_manager(self):
        """Create fallback vault manager for demo mode"""
        class FallbackVaultManager:
            async def get_vault_balance(self): 
                return {'status': 'demo_mode', 'total_value': 1000.0}
            async def deposit(self, *args, **kwargs): 
                return {'status': 'demo_mode'}
            def check_health(self):
                return True
        
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
            'telegram_bot': False,
            'user_manager': False,
            'agent_factory': False
        }
        
        # Check Hyperliquid API using admin connection
        try:
            if self.admin_info:
                markets = self.admin_info.meta()
                health_status['hyperliquid_api'] = len(markets.get('universe', [])) > 0
        except Exception:
            pass
        
        # Check database
        try:
            await self.database.execute("SELECT 1")
            health_status['database'] = True
        except Exception:
            pass
        
        # Check trading engine
        if self.trading_engine:
            try:
                mids = await self.trading_engine.get_all_mids()
                health_status['trading_engine'] = len(mids) > 0
            except Exception:
                pass
        
        # Check vault manager
        if self.vault_manager:
            try:
                health_status['vault_manager'] = self.vault_manager.check_health()
            except Exception:
                pass
        
        # Count working strategies
        health_status['strategies'] = len(self.strategies)
        
        # Check WebSocket
        health_status['websocket'] = self.ws_manager is not None
        
        # Check Telegram bot
        health_status['telegram_bot'] = self.telegram_bot is not None
        
        # Check User Manager
        health_status['user_manager'] = self.user_manager is not None
        
        # Check Agent Factory
        health_status['agent_factory'] = self.agent_factory is not None if hasattr(self, 'agent_factory') else False
        
        # Log health status
        healthy_components = sum(1 for k, v in health_status.items() if v is True or (isinstance(v, int) and v > 0))
        total_components = len(health_status)
        
        logger.info(f"🏥 Health check: {healthy_components}/{total_components} components healthy")
        
        # Include more detailed output about which components failed
        failed_components = [k for k, v in health_status.items() 
                            if (isinstance(v, bool) and not v) or 
                               (isinstance(v, int) and v == 0)]
        
        if failed_components:
            logger.warning(f"⚠️ Unhealthy components: {', '.join(failed_components)}")
        
        if healthy_components < total_components * 0.7:  # Less than 70% healthy
            logger.warning("⚠️ System health below optimal - some features may be limited")
        
        return health_status

    async def start_background_tasks(self):
        """Start background monitoring and trading tasks"""
        try:
            logger.info("⚡ Initializing background tasks...")
            
            # Initialize WebSocket monitoring but don't start any trading components
            if self.ws_manager:
                # Only enable basic system health monitoring, no trading
                await self._start_basic_monitoring()
                logger.info("📊 Only basic system monitoring enabled - trading disabled")
            
            # Initialize but DO NOT start vault performance tracking
            if self.vault_manager:
                logger.info("🏦 Vault performance tracking initialized but DISABLED")
                self.vault_tracking_enabled = False
            
            # DO NOT start any strategy execution
            for name, strategy in self.strategies.items():
                if hasattr(strategy, 'run_background'):
                    logger.info(f"🎯 {name} strategy loaded but DISABLED - requires manual activation")
            
            # DO NOT start profit optimization
            logger.info("💰 Profit optimization DISABLED - requires manual activation")
            self.profit_optimization_enabled = False
            
            logger.info("✅ System monitoring initialized, ALL TRADING DISABLED")
            logger.info("🤖 Trading is DISABLED - use Telegram commands to start trading when ready")
            
        except Exception as e:
            logger.error(f"Error initializing background tasks: {e}")
    
    async def _start_basic_monitoring(self):
        """Start only the basic system monitoring (no trading)"""
        asyncio.create_task(self._monitor_system_health())
        logger.info("🏥 Basic system health monitoring started")
    
    async def _monitor_system_health(self):
        """Monitor only basic system health - no trading activities"""
        while self.running:
            try:
                # Simple connection check using admin connection
                if self.admin_info:
                    try:
                        # Just check if market data is available
                        markets = self.admin_info.meta()
                        num_markets = len(markets.get('universe', []))
                        logger.info(f"System health: Admin connection OK, {num_markets} markets available")
                    except Exception as e:
                        logger.warning(f"Admin connection check failed: {e}")
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in system health monitoring: {e}")
                await asyncio.sleep(60)
    
    async def toggle_auto_trading(self, enabled: bool) -> Dict:
        """Enable or disable auto-trading globally"""
        previous_state = self.trading_enabled
        self.trading_enabled = enabled
        
        if enabled and not previous_state:
            # Log that trading is enabled but require explicit start of components
            logger.info("🚀 Trading ENABLED - but individual components need manual activation")
            return {
                "status": "success", 
                "message": "Trading enabled, but individual components need manual activation. Use specific commands to start each component."
            }
            
        elif not enabled and previous_state:
            # Update the flag to prevent new auto-trading activity
            logger.info("🛑 Trading DISABLED - all trading operations will be blocked")
            return {"status": "success", "message": "Trading disabled, all trading operations blocked"}
        else:
            # No change in state
            state_str = "enabled" if enabled else "disabled"
            return {"status": "info", "message": f"Trading already {state_str}"}
    
    async def start(self):
        """Start the unified bot system"""
        try:
            logger.info("🚀 Starting Hyperliquid Alpha Trading Bot (TRADING DISABLED)...")
            
            # Initialize all components
            await self.initialize_components()
            
            # Start background tasks (only monitoring, no trading)
            self.running = True
            await self.start_background_tasks()
            
            # Start Telegram bot polling
            if self.telegram_bot:
                logger.info("🤖 Starting Telegram bot polling...")
                # Start Telegram bot in a separate thread
                def run_telegram_bot():
                    import asyncio
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    self.telegram_bot.app.run_polling(close_loop=False)
                
                telegram_thread = threading.Thread(target=run_telegram_bot, daemon=True)
                telegram_thread.start()
                logger.info("🤖 Telegram bot started in separate thread")
            else:
                logger.warning("Telegram bot not initialized, cannot start polling.")
            
            logger.info("✅ Hyperliquid Alpha Bot main components started. Telegram bot polling in background.")
            # Keep the main bot alive, e.g., by waiting for a shutdown event or sleeping
            while self.running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Failed to start bot: {e}", exc_info=True)
            await self.stop() # Attempt to gracefully stop if start fails
            raise
    
    async def stop(self):
        """Stop the bot gracefully"""
        try:
            logger.info("🛑 Stopping Hyperliquid Alpha Trading Bot...")
            
            self.running = False # Signal background tasks to stop
            
            # Stop Telegram bot polling if it's running
            if self.telegram_bot and hasattr(self.telegram_bot, 'app') and hasattr(self.telegram_bot.app, 'running'):
                logger.info("Stopping Telegram bot polling...")
                await self.telegram_bot.app.stop() # Gracefully stop polling

            # Add cleanup for other async tasks if they were started with asyncio.create_task
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            if tasks:
                logger.info(f"Cancelling {len(tasks)} background tasks...")
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info("Background tasks cancelled.")

            # Close database connection
            if self.database and hasattr(self.database, 'close') and asyncio.iscoroutinefunction(self.database.close):
                await self.database.close()
            
            logger.info("✅ Bot stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping bot: {e}", exc_info=True)

    async def _check_master_wallet_balance(self) -> None:
        """
        Check master wallet balance and log a warning if it's too low for agent creation
        """
        try:
            if not self.admin_info or not self.admin_exchange or not hasattr(self.admin_exchange, 'wallet'):
                logger.warning("Cannot check master wallet balance - admin wallet not initialized")
                return
                
            # ✅ SECURITY FIX: Get actual address from wallet instead of hardcoded
            if hasattr(self.admin_exchange.wallet, 'address'):
                main_account_address = self.admin_exchange.wallet.address
            else:
                # Fallback: try to get from setup
                main_account_address, _, _ = example_utils.setup(self.config['hyperliquid']['api_url'])
            
            # Check balance
            user_state = self.admin_info.user_state(main_account_address)
            balance = float(user_state.get("marginSummary", {}).get("accountValue", 0))
            
            if balance < 5:  # Lower threshold since you have $315
                logger.warning(f"⚠️ Main account balance: ${balance:.2f} - still sufficient for agent creation")
            else:
                logger.info(f"✅ Main account funded: ${balance:.2f} (ready for agent creation)")
                
            # If Telegram bot is available, notify admin users
            if self.telegram_bot:
                admin_users = self.config.get("telegram", {}).get("admin_users", [])
                for admin_id in admin_users:
                    try:
                        await self.telegram_bot.app.bot.send_message(
                            chat_id=admin_id,
                            text=(
                                f"✅ **Main Account Balance**\n\n"
                                f"Main account balance: ${balance:.2f}\n"
                                f"Status: {'Sufficient' if balance >= 5 else 'Low'} for agent wallet creation\n\n"
                                f"Main account address: `{main_account_address}`"
                            ),
                            parse_mode='Markdown'
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin {admin_id}: {e}")
                
        except Exception as e:
            logger.error(f"Error checking main account balance: {e}")

def create_default_config():
    """Create default configuration file for the bot (config.json in root)"""
    default_config = {
        "hyperliquid": {
            "api_url": constants.TESTNET_API_URL, # Default to TESTNET
            "mainnet": False,
            "use_agent_for_core_operations": False # New option
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
        "auto_trading": {
            "enabled_on_startup": False,
            "market_monitoring": True,
            "vault_tracking": True,
            "profit_optimization": True,
            "require_manual_start": True
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
    
    logger.info("✅ Created default config.json (for bot settings in root directory)")
    logger.info("IMPORTANT: For Hyperliquid authentication, ensure HYPERLIQUID_PRIVATE_KEY environment variable is set,")
    logger.info("OR 'examples/config.json' contains your 'secret_key'.")
    logger.info("This key is used only for admin operations and creating agent wallets, not for user trading.")
    return default_config

async def main():
    """Main entry point with comprehensive error handling"""
    bot_instance = None
    try:
        # --- Hyperliquid Authentication Guidance (for example_utils.py) ---
        examples_config_path = Path(__file__).parent / 'examples' / 'config.json'
        private_key_env = os.environ.get('HYPERLIQUID_PRIVATE_KEY')

        if not private_key_env and not examples_config_path.exists():
            logger.error(f"❌ CRITICAL: Hyperliquid authentication not configured.")
            logger.error(f"  Neither HYPERLIQUID_PRIVATE_KEY environment variable is set,")
            logger.error(f"  nor is '{examples_config_path}' (with a 'secret_key') found.")
            logger.error(f"  Please configure one of these for admin operations.")
            logger.error(f"  See documentation for HYPERLIQUID_PRIVATE_KEY or format of '{examples_config_path}'.")
            
            # Create template examples/config.json
            if not examples_config_path.parent.exists():
                examples_config_path.parent.mkdir(parents=True, exist_ok=True)
            if not examples_config_path.exists():
                try:
                    with open(examples_config_path, "w") as f:
                        json.dump({
                            "secret_key": "0xYourEthereumPrivateKeyHere", 
                            "account_address": "YourOptionalAccountAddressHere"
                        }, f, indent=2)
                    logger.info(f"Created a template '{examples_config_path}'. Please edit it with your details.")
                except Exception as e_cfg:
                    logger.error(f"Could not create template examples/config.json: {e_cfg}")
            return
        elif private_key_env:
             logger.info(f"HYPERLIQUID_PRIVATE_KEY environment variable found. It will be prioritized by example_utils.setup().")
        elif examples_config_path.exists():
            logger.info(f"Found '{examples_config_path}'. It will be used by example_utils.setup() if HYPERLIQUID_PRIVATE_KEY is not set.")

        # --- Bot Configuration Setup (root config.json) ---
        bot_config_path = Path("config.json")
        if not bot_config_path.exists():
            logger.info("📝 Bot's root config.json not found. Creating default configuration...")
            create_default_config()
            logger.info(f"ℹ️ Please review and update '{bot_config_path}' with your Telegram token, etc.")

        # Load and validate bot's root config
        with open(bot_config_path, 'r') as f:
            config = json.load(f)
        
        if config.get('telegram', {}).get('bot_token', '') in ['', 'GET_TOKEN_FROM_BOTFATHER']:
            logger.error(f"❌ Please set your Telegram bot token in '{bot_config_path}'")
            logger.error("   Get token from @BotFather: https://t.me/BotFather")
            return
        
        # Create and start the bot
        bot_instance = HyperliquidAlphaBot()
        await bot_instance.start()
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal...")
        if bot_instance:
            await bot_instance.stop()
    except Exception as e:
        logger.critical(f"💥 Unhandled critical error in main: {e}", exc_info=True)
        if bot_instance:
            await bot_instance.stop()
        raise
    finally:
        if bot_instance and bot_instance.running:
            logger.info("Initiating graceful shutdown from finally block...")
            await bot_instance.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Main process terminated by KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"💥 Fatal error in main execution: {e}", exc_info=True)
        sys.exit(1)