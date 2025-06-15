"""
Test script to verify agent trading functionality
"""

import asyncio
import example_utils
from hyperliquid.utils import constants
from hyperliquid.info import Info

async def test_agent_trading():
    """Test that agent trading works correctly with the fixed system"""
    
    print("🧪 TESTING AGENT TRADING FUNCTIONALITY")
    print("=" * 50)
    
    # Setup connection - this gives us the correct agent
    address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
    
    print(f"📍 Main Account: {address}")
    print(f"🤖 Agent Address: {exchange.wallet.address}")
    
    # Check balances
    main_state = info.user_state(address)
    main_balance = float(main_state.get('marginSummary', {}).get('accountValue', 0))
    print(f"💰 Main Balance: ${main_balance:.2f}")
    
    if main_balance < 5:
        print("❌ Insufficient funds for testing")
        return False
    
    # Get current BTC price for realistic test
    try:
        mids = info.all_mids()
        btc_price = float(mids.get('BTC', 30000))
        # ✅ FIX: Use proper rounding to avoid float precision errors
        test_price = round(btc_price * 0.9, 2)  # 10% below market
        
        print(f"📊 Current BTC price: ${btc_price:,.2f}")
        print(f"🎯 Test order price: ${test_price:,.2f}")
        
        # Test order placement
        print("\n🧪 Placing test order...")
        
        test_result = exchange.order(
            "BTC",                           # coin
            True,                           # is_buy
            0.001,                          # size
            test_price,                     # price (properly rounded)
            {"limit": {"tif": "Alo"}}       # order_type
        )
        
        print(f"📝 Order result: {test_result}")
        
        if test_result and test_result.get("status") == "ok":
            print("✅ SUCCESS: Agent can place orders!")
            
            # Try to cancel orders (cleanup) - handle missing methods gracefully
            try:
                if hasattr(exchange, 'cancel_all'):
                    cancel_result = exchange.cancel_all("BTC")
                    print(f"🧹 Cancel result: {cancel_result}")
                else:
                    print("⚠️ Could not cancel (this is ok): 'Exchange' object has no attribute 'cancel_all'")
            except Exception as e:
                print(f"⚠️ Could not cancel (this is ok): {e}")
                
            return True
        else:
            print(f"❌ Order failed: {test_result}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

async def main():
    success = await test_agent_trading()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 AGENT TRADING TEST: PASSED")
        print("✅ Your system is ready for trading!")
        print("✅ Start the Telegram bot to begin trading")
    else:
        print("❌ AGENT TRADING TEST: FAILED")
        print("❌ Check the error messages above")

if __name__ == "__main__":
    asyncio.run(main())
