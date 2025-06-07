"""
Strategy Manager for Hyperliquid Trading Bot
Orchestrates all trading strategies and manages their execution
"""

from typing import Dict, List, Optional
import asyncio
import logging
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import bot_db

logger = logging.getLogger(__name__)

class StrategyManager:
    """
    Central manager for all trading strategies
    Handles strategy lifecycle, monitoring, and coordination
    """
    
    def __init__(self, trading_engine, config):
        self.trading_engine = trading_engine
        self.config = config
        self.strategies = {}
        self.active = {}
        self.performance_tracker = {}
        self.running = False
        
        logger.info("Initializing StrategyManager")
        self._load_strategies()
        
    def _load_strategies(self):
        """Load enabled strategies based on configuration"""
        try:
            # Import strategies
            from strategies.grid_trading_engine import GridTradingEngine
            from strategies.automated_trading import AutomatedTrading
            from strategies.seedify_imc import SeedifyIMCManager
         
            
            # Load grid trading strategy
            if self.config.get('strategies', {}).get('grid_trading', {}).get('enabled', False):
                self.strategies['grid'] = GridTradingEngine(
                    self.trading_engine.exchange,
                    self.trading_engine.info
                )
                logger.info("Grid trading strategy loaded")
            
            # Load automated trading
            if self.config.get('strategies', {}).get('automated_trading', {}).get('enabled', True):
                self.strategies['auto'] = AutomatedTrading(
                    self.trading_engine.exchange,
                    self.trading_engine.info
                )
                logger.info("Automated trading strategy loaded")
            
            # Load IMC strategies
            if self.config.get('strategies', {}).get('imc', {}).get('enabled', False):
                self.strategies['imc'] = SeedifyIMCManager(
                    self.trading_engine.exchange,
                    self.trading_engine.info,
                    self.config
                )
                logger.info("IMC strategy loaded")
            
            # Load NFT hunter (always available for alpha)
         
            
        except Exception as e:
            logger.error(f"Error loading strategies: {e}")
            # Ensure we have at least basic automated trading
            try:
                from strategies.automated_trading import AutomatedTrading
                self.strategies['auto'] = AutomatedTrading(
                    self.trading_engine.exchange,
                    self.trading_engine.info
                )
                logger.info("Fallback: Basic automated trading loaded")
            except Exception as fallback_error:
                logger.error(f"Failed to load fallback strategy: {fallback_error}")
    
    async def start_strategy(self, strategy_name: str, params: Dict = None) -> Dict:
        """Start a specific strategy with given parameters"""
        try:
            if strategy_name not in self.strategies:
                return {
                    'success': False, 
                    'error': f'Strategy "{strategy_name}" not found. Available: {list(self.strategies.keys())}'
                }
            
            if params is None:
                params = {}
            
            strategy = self.strategies[strategy_name]
            
            # Generate unique strategy ID
            strategy_id = f"{strategy_name}_{int(datetime.now().timestamp())}"
            
            # Create strategy task based on strategy type
            if strategy_name == 'grid':
                task = asyncio.create_task(self._run_grid_strategy(strategy, params))
            elif strategy_name == 'auto':
                task = asyncio.create_task(self._run_auto_strategy(strategy, params))
            elif strategy_name == 'imc':
                task = asyncio.create_task(self._run_imc_strategy(strategy, params))
            elif strategy_name == 'nft':
                task = asyncio.create_task(self._run_nft_strategy(strategy, params))
            else:
                # Generic strategy runner
                task = asyncio.create_task(self._run_generic_strategy(strategy, params))
            
            # Store active strategy
            self.active[strategy_id] = {
                'strategy': strategy_name,
                'params': params,
                'task': task,
                'started_at': datetime.now(),
                'status': 'running'
            }
            
            # Initialize performance tracking
            self.performance_tracker[strategy_id] = {
                'trades_executed': 0,
                'total_pnl': 0.0,
                'total_fees': 0.0,
                'success_rate': 0.0,
                'last_update': datetime.now()
            }
            
            logger.info(f"Started strategy {strategy_name} with ID {strategy_id}")
            
            return {
                'success': True, 
                'strategy_id': strategy_id,
                'message': f'Strategy {strategy_name} started successfully'
            }
            
        except Exception as e:
            logger.error(f"Error starting strategy {strategy_name}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _run_grid_strategy(self, strategy, params: Dict):
        """Run grid trading strategy"""
        try:
            coin = params.get('coin', 'BTC')
            levels = params.get('levels', 10)
            spacing = params.get('spacing', 0.002)
            
            # Start grid
            result = await strategy.start_grid(coin, levels, spacing)
            if result['status'] != 'success':
                raise Exception(f"Failed to start grid: {result}")
            
            # Monitor grid performance
            while True:
                await asyncio.sleep(60)  # Check every minute
                performance = await strategy.monitor_grid_performance(coin)
                if performance['status'] == 'success':
                    logger.info(f"Grid performance: {performance['performance']}")
                
        except asyncio.CancelledError:
            # Clean shutdown
            logger.info(f"Grid strategy for {coin} cancelled")
            await strategy.stop_grid(coin)
        except Exception as e:
            logger.error(f"Grid strategy error: {e}")
            raise
    
    async def _run_auto_strategy(self, strategy, params: Dict):
        """Run automated trading strategy"""
        try:
            strategy_type = params.get('type', 'momentum')
            coin = params.get('coin', 'ETH')
            
            while True:
                if strategy_type == 'momentum':
                    result = await strategy.momentum_strategy(coin)
                elif strategy_type == 'scalping':
                    result = await strategy.scalping_strategy(coin)
                elif strategy_type == 'dca':
                    result = await strategy.dca_strategy(coin, params.get('amount', 100))
                else:
                    raise Exception(f"Unknown strategy type: {strategy_type}")
                
                logger.info(f"Auto strategy result: {result}")
                
                # Wait before next execution
                await asyncio.sleep(params.get('interval', 300))  # 5 minutes default
                
        except asyncio.CancelledError:
            logger.info(f"Auto strategy {strategy_type} cancelled")
        except Exception as e:
            logger.error(f"Auto strategy error: {e}")
            raise
    
    async def _run_imc_strategy(self, strategy, params: Dict):
        """Run IMC/vault strategy"""
        try:
            capital = params.get('capital', 1000)
            
            # Execute comprehensive IMC strategy
            result = await strategy.execute_comprehensive_strategy(capital)
            logger.info(f"IMC strategy result: {result}")
            
            # Monitor performance periodically
            while True:
                await asyncio.sleep(3600)  # Check hourly
                
                # Update vault performance
                vault_stats = await strategy.track_hlp_performance()
                logger.info(f"Vault performance: {vault_stats}")
                
        except asyncio.CancelledError:
            logger.info("IMC strategy cancelled")
        except Exception as e:
            logger.error(f"IMC strategy error: {e}")
            raise
    
    async def _run_nft_strategy(self, strategy, params: Dict):
        """Run NFT hunting strategy"""
        try:
            budget = params.get('budget', 5000)
            
            # Execute NFT hunting
            result = await strategy.execute_nft_strategy(budget)
            logger.info(f"NFT strategy result: {result}")
            
            # Monitor alpha communities
            while True:
                await asyncio.sleep(3600)  # Check hourly for new alpha
                
                alpha = await strategy.monitor_alpha_communities()
                if alpha.get('urgent_alerts'):
                    logger.info(f"NFT Alpha alerts: {alpha['urgent_alerts']}")
                
        except asyncio.CancelledError:
            logger.info("NFT strategy cancelled")
        except Exception as e:
            logger.error(f"NFT strategy error: {e}")
            raise
    
    async def _run_generic_strategy(self, strategy, params: Dict):
        """Generic strategy runner for custom strategies"""
        try:
            # Attempt to run strategy with params
            if hasattr(strategy, 'run'):
                await strategy.run(**params)
            elif hasattr(strategy, 'execute'):
                await strategy.execute(**params)
            else:
                raise Exception("Strategy has no run() or execute() method")
                
        except asyncio.CancelledError:
            logger.info("Generic strategy cancelled")
        except Exception as e:
            logger.error(f"Generic strategy error: {e}")
            raise
    
    async def stop_strategy(self, strategy_id: str) -> Dict:
        """Stop a running strategy"""
        try:
            if strategy_id not in self.active:
                return {'success': False, 'error': 'Strategy not found'}
            
            # Cancel the task
            strategy_info = self.active[strategy_id]
            strategy_info['task'].cancel()
            strategy_info['status'] = 'stopping'
            
            # Wait for cancellation
            try:
                await asyncio.wait_for(strategy_info['task'], timeout=10.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            
            # Remove from active strategies
            del self.active[strategy_id]
            
            # Archive performance data
            if strategy_id in self.performance_tracker:
                perf = self.performance_tracker[strategy_id]
                perf['stopped_at'] = datetime.now()
                # Could save to database here
                del self.performance_tracker[strategy_id]
            
            logger.info(f"Stopped strategy {strategy_id}")
            
            return {'success': True, 'message': f'Strategy {strategy_id} stopped'}
            
        except Exception as e:
            logger.error(f"Error stopping strategy {strategy_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def stop_all_strategies(self) -> Dict:
        """Stop all running strategies"""
        try:
            results = []
            
            for strategy_id in list(self.active.keys()):
                result = await self.stop_strategy(strategy_id)
                results.append({'strategy_id': strategy_id, 'result': result})
            
            return {
                'success': True,
                'stopped_count': len(results),
                'results': results
            }
            
        except Exception as e:
            logger.error(f"Error stopping all strategies: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_active_strategies(self) -> List[Dict]:
        """Get information about all active strategies"""
        try:
            active_list = []
            
            for strategy_id, info in self.active.items():
                performance = self.performance_tracker.get(strategy_id, {})
                
                active_list.append({
                    'id': strategy_id,
                    'strategy': info['strategy'],
                    'params': info['params'],
                    'started_at': info['started_at'],
                    'status': info['status'],
                    'running': not info['task'].done(),
                    'runtime_minutes': (datetime.now() - info['started_at']).total_seconds() / 60,
                    'performance': performance
                })
            
            return active_list
            
        except Exception as e:
            logger.error(f"Error getting active strategies: {e}")
            return []
    
    async def get_strategy_performance(self, strategy_id: str) -> Dict:
        """Get detailed performance metrics for a strategy"""
        try:
            if strategy_id not in self.performance_tracker:
                return {'error': 'Strategy not found or not tracked'}
            
            performance = self.performance_tracker[strategy_id].copy()
            
            # Add real-time data from exchange if available
            if hasattr(self.trading_engine, 'info'):
                user_fills = self.trading_engine.info.user_fills(self.trading_engine.exchange.account_address)
                
                # Calculate recent performance
                start_time = self.active[strategy_id]['started_at'] if strategy_id in self.active else datetime.now()
                recent_fills = [
                    fill for fill in user_fills 
                    if datetime.fromtimestamp(int(fill.get('time', 0)) / 1000) > start_time
                ]
                
                performance.update({
                    'recent_fills': len(recent_fills),
                    'recent_volume': sum(float(fill.get('sz', 0)) * float(fill.get('px', 0)) for fill in recent_fills),
                    'recent_pnl': sum(float(fill.get('closedPnl', 0)) for fill in recent_fills)
                })
            
            return performance
            
        except Exception as e:
            logger.error(f"Error getting strategy performance: {e}")
            return {'error': str(e)}
    
    async def update_performance(self, strategy_id: str, metrics: Dict):
        """Update performance metrics for a strategy"""
        try:
            if strategy_id in self.performance_tracker:
                self.performance_tracker[strategy_id].update(metrics)
                self.performance_tracker[strategy_id]['last_update'] = datetime.now()
                
                # Record trade to database
                await bot_db.record_trade(
                    metrics.get('coin', 'UNKNOWN'),
                    metrics.get('side', 'buy'),
                    metrics.get('size', 0),
                    metrics.get('price', 0),
                    metrics.get('pnl', 0),
                    metrics.get('fee', 0),
                    metrics.get('fee_type', 'taker_fee')
                )
                
        except Exception as e:
            logger.error(f"Error updating performance for {strategy_id}: {e}")
    
    async def get_strategy_summary(self) -> str:
        """Generate a comprehensive summary of all strategies"""
        try:
            active_strategies = await self.get_active_strategies()
            
            if not active_strategies:
                return "📊 No active strategies running. Use /start_strategy to begin trading!"
            
            summary = "🤖 STRATEGY MANAGER SUMMARY\n\n"
            
            for strategy in active_strategies:
                status_emoji = "🟢" if strategy['running'] else "🔴"
                summary += f"{status_emoji} {strategy['strategy'].upper()} Strategy\n"
                summary += f"  • ID: {strategy['id'][:8]}...\n"
                summary += f"  • Runtime: {strategy['runtime_minutes']:.1f} minutes\n"
                summary += f"  • Status: {strategy['status']}\n"
                
                if strategy['performance']:
                    perf = strategy['performance']
                    summary += f"  • Trades: {perf.get('trades_executed', 0)}\n"
                    summary += f"  • PnL: ${perf.get('total_pnl', 0):.2f}\n"
                    summary += f"  • Fees: ${perf.get('total_fees', 0):.2f}\n"
                
                summary += "\n"
            
            # Add available strategies
            summary += f"📋 Available Strategies: {', '.join(self.strategies.keys())}\n"
            summary += f"⚡ Total Active: {len(active_strategies)}\n"
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating strategy summary: {e}")
            return f"Error generating summary: {str(e)}"
    
    async def run(self):
        """Main strategy manager monitoring loop"""
        self.running = True
        logger.info("Strategy manager monitoring loop started")
        
        try:
            while self.running:
                # Monitor active strategies
                for strategy_id, info in list(self.active.items()):
                    if info['task'].done():
                        try:
                            # Strategy completed
                            result = info['task'].result()
                            logger.info(f"Strategy {strategy_id} completed: {result}")
                        except Exception as e:
                            logger.error(f"Strategy {strategy_id} failed: {e}")
                        
                        # Update status and clean up
                        info['status'] = 'completed'
                        del self.active[strategy_id]
                
                # Health check - restart critical strategies if needed
                await self._health_check()
                
                # Sleep before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
        except asyncio.CancelledError:
            logger.info("Strategy manager monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Strategy manager monitoring error: {e}")
        finally:
            self.running = False
    
    async def _health_check(self):
        """Perform health check on strategies and restart if needed"""
        try:
            # Check if any critical strategies need restarting
            critical_strategies = self.config.get('strategies', {}).get('critical', [])
            
            for strategy_name in critical_strategies:
                # Check if strategy is running
                is_running = any(
                    info['strategy'] == strategy_name 
                    for info in self.active.values()
                )
                
                if not is_running and strategy_name in self.strategies:
                    logger.warning(f"Critical strategy {strategy_name} not running, attempting restart")
                    
                    # Get default params for strategy
                    default_params = self.config.get('strategies', {}).get(strategy_name, {}).get('default_params', {})
                    
                    # Restart strategy
                    result = await self.start_strategy(strategy_name, default_params)
                    if result['success']:
                        logger.info(f"Successfully restarted critical strategy {strategy_name}")
                    else:
                        logger.error(f"Failed to restart critical strategy {strategy_name}: {result['error']}")
                        
        except Exception as e:
            logger.error(f"Health check error: {e}")
    
    def stop(self):
        """Stop the strategy manager"""
        self.running = False
        logger.info("Strategy manager stop requested")
    
    def get_available_strategies(self) -> Dict:
        """Get list of available strategies and their capabilities"""
        return {
            name: {
                'name': name,
                'description': strategy.__doc__ or f"{name} trading strategy",
                'loaded': True,
                'methods': [method for method in dir(strategy) if not method.startswith('_')]
            }
            for name, strategy in self.strategies.items()
        }
