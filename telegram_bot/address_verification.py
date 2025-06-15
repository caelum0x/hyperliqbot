"""
Address verification and collection system
Implements signature-based ownership proof for security
"""
import asyncio
import logging
import time
import hashlib
import secrets
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from hyperliquid.info import Info
from eth_account.messages import encode_defunct
from eth_account import Account

logger = logging.getLogger(__name__)

class AddressVerificationManager:
    """
    🛡️ SECURITY: Proper address verification with signature proof
    """
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.info = Info(base_url)
        self.pending_verifications = {}  # {user_id: verification_data}
        self.verified_addresses = {}     # {user_id: address}
        self.verification_timeout = 300  # 5 minutes
        
        logger.info("AddressVerificationManager initialized")
    
    async def start_address_verification(self, user_id: int, claimed_address: str) -> Dict:
        """
        Start the address verification process
        
        Args:
            user_id: Telegram user ID
            claimed_address: Address the user claims to own
            
        Returns:
            Dict with verification challenge or error
        """
        try:
            # Validate address format
            if not self._validate_address_format(claimed_address):
                return {
                    "status": "error",
                    "message": "Invalid address format. Must be 42 characters starting with 0x."
                }
            
            # Check if address exists on Hyperliquid
            try:
                user_state = self.info.user_state(claimed_address)
                if not user_state or not isinstance(user_state, dict):
                    return {
                        "status": "error",
                        "message": "Address not found on Hyperliquid. Ensure you have an active account."
                    }
            except Exception as e:
                logger.error(f"Error checking address on Hyperliquid: {e}")
                return {
                    "status": "error",
                    "message": "Could not verify address on Hyperliquid. Please try again."
                }
            
            # Generate verification challenge
            challenge = self._generate_challenge(user_id)
            expiry = datetime.now() + timedelta(seconds=self.verification_timeout)
            
            # Store verification data
            self.pending_verifications[user_id] = {
                "address": claimed_address.lower(),
                "challenge": challenge,
                "expiry": expiry,
                "created_at": datetime.now()
            }
            
            # Create message to sign
            message = f"Hyperliquid Bot Verification\nChallenge: {challenge}\nUser ID: {user_id}\nTime: {int(time.time())}"
            
            return {
                "status": "success",
                "challenge": challenge,
                "message_to_sign": message,
                "address": claimed_address,
                "expiry_minutes": self.verification_timeout // 60,
                "instructions": (
                    "To verify ownership of this address, please sign the message above with your wallet.\n\n"
                    "**How to sign:**\n"
                    "1. Copy the message above\n"
                    "2. Use your wallet's 'Sign Message' feature\n"
                    "3. Paste the signature back to this bot\n\n"
                    "**Common wallets:**\n"
                    "• MetaMask: Account menu → Sign Message\n"
                    "• WalletConnect: Use signing feature\n"
                    "• Hardware wallets: Use companion app"
                )
            }
            
        except Exception as e:
            logger.error(f"Error starting address verification: {e}")
            return {
                "status": "error",
                "message": f"Verification error: {str(e)}"
            }
    
    async def verify_signature(self, user_id: int, signature: str) -> Dict:
        """
        Verify the signature provided by the user
        
        Args:
            user_id: Telegram user ID
            signature: Signature provided by user
            
        Returns:
            Dict with verification result
        """
        try:
            # Check if user has pending verification
            if user_id not in self.pending_verifications:
                return {
                    "status": "error",
                    "message": "No pending verification found. Please start verification process first."
                }
            
            verification_data = self.pending_verifications[user_id]
            
            # Check if verification has expired
            if datetime.now() > verification_data["expiry"]:
                del self.pending_verifications[user_id]
                return {
                    "status": "error",
                    "message": "Verification expired. Please start the process again."
                }
            
            # Reconstruct the message that should have been signed
            challenge = verification_data["challenge"]
            created_timestamp = int(verification_data["created_at"].timestamp())
            message = f"Hyperliquid Bot Verification\nChallenge: {challenge}\nUser ID: {user_id}\nTime: {created_timestamp}"
            
            # Verify signature
            try:
                # Encode message for verification
                encoded_message = encode_defunct(text=message)
                
                # Recover address from signature
                recovered_address = Account.recover_message(encoded_message, signature=signature)
                
                # Check if recovered address matches claimed address
                claimed_address = verification_data["address"]
                if recovered_address.lower() != claimed_address.lower():
                    return {
                        "status": "error",
                        "message": f"Signature verification failed. Expected address {claimed_address}, got {recovered_address}"
                    }
                
                # Verification successful
                self.verified_addresses[user_id] = claimed_address
                del self.pending_verifications[user_id]
                
                logger.info(f"Address verification successful for user {user_id}: {claimed_address}")
                
                return {
                    "status": "success",
                    "message": "Address ownership verified successfully!",
                    "verified_address": claimed_address
                }
                
            except Exception as sig_error:
                logger.error(f"Signature verification error: {sig_error}")
                return {
                    "status": "error",
                    "message": "Invalid signature format or verification failed. Please try again."
                }
                
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return {
                "status": "error",
                "message": f"Verification error: {str(e)}"
            }
    
    def get_verified_address(self, user_id: int) -> Optional[str]:
        """Get verified address for a user"""
        return self.verified_addresses.get(user_id)
    
    def is_address_verified(self, user_id: int) -> bool:
        """Check if user has a verified address"""
        return user_id in self.verified_addresses
    
    def _generate_challenge(self, user_id: int) -> str:
        """Generate a unique challenge for verification"""
        timestamp = str(int(time.time()))
        random_bytes = secrets.token_bytes(16)
        data = f"{user_id}_{timestamp}_{random_bytes.hex()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def _validate_address_format(self, address: str) -> bool:
        """Validate Ethereum address format"""
        if not address or not isinstance(address, str):
            return False
        
        # Must start with 0x and be 42 characters total
        if not address.startswith("0x") or len(address) != 42:
            return False
        
        # Must contain only valid hex characters
        try:
            int(address[2:], 16)
            return True
        except ValueError:
            return False
    
    async def cleanup_expired_verifications(self):
        """Cleanup expired verification attempts"""
        try:
            current_time = datetime.now()
            expired_users = []
            
            for user_id, data in self.pending_verifications.items():
                if current_time > data["expiry"]:
                    expired_users.append(user_id)
            
            for user_id in expired_users:
                del self.pending_verifications[user_id]
                logger.info(f"Cleaned up expired verification for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired verifications: {e}")
    
    async def start_cleanup_task(self):
        """Start background task to cleanup expired verifications"""
        while True:
            try:
                await self.cleanup_expired_verifications()
                await asyncio.sleep(60)  # Cleanup every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(60)
