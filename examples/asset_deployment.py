"""
Examples demonstrating Hyperliquid token deployment (HIP-1 and HIP-3)
"""

import asyncio
import time
import json
import logging
from typing import Dict

import example_utils
from hyperliquid.utils import constants

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AssetDeploymentExamples:
    """Examples for Hyperliquid token deployment operations"""
    
    def __init__(self, base_url=None):
        """Initialize with Hyperliquid connection"""
        # Set up connection using standard pattern
        self.address, self.info, self.exchange = example_utils.setup(
            base_url=base_url or constants.TESTNET_API_URL,
            skip_ws=True
        )
        
        # Get network info
        self.is_mainnet = self.exchange.base_url == constants.MAINNET_API_URL
        
        logger.info(f"Asset deployment examples initialized with address: {self.address}")
        logger.info(f"Network: {'Mainnet' if self.is_mainnet else 'Testnet'}")
    
    async def demonstrate_hip1_token_deployment(self) -> Dict:
        """
        Demonstrate deploying a token following HIP-1 standard
        """
        logger.info("== Example: HIP-1 Token Deployment ==")
        
        # Step 1: Register Token
        token_spec = {
            "name": "EXAMPLE",  # Token symbol
            "sz_decimals": 2,   # Size decimals
            "wei_decimals": 18,  # Wei decimals
            "max_gas": 100000,   # Max gas
            "full_name": "Example Token"  # Optional
        }
        
        logger.info(f"1. Register Token: {json.dumps(token_spec, indent=2)}")
        
        register_token_action = {
            "type": "spotDeploy",
            "registerToken2": {
                "spec": {
                    "name": token_spec["name"],
                    "szDecimals": token_spec["sz_decimals"],
                    "weiDecimals": token_spec["wei_decimals"]
                },
                "maxGas": token_spec["max_gas"],
                "fullName": token_spec["full_name"]
            }
        }
        
        # Simulate token index returned
        token_index = 5  # In real implementation, this comes from the API response
        
        # Step 2: User Genesis - Initial token distribution
        user_genesis = {
            "user_and_wei": [
                [self.address, "1000000000000000000000000"]  # 1,000,000 tokens to deployer
            ],
            "existing_token_and_wei": []
        }
        
        logger.info(f"2. User Genesis: Distributing tokens to {len(user_genesis['user_and_wei'])} users")
        
        user_genesis_action = {
            "type": "spotDeploy",
            "userGenesis": {
                "token": token_index,
                "userAndWei": user_genesis["user_and_wei"],
                "existingTokenAndWei": user_genesis["existing_token_and_wei"]
            }
        }
        
        # Step 3: Genesis - Set max supply
        genesis_details = {
            "max_supply": "1000000000000000000000000",  # 1,000,000 tokens total
            "no_hyperliquidity": False
        }
        
        logger.info(f"3. Genesis: Setting max supply to {int(genesis_details['max_supply']) / 10**18} tokens")
        
        genesis_action = {
            "type": "spotDeploy",
            "genesis": {
                "token": token_index,
                "maxSupply": genesis_details["max_supply"],
                "noHyperliquidity": genesis_details["no_hyperliquidity"]
            }
        }
        
        # Step 4: Register Spot - Pair with USDC
        spot_registration = {
            "base_token": 0  # USDC
        }
        
        logger.info(f"4. Register Spot: Pairing with token index {spot_registration['base_token']} (USDC)")
        
        register_spot_action = {
            "type": "spotDeploy",
            "registerSpot": {
                "tokens": [
                    spot_registration["base_token"],
                    token_index
                ]
            }
        }
        
        # Simulate spot index returned
        spot_index = 3  # In real implementation, this comes from the API response
        
        # Step 5: Register Hyperliquidity - Market making parameters
        hyperliquidity_settings = {
            "start_price": "0.1",     # $0.10 per token
            "order_size": "100",      # 100 tokens per order
            "n_orders": 20,           # 20 orders on each side
            "n_seeded_levels": 5      # 5 levels seeded with USDC
        }
        
        logger.info(f"5. Register Hyperliquidity: Starting price ${hyperliquidity_settings['start_price']}")
        
        hyperliq_action = {
            "type": "spotDeploy",
            "registerHyperliquidity": {
                "spot": spot_index,
                "startPx": hyperliquidity_settings["start_price"],
                "orderSz": hyperliquidity_settings["order_size"],
                "nOrders": hyperliquidity_settings["n_orders"],
                "nSeededLevels": hyperliquidity_settings["n_seeded_levels"]
            }
        }
        
        # Optional Step 6: Set deployer fee share
        fee_share_action = {
            "type": "spotDeploy",
            "setDeployerTradingFeeShare": {
                "token": token_index,
                "share": "0.5%"  # 0.5% fee share
            }
        }
        
        logger.info("6. Set Deployer Fee Share: 0.5%")
        
        return {
            "status": "simulated",
            "token_spec": token_spec,
            "user_genesis": user_genesis,
            "genesis_details": genesis_details,
            "spot_registration": spot_registration,
            "hyperliquidity_settings": hyperliquidity_settings,
            "token_index": token_index,
            "spot_index": spot_index,
            "message": "This is a simulated HIP-1 token deployment. In real implementation, these actions would be executed sequentially."
        }
    
    async def demonstrate_hip3_perp_dex_deployment(self) -> Dict:
        """
        Demonstrate deploying a perpetual DEX following HIP-3 standard
        """
        logger.info("== Example: HIP-3 Perpetual DEX Deployment ==")
        
        # Prepare parameters
        dex_name = "EXDEX"
        full_name = "Example Perpetual DEX"
        asset_name = "BTC"
        sz_decimals = 6
        oracle_price = "65000"
        max_gas = 500000
        
        # Construct registerAsset action
        schema_input = {
            "fullName": full_name,
            "collateralToken": 0,  # USDC
            "oracleUpdater": self.address  # Deployer is oracle updater
        }
        
        coin_symbol = f"{dex_name}:{asset_name}"
        
        asset_request = {
            "coin": coin_symbol,
            "szDecimals": sz_decimals,
            "oraclePx": oracle_price,
            "marginTableId": 10,  # Standard margin table ID
            "onlyIsolated": False
        }
        
        register_action = {
            "type": "perpDeploy",
            "registerAsset": {
                "maxGas": max_gas,
                "assetRequest": asset_request,
                "dex": dex_name,
                "schema": schema_input
            }
        }
        
        logger.info(f"Deploying perpetual DEX '{dex_name}' with first asset '{asset_name}'")
        logger.info(f"Initial asset price: ${oracle_price}")
        
        # In real implementation, this would be sent to the API:
        # nonce = int(time.time() * 1000)
        # response = self.exchange._post_exchange(register_action, nonce)
        
        return {
            "status": "simulated",
            "dex_name": dex_name,
            "asset_name": asset_name,
            "coin_symbol": coin_symbol,
            "register_action": register_action,
            "message": "This is a simulated HIP-3 perp DEX deployment. In real implementation, this action would be executed."
        }
    
    async def demonstrate_add_perp_asset(self) -> Dict:
        """
        Demonstrate adding an asset to an existing perpetual DEX
        """
        logger.info("== Example: Add Asset to Perpetual DEX ==")
        
        # Prepare parameters
        dex_name = "EXDEX"
        asset_name = "ETH"
        sz_decimals = 6
        oracle_price = "3000"
        max_gas = 200000
        
        coin_symbol = f"{dex_name}:{asset_name}"
        
        asset_request = {
            "coin": coin_symbol,
            "szDecimals": sz_decimals,
            "oraclePx": oracle_price,
            "marginTableId": 10,  # Standard margin table ID
            "onlyIsolated": False
        }
        
        register_action = {
            "type": "perpDeploy",
            "registerAsset": {
                "maxGas": max_gas,
                "assetRequest": asset_request,
                "dex": dex_name
                # No schema for additional assets
            }
        }
        
        logger.info(f"Adding asset '{asset_name}' to existing DEX '{dex_name}'")
        logger.info(f"Initial asset price: ${oracle_price}")
        
        # In real implementation, this would be sent to the API:
        # nonce = int(time.time() * 1000)
        # response = self.exchange._post_exchange(register_action, nonce)
        
        return {
            "status": "simulated",
            "dex_name": dex_name,
            "asset_name": asset_name,
            "coin_symbol": coin_symbol,
            "register_action": register_action,
            "message": "This is a simulated asset addition. In real implementation, this action would be executed."
        }
    
    async def demonstrate_update_oracle_prices(self) -> Dict:
        """
        Demonstrate updating oracle prices for a perpetual DEX
        """
        logger.info("== Example: Update Oracle Prices ==")
        
        # Prepare parameters
        dex_name = "EXDEX"
        oracle_prices = {
            "BTC": "66000",
            "ETH": "3100",
            "SOL": "150"
        }
        
        # Optional mark prices (if different from oracle)
        mark_prices = {
            "BTC": "66050",
            "ETH": "3105",
            "SOL": "151"
        }
        
        # Convert dictionary to list of tuples for oracle prices
        oracle_px_list = []
        for asset, price in sorted(oracle_prices.items()):
            coin_symbol = f"{dex_name}:{asset}"
            oracle_px_list.append([coin_symbol, price])
        
        # Convert dictionary to list of tuples for mark prices
        mark_px_list = []
        for asset, price in sorted(mark_prices.items()):
            coin_symbol = f"{dex_name}:{asset}"
            mark_px_list.append([coin_symbol, price])
        
        # Construct setOracle action
        set_oracle_action = {
            "type": "perpDeploy",
            "setOracle": {
                "dex": dex_name,
                "oraclePxs": oracle_px_list,
                "markPxs": mark_px_list
            }
        }
        
        logger.info(f"Updating oracle prices for DEX '{dex_name}'")
        for asset, price in oracle_prices.items():
            logger.info(f"{asset} oracle price: ${price}")
        
        # In real implementation, this would be sent to the API:
        # nonce = int(time.time() * 1000)
        # response = self.exchange._post_exchange(set_oracle_action, nonce)
        
        return {
            "status": "simulated",
            "dex_name": dex_name,
            "oracle_prices": oracle_prices,
            "mark_prices": mark_prices,
            "set_oracle_action": set_oracle_action,
            "message": "This is a simulated oracle price update. In real implementation, this action would be executed."
        }


async def run_asset_deployment_examples():
    """Run all asset deployment examples"""
    deployment_examples = AssetDeploymentExamples()
    
    # Example 1: HIP-1 token deployment
    hip1_result = await deployment_examples.demonstrate_hip1_token_deployment()
    logger.info(f"HIP-1 deployment result: {json.dumps(hip1_result, indent=2)}")
    
    # Example 2: HIP-3 perpetual DEX deployment
    hip3_result = await deployment_examples.demonstrate_hip3_perp_dex_deployment()
    logger.info(f"HIP-3 deployment result: {json.dumps(hip3_result, indent=2)}")
    
    # Example 3: Add asset to perp DEX
    add_asset_result = await deployment_examples.demonstrate_add_perp_asset()
    logger.info(f"Add asset result: {json.dumps(add_asset_result, indent=2)}")
    
    # Example 4: Update oracle prices
    oracle_result = await deployment_examples.demonstrate_update_oracle_prices()
    logger.info(f"Oracle update result: {json.dumps(oracle_result, indent=2)}")


if __name__ == "__main__":
    asyncio.run(run_asset_deployment_examples())
