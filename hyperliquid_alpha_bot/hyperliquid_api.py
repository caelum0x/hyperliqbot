"""
HYPERLIQUID API WRAPPER - All SDK interactions
Real implementation using Hyperliquid Python SDK with proper notation
"""

import json
import asyncio
import sys
import os
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import Hyperliquid SDK
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import example_utils

# Import our internal components with absolute imports
from telegram_bot.user_manager import UserSession, HyperliquidTrader
from trading_engine.core_engine import ProfitOptimizedTrader, TradingConfig
from strategies.seedify_imc import SeedifyIMCManager
from strategies.hyperevm_network import HyperEVMConnector

logger = logging.getLogger(__name__)

class HyperliquidAPI:
    def __init__(self):
        self.config = self._load_config()
        self.info = None
        self.user_exchanges = {}  # user_id -> Exchange object
        self.trading_config = TradingConfig()
        self._initialize_info()
    
    def _load_config(self) -> Dict:
        """Load configuration"""
        try:
            with open("config.json", "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def _initialize_info(self):
        """Initialize Info object for read-only operations"""
        try:
            base_url = self.config.get("base_url", constants.TESTNET_API_URL)
            self.info = Info(base_url, skip_ws=True)
            logger.info(f"Initialized Hyperliquid API: {base_url}")
        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid API: {e}")
    
    async def connect_user_wallet(self, user_id: int, private_key: str) -> Dict:
        """Connect user's wallet using real SDK and create integrated session"""
        try:
            # Setup using SDK's example_utils
            base_url = self.config.get("base_url", constants.TESTNET_API_URL)
            address, info, exchange = example_utils.setup(base_url, skip_ws=True)
            
            # Override with user's private key
            from eth_account import Account
            account = Account.from_key(private_key)
            exchange.wallet = account
            
            # Test connection with real API call
            user_state = info.user_state(account.address)
            account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
            
            # Create integrated trading components
            trader = ProfitOptimizedTrader(exchange, info, self.trading_config)
            
            # Initialize strategy managers
            seedify_manager = SeedifyIMCManager(exchange, info, self.config)
            hyperevm_connector = HyperEVMConnector(self.config)
            hyperevm_connector.set_account(private_key)
            
            # Store comprehensive user session
            self.user_exchanges[user_id] = {
                'exchange': exchange,
                'info': info,
                'address': account.address,
                'balance': account_value,
                'connected_at': datetime.now(),
                'trader': trader,
                'seedify_manager': seedify_manager,
                'hyperevm_connector': hyperevm_connector,
                'private_key': private_key  # Encrypt in production
            }
            
            logger.info(f"Connected user {user_id}: {account.address}")
            
            return {
                'success': True,
                'address': account.address,
                'balance': account_value,
                'components_initialized': True
            }
            
        except Exception as e:
            logger.error(f"Failed to connect user wallet: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_user_info(self, user_id: int) -> Dict:
        """Get real user account information"""
        try:
            if user_id not in self.user_exchanges:
                return {'error': 'User not connected'}
            
            user_data = self.user_exchanges[user_id]
            address = user_data['address']
            info = user_data['info']
            
            # Get latest account state from Hyperliquid API
            user_state = info.user_state(address)
            margin_summary = user_state.get('marginSummary', {})
            cross_summary = user_state.get('crossMarginSummary', {})
            
            # Count real positions using proper notation (szi = signed size)
            positions = user_state.get('assetPositions', [])
            active_positions = len([p for p in positions 
                                 if float(p.get('position', {}).get('szi', 0)) != 0])
            
            return {
                'address': address,
                'balance': float(margin_summary.get('accountValue', 0)),
                'available': float(cross_summary.get('availableBalance', 0)),
                'margin_used': float(cross_summary.get('marginUsed', 0)),
                'total_pnl': float(margin_summary.get('totalPnl', 0)),
                'positions': active_positions,
                'updated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return {'error': str(e)}
    
    async def place_order(self, user_id: int, coin: str, is_buy: bool, sz: float, 
                         px: float, post_only: bool = False, asset: int = None) -> Dict:
        """Place real order using Hyperliquid API with proper notation"""
        try:
            if user_id not in self.user_exchanges:
                return {'success': False, 'error': 'User not connected'}
            
            exchange = self.user_exchanges[user_id]['exchange']
            
            # Get asset index if not provided
            if asset is None:
                meta_response = self.info.meta()
                universe = meta_response.get('universe', [])
                asset = next((i for i, c in enumerate(universe) if c['name'] == coin), None)
                if asset is None:
                    return {'success': False, 'error': f'Asset {coin} not found'}
            
            # Use proper TIF notation: ALO = Add Liquidity Only (post only)
            tif = "Alo" if post_only else "Gtc"
            order_type = {"limit": {"tif": tif}}
            
            # Use proper field notation: a=asset, b=isBuy, p=price, s=size, r=reduceOnly, t=type
            order_request = {
                "a": asset,
                "b": is_buy,
                "p": str(px),  # Price as string
                "s": str(sz),  # Size as string  
                "r": False,    # reduceOnly
                "t": order_type
            }
            
            result = exchange.order(
                coin, is_buy, sz, px, order_type, reduce_only=False
            )
            
            if result.get('status') == 'ok':
                logger.info(f"Order placed for user {user_id}: {coin} {sz}@{px}")
                return {'success': True, 'result': result}
            else:
                return {'success': False, 'error': result}
                
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {'success': False, 'error': str(e)}
    
    async def cancel_order(self, user_id: int, coin: str, oid: int, asset: int = None) -> Dict:
        """Cancel specific order using proper notation"""
        try:
            if user_id not in self.user_exchanges:
                return {'success': False, 'error': 'User not connected'}
            
            user_data = self.user_exchanges[user_id]
            exchange = user_data['exchange']
            
            # Get asset index if not provided
            if asset is None:
                meta_response = self.info.meta()
                universe = meta_response.get('universe', [])
                asset = next((i for i, c in enumerate(universe) if c['name'] == coin), None)
                if asset is None:
                    return {'success': False, 'error': f'Asset {coin} not found'}
            
            # Use proper notation: a=asset, o=oid (order id)
            cancel_request = {
                "a": asset,
                "o": oid
            }
            
            result = exchange.cancel(coin, oid)
            
            if result.get('status') == 'ok':
                logger.info(f"Order cancelled for user {user_id}: {oid}")
                return {'success': True, 'result': result}
            else:
                return {'success': False, 'error': result}
                
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return {'success': False, 'error': str(e)}
    
    async def cancel_all_orders(self, user_id: int, coin: str = None) -> Dict:
        """Cancel all orders using real API"""
        try:
            if user_id not in self.user_exchanges:
                return {'success': False, 'error': 'User not connected'}
            
            user_data = self.user_exchanges[user_id]
            exchange = user_data['exchange']
            info = user_data['info']
            address = user_data['address']
            
            # Get real open orders
            open_orders = info.open_orders(address)
            
            cancelled = 0
            for order in open_orders:
                if coin is None or order['coin'] == coin:
                    try:
                        result = exchange.cancel(order['coin'], order['oid'])
                        if result.get('status') == 'ok':
                            cancelled += 1
                    except Exception as e:
                        logger.error(f"Failed to cancel order {order['oid']}: {e}")
            
            return {'success': True, 'cancelled': cancelled}
            
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_mid_price(self, coin: str) -> float:
        """Get real mid price from Hyperliquid"""
        try:
            all_mids = self.info.all_mids()
            return float(all_mids.get(coin, 0))
        except Exception as e:
            logger.error(f"Error getting mid price for {coin}: {e}")
            return 0
    
    async def get_l2_book(self, coin: str, n_sig_figs: int = 5) -> Dict:
        """Get L2 order book snapshot"""
        try:
            l2_snapshot = self.info.l2_snapshot(coin, nSigFigs=n_sig_figs)
            return {
                'coin': coin,
                'levels': l2_snapshot.get('levels', [[], []]),  # [bids, asks]
                'time': l2_snapshot.get('time', 0)
            }
        except Exception as e:
            logger.error(f"Error getting L2 book for {coin}: {e}")
            return {'error': str(e)}
    
    async def get_user_trading_stats(self, user_id: int) -> Dict:
        """Get real user trading statistics from Hyperliquid API"""
        try:
            if user_id not in self.user_exchanges:
                return {'error': 'User not connected'}
            
            user_data = self.user_exchanges[user_id]
            address = user_data['address']
            info = user_data['info']
            
            # Get real fills from Hyperliquid
            fills = info.user_fills(address)
            
            # Calculate real stats from actual trading data
            total_volume = 0
            total_rebates = 0
            total_fees_paid = 0
            trades_count = len(fills)
            total_pnl = 0
            
            # Filter recent fills (last 24 hours)
            now = datetime.now()
            recent_fills = []
            
            for fill in fills:
                fill_time = datetime.fromtimestamp(int(fill.get('time', 0)) / 1000)
                # Use proper notation: px=price, sz=size
                volume = float(fill['sz']) * float(fill['px'])
                total_volume += volume
                
                fee = float(fill.get('fee', 0))
                if fee < 0:  # Rebate (negative fee)
                    total_rebates += abs(fee)
                else:
                    total_fees_paid += fee
                
                if 'closedPnl' in fill:
                    total_pnl += float(fill['closedPnl'])
                
                # Check if within last 24 hours
                if (now - fill_time).days == 0:
                    recent_fills.append(fill)
            
            # Calculate 24h stats
            volume_24h = sum(float(f['sz']) * float(f['px']) for f in recent_fills)
            trades_24h = len(recent_fills)
            rebates_24h = sum(abs(float(f.get('fee', 0))) for f in recent_fills 
                            if float(f.get('fee', 0)) < 0)
            
            return {
                'volume_24h': volume_24h,
                'trades_24h': trades_24h,
                'rebates_24h': rebates_24h,
                'total_volume': total_volume,
                'total_trades': trades_count,
                'total_rebates': total_rebates,
                'total_fees_paid': total_fees_paid,
                'net_fees': total_fees_paid - total_rebates,
                'total_pnl': total_pnl
            }
            
        except Exception as e:
            logger.error(f"Error getting trading stats: {e}")
            return {'error': str(e)}
    
    async def get_user_volume_stats(self, user_id: int) -> Dict:
        """Get real volume statistics for rebate calculation"""
        try:
            if user_id not in self.user_exchanges:
                return {'error': 'User not connected'}
            
            user_data = self.user_exchanges[user_id]
            address = user_data['address']
            info = user_data['info']
            
            # Get real fills for volume calculation
            fills = info.user_fills(address)
            
            total_volume = 0
            maker_volume = 0
            
            # Filter to last 14 days for fee tier calculation
            now = datetime.now()
            fourteen_days_ago = now - timedelta(days=14)
            
            for fill in fills:
                fill_time = datetime.fromtimestamp(int(fill.get('time', 0)) / 1000)
                
                if fill_time >= fourteen_days_ago:
                    # Use proper notation: px=price, sz=size
                    volume = float(fill['sz']) * float(fill['px'])
                    total_volume += volume
                    
                    # Maker orders have negative or zero fees
                    fee = float(fill.get('fee', 0))
                    if fee <= 0:
                        maker_volume += volume
            
            maker_percentage = (maker_volume / total_volume * 100) if total_volume > 0 else 0
            
            return {
                'volume_14d': total_volume,
                'maker_volume_14d': maker_volume,
                'maker_percentage': maker_percentage,
                'fee_tier': self._calculate_fee_tier(total_volume),
                'rebate_tier': self._calculate_rebate_tier(maker_percentage)
            }
            
        except Exception as e:
            logger.error(f"Error getting volume stats: {e}")
            return {'error': str(e)}
    
    def _calculate_fee_tier(self, volume_14d: float) -> Dict:
        """Calculate fee tier based on real Hyperliquid structure"""
        if volume_14d < 5000000:
            return {"tier": "Bronze", "taker_fee": 0.00035, "maker_fee": 0.0001}
        elif volume_14d < 25000000:
            return {"tier": "Silver", "taker_fee": 0.000325, "maker_fee": 0.00005}
        elif volume_14d < 125000000:
            return {"tier": "Gold", "taker_fee": 0.0003, "maker_fee": 0.0}
        elif volume_14d < 500000000:
            return {"tier": "Platinum", "taker_fee": 0.000275, "maker_fee": 0.0}
        else:
            return {"tier": "Diamond", "taker_fee": 0.00019, "maker_fee": 0.0}
    
    def _calculate_rebate_tier(self, maker_percentage: float) -> Dict:
        """Calculate rebate tier based on maker percentage"""
        if maker_percentage >= 3.0:
            return {"tier": "Tier 3", "rebate": -0.00003}  # -0.003%
        elif maker_percentage >= 1.5:
            return {"tier": "Tier 2", "rebate": -0.00002}  # -0.002%
        elif maker_percentage >= 0.5:
            return {"tier": "Tier 1", "rebate": -0.00001}  # -0.001%
        else:
            return {"tier": "No rebate", "rebate": 0.0}
    
    async def get_vault_stats(self, vault_address: str) -> Dict:
        """Get real vault statistics"""
        try:
            if not vault_address:
                return {'error': 'No vault address provided'}
            
            # Get real vault state from Hyperliquid
            vault_state = self.info.user_state(vault_address)
            account_value = float(vault_state.get('marginSummary', {}).get('accountValue', 0))
            total_pnl = float(vault_state.get('marginSummary', {}).get('totalPnl', 0))
            
            # Get vault trading performance
            vault_fills = self.info.user_fills(vault_address)
            vault_volume = sum(float(f['sz']) * float(f['px']) for f in vault_fills)
            
            # Get vault positions using proper notation (szi = signed size)
            positions = vault_state.get('assetPositions', [])
            active_positions = []
            for pos in positions:
                position_data = pos.get('position', {})
                szi = float(position_data.get('szi', 0))
                if szi != 0:
                    active_positions.append({
                        'coin': position_data.get('coin'),
                        'szi': szi,  # signed size
                        'entry_px': float(position_data.get('entryPx', 0)),
                        'unrealized_pnl': float(position_data.get('unrealizedPnl', 0))
                    })
            
            return {
                'vault_address': vault_address,
                'total_value': account_value,
                'total_pnl': total_pnl,
                'total_volume': vault_volume,
                'trades_count': len(vault_fills),
                'active_positions': active_positions,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting vault stats: {e}")
            return {'error': str(e)}
    
    async def get_open_orders(self, user_id: int) -> List[Dict]:
        """Get user's open orders"""
        try:
            if user_id not in self.user_exchanges:
                return []
            
            user_data = self.user_exchanges[user_id]
            address = user_data['address']
            info = user_data['info']
            
            open_orders = info.open_orders(address)
            
            # Return orders with proper notation
            formatted_orders = []
            for order in open_orders:
                formatted_orders.append({
                    'coin': order.get('coin'),
                    'oid': order.get('oid'),  # order id
                    'side': order.get('side'),
                    'sz': float(order.get('sz', 0)),  # size
                    'limit_px': float(order.get('limitPx', 0)),  # limit price
                    'reduce_only': order.get('reduceOnly', False),
                    'timestamp': order.get('timestamp', 0)
                })
            
            return formatted_orders
            
        except Exception as e:
            logger.error(f"Error getting open orders: {e}")
            return []
    
    async def vault_transfer(self, user_id: int, vault_address: str, is_deposit: bool, usd_amount: float) -> Dict:
        """Transfer to/from vault using proper API"""
        try:
            if user_id not in self.user_exchanges:
                return {'success': False, 'error': 'User not connected'}
            
            exchange = self.user_exchanges[user_id]['exchange']
            
            # Use proper vault transfer action
            result = exchange.vault_transfer(
                vault_address=vault_address,
                is_deposit=is_deposit,
                usd=usd_amount
            )
            
            if result.get('status') == 'ok':
                action = "deposit" if is_deposit else "withdrawal"
                logger.info(f"Vault {action} successful: ${usd_amount} to {vault_address}")
                return {'success': True, 'result': result}
            else:
                return {'success': False, 'error': result}
                
        except Exception as e:
            logger.error(f"Error in vault transfer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_hlp_performance(self) -> Dict:
        """Get real HLP performance data"""
        try:
            # Real HLP vault address
            hlp_address = "0x6a7296d6b5127b0fb9f4a8ad68fcdf2eec1e4dc5"
            
            try:
                hlp_state = self.info.user_state(hlp_address)
                hlp_value = float(hlp_state.get('marginSummary', {}).get('accountValue', 0))
                
                return {
                    'address': hlp_address,
                    'total_value': hlp_value,
                    'apy': 36.0,  # Current known APY
                    'lockup_days': 4,
                    'status': 'active'
                }
            except Exception:
                # Fallback if direct query fails
                return {
                    'address': hlp_address,
                    'total_value': 391000000,  # Known approximate value
                    'apy': 36.0,
                    'lockup_days': 4,
                    'status': 'estimated'
                }
                
        except Exception as e:
            logger.error(f"Error getting HLP performance: {e}")
            return {'error': str(e)}
    
    async def get_perpetual_meta(self, dex: str = "") -> Dict:
        """Get perpetual metadata"""
        try:
            meta_response = self.info.meta(dex=dex)
            return {
                'universe': meta_response.get('universe', []),
                'margin_tables': meta_response.get('marginTables', [])
            }
        except Exception as e:
            logger.error(f"Error getting perp meta: {e}")
            return {'error': str(e)}
    
    async def get_spot_meta(self) -> Dict:
        """Get spot metadata"""
        try:
            spot_meta = self.info.spot_meta()
            return {
                'tokens': spot_meta.get('tokens', []),
                'universe': spot_meta.get('universe', [])
            }
        except Exception as e:
            logger.error(f"Error getting spot meta: {e}")
            return {'error': str(e)}
    
    async def get_integrated_user_session(self, user_id: int) -> Optional[Dict]:
        """Get complete user session with all components"""
        return self.user_exchanges.get(user_id)
    
    async def execute_strategy(self, user_id: int, strategy_type: str, params: Dict) -> Dict:
        """Execute trading strategy using integrated components"""
        try:
            session = self.user_exchanges.get(user_id)
            if not session:
                return {'error': 'User not connected'}
            
            trader = session['trader']
            
            if strategy_type == 'market_making':
                return await trader.place_maker_order(
                    params['coin'], params['is_buy'], params['sz'], params['px']
                )
            elif strategy_type == 'profit_taking':
                return await trader.profit_taking_strategy(
                    params['coin'], params.get('target_profit_pct', 0.02)
                )
            elif strategy_type == 'volume_farming':
                seedify_manager = session['seedify_manager']
                return await seedify_manager.create_volume_farming_strategy(params['capital'])
            else:
                return {'error': f'Unknown strategy: {strategy_type}'}
                
        except Exception as e:
            logger.error(f"Error executing strategy: {e}")
            return {'error': str(e)}