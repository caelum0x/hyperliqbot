import asyncio
import json
from typing import Dict, List, Optional
from web3 import Web3
from eth_account import Account
from dataclasses import dataclass
import logging

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

class HyperEVMBridge:
    """
    Real bridge interface for HyperEVM - tracks actual network state
    """
    
    def __init__(self, connector: HyperEVMConnector):
        self.connector = connector
        self.logger = logging.getLogger(__name__)
    
    async def estimate_bridge_cost(self, amount: float) -> Dict:
        """Estimate bridging costs"""
        try:
            network_status = await self.connector.get_network_status()
            
            if not network_status.get("connected"):
                return {"error": "Network not connected"}
            
            gas_price_gwei = network_status.get("gas_price_gwei", 20)
            estimated_gas = 50000  # Estimated gas for bridge transaction
            bridge_fee_eth = (gas_price_gwei * estimated_gas) / 1e9
            
            return {
                "amount": amount,
                "estimated_gas": estimated_gas,
                "gas_price_gwei": gas_price_gwei,
                "bridge_fee_eth": bridge_fee_eth,
                "bridge_fee_usd": bridge_fee_eth * 3000  # Approximate ETH price
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def check_bridge_status(self, tx_hash: str) -> Dict:
        """Check bridge transaction status"""
        try:
            if not self.connector.connected:
                return {"error": "Not connected to network"}
            
            receipt = self.connector.web3.eth.get_transaction_receipt(tx_hash)
            
            return {
                "tx_hash": tx_hash,
                "status": "success" if receipt.status == 1 else "failed",
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed
            }
        except Exception as e:
            return {"error": str(e)}

class HyperEVMMonitor:
    """
    Monitor real HyperEVM network for opportunities and data
    """
    
    def __init__(self, connector: HyperEVMConnector):
        self.connector = connector
        self.logger = logging.getLogger(__name__)
    
    async def check_gas_prices(self) -> Dict:
        """Monitor gas prices for optimal transaction timing"""
        try:
            network_status = await self.connector.get_network_status()
            
            if not network_status.get("connected"):
                return {"error": "Network not connected"}
            
            current_gas = network_status.get("gas_price_gwei", 0)
            
            # Simple gas price analysis
            recommendation = "normal"
            if current_gas < 10:
                recommendation = "low_cost"
            elif current_gas > 50:
                recommendation = "high_cost"
            
            return {
                "current_gas_gwei": current_gas,
                "recommendation": recommendation,
                "optimal_for_transactions": current_gas < 30
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def get_account_summary(self, address: str = None) -> Dict:
        """Get comprehensive account summary"""
        try:
            native_balance = await self.connector.get_native_balance(address)
            usdc_balance = await self.connector.get_usdc_balance(address)
            network_status = await self.connector.get_network_status()
            
            return {
                "address": address or (self.connector.account.address if self.connector.account else ""),
                "native_balance": native_balance,
                "usdc_balance": usdc_balance,
                "network_status": network_status,
                "total_value_estimate": usdc_balance + (native_balance * 3000)  # Rough USD estimate
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def get_protocol_opportunities(self) -> Dict:
        """Scan for DeFi protocol opportunities"""
        try:
            # Placeholder for when protocols are deployed
            return {
                "hyperlend": {"status": "coming_soon", "estimated_apy": "TBD"},
                "hyperswap": {"status": "coming_soon", "liquidity": "TBD"},
                "hyperbeat": {"status": "coming_soon", "yield_strategies": "TBD"}
            }
        except Exception as e:
            return {"error": str(e)}
