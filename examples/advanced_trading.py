"""
Advanced trading examples for Hyperliquid API:
- TWAP orders
- Builder fee approval
- Reserving additional actions
"""

import asyncio
import time
import json
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

import example_utils  # Import the standard example utilities

async def main():
    """Run advanced trading examples"""
    print("Hyperliquid Advanced Trading Examples")
    
    # Set up connection using standard pattern
    address, info, exchange = example_utils.setup(
        base_url=constants.TESTNET_API_URL,  # Use testnet by default
        skip_ws=True
    )
    
    # Show connected address
    print(f"Connected address: {address}")
    
    # Example 1: Place a TWAP order
    print("\n=== Example 1: TWAP Order ===")
    
    # Get ETH asset ID
    meta = info.meta()
    eth_id = None
    for i, asset in enumerate(meta.get("universe", [])):
        if asset.get("name") == "ETH":
            eth_id = i
            break
    
    if eth_id is not None:
        # Place TWAP buy order: 0.01 ETH over 10 minutes with randomization
        twap_action = {
            "type": "twapOrder",
            "twap": {
                "a": eth_id,       # asset ID
                "b": True,         # isBuy = true
                "s": "0.01",       # size = 0.01 ETH
                "r": False,        # reduceOnly = false
                "m": 10,           # duration = 10 minutes
                "t": True          # randomize = true
            }
        }
        
        # Generate nonce
        nonce = int(time.time() * 1000)
        
        # Post the TWAP order
        print("Placing TWAP buy order for 0.01 ETH over 10 minutes...")
        twap_result = exchange._post_exchange(twap_action, nonce)
        print(f"TWAP order result: {json.dumps(twap_result, indent=2)}")
        
        # Get TWAP ID if available
        twap_id = None
        if (twap_result.get("status") == "ok" and 
            "response" in twap_result and 
            "data" in twap_result["response"] and
            "status" in twap_result["response"]["data"] and
            "running" in twap_result["response"]["data"]["status"]):
            twap_id = twap_result["response"]["data"]["status"]["running"]["twapId"]
            print(f"TWAP ID: {twap_id}")
        
        # Wait 10 seconds, then cancel the TWAP order
        if twap_id:
            print("Waiting 10 seconds before cancelling...")
            await asyncio.sleep(10)
            
            # Cancel TWAP order
            cancel_action = {
                "type": "twapCancel",
                "a": eth_id,       # asset ID
                "t": twap_id       # TWAP ID
            }
            
            # Generate new nonce
            nonce = int(time.time() * 1000)
            
            # Cancel the TWAP order
            print(f"Cancelling TWAP order with ID: {twap_id}")
            cancel_result = exchange._post_exchange(cancel_action, nonce)
            print(f"TWAP cancel result: {json.dumps(cancel_result, indent=2)}")
    else:
        print("Could not find ETH in available assets")
    
    # Example 2: Approve Builder Fee
    print("\n=== Example 2: Approve Builder Fee ===")
    
    # Sample builder address (use a real address in production)
    builder_address = "0x1234567890123456789012345678901234567890"
    max_fee_rate = "0.001%"
    
    # Current timestamp
    timestamp = int(time.time() * 1000)
    
    # Determine environment details
    hyperliquid_chain = "Testnet"  # Use "Mainnet" for production
    signature_chain_id = "0x66eed"  # Use "0xa4b1" for mainnet
    
    # Construct builder fee approval action
    action = {
        "type": "approveBuilderFee",
        "hyperliquidChain": hyperliquid_chain,
        "signatureChainId": signature_chain_id,
        "maxFeeRate": max_fee_rate,
        "builder": builder_address,
        "nonce": timestamp
    }
    
    # Generate nonce (same as timestamp)
    nonce = timestamp
    
    print(f"Approving builder fee for {builder_address} at max rate: {max_fee_rate}")
    # Note: This is commented out by default to avoid actual approvals in examples
    # fee_result = exchange._post_exchange(action, nonce)
    # print(f"Fee approval result: {json.dumps(fee_result, indent=2)}")
    print("(Action not executed in example - uncomment to test with a real builder address)")
    
    # Example 3: Reserve Additional Actions
    print("\n=== Example 3: Reserve Additional Actions ===")
    
    # Construct reserve action
    reserve_action = {
        "type": "reserveAdditionalActions"
    }
    
    # Generate nonce
    nonce = int(time.time() * 1000)
    
    print("Reserving additional actions (cost: 0.0005 USDC)")
    # Note: This is commented out by default to avoid charges
    # reserve_result = exchange._post_exchange(reserve_action, nonce)
    # print(f"Reserve result: {json.dumps(reserve_result, indent=2)}")
    print("(Action not executed in example - uncomment to test with actual USDC)")
    
    print("\nAdvanced Trading Examples Complete")

if __name__ == "__main__":
    asyncio.run(main())
