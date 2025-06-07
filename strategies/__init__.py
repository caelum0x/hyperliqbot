"""
Trading strategies module
Exports all available strategies for easy import
"""

# Core strategy classes
try:
    from .hyperliquid_profit_bot import HyperliquidProfitBot, BotReferralSystem, RevenueCalculator
except ImportError:
    HyperliquidProfitBot = None

try:
    from .automated_trading import AutomatedTradingEngine
except ImportError:
    AutomatedTradingEngine = None

try:
    from .grid_trading_engine import GridTradingEngine
except ImportError:
    GridTradingEngine = None

try:
    from .hyperevm_ecosystem import HyperEVMEcosystem
except ImportError:
    HyperEVMEcosystem = None

try:
    from .hyperevm_network import HyperEVMConnector, HyperEVMMonitor
except ImportError:
    HyperEVMConnector = None
    HyperEVMMonitor = None

try:
    from .seedify_imc import SeedifyIMCManager
except ImportError:
    SeedifyIMCManager = None

# Export available strategies
__all__ = [
    'HyperliquidProfitBot',
    'BotReferralSystem', 
    'RevenueCalculator',
    'AutomatedTradingEngine',
    'GridTradingEngine',
    'HyperEVMEcosystem',
    'HyperEVMConnector',
    'HyperEVMMonitor',
    'SeedifyIMCManager'
]

# Strategy registry for dynamic loading
AVAILABLE_STRATEGIES = {}

if HyperliquidProfitBot:
    AVAILABLE_STRATEGIES['profit_bot'] = HyperliquidProfitBot
if AutomatedTradingEngine:
    AVAILABLE_STRATEGIES['automated_trading'] = AutomatedTradingEngine
if GridTradingEngine:
    AVAILABLE_STRATEGIES['grid_trading'] = GridTradingEngine
if HyperEVMEcosystem:
    AVAILABLE_STRATEGIES['hyperevm'] = HyperEVMEcosystem
