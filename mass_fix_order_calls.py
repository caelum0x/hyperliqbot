# mass_fix_order_calls.py - Run this to fix all order calls automatically

import os
import re
from pathlib import Path

def fix_order_calls_in_file(file_path):
    """Fix order calls in a single file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        fixes_applied = 0
        
        # Pattern 1: Fix keyword-based order calls to positional
        # Matches: exchange.order(coin="BTC", is_buy=True, sz=0.001, px=1.0, order_type=...)
        pattern1 = r'(\w+\.order)\s*\(\s*coin\s*=\s*["\']([^"\']+)["\']\s*,\s*is_buy\s*=\s*(\w+)\s*,\s*sz\s*=\s*([^,]+)\s*,\s*px\s*=\s*([^,]+)\s*,\s*order_type\s*=\s*([^)]+)\s*\)'
        
        def replace_pattern1(match):
            exchange = match.group(1)
            coin = match.group(2)
            is_buy = match.group(3)
            size = match.group(4)
            price = match.group(5)
            order_type = match.group(6)
            
            return f'{exchange}("{coin}", {is_buy}, {size}, {price}, {order_type})'
        
        new_content = re.sub(pattern1, replace_pattern1, content)
        if new_content != content:
            fixes_applied += len(re.findall(pattern1, content))
            content = new_content
        
        # Pattern 2: Fix mixed keyword calls
        # Matches: exchange.order("BTC", True, sz=0.001, px=1.0, order_type=...)
        pattern2 = r'(\w+\.order)\s*\(\s*["\']([^"\']+)["\']\s*,\s*(\w+)\s*,\s*sz\s*=\s*([^,]+)\s*,\s*px\s*=\s*([^,]+)\s*,\s*order_type\s*=\s*([^)]+)\s*\)'
        
        def replace_pattern2(match):
            exchange = match.group(1)
            coin = match.group(2)
            is_buy = match.group(3)
            size = match.group(4)
            price = match.group(5)
            order_type = match.group(6)
            
            return f'{exchange}("{coin}", {is_buy}, {size}, {price}, {order_type})'
        
        new_content = re.sub(pattern2, replace_pattern2, content)
        if new_content != content:
            fixes_applied += len(re.findall(pattern2, content))
            content = new_content
        
        # Pattern 3: Fix legacy asset-based calls
        # Matches: exchange.order(asset=0, is_buy=True, sz=0.001, px=1.0, ...)
        pattern3 = r'(\w+\.order)\s*\(\s*asset\s*=\s*\d+\s*,\s*is_buy\s*=\s*(\w+)\s*,\s*sz\s*=\s*([^,]+)\s*,\s*px\s*=\s*([^,]+)\s*(?:,\s*[^)]+)?\s*\)'
        
        def replace_pattern3(match):
            exchange = match.group(1)
            is_buy = match.group(2)
            size = match.group(3)
            price = match.group(4)
            
            return f'{exchange}("BTC", {is_buy}, {size}, {price}, {{"limit": {{"tif": "Alo"}}}})'
        
        new_content = re.sub(pattern3, replace_pattern3, content)
        if new_content != content:
            fixes_applied += len(re.findall(pattern3, content))
            content = new_content
        
        # Write back if changes were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Fixed {fixes_applied} order calls in {file_path}")
            return fixes_applied
        else:
            print(f"ℹ️ No order calls found in {file_path}")
            return 0
            
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return 0

def main():
    """Fix order calls in all bot files"""
    
    # Files to check and fix
    files_to_fix = [
        "telegram_bot/wallet_manager.py",
        "telegram_bot/bot.py",
        "trading_engine/core_engine.py", 
        "strategies/automated_trading.py",
        "strategies/grid_trading_engine.py",
        "strategies/hyperliquid_profit_bot.py",
        "main.py"
    ]
    
    total_fixes = 0
    
    print("🔧 Starting mass fix of order calls...")
    print("=" * 50)
    
    for file_path in files_to_fix:
        if os.path.exists(file_path):
            fixes = fix_order_calls_in_file(file_path)
            total_fixes += fixes
        else:
            print(f"⚠️ File not found: {file_path}")
    
    print("=" * 50)
    print(f"🎯 TOTAL FIXES APPLIED: {total_fixes}")
    
    if total_fixes > 0:
        print("\n✅ SUCCESS! All order calls have been fixed.")
        print("🚀 Now restart your bot and test /test_trade")
        print("📝 Expected result: '✅ API Test Successful!' or '✅ Perfect! Test Fully Successful!'")
    else:
        print("\n⚠️ No fixes were needed, or files couldn't be processed.")
        print("🔍 You may need to manually check the files.")

if __name__ == "__main__":
    main()