"""
Examples demonstrating Hyperliquid bridge operations with Arbitrum
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

class BridgeExamples:
    """Examples for Hyperliquid bridge operations"""
    
    def __init__(self, base_url=None):
        """Initialize with Hyperliquid connection"""
        # Set up connection using standard pattern
        self.address, self.info, self.exchange = example_utils.setup(
            base_url=base_url or constants.TESTNET_API_URL,
            skip_ws=True
        )
        
        # Get network info
        self.is_mainnet = self.exchange.base_url == constants.MAINNET_API_URL
        self.bridge_address = (
            "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7" if self.is_mainnet 
            else "0x08cfc1B6b2dCF36A1480b99353A354AA8AC56f89"
        )
        
        logger.info(f"Bridge examples initialized with address: {self.address}")
        logger.info(f"Network: {'Mainnet' if self.is_mainnet else 'Testnet'}")
        logger.info(f"Bridge contract: {self.bridge_address}")
    
    async def demonstrate_bridge_deposit(self, amount: float = 10.0) -> Dict:
        """
        Demonstrate depositing USDC to Hyperliquid through the Arbitrum bridge
        
        Args:
            amount: Amount of USDC to deposit (min 5 USDC)
        """
        logger.info(f"== Example: Bridge Deposit {amount} USDC ==")
        
        # Check minimum deposit
        if amount < 5.0:
            logger.warning("Warning: Minimum deposit amount is 5 USDC. Lesser amounts will be lost.")
            logger.info("Adjusting deposit amount to 5 USDC")
            amount = 5.0
        
        # First check USDC balance on Arbitrum
        usdc_balance = self._get_arbitrum_usdc_balance()
        logger.info(f"Current Arbitrum USDC balance: {usdc_balance}")
        
        if usdc_balance < amount:
            logger.error(f"Insufficient USDC balance. Have {usdc_balance}, need {amount}")
            return {"status": "error", "message": "Insufficient USDC balance"}
        
        # In a real implementation, this would trigger a blockchain transaction
        # Here we show the payload that would be sent
        logger.info(f"Would send {amount} USDC to bridge contract: {self.bridge_address}")
        logger.info("This would be a standard ERC20 transfer on Arbitrum")
        
        # Simulate deposit (in real implementation, this would be a blockchain call)
        simulated_tx_hash = f"0x{''.join(['abcdef0123456789'[hash(str(time.time())) % 16] for _ in range(64)])}"
        
        return {
            "status": "simulated",
            "bridge_address": self.bridge_address,
            "amount": amount,
            "tx_hash": simulated_tx_hash,
            "message": "This is a simulated deposit. In real implementation, a transaction would be sent."
        }
    
    async def demonstrate_bridge_withdrawal(self, amount: float = 10.0) -> Dict:
        """
        Demonstrate withdrawing USDC from Hyperliquid to Arbitrum
        
        Args:
            amount: Amount of USDC to withdraw
        """
        logger.info(f"== Example: Bridge Withdrawal {amount} USDC ==")
        
        # Check Hyperliquid balance
        user_state = self.info.user_state(self.address)
        withdrawable = float(user_state.get("withdrawable", 0))
        
        logger.info(f"Current withdrawable balance: {withdrawable} USDC")
        
        if withdrawable < amount:
            logger.error(f"Insufficient withdrawable balance. Have {withdrawable}, need {amount}")
            return {"status": "error", "message": "Insufficient withdrawable balance"}
        
        # Prepare withdrawal action
        timestamp = int(time.time())
        hyperliquid_chain = "Mainnet" if self.is_mainnet else "Testnet"
        signature_chain_id = "0xa4b1" if self.is_mainnet else "0x66eed"
        destination = self.address  # Usually the same as sender address
        
        # Construct withdraw action (this is the real payload structure)
        action = {
            "type": "withdraw3",
            "signatureChainId": signature_chain_id,
            "hyperliquidChain": hyperliquid_chain,
            "destination": destination,
            "amount": str(amount),
            "time": timestamp
        }
        
        # Generate nonce (must match time)
        nonce = timestamp
        
        logger.info(f"Withdraw payload: {json.dumps(action, indent=2)}")
        logger.info(f"Using nonce: {nonce} (same as time)")
        
        # In real implementation, we would execute:
        # response = self.exchange._post_exchange(action, nonce)
        
        # For this example, we just return the payload
        return {
            "status": "payload_prepared",
            "action": action,
            "nonce": nonce,
            "message": "This is the withdrawal payload. In real implementation, it would be signed and sent."
        }
    
    async def demonstrate_permit_deposit(self, owner: str = None, amount: float = 10.0) -> Dict:
        """
        Demonstrate depositing USDC with permit functionality
        
        Args:
            owner: Address of the user with funds (defaults to self.address)
            amount: Amount of USDC to deposit (min 5 USDC)
        """
        logger.info(f"== Example: Permit Deposit {amount} USDC ==")
        
        # Use self address if no owner provided
        owner = owner or self.address
        
        # Check minimum deposit
        if amount < 5.0:
            logger.warning("Warning: Minimum deposit amount is 5 USDC. Lesser amounts will be lost.")
            logger.info("Adjusting deposit amount to 5 USDC")
            amount = 5.0
        
        # Create permit payload
        nonce = 0  # In real implementation, get this from the USDC contract
        deadline = int(time.time()) + 3600  # 1 hour from now
        
        # Prepare permit payload
        permit_payload = {
            "owner": owner,
            "spender": self.bridge_address,
            "value": int(amount * 1_000_000),  # Convert to USDC micro units
            "nonce": nonce,
            "deadline": deadline
        }
        
        # Prepare domain data
        domain = {
            "name": "USD Coin" if self.is_mainnet else "USDC2",
            "version": "2" if self.is_mainnet else "1",
            "chainId": 42161 if self.is_mainnet else 421614,  # Arbitrum / Arbitrum Goerli
            "verifyingContract": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831" if self.is_mainnet else "0x1baAbB04529D43a73232B713C0FE471f7c7334d5"
        }
        
        # Permit types
        permit_types = {
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"}
            ]
        }
        
        logger.info(f"Permit deposit payload: {json.dumps(permit_payload, indent=2)}")
        logger.info(f"Permit domain: {json.dumps(domain, indent=2)}")
        logger.info("In real implementation, this would be signed with EIP-712 and sent to the bridge")
        
        return {
            "status": "payload_prepared",
            "permit_payload": permit_payload,
            "domain": domain,
            "types": permit_types,
            "message": "This is the permit payload. In real implementation, it would be signed and sent."
        }
    
    def _get_arbitrum_usdc_balance(self) -> float:
        """Simulate getting USDC balance on Arbitrum"""
        # In a real implementation, this would query the Arbitrum RPC
        # For this example, we return a simulated balance
        return 100.0  # Simulated 100 USDC balance


async def run_bridge_examples():
    """Run all bridge examples"""
    bridge_examples = BridgeExamples()
    
    # Example 1: Bridge deposit
    deposit_result = await bridge_examples.demonstrate_bridge_deposit(10.0)
    logger.info(f"Deposit result: {json.dumps(deposit_result, indent=2)}")
    
    # Example 2: Bridge withdrawal
    withdrawal_result = await bridge_examples.demonstrate_bridge_withdrawal(5.0)
    logger.info(f"Withdrawal result: {json.dumps(withdrawal_result, indent=2)}")
    
    # Example 3: Permit deposit
    permit_result = await bridge_examples.demonstrate_permit_deposit(amount=7.5)
    logger.info(f"Permit result: {json.dumps(permit_result, indent=2)}")


if __name__ == "__main__":
    asyncio.run(run_bridge_examples())
