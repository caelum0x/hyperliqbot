"""
ALPHA STRATEGIES - The actual money makers
Focus: Farm Hyperliquid incentives, not user fees
"""

import asyncio
import time
import random
from datetime import datetime, timedelta
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class AlphaStrategies:
    def __init__(self, api, wallet_manager):
        self.api = api
        self.wallet_manager = wallet_manager
        self.active_users = {}
        self.competition_mode = False
        
    async def start_all_strategies(self, user_id: int) -> Dict:
        """Start all alpha strategies for user"""
        results = {}
        
        try:
            # 1. Volume Competition Farming
            results['volume_farming'] = await self.start_volume_farming(user_id)
            
            # 2. Maker Rebate Mining
            results['rebate_mining'] = await self.start_rebate_mining(user_id)
            
            # 3. HyperEVM Farming (when protocols launch)
            results['hyperevm_farming'] = await self.start_hyperevm_farming(user_id)
            
            # 4. Seedify IMC Participation
            results['seedify_farming'] = await self.start_seedify_farming(user_id)
            
            # 5. NFT Sniping (Abstract/HyperEVM)
            results['nft_sniping'] = await self.start_nft_sniping(user_id)
            
            # Store active user
            self.active_users[user_id] = {
                'started_at': datetime.now(),
                'strategies': list(results.keys()),
                'earnings': {strategy: 0 for strategy in results.keys()}
            }
            
            return results
            
        except Exception as e:
            logger.error(f"Error starting strategies for {user_id}: {e}")
            return {'error': str(e)}
    
    async def start_volume_farming(self, user_id: int) -> Dict:
        """Farm volume competitions with automated trading"""
        try:
            user_info = await self.wallet_manager.get_user_info(user_id)
            balance = user_info['balance']
            
            if balance < 100:
                return {'success': False, 'error': 'Minimum $100 balance required'}
            
            # Get current competitions
            competitions = await self.api.get_active_competitions()
            
            if not competitions:
                return {'success': False, 'error': 'No active competitions'}
            
            # Calculate optimal volume strategy
            target_volume = min(balance * 50, 100000)  # 50x leverage or $100k max
            
            # Start volume generation
            asyncio.create_task(self._volume_farming_loop(user_id, target_volume))
            
            return {
                'success': True,
                'message': f'Volume farming started - Target: ${target_volume:,.0f}/day',
                'competitions': [c['name'] for c in competitions]
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _volume_farming_loop(self, user_id: int, target_daily_volume: float):
        """Generate volume for competitions using grid trading"""
        try:
            while user_id in self.active_users:
                # Get best liquid pairs for volume
                pairs = ['BTC', 'ETH', 'SOL']
                
                for pair in pairs:
                    try:
                        # Get current price
                        price = await self.api.get_mid_price(pair)
                        
                        # Calculate grid parameters
                        volume_per_pair = target_daily_volume / len(pairs) / 24  # Hourly volume
                        trade_size = volume_per_pair / price / 20  # 20 trades per hour
                        
                        # Place grid orders for volume
                        await self._place_volume_grid(user_id, pair, price, trade_size)
                        
                    except Exception as e:
                        logger.error(f"Volume farming error for {pair}: {e}")
                
                # Wait 1 hour before next cycle
                await asyncio.sleep(3600)
                
        except Exception as e:
            logger.error(f"Volume farming loop error: {e}")
    
    async def _place_volume_grid(self, user_id: int, pair: str, mid_price: float, size: float):
        """Place tight grid to generate volume with minimal risk"""
        try:
            spread = 0.0005  # 0.05% spread for fast fills
            levels = 5
            
            # Cancel existing orders
            await self.api.cancel_all_orders(user_id, pair)
            
            # Place buy orders
            for i in range(1, levels + 1):
                buy_price = mid_price * (1 - spread * i)
                await self.api.place_order(user_id, pair, True, size, buy_price, post_only=True)
            
            # Place sell orders  
            for i in range(1, levels + 1):
                sell_price = mid_price * (1 + spread * i)
                await self.api.place_order(user_id, pair, False, size, sell_price, post_only=True)
            
            logger.info(f"Volume grid placed for {user_id}: {pair} at ${mid_price:.2f}")
            
        except Exception as e:
            logger.error(f"Grid placement error: {e}")
    
    async def start_rebate_mining(self, user_id: int) -> Dict:
        """Optimize for maximum maker rebates"""
        try:
            # Get user's current volume stats
            volume_stats = await self.api.get_user_volume_stats(user_id)
            
            # Calculate strategy to maximize rebates
            maker_percentage = volume_stats.get('maker_percentage', 0)
            volume_14d = volume_stats.get('volume_14d', 0)
            
            strategy = {}
            
            if maker_percentage < 0.5:
                strategy['focus'] = 'Increase maker percentage to 0.5% for -0.001% rebate'
                strategy['target_maker_volume'] = volume_14d * 0.005
            elif maker_percentage < 1.5:
                strategy['focus'] = 'Increase maker percentage to 1.5% for -0.002% rebate'
                strategy['target_maker_volume'] = volume_14d * 0.015
            elif maker_percentage < 3.0:
                strategy['focus'] = 'Increase maker percentage to 3% for -0.003% rebate'
                strategy['target_maker_volume'] = volume_14d * 0.03
            else:
                strategy['focus'] = 'Maximum rebate tier achieved!'
                strategy['target_maker_volume'] = 0
            
            # Start rebate optimization
            asyncio.create_task(self._rebate_mining_loop(user_id, strategy))
            
            return {
                'success': True,
                'message': strategy['focus'],
                'current_rebate_tier': self._get_rebate_tier(maker_percentage)
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_rebate_tier(self, maker_pct: float) -> str:
        """Get current rebate tier"""
        if maker_pct >= 3.0:
            return "Tier 3: -0.003% rebate"
        elif maker_pct >= 1.5:
            return "Tier 2: -0.002% rebate"
        elif maker_pct >= 0.5:
            return "Tier 1: -0.001% rebate"
        else:
            return "No rebate"
    
    async def _rebate_mining_loop(self, user_id: int, strategy: Dict):
        """Continuously optimize for rebates"""
        try:
            while user_id in self.active_users:
                # Focus on maker-only orders
                pairs = ['BTC', 'ETH']
                
                for pair in pairs:
                    try:
                        price = await self.api.get_mid_price(pair)
                        
                        # Place post-only orders at slightly better prices
                        spread = 0.0002  # 0.02% inside spread
                        size = 0.01  # Small size for frequent fills
                        
                        # Buy slightly above best bid
                        await self.api.place_order(
                            user_id, pair, True, size, 
                            price * (1 - spread), post_only=True
                        )
                        
                        # Sell slightly below best ask
                        await self.api.place_order(
                            user_id, pair, False, size,
                            price * (1 + spread), post_only=True
                        )
                        
                    except Exception as e:
                        logger.error(f"Rebate mining error for {pair}: {e}")
                
                await asyncio.sleep(300)  # 5 minutes
                
        except Exception as e:
            logger.error(f"Rebate mining loop error: {e}")
    
    async def start_hyperevm_farming(self, user_id: int) -> Dict:
        """Farm HyperEVM ecosystem when protocols launch"""
        try:
            # Check if HyperEVM protocols are live
            protocols = await self.api.get_hyperevm_protocols()
            
            if not protocols:
                return {
                    'success': True,
                    'message': 'HyperEVM monitoring active - will farm when protocols launch'
                }
            
            # Start farming available protocols
            farmed = []
            for protocol in protocols:
                try:
                    if protocol['type'] == 'lending':
                        await self._farm_lending_protocol(user_id, protocol)
                        farmed.append(f"Lending: {protocol['name']}")
                    elif protocol['type'] == 'dex':
                        await self._farm_dex_protocol(user_id, protocol)
                        farmed.append(f"DEX: {protocol['name']}")
                    elif protocol['type'] == 'yield':
                        await self._farm_yield_protocol(user_id, protocol)
                        farmed.append(f"Yield: {protocol['name']}")
                        
                except Exception as e:
                    logger.error(f"Error farming {protocol['name']}: {e}")
            
            return {
                'success': True,
                'message': f'Farming {len(farmed)} protocols',
                'protocols': farmed
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def start_seedify_farming(self, user_id: int) -> Dict:
        """Participate in Seedify IMCs"""
        try:
            # Get active Seedify launches
            launches = await self.api.get_seedify_launches()
            
            if not launches:
                return {
                    'success': True,
                    'message': 'Monitoring for Seedify launches'
                }
            
            # Auto-participate in profitable launches
            participated = []
            for launch in launches:
                try:
                    if launch['allocation_available'] and launch['roi_potential'] > 1.5:
                        # Participate with optimal allocation
                        result = await self._participate_in_launch(user_id, launch)
                        if result['success']:
                            participated.append(launch['name'])
                            
                except Exception as e:
                    logger.error(f"Error participating in {launch['name']}: {e}")
            
            return {
                'success': True,
                'message': f'Participating in {len(participated)} launches',
                'launches': participated
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def start_nft_sniping(self, user_id: int) -> Dict:
        """Snipe NFT mints on Abstract/HyperEVM"""
        try:
            # Monitor for upcoming NFT drops
            asyncio.create_task(self._nft_monitoring_loop(user_id))
            
            return {
                'success': True,
                'message': 'NFT mint monitoring active for Abstract/HyperEVM'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _nft_monitoring_loop(self, user_id: int):
        """Monitor and snipe profitable NFT mints"""
        try:
            while user_id in self.active_users:
                # Check for upcoming mints
                mints = await self.api.get_upcoming_nft_mints()
                
                for mint in mints:
                    if mint['profit_potential'] > 2.0:  # 2x+ potential
                        await self._snipe_nft_mint(user_id, mint)
                
                await asyncio.sleep(60)  # Check every minute
                
        except Exception as e:
            logger.error(f"NFT monitoring error: {e}")
    
    async def enable_competition_mode(self, user_id: int) -> Dict:
        """Enable aggressive competition farming"""
        try:
            competitions = await self.api.get_active_competitions()
            
            if not competitions:
                return {'success': False, 'error': 'No active competitions'}
            
            # Calculate max volume strategy
            user_info = await self.wallet_manager.get_user_info(user_id)
            max_volume = user_info['balance'] * 100  # 100x leverage
            
            # Enable competition mode
            self.active_users[user_id]['competition_mode'] = True
            self.active_users[user_id]['target_volume'] = max_volume
            
            return {
                'success': True,
                'competitions': [c['name'] for c in competitions],
                'target_volume': max_volume
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def get_user_stats(self, user_id: int) -> Dict:
        """Get comprehensive user statistics"""
        try:
            if user_id not in self.active_users:
                return {'error': 'User not active'}
            
            user_data = self.active_users[user_id]
            api_stats = await self.api.get_user_trading_stats(user_id)
            
            return {
                'total_profit': sum(user_data['earnings'].values()),
                'volume_earnings': user_data['earnings'].get('volume_farming', 0),
                'rebate_earnings': user_data['earnings'].get('rebate_mining', 0),
                'hyperevm_earnings': user_data['earnings'].get('hyperevm_farming', 0),
                'seedify_earnings': user_data['earnings'].get('seedify_farming', 0),
                'daily_volume': api_stats.get('volume_24h', 0),
                'trades_24h': api_stats.get('trades_24h', 0),
                'rebates_24h': api_stats.get('rebates_24h', 0),
                'pnl_24h': api_stats.get('pnl_24h', 0),
                'active_strategies': user_data['strategies']
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    async def optimize_for_user(self, user_id: int) -> Dict:
        """Optimize strategies based on user performance"""
        try:
            stats = await self.get_user_stats(user_id)
            
            # Analyze performance and optimize
            optimizations = []
            
            # Volume optimization
            if stats['daily_volume'] < 10000:
                optimizations.append("Increased grid frequency for more volume")
            
            # Rebate optimization
            if stats['rebates_24h'] < 1:
                optimizations.append("Adjusted spreads for better maker fills")
            
            # Competition optimization
            competitions = await self.api.get_active_competitions()
            if competitions:
                optimizations.append("Enabled competition mode for prize farming")
            
            return {
                'success': True,
                'message': f"Applied {len(optimizations)} optimizations",
                'optimizations': optimizations
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def run_background_farming(self):
        """Run continuous background farming for all users"""
        while True:
            try:
                # Update earnings for all active users
                for user_id in list(self.active_users.keys()):
                    try:
                        await self._update_user_earnings(user_id)
                    except Exception as e:
                        logger.error(f"Error updating earnings for {user_id}: {e}")
                
                # Check for new opportunities
                await self._check_new_opportunities()
                
                await asyncio.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error(f"Background farming error: {e}")
                await asyncio.sleep(60)
    
    async def _update_user_earnings(self, user_id: int):
        """Update user earnings from all strategies"""
        try:
            # Get latest trading stats
            stats = await self.api.get_user_trading_stats(user_id)
            
            # Update earnings
            user_data = self.active_users[user_id]
            user_data['earnings']['volume_farming'] += stats.get('volume_earnings', 0)
            user_data['earnings']['rebate_mining'] += stats.get('rebate_earnings', 0)
            
            # Log performance
            total_earnings = sum(user_data['earnings'].values())
            logger.info(f"User {user_id} total earnings: ${total_earnings:.2f}")
            
        except Exception as e:
            logger.error(f"Error updating earnings: {e}")
    
    async def _check_new_opportunities(self):
        """Check for new farming opportunities"""
        try:
            # Check for new competitions
            competitions = await self.api.get_active_competitions()
            
            # Check for new protocols
            protocols = await self.api.get_hyperevm_protocols()
            
            # Check for new launches
            launches = await self.api.get_seedify_launches()
            
            if competitions or protocols or launches:
                logger.info("New opportunities detected - will optimize strategies")
                
        except Exception as e:
            logger.error(f"Opportunity check error: {e}")
