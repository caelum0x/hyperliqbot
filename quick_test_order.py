# quick_test_order.py - Run this to find the correct method
import example_utils
from hyperliquid.utils import constants

def test_order_methods():
    """Test different order method formats"""
    address, info, exchange = example_utils.setup(constants.MAINNET_API_URL, skip_ws=True)
    
    print(f"Testing with address: {address}")
    
    # Test Method 1: All positional
    try:
        print("Testing Method 1: All positional parameters")
        result = exchange.order("BTC", True, 0.001, 1.0, {"limit": {"tif": "Alo"}})
        print(f"✅ SUCCESS - Method 1 works: {result}")
        return "Method 1"
    except Exception as e:
        print(f"❌ Method 1 failed: {e}")
    
    # Test Method 2: All keywords
    try:
        print("Testing Method 2: All keyword parameters")
        result = exchange.order(
            coin="BTC", 
            is_buy=True, 
            sz=0.001, 
            px=1.0, 
            order_type={"limit": {"tif": "Alo"}}
        )
        print(f"✅ SUCCESS - Method 2 works: {result}")
        return "Method 2"
    except Exception as e:
        print(f"❌ Method 2 failed: {e}")
    
    # Test Method 3: Mixed
    try:
        print("Testing Method 3: Mixed parameters")
        result = exchange.order("BTC", True, sz=0.001, px=1.0, order_type={"limit": {"tif": "Alo"}})
        print(f"✅ SUCCESS - Method 3 works: {result}")
        return "Method 3"
    except Exception as e:
        print(f"❌ Method 3 failed: {e}")
    
    # Test Method 4: Check actual method signature
    try:
        import inspect
        sig = inspect.signature(exchange.order)
        print(f"📋 Actual method signature: {sig}")
        print(f"📋 Parameters: {list(sig.parameters.keys())}")
    except Exception as e:
        print(f"❌ Could not inspect method: {e}")
    
    return "All methods failed"

if __name__ == "__main__":
    result = test_order_methods()
    print(f"\n🎯 RESULT: {result}")