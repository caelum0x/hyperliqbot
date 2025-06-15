#!/usr/bin/env python3
"""
Utility to fix trading states and diagnose issues with user wallets.
Run this script when you need to reset trading states.
"""

import asyncio
import aiosqlite
import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger("fix_trading")

async def list_users(db_path):
    """List all users in the database"""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT user_id, agent_name, agent_address, main_address, 
                       trading_enabled, approval_status, created_at, last_balance 
                FROM agent_wallets
            """) as cursor:
                rows = await cursor.fetchall()
                
                if not rows:
                    print("No users found in the database.")
                    return
                
                print(f"\n{'='*80}\n")
                print(f" {'USER ID':<15} {'MAIN ADDRESS':<20} {'AGENT ADDRESS':<20} {'TRADING':<10} {'APPROVAL':<10} {'BALANCE':<10}")
                print(f"{'-'*80}")
                
                for row in rows:
                    print(f" {row['user_id']:<15} {row['main_address'][:18]+'...':<20} {row['agent_address'][:18]+'...':<20} {'✅' if row['trading_enabled'] else '❌':<10} {row['approval_status']:<10} ${float(row['last_balance']):<10.2f}")
                
                print(f"\n{'='*80}\n")
                print(f"Total users: {len(rows)}")
    except Exception as e:
        logger.error(f"Error listing users: {e}")

async def reset_trading_state(db_path, user_id):
    """Reset the trading state for a specific user"""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Update the trading_enabled flag to 0
            await db.execute("""
                UPDATE agent_wallets
                SET trading_enabled = 0
                WHERE user_id = ?
            """, (user_id,))
            await db.commit()
            
            # Verify the update worked
            async with db.execute("SELECT trading_enabled FROM agent_wallets WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] == 0:
                    print(f"✅ Successfully reset trading state for user {user_id}")
                    return True
                else:
                    print(f"❌ Failed to reset trading state for user {user_id}")
                    return False
    except Exception as e:
        logger.error(f"Error resetting trading state: {e}")
        return False

async def fix_all_users(db_path):
    """Reset the trading state for all users"""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Update all trading_enabled flags to 0
            await db.execute("UPDATE agent_wallets SET trading_enabled = 0")
            await db.commit()
            count = (await db.execute("SELECT changes()")).fetchone()[0]
            
            print(f"✅ Reset trading state for {count} users")
            return count
    except Exception as e:
        logger.error(f"Error resetting all users: {e}")
        return 0

async def show_user_details(db_path, user_id):
    """Show detailed information about a user"""
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Get wallet info
            async with db.execute("""
                SELECT * FROM agent_wallets WHERE user_id = ?
            """, (user_id,)) as cursor:
                wallet = await cursor.fetchone()
                
                if not wallet:
                    print(f"❌ User {user_id} not found in database")
                    return
                
                print(f"\n{'='*80}\n")
                print(f" USER DETAILS: {user_id}\n")
                print(f" Agent Name:     {wallet['agent_name']}")
                print(f" Agent Address:  {wallet['agent_address']}")
                print(f" Main Address:   {wallet['main_address']}")
                print(f" Created At:     {wallet['created_at']}")
                print(f" Trading:        {'✅ Enabled' if wallet['trading_enabled'] else '❌ Disabled'}")
                print(f" Approval:       {wallet['approval_status']}")
                print(f" Last Balance:   ${float(wallet['last_balance']):.2f}")
                print(f" Last Checked:   {wallet['last_checked']}")
                
                # Get recent balance checks
                async with db.execute("""
                    SELECT * FROM balance_checks 
                    WHERE user_id = ? 
                    ORDER BY timestamp DESC LIMIT 5
                """, (user_id,)) as cursor:
                    balances = await cursor.fetchall()
                    
                    if balances:
                        print(f"\n Recent Balance History:")
                        for bal in balances:
                            print(f" • {bal['timestamp']}: ${float(bal['balance']):.2f}")
                
                print(f"\n{'='*80}\n")
    except Exception as e:
        logger.error(f"Error showing user details: {e}")

async def main():
    parser = argparse.ArgumentParser(description="Fix trading states for Hyperliquid bot users")
    parser.add_argument("--db", default="agent_wallets.db", help="Path to the agent_wallets.db file")
    parser.add_argument("--list-users", action="store_true", help="List all users in the database")
    parser.add_argument("--reset", type=int, help="Reset trading state for a specific user ID")
    parser.add_argument("--reset-all", action="store_true", help="Reset trading state for all users")
    parser.add_argument("--user-details", type=int, help="Show detailed information for a specific user ID")
    
    args = parser.parse_args()
    
    # Check if database exists
    if not os.path.exists(args.db):
        logger.error(f"Database file not found: {args.db}")
        sys.exit(1)
    
    if args.list_users:
        await list_users(args.db)
    elif args.reset is not None:
        await reset_trading_state(args.db, args.reset)
    elif args.reset_all:
        await fix_all_users(args.db)
    elif args.user_details is not None:
        await show_user_details(args.db, args.user_details)
    else:
        parser.print_help()

if __name__ == "__main__":
    asyncio.run(main())
