#!/usr/bin/env python3
"""
Real Vault Trading Example - Based on Hyperliquid SDK basic_vault.py
Shows how to actually trade on behalf of a vault
"""

import example_utils
from hyperliquid.utils import constants
import logging
from telegram_bot.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def trade_for_vault():
    """Example of trading on behalf of a vault using real SDK"""
    
    # Setup connection using existing config
    api_url = config.get_api_url()
    address, info, exchange = example_utils.setup(api_url, skip_ws=True)
    
    # Your vault address from config
    vault_address = config.get_vault_address()
    
    if not vault_address:
        logger.error("No vault address configured!")
        return
    
    # Check vault state
    vault_state = info.user_state(vault_address)
    logger.info(f"Vault state: {vault_state}")
    
    # Get vault balance
    account_value = float(vault_state.get('marginSummary', {}).get('accountValue', 0))
    logger.info(f"Vault value: ${account_value:,.2f}")
    
    if account_value < 50:
        logger.warning("Vault balance too low for trading")
        return
    
    # Place an order on behalf of the vault
    # IMPORTANT: Pass vault_address to trade for vault
    order_result = exchange.order(
        "ETH",           # coin
        True,            # is_buy
        0.01,            # size
        3000,            # price
        {"limit": {"tif": "Alo"}},  # Post-only for maker rebates
        reduce_only=False,
        vault_address=vault_address  # THIS IS THE KEY PART
    )
    
    logger.info(f"Order result: {order_result}")
    
    if order_result['status'] == 'ok':
        logger.info("Successfully placed order for vault!")
        
        # Check open orders for the vault
        vault_orders = info.open_orders(vault_address)
        logger.info(f"Vault has {len(vault_orders)} open orders")
        
        for order in vault_orders:
            logger.info(f"Order: {order['coin']} {order['side']} {order['sz']} @ {order['limitPx']}")
    
    return order_result


def deposit_to_vault():
    """Deposit to your own vault"""
    
    api_url = config.get_api_url()
    address, info, exchange = example_utils.setup(api_url, skip_ws=True)
    vault_address = config.get_vault_address()
    
    if not vault_address:
        logger.error("No vault address configured!")
        return
    
    # Check personal balance
    user_state = info.user_state(address)
    available = float(user_state.get('crossMarginSummary', {}).get('availableBalance', 0))
    
    if available < 100:
        logger.warning("Insufficient personal balance for deposit")
        return
    
    # Deposit to vault
    deposit_result = exchange.vault_transfer(
        vault_address=vault_address,
        is_deposit=True,
        usd=100  # Deposit 100 USDC
    )
    
    logger.info(f"Deposit result: {deposit_result}")
    
    if deposit_result.get('status') == 'ok':
        logger.info("Successfully deposited to vault!")
        
        # Check new vault balance
        vault_state = info.user_state(vault_address)
        new_balance = float(vault_state.get('marginSummary', {}).get('accountValue', 0))
        logger.info(f"New vault balance: ${new_balance:,.2f}")
    
    return deposit_result


def manage_vault_positions():
    """Example of managing positions for a vault"""
    
    api_url = config.get_api_url()
    address, info, exchange = example_utils.setup(api_url, skip_ws=True)
    vault_address = config.get_vault_address()
    
    if not vault_address:
        logger.error("No vault address configured!")
        return
    
    # Get all positions for vault
    vault_state = info.user_state(vault_address)
    positions = vault_state.get('assetPositions', [])
    
    for pos in positions:
        position = pos.get('position', {})
        coin = position.get('coin')
        size = float(position.get('szi', 0))
        entry_price = float(position.get('entryPx', 0))
        unrealized_pnl = float(position.get('unrealizedPnl', 0))
        
        if size != 0:
            logger.info(f"{coin}: Size={size}, Entry=${entry_price:.2f}, PnL=${unrealized_pnl:.2f}")
            
            # Example: Close position if profit > $10
            if unrealized_pnl > 10:
                logger.info(f"Taking profit on {coin}")
                
                # Place reduce-only order to close
                close_result = exchange.order(
                    coin,
                    (size < 0),  # is_buy: Buy if short, sell if long
                    abs(size),
                    None,  # Market order
                    {"market": {}},
                    reduce_only=True,
                    vault_address=vault_address
                )
                logger.info(f"Close result: {close_result}")


def calculate_vault_performance():
    """Calculate real vault performance metrics"""
    
    api_url = config.get_api_url()
    address, info, exchange = example_utils.setup(api_url, skip_ws=True)
    vault_address = config.get_vault_address()
    
    if not vault_address:
        logger.error("No vault address configured!")
        return {}
    
    # Get vault fills (trades)
    fills = info.user_fills(vault_address)
    
    # Calculate metrics
    total_volume = 0
    total_pnl = 0
    maker_rebates = 0
    
    for fill in fills:
        volume = float(fill['sz']) * float(fill['px'])
        total_volume += volume
        
        # Check if maker (negative fee = rebate)
        fee = float(fill.get('fee', 0))
        if fee < 0:
            maker_rebates += abs(fee)
            
        # Add realized PnL if available
        if 'closedPnl' in fill:
            total_pnl += float(fill['closedPnl'])
    
    logger.info(f"Vault Performance:")
    logger.info(f"Total Volume: ${total_volume:,.2f}")
    logger.info(f"Total PnL: ${total_pnl:,.2f}")
    logger.info(f"Maker Rebates Earned: ${maker_rebates:.4f}")
    logger.info(f"Number of Trades: {len(fills)}")
    
    # Calculate vault owner's 10% share
    if total_pnl > 0:
        owner_profit_share = total_pnl * 0.10
        logger.info(f"Vault Owner Profit Share (10%): ${owner_profit_share:.2f}")
    
    return {
        'volume': total_volume,
        'pnl': total_pnl,
        'rebates': maker_rebates,
        'trades': len(fills),
        'profit_share': max(0, total_pnl * 0.10) if total_pnl > 0 else 0
    }


def run_vault_example():
    """Run complete vault example"""
    logger.info("=== Hyperliquid Vault Trading Example ===")
    
    try:
        # 1. Deposit to vault
        logger.info("1. Depositing to vault...")
        deposit_to_vault()
        
        # 2. Trade for vault
        logger.info("2. Trading for vault...")
        trade_for_vault()
        
        # 3. Manage positions
        logger.info("3. Managing vault positions...")
        manage_vault_positions()
        
        # 4. Check performance
        logger.info("4. Calculating vault performance...")
        performance = calculate_vault_performance()
        
        logger.info("=== Example Complete ===")
        return performance
        
    except Exception as e:
        logger.error(f"Example failed: {e}")
        return {}


if __name__ == "__main__":
    # Run the complete example
    run_vault_example()
