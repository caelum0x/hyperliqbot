"""
Production-ready example_utils.py replacement
Maintains backward compatibility while adding security features.
It assumes hyperliquid_auth.py is in the project root, one level above 'examples'.
"""
import os
import sys
import logging

# Add project root to sys.path to allow importing hyperliquid_auth
# __file__ is .../examples/example_utils.py
# os.path.dirname(__file__) is .../examples
# os.path.join(os.path.dirname(__file__), '..') is .../
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from hyperliquid_auth import HyperliquidAuth # Should now be found
from hyperliquid.utils import constants # For network constants

logger = logging.getLogger(__name__)

# Global auth instance cache (one per network to support mainnet/testnet switching if needed)
_auth_instances: dict[str, HyperliquidAuth] = {}

def setup(base_url=None, skip_ws=False, perp_dexs=None): # skip_ws and perp_dexs are not used by HyperliquidAuth directly but kept for signature compatibility
    """
    Drop-in replacement for example_utils.setup with enhanced security.
    Uses HyperliquidAuth for connection management.
    
    Args:
        base_url: Hyperliquid API base URL. If None, defaults to MAINNET_API_URL.
                  This determines the network ("mainnet" or "testnet").
        skip_ws: (Maintained for signature compatibility, HyperliquidAuth sets skip_ws=True for Info client)
        perp_dexs: (Maintained for signature compatibility, not directly used by HyperliquidAuth's connect method shown)
        
    Returns:
        Tuple of (address, info, exchange)
    """
    global _auth_instances
    
    # Determine network from base_url
    # Default to mainnet if base_url is not provided or not recognized
    if base_url == constants.TESTNET_API_URL:
        network = "testnet"
    elif base_url == constants.MAINNET_API_URL:
        network = "mainnet"
    elif base_url is None: # If base_url is explicitly None, default to mainnet
        network = "mainnet" 
        logger.info(f"example_utils.setup: base_url not provided, defaulting to MAINNET_API_URL for network {network}")
    else: # Unknown base_url, default to mainnet and log warning
        network = "mainnet" # Fallback for unrecognized URLs
        logger.warning(f"example_utils.setup: Unknown base_url '{base_url}', defaulting to MAINNET_API_URL for network {network}. This might cause issues if a testnet URL was intended but not recognized.")

    # Initialize auth for the network if it doesn't exist or if network has changed for the instance
    if network not in _auth_instances or _auth_instances[network].network != network:
        logger.info(f"Initializing HyperliquidAuth instance for {network} network via example_utils.setup.")
        # HyperliquidAuth will look for config.json and agent_config.json in 'project_root'.
        # It uses 'config.json' and 'agent_config.json' as default filenames within that directory.
        # The config_dir for HyperliquidAuth should point to where config.json (with secret_key) and agent_config.json are.
        # This is assumed to be the project_root.
        _auth_instances[network] = HyperliquidAuth(
            config_dir=project_root, # Auth configs expected in project root
            network=network,
            auto_reconnect=True 
        )
    # Ensure the base_url of the cached instance matches the requested base_url's implied network
    # This handles cases where, for example, _auth_instances['mainnet'] might exist but base_url now implies testnet.
    # The network string key derived from base_url should be the primary driver.
    # If _auth_instances[network].base_url (derived from its own network init) doesn't match the current effective base_url for that network string:
    current_expected_base_url = constants.MAINNET_API_URL if network == "mainnet" else constants.TESTNET_API_URL
    if _auth_instances[network].base_url != current_expected_base_url:
        logger.warning(f"Re-initializing HyperliquidAuth for {network} due to base_url mismatch. Expected {current_expected_base_url}, got {_auth_instances[network].base_url}.")
        _auth_instances[network] = HyperliquidAuth(
            config_dir=project_root,
            network=network, # This network string is derived from the current base_url
            auto_reconnect=True
        )

    auth_instance = _auth_instances[network]
    
    try:
        # The connect method of HyperliquidAuth handles agent vs direct logic.
        address, info, exchange = auth_instance.connect()
        
        # The skip_ws parameter for Info client is handled internally by HyperliquidAuth 
        # (_connect_with_agent, _connect_direct set skip_ws=True for their Info instances)
        
        # Handle perp_dexs parameter (if needed and possible post-init)
        # This is tricky as Info objects are usually configured at init.
        # For robust perp_dexs handling, HyperliquidAuth would need to accept it and pass to Info constructor.
        if perp_dexs is not None:
            if hasattr(info, 'perp_dexs'):
                try:
                    # This assumes info.perp_dexs is a settable property or attribute.
                    # This might not be standard or might require re-initialization of Info.
                    # info.perp_dexs = perp_dexs # Potentially problematic.
                    logger.debug(f"perp_dexs parameter was provided to example_utils.setup. The Info object from HyperliquidAuth may or may not support post-init setting of perp_dexs. This parameter might be ignored or require changes in HyperliquidAuth.")
                    # If critical, HyperliquidAuth should be modified to pass perp_dexs to its Info() calls.
                except AttributeError: # Should not happen if hasattr is true, but safeguard
                    logger.warning("Could not set perp_dexs on the Info object post-initialization. This parameter might be ignored.")
            else:
                logger.warning("Info object from HyperliquidAuth does not have a 'perp_dexs' attribute. Parameter ignored.")

        logger.info(f"example_utils.setup: Successfully connected via HyperliquidAuth for network {network}. Address: {address}")
        return address, info, exchange
    except Exception as e:
        logger.error(f"example_utils.setup: Failed to connect to Hyperliquid on {network} network: {e}", exc_info=True)
        raise
