#!/usr/bin/env python3
"""
Production setup script for Hyperliquid agent wallet
Creates a secure agent wallet for trading operations
"""
import os
import json
import logging
import argparse
import getpass
import time # Added for default agent name timestamp

# Assuming hyperliquid_auth.py is in the same directory or Python path
from hyperliquid_auth import HyperliquidAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("setup_agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def setup_config(config_path, force=False):
    """Set up main config file with private key"""
    if os.path.exists(config_path) and not force:
        logger.info(f"Config file {config_path} already exists")
        if input(f"Overwrite existing config file '{config_path}'? (y/n): ").lower() != 'y':
            logger.info(f"Skipping overwrite of {config_path}.")
            return False # Indicates not to proceed with overwriting
    
    # Get private key securely
    private_key = ""
    while not private_key:
        private_key = getpass.getpass("Enter your Ethereum private key (for the main account, 64 hex chars, optionally starting with 0x): ")
        if not private_key:
            logger.warning("Private key cannot be empty.")
            if input("Try again? (y/n): ").lower() != 'y':
                return False # Abort if user doesn't want to retry

    # Validate format (basic check)
    is_valid_format = (private_key.startswith("0x") and len(private_key) == 66) or \
                      (not private_key.startswith("0x") and len(private_key) == 64)

    if not is_valid_format:
        logger.warning("Private key format appears invalid. It should be a 64-character hex string, optionally prefixed with '0x'.")
        if input("Continue anyway with the provided key? (y/n): ").lower() != 'y':
            return False
    
    # Add 0x prefix if missing and length is 64
    if not private_key.startswith("0x") and len(private_key) == 64:
        private_key = "0x" + private_key
    
    # Create config content
    # This script creates a config focused on the secret key.
    # If this config_path points to the main bot's config.json,
    # it will overwrite it. Users should be cautious or use --config-dir.
    config_content = {
        "secret_key": private_key,
        "account_address": ""  # This can be derived or manually set if needed for specific vault scenarios
    }
    
    # Save config with secure permissions
    try:
        # Ensure directory exists if config_path includes directories
        os.makedirs(os.path.dirname(config_path) or ".", exist_ok=True)
        
        with open(config_path, "w") as f:
            json.dump(config_content, f, indent=2)
        
        # Set secure file permissions
        os.chmod(config_path, 0o600)  # Read/write for owner only
        logger.info(f"Config saved to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Could not save or set permissions for {config_path}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Set up Hyperliquid main config (e.g., config.json for key) and agent wallet (agent_config.json).",
        formatter_class=argparse.RawTextHelpFormatter # Allows for better help text formatting
    )
    parser.add_argument(
        "--network", 
        choices=["mainnet", "testnet"], 
        default="mainnet", 
        help="Network to use for the agent (default: mainnet)"
    )
    parser.add_argument(
        "--config-dir", 
        default=".", 
        help="Directory where key config (e.g., config.json) and agent_config.json will be stored (default: current directory)"
    )
    parser.add_argument(
        "--main-config-file", # Renamed from --config-path for clarity
        default="config.json",
        help="Filename for the main private key configuration (default: config.json within --config-dir)"
    )
    parser.add_argument(
        "--agent-config-file",
        default="agent_config.json",
        help="Filename for the agent wallet configuration (default: agent_config.json within --config-dir)"
    )
    parser.add_argument(
        "--force-main-config", # Renamed from --force for clarity
        action="store_true", 
        help="Force overwrite of existing main config file."
    )
    parser.add_argument(
        "--force-agent-config", 
        action="store_true", 
        help="Force creation of a new agent, potentially overwriting existing agent_config.json."
    )
    parser.add_argument(
        "--agent-name", 
        default=None, 
        help="Custom name for the agent wallet (e.g., 'prod_bot_01'). If not provided, one will be prompted or generated."
    )
    parser.add_argument(
        "--skip-agent",
        action="store_true",
        help="Only set up the main config file (for the private key) and skip agent creation."
    )

    args = parser.parse_args()
    
    # Ensure config directory exists
    config_dir_abs = os.path.abspath(args.config_dir)
    os.makedirs(config_dir_abs, exist_ok=True)
    
    # Paths for config files
    main_config_full_path = os.path.join(config_dir_abs, args.main_config_file)
    agent_config_full_path = os.path.join(config_dir_abs, args.agent_config_file) # Used for checking existence

    logger.info(f"Configuration directory: {config_dir_abs}")
    logger.info(f"Main key config file: {main_config_full_path}")
    if not args.skip_agent:
        logger.info(f"Agent config file: {agent_config_full_path}")
        logger.info(f"Agent network: {args.network}")

    # Set up main config.json (for the private key) if needed
    # The setup_config function handles the 'force' logic internally.
    if not os.path.exists(main_config_full_path) or args.force_main_config:
        logger.info(f"Setting up main key configuration file: {main_config_full_path}")
        if not setup_config(main_config_full_path, args.force_main_config): # Pass force flag
            logger.error("Main key config setup failed or was aborted. Cannot proceed with agent creation if it was intended.")
            if not args.skip_agent:
                 return # Stop if agent creation was intended but main config failed
            else:
                 logger.info("Skipping agent creation as requested.")
                 return # Stop after main config setup if --skip-agent
    elif not os.path.exists(main_config_full_path): # Should be caught by above, but safeguard
        logger.error(f"Main key config file {main_config_full_path} is required. Please create it or run with --force-main-config.")
        return
    else:
        logger.info(f"Main key config file {main_config_full_path} already exists. Use --force-main-config to overwrite.")

    if args.skip_agent:
        logger.info("Agent creation skipped as per --skip-agent flag.")
        return

    # Check if agent wallet already exists
    if os.path.exists(agent_config_full_path) and not args.force_agent_config:
        logger.info(f"Agent wallet config {agent_config_full_path} already exists.")
        try:
            with open(agent_config_full_path, "r") as f:
                existing_agent_config = json.load(f)
            if existing_agent_config.get("network") == args.network:
                logger.info(f"Existing agent config is for the target network: {args.network}.")
            else:
                logger.warning(f"Existing agent config is for network '{existing_agent_config.get('network')}', but target is '{args.network}'.")
            
            if input(f"Create a NEW agent wallet for network '{args.network}'? This may overwrite '{agent_config_full_path}'. (y/n): ").lower() != 'y':
                logger.info("Skipping creation of a new agent wallet.")
                return
        except Exception as e: # Handle cases like invalid JSON
            logger.error(f"Could not read or parse existing agent config {agent_config_full_path}: {e}. Will proceed to create a new one if desired.")
            if input(f"Proceed to create a new agent wallet for network '{args.network}'? (y/n): ").lower() != 'y':
                return
    
    # Initialize HyperliquidAuth
    # It will use args.main_config_file as its 'config_file' for direct auth needed for agent creation
    auth = HyperliquidAuth(
        config_dir=config_dir_abs,
        config_file=args.main_config_file, 
        agent_config_file=args.agent_config_file,
        network=args.network
    )
    
    # Get agent name
    agent_name_to_create = args.agent_name
    if not agent_name_to_create:
        default_agent_name = f"{args.network}_bot_{int(time.time()) % 10000}"
        agent_name_to_create = input(f"Enter a name for your new agent wallet on {args.network} (e.g., '{default_agent_name}'): ")
        if not agent_name_to_create: # If user just presses Enter
            agent_name_to_create = default_agent_name
            logger.info(f"No agent name provided, using default: {agent_name_to_create}")
    
    # Create agent wallet
    try:
        logger.info(f"Attempting to create agent wallet '{agent_name_to_create}' on {args.network}...")
        # HyperliquidAuth.create_agent_wallet will use the main_config_file specified for its direct auth step
        agent_config_details = auth.create_agent_wallet(agent_name_to_create)
        
        print("\n" + "="*50)
        print("✅ AGENT WALLET SETUP COMPLETE")
        print("="*50)
        print(f"Network: {args.network}")
        print(f"Main address (from {main_config_full_path}): {agent_config_details['main_address']}")
        print(f"Agent address (newly created): {agent_config_details['agent_address']}")
        print(f"Agent name: {agent_config_details['agent_name']}")
        print(f"\nAgent wallet configuration saved to: {auth.agent_config_path}") # Use path from auth instance
        print("\n⚠️  IMPORTANT:")
        print(f"  Keep '{main_config_full_path}' (main private key) extremely secure!")
        print(f"  Also protect '{auth.agent_config_path}' (agent's key).")
        print("="*50)
        
    except Exception as e:
        logger.error(f"Failed to create agent wallet '{agent_name_to_create}' on {args.network}: {e}", exc_info=True)
        print(f"\n❌ Agent wallet setup for '{agent_name_to_create}' failed. See setup_agent.log for details.")

if __name__ == "__main__":
    main()
