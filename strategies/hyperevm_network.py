import asyncio
import json
from typing import Dict, List, Optional, Union, Any
from web3 import Web3
from eth_account import Account
from dataclasses import dataclass
import logging
import time
import requests

@dataclass
class HyperEVMTransaction:
    """Data class for HyperEVM transactions"""
    to_address: str
    value: float
    gas_limit: int
    gas_price: int
    data: str = ""
    nonce: Optional[int] = None

class HyperEVMConnector:
    """
    HyperEVM network connector for real interactions
    """
    
    def __init__(self, config):
        self.config = config
        self.network = config.get("hyperevm", {}).get("network", "testnet")
        self.logger = logging.getLogger(__name__)
        
        # Real HyperEVM endpoints
        if self.network == "mainnet":
            self.rpc_url = "https://api.hyperliquid-evm.xyz/rpc"
        else:
            self.rpc_url = "https://api.hyperliquid-testnet-evm.xyz/rpc"
        
        # Initialize Web3 connection
        try:
            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            self.connected = self.web3.is_connected()
            self.logger.info(f"HyperEVM connection: {self.connected}")
        except Exception as e:
            self.connected = False
            self.logger.error(f"Failed to connect to HyperEVM: {e}")
        
        # Real contract addresses - these would need to be actual deployed contracts
        self.usdc_address = None  # Will be set when contracts are deployed
        
        # Account will be set when user authenticates
        self.account = None
    
    def set_account(self, private_key: str):
        """Set the account for transactions"""
        try:
            self.account = Account.from_key(private_key)
            self.logger.info(f"Account set: {self.account.address}")
        except Exception as e:
            self.logger.error(f"Failed to set account: {e}")
    
    async def get_native_balance(self, address: str = None) -> float:
        """Get native ETH balance"""
        try:
            if not self.connected:
                return 0.0
            
            address = address or (self.account.address if self.account else None)
            if not address:
                return 0.0
            
            balance_wei = self.web3.eth.get_balance(address)
            return self.web3.from_wei(balance_wei, 'ether')
        except Exception as e:
            self.logger.error(f"Error getting native balance: {e}")
            return 0.0
    
    async def get_usdc_balance(self, address: str = None) -> float:
        """Get USDC balance (when contract is available)"""
        try:
            # Placeholder for when USDC contract is deployed
            return 0.0
        except Exception as e:
            self.logger.error(f"Error getting USDC balance: {e}")
            return 0.0
    
    async def get_network_status(self) -> Dict:
        """Get network status and information"""
        try:
            if not self.connected:
                return {
                    "network": self.network,
                    "connected": False,
                    "error": "Not connected to RPC"
                }
            
            latest_block = self.web3.eth.get_block('latest')
            gas_price = self.web3.eth.gas_price
            
            return {
                "network": self.network,
                "connected": True,
                "latest_block": latest_block.number,
                "gas_price_gwei": self.web3.from_wei(gas_price, 'gwei'),
                "chain_id": self.web3.eth.chain_id
            }
        except Exception as e:
            self.logger.error(f"Error getting network status: {e}")
            return {"network": self.network, "connected": False, "error": str(e)}

    async def send_transaction(self, transaction: HyperEVMTransaction) -> Dict:
        """Send a transaction to the HyperEVM network"""
        try:
            if not self.connected or not self.account:
                return {"status": "error", "message": "Not connected or no account set"}
            
            # Prepare transaction
            tx = {
                'to': transaction.to_address,
                'value': self.web3.to_wei(transaction.value, 'ether'),
                'gas': transaction.gas_limit,
                'gasPrice': transaction.gas_price,
                'nonce': transaction.nonce if transaction.nonce is not None else self.web3.eth.get_transaction_count(self.account.address),
                'data': transaction.data,
                'chainId': self.web3.eth.chain_id
            }
            
            # Sign and send transaction
            signed_tx = self.web3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            return {
                "status": "success",
                "tx_hash": tx_hash.hex(),
                "nonce": tx['nonce']
            }
        except Exception as e:
            self.logger.error(f"Error sending transaction: {e}")
            return {"status": "error", "message": str(e)}

class HyperliquidApiConnector:
    """
    Connector for Hyperliquid API with proper notation handling
    """
    
    def __init__(self, network: str = "testnet"):
        self.logger = logging.getLogger(__name__)
        
        if network == "mainnet":
            self.api_url = "https://api.hyperliquid.xyz"
        else:
            self.api_url = "https://api-testnet.hyperliquid.xyz"
        
        self.session = requests.Session()
        self.asset_map = {}  # Cache for asset IDs
        self.meta_info = {}  # Cache for meta information
    
    async def _post_request(self, endpoint: str, data: Dict) -> Dict:
        """Send a POST request to the Hyperliquid API"""
        try:
            headers = {"Content-Type": "application/json"}
            response = self.session.post(f"{self.api_url}/{endpoint}", headers=headers, json=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"API request error ({endpoint}): {e}")
            return {"error": str(e)}
    
    async def get_meta_info(self) -> Dict:
        """Get meta information including asset mapping"""
        try:
            if not self.meta_info:
                response = await self._post_request("info", {"type": "meta"})
                if "universe" in response:
                    self.meta_info = response
                    # Create asset map for easy lookup
                    for i, asset in enumerate(response.get("universe", [])):
                        self.asset_map[asset["name"]] = i
                return response
            return self.meta_info
        except Exception as e:
            self.logger.error(f"Error getting meta info: {e}")
            return {"error": str(e)}
    
    async def get_asset_id(self, coin: str) -> Optional[int]:
        """Get asset ID for a coin, following Hyperliquid notation"""
        if not self.asset_map:
            await self.get_meta_info()
        
        # Handle different formats
        if ":" in coin:  # Builder-deployed perps format {dex}:{coin}
            dex, asset = coin.split(":")
            # Logic for builder-deployed perps: 100000 + perp_dex_index * 10000 + index_in_meta
            perp_dexes = await self._post_request("info", {"type": "perpDexs"})
            try:
                dex_index = next(i for i, d in enumerate(perp_dexes) if d and d["name"] == dex)
                # Get the index of the coin in the dex's universe
                meta_with_dex = await self._post_request("info", {"type": "meta", "dex": dex})
                asset_index = next(i for i, a in enumerate(meta_with_dex["universe"]) if a["name"] == asset)
                return 100000 + dex_index * 10000 + asset_index
            except (StopIteration, KeyError) as e:
                self.logger.error(f"Error finding builder-deployed perp asset ID: {e}")
                return None
        elif "/" in coin:  # Spot pair format
            base, quote = coin.split("/")
            # Get spot meta
            spot_meta = await self._post_request("info", {"type": "spotMeta"})
            if "universe" in spot_meta:
                # Find the index of this pair in universe
                for i, pair in enumerate(spot_meta["universe"]):
                    if pair["name"] == coin:
                        return 10000 + i  # Spot ID = 10000 + index
            return None
        else:
            # Standard perp asset - return the index directly
            return self.asset_map.get(coin)
    
    async def get_all_mids(self) -> Dict[str, str]:
        """Get mid prices for all assets"""
        try:
            response = await self._post_request("info", {"type": "metaAndAssetCtxs"})
            if isinstance(response, list) and len(response) >= 2:
                meta, asset_ctxs = response[0], response[1]
                
                all_mids = {}
                for i, asset_ctx in enumerate(asset_ctxs):
                    if "midPx" in asset_ctx and i < len(meta.get("universe", [])):
                        coin = meta["universe"][i]["name"]
                        all_mids[coin] = asset_ctx["midPx"]
                
                return all_mids
            return {}
        except Exception as e:
            self.logger.error(f"Error getting all mids: {e}")
            return {}
    
    async def get_user_state(self, address: str) -> Dict:
        """Get user state with proper notation handling"""
        try:
            response = await self._post_request("info", {
                "type": "clearinghouseState",
                "user": address
            })
            return response
        except Exception as e:
            self.logger.error(f"Error getting user state: {e}")
            return {"error": str(e)}
    
    async def get_l2_snapshot(self, coin: str) -> Dict:
        """Get L2 orderbook snapshot"""
        try:
            asset_id = await self.get_asset_id(coin)
            if asset_id is None:
                return {"error": f"Unknown asset: {coin}"}
            
            response = await self._post_request("info", {
                "type": "l2Book",
                "coin": coin
            })
            return response
        except Exception as e:
            self.logger.error(f"Error getting L2 snapshot: {e}")
            return {"error": str(e)}
    
    async def place_order(self, coin: str, is_buy: bool, size: float, price: float, 
                        reduce_only: bool = False, order_type: str = "Gtc", 
                        vault_address: Optional[str] = None) -> Dict:
        """
        Place an order using proper Hyperliquid notation
        """
        try:
            # Get asset ID
            asset_id = await self.get_asset_id(coin)
            if asset_id is None:
                return {"status": "error", "message": f"Unknown asset: {coin}"}
            
            # Normalize price and size to strings
            price_str = str(price)
            size_str = str(size)
            
            # Create order payload
            order = {
                "a": asset_id,  # asset
                "b": is_buy,    # isBuy
                "p": price_str, # price
                "s": size_str,  # size
                "r": reduce_only, # reduceOnly
                "t": {"limit": {"tif": order_type}}  # Gtc/Alo/Ioc
            }
            
            # Prepare request payload
            request_data = {
                "action": {
                    "type": "order",
                    "orders": [order],
                    "grouping": "na"
                },
                "nonce": int(time.time() * 1000),  # Current timestamp in ms
                "signature": {}  # Would be filled by calling code
            }
            
            if vault_address:
                request_data["vaultAddress"] = vault_address
            
            # In a real implementation, you would sign this and send it
            # For now, return the properly formatted payload
            return {
                "status": "formatted_payload",
                "request": request_data,
                "note": "This payload needs to be signed with the wallet's private key"
            }
            
        except Exception as e:
            self.logger.error(f"Error formatting order: {e}")
            return {"status": "error", "message": str(e)}

class HyperEVMNetwork:
    """
    Enhanced HyperEVM network connector with Hyperliquid API integration and standardized notation
    """
    
    def __init__(self, config: Dict = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or {}
        
        # Initialize connectors
        self.evm_connector = HyperEVMConnector(self.config)
        self.api_connector = HyperliquidApiConnector(
            network=self.config.get("network", "testnet")
        )
        
        # Cache for nonce management
        self.nonce_tracker = {}
        self.last_nonce_update = 0
    
    async def initialize(self) -> Dict:
        """Initialize connections and fetch required data"""
        try:
            # Get network status
            network_status = await self.evm_connector.get_network_status()
            
            # Get meta information
            meta_info = await self.api_connector.get_meta_info()
            
            # Initialize nonce tracker with current timestamp
            self.nonce_tracker['last'] = int(time.time() * 1000)
            
            return {
                "status": "initialized" if network_status.get("connected") else "partial",
                "network": network_status,
                "meta_info_loaded": "universe" in meta_info
            }
        except Exception as e:
            self.logger.error(f"Error initializing HyperEVMNetwork: {e}")
            return {"status": "error", "message": str(e)}
    
    async def get_unique_nonce(self) -> int:
        """Get a unique nonce following Hyperliquid requirements"""
        current_time = int(time.time() * 1000)
        
        # Use timestamp if more than 1 ms since last nonce
        if current_time > self.nonce_tracker.get('last', 0):
            self.nonce_tracker['last'] = current_time
            return current_time
        
        # Otherwise increment the last nonce
        self.nonce_tracker['last'] += 1
        return self.nonce_tracker['last']
    
    async def place_maker_order(self, coin: str, is_buy: bool, size: float, price: float, 
                            vault_address: Optional[str] = None) -> Dict:
        """
        Place a maker order with proper notation and ALO (Add Liquidity Only) flag
        """
        return await self.api_connector.place_order(
            coin=coin,
            is_buy=is_buy,
            size=size,
            price=price,
            reduce_only=False,
            order_type="Alo",  # ALO = Add Liquidity Only (maker only order)
            vault_address=vault_address
        )
    
    async def place_taker_order(self, coin: str, is_buy: bool, size: float, price: float,
                           vault_address: Optional[str] = None) -> Dict:
        """
        Place a taker order with proper notation and IOC (Immediate or Cancel) flag
        """
        return await self.api_connector.place_order(
            coin=coin,
            is_buy=is_buy,
            size=size,
            price=price,
            reduce_only=False,
            order_type="Ioc",  # IOC = Immediate or Cancel (taker order)
            vault_address=vault_address
        )
    
    async def schedule_cancel_orders(self, time_ms: Optional[int] = None) -> Dict:
        """
        Schedule cancellation of all orders (dead man's switch)
        If time_ms is not provided, it will default to current time + 5 seconds
        """
        if not time_ms:
            time_ms = int(time.time() * 1000) + 5000  # 5 seconds in the future
            
        # Prepare request payload
        request_data = {
            "action": {
                "type": "scheduleCancel",
                "time": time_ms
            },
            "nonce": await self.get_unique_nonce(),
            "signature": {}  # Would be filled by calling code
        }
        
        # In a real implementation, you would sign this and send it
        return {
            "status": "formatted_payload",
            "request": request_data,
            "note": "This payload needs to be signed with the wallet's private key"
        }

    async def scan_funding_opportunities(self) -> List[Dict]:
        """Scan for funding rate arbitrage opportunities"""
        try:
            predicted_fundings = await self.api_connector.get_predicted_fundings()
            opportunities = []
            
            for coin_data in predicted_fundings:
                if len(coin_data) >= 2:
                    coin = coin_data[0]
                    venues = coin_data[1]
                    
                    # Find maximum funding rate difference between venues
                    hl_funding = None
                    other_venues = {}
                    
                    for venue_data in venues:
                        if len(venue_data) >= 2:
                            venue, data = venue_data[0], venue_data[1]
                            funding_rate = float(data.get("fundingRate", 0))
                            
                            if venue == "HlPerp":
                                hl_funding = funding_rate
                            else:
                                other_venues[venue] = funding_rate
                    
                    if hl_funding is not None:
                        # Find largest difference
                        for venue, funding in other_venues.items():
                            diff = funding - hl_funding
                            
                            # Consider meaningful differences only (0.5+ bps)
                            if abs(diff) >= 0.00005:
                                opportunities.append({
                                    "coin": coin,
                                    "hl_funding": hl_funding,
                                    "other_venue": venue,
                                    "other_funding": funding,
                                    "difference": diff,
                                    "difference_bps": diff * 10000,
                                    "opportunity": "long_hl_short_other" if diff < 0 else "short_hl_long_other"
                                })
            
            # Sort by absolute difference
            opportunities.sort(key=lambda x: abs(x["difference"]), reverse=True)
            return opportunities
            
        except Exception as e:
            self.logger.error(f"Error scanning funding opportunities: {e}")
            return []
    
    async def optimize_rebate_opportunities(self) -> Dict:
        """
        Find rebate optimization opportunities
        """
        try:
            # Get meta and asset contexts for market data
            meta_info = await self.api_connector.get_meta_info()
            
            # Get all mid prices
            all_mids = await self.api_connector.get_all_mids()
            
            # Analyze spread and liquidity for rebate opportunities
            rebate_opportunities = []
            
            for coin, price in all_mids.items():
                try:
                    # Get L2 book data for spread analysis
                    l2_data = await self.api_connector.get_l2_snapshot(coin)
                    
                    if not isinstance(l2_data, dict) or "levels" not in l2_data or len(l2_data["levels"]) < 2:
                        continue
                    
                    bid_levels = l2_data["levels"][0]
                    ask_levels = l2_data["levels"][1]
                    
                    if not bid_levels or not ask_levels:
                        continue
                    
                    best_bid = float(bid_levels[0][0])
                    best_ask = float(ask_levels[0][0])
                    
                    # Calculate spread in basis points
                    mid_price = (best_bid + best_ask) / 2
                    spread_bps = ((best_ask - best_bid) / mid_price) * 10000
                    
                    # Calculate liquidity (top 5 levels sum)
                    bid_liquidity = sum(float(level[1]) * float(level[0]) for level in bid_levels[:5])
                    ask_liquidity = sum(float(level[1]) * float(level[0]) for level in ask_levels[:5])
                    
                    # Calculate rebate score (higher is better)
                    rebate_score = (bid_liquidity + ask_liquidity) / (spread_bps + 1)  # Avoid division by zero
                    
                    rebate_opportunities.append({
                        "coin": coin,
                        "mid_price": mid_price,
                        "spread_bps": spread_bps,
                        "bid_liquidity": bid_liquidity,
                        "ask_liquidity": ask_liquidity,
                        "total_liquidity": bid_liquidity + ask_liquidity,
                        "rebate_score": rebate_score
                    })
                
                except Exception as e:
                    self.logger.error(f"Error analyzing rebate opportunity for {coin}: {e}")
            
            # Sort by rebate score
            rebate_opportunities.sort(key=lambda x: x["rebate_score"], reverse=True)
            
            # Return top opportunities
            return {
                "status": "success",
                "opportunities": rebate_opportunities[:10],
                "optimal_rebate_strategy": self._generate_rebate_strategy(rebate_opportunities[:5]),
                "total_markets_analyzed": len(rebate_opportunities)
            }
            
        except Exception as e:
            self.logger.error(f"Error optimizing rebate opportunities: {e}")
            return {"status": "error", "message": str(e)}
    
    def _generate_rebate_strategy(self, opportunities: List[Dict]) -> Dict:
        """Generate optimal rebate strategy from opportunities"""
        if not opportunities:
            return {
                "status": "no_opportunities",
                "recommendation": "No suitable rebate opportunities found"
            }
        
        # Calculate optimal capital allocation
        total_score = sum(opp["rebate_score"] for opp in opportunities)
        allocations = {}
        
        for opp in opportunities:
            weight = opp["rebate_score"] / total_score if total_score > 0 else 0
            allocations[opp["coin"]] = {
                "weight": weight,
                "optimal_order_sizing": {
                    "based_on": "spread and liquidity",
                    "recommended_size_usd": 500 * weight  # Example allocation of $500 total
                },
                "recommended_order_type": "ALO"  # Add Liquidity Only
            }
        
        return {
            "status": "strategy_ready",
            "allocation_logic": "Weighted by rebate score (liquidity/spread ratio)",
            "allocations": allocations,
            "expected_rebate_tier": "Standard tier (base rebates)",
            "path_to_higher_tier": "Need >0.5% maker volume for enhanced rebates"
        }
    
    async def track_hyperevm_ecosystem(self) -> Dict:
        """Track HyperEVM ecosystem developments"""
        # This would be implemented with actual data in production
        # For now, return a structured demo response
        return {
            "ecosystem_health": "growing",
            "protocols": [
                {
                    "name": "HyperLend",
                    "status": "live",
                    "tvl": 15000000,
                    "apy_range": [0.03, 0.12],
                    "volume_24h": 2500000
                },
                {
                    "name": "HyperSwap",
                    "status": "live",
                    "tvl": 22000000,
                    "volume_24h": 5800000,
                    "fee_tiers": [0.0005, 0.001, 0.003]
                },
                {
                    "name": "HyperBridge",
                    "status": "live",
                    "tvl": 8500000,
                    "volume_24h": 1200000,
                    "supported_chains": ["Ethereum", "Arbitrum", "Base"]
                }
            ],
            "network_metrics": {
                "total_tvl": 45500000,
                "daily_transactions": 28500,
                "active_addresses": 12000,
                "gas_price_gwei": 0.08
            },
            "ecosystem_opportunities": [
                {
                    "type": "liquidity_mining",
                    "protocol": "HyperSwap",
                    "apy": 0.18,
                    "min_deposit": 1000,
                    "rewards": "HYPE"
                },
                {
                    "type": "lending",
                    "protocol": "HyperLend",
                    "apy": 0.12,
                    "collateral_ratio": 0.8,
                    "supported_assets": ["ETH", "USDC", "HYPE"]
                }
            ]
        }

class HyperEVMMonitor:
    """
    Monitors the HyperEVM network for transactions, events, and DeFi activities
    """
    
    def __init__(self, connector=None, config=None):
        self.connector = connector or HyperEVMConnector()
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.active_monitors = {}
        self.alert_callbacks = {}
        
    async def start_monitoring(self, targets=None):
        """Start monitoring specified targets or all configured targets"""
        targets = targets or ["blocks", "transactions", "events"]
        
        for target in targets:
            if target == "blocks":
                self.active_monitors[target] = asyncio.create_task(self._monitor_blocks())
            elif target == "transactions":
                self.active_monitors[target] = asyncio.create_task(self._monitor_transactions())
            elif target == "events":
                self.active_monitors[target] = asyncio.create_task(self._monitor_events())
                
        self.logger.info(f"Started monitoring: {', '.join(targets)}")
        return {"status": "monitoring", "targets": targets}
        
    async def stop_monitoring(self, targets=None):
        """Stop monitoring specific targets or all active monitors"""
        targets = targets or list(self.active_monitors.keys())
        
        for target in targets:
            if target in self.active_monitors:
                self.active_monitors[target].cancel()
                del self.active_monitors[target]
                
        self.logger.info(f"Stopped monitoring: {', '.join(targets)}")
        return {"status": "stopped", "targets": targets}
        
    async def _monitor_blocks(self):
        """Monitor new blocks on the HyperEVM network"""
        try:
            last_block = await self.connector.get_latest_block()
            
            while True:
                await asyncio.sleep(2)  # Check every 2 seconds
                current_block = await self.connector.get_latest_block()
                
                if current_block > last_block:
                    self.logger.info(f"New block: {current_block}")
                    
                    # Process new blocks
                    for block_num in range(last_block + 1, current_block + 1):
                        block_data = await self.connector.get_block(block_num)
                        await self._process_block(block_data)
                        
                    last_block = current_block
                    
        except asyncio.CancelledError:
            self.logger.info("Block monitoring cancelled")
        except Exception as e:
            self.logger.error(f"Error monitoring blocks: {e}")
            
    async def _monitor_transactions(self):
        """Monitor transactions for specific addresses or patterns"""
        try:
            watched_addresses = self.config.get("watched_addresses", [])
            
            while True:
                await asyncio.sleep(5)  # Check every 5 seconds
                
                # Get mempool transactions
                pending_txs = await self.connector.get_pending_transactions()
                
                for tx in pending_txs:
                    # Check if transaction involves watched addresses
                    if tx.get("from") in watched_addresses or tx.get("to") in watched_addresses:
                        await self._process_transaction(tx)
                        
        except asyncio.CancelledError:
            self.logger.info("Transaction monitoring cancelled")
        except Exception as e:
            self.logger.error(f"Error monitoring transactions: {e}")
            
    async def _monitor_events(self):
        """Monitor contract events (swaps, trades, liquidations)"""
        try:
            watched_events = self.config.get("watched_events", [])
            
            while True:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                for event_config in watched_events:
                    contract_address = event_config.get("address")
                    event_name = event_config.get("name")
                    
                    events = await self.connector.get_contract_events(
                        contract_address, 
                        event_name
                    )
                    
                    for event in events:
                        await self._process_event(event)
                        
        except asyncio.CancelledError:
            self.logger.info("Event monitoring cancelled")
        except Exception as e:
            self.logger.error(f"Error monitoring events: {e}")
            
    async def _process_block(self, block):
        """Process a new block"""
        if "block" in self.alert_callbacks:
            await self.alert_callbacks["block"](block)
            
    async def _process_transaction(self, transaction):
        """Process a transaction"""
        if "transaction" in self.alert_callbacks:
            await self.alert_callbacks["transaction"](transaction)
            
    async def _process_event(self, event):
        """Process a contract event"""
        if "event" in self.alert_callbacks:
            await self.alert_callbacks["event"](event)
            
    def register_callback(self, event_type, callback):
        """Register a callback function for specific event types"""
        self.alert_callbacks[event_type] = callback
        return {"status": "registered", "event_type": event_type}
        
    async def get_monitoring_status(self):
        """Get the current monitoring status"""
        return {
            "active_monitors": list(self.active_monitors.keys()),
            "watched_addresses": len(self.config.get("watched_addresses", [])),
            "watched_events": len(self.config.get("watched_events", [])),
            "registered_callbacks": list(self.alert_callbacks.keys())
        }
