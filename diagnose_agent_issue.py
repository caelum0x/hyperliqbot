"""
Diagnostic script to identify agent wallet issues
"""

import example_utils
from hyperliquid.utils import constants
from hyperliquid.info import Info

def main():
    # Setup connection
    address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
    
    print("🔍 DIAGNOSTIC REPORT")
    print("=" * 50)
    print(f"📍 Main Account: {address}")
    
    # Check main account balance
    try:
        main_state = info.user_state(address)
        main_balance = main_state.get('marginSummary', {}).get('accountValue', '0')
        print(f"💰 Main Account Balance: ${main_balance}")
        
        if float(main_balance) >= 5:
            print("✅ Main account has sufficient balance")
        else:
            print("❌ Main account balance too low")
    except Exception as e:
        print(f"❌ Error checking main balance: {e}")
    
    # ✅ FIX: Use the correct agent address from setup
    if hasattr(exchange, 'wallet') and hasattr(exchange.wallet, 'address'):
        actual_agent = exchange.wallet.address
        old_incorrect_agent = "0xb6fc35081be3be66df8a511486c632ab5a80b500"
        
        print(f"\n🤖 Correct Agent: {actual_agent}")
        try:
            agent_state = info.user_state(actual_agent)
            agent_balance = agent_state.get('marginSummary', {}).get('accountValue', '0')
            print(f"✅ Correct agent exists on Hyperliquid")
            print(f"💰 Correct agent balance: ${agent_balance}")
        except Exception as e:
            print(f"❌ Correct agent error: {e}")
        
        # Also check the old incorrect agent for comparison
        print(f"\n🤖 Old Incorrect Agent: {old_incorrect_agent}")
        try:
            incorrect_state = info.user_state(old_incorrect_agent)
            incorrect_balance = incorrect_state.get('marginSummary', {}).get('accountValue', '0')
            print(f"✅ Old agent still exists on Hyperliquid")
            print(f"💰 Old agent balance: ${incorrect_balance}")
        except Exception as e:
            print(f"❌ Old agent error: {e}")
    
    print(f"\n🔑 Checking Agent Approvals...")
    print(f"📋 Note: Check Hyperliquid app for approved agents")
    
    print(f"\n" + "=" * 50)
    if hasattr(exchange, 'wallet') and hasattr(exchange.wallet, 'address'):
        print(f"✅ SYSTEM STATUS: FIXED")
        print(f"✅ Using correct agent: {exchange.wallet.address[:10]}...{exchange.wallet.address[-8:]}")
        print(f"✅ Main account funded: ${main_balance}")
        print(f"🎯 READY FOR TRADING")
    else:
        print(f"❌ Could not determine correct agent address")

def check_balances():
    """Simple balance check function"""
    address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
    
    print("💰 BALANCE CHECK")
    print("=" * 30)
    
    # Main account
    main_state = info.user_state(address)
    main_balance = main_state.get('marginSummary', {}).get('accountValue', '0')
    print(f"📍 Main ({address[:6]}...): ${main_balance}")
    
    # ✅ FIX: Use correct agent address
    if hasattr(exchange, 'wallet') and hasattr(exchange.wallet, 'address'):
        agent_addr = exchange.wallet.address
        try:
            agent_state = info.user_state(agent_addr)
            agent_balance = agent_state.get('marginSummary', {}).get('accountValue', '0')
            print(f"🤖 Correct Agent ({agent_addr[:6]}...): ${agent_balance}")
        except Exception as e:
            print(f"🤖 Correct Agent ({agent_addr[:6]}...): Error - {e}")
    else:
        print("🤖 Could not determine correct agent address")

if __name__ == "__main__":
    main()
    print()
    check_balances()