"""
Fix pip installation and setup all dependencies
"""

import os
import sys
import subprocess
import urllib.request
import json

def fix_pip():
    """Download and install pip"""
    print("🔧 Fixing pip installation...")
    
    try:
        # Download get-pip.py
        print("📥 Downloading get-pip.py...")
        url = "https://bootstrap.pypa.io/get-pip.py"
        urllib.request.urlretrieve(url, "get-pip.py")
        
        # Install pip
        print("⚙️ Installing pip...")
        result = subprocess.run([sys.executable, "get-pip.py"], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ pip installed successfully!")
            # Clean up
            os.remove("get-pip.py")
            return True
        else:
            print(f"❌ pip installation failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error fixing pip: {e}")
        return False

def install_packages():
    """Install required packages one by one"""
    packages = [
        "python-telegram-bot>=20.0",
        "web3>=6.0.0", 
        "eth-account>=0.8.0",
        "numpy>=1.21.0",
        "pandas>=1.3.0",
        "scikit-learn>=1.0.0",
        "ta>=0.10.0",
        "aiohttp>=3.8.0",
        "websockets>=10.0",
        "requests>=2.25.0",
        "cryptography>=3.4.0"
    ]
    
    print("📦 Installing packages...")
    
    for package in packages:
        try:
            print(f"⚙️ Installing {package}...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package], 
                capture_output=True, 
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ {package} installed successfully")
            else:
                print(f"⚠️ Failed to install {package}: {result.stderr}")
                
        except Exception as e:
            print(f"❌ Error installing {package}: {e}")
    
    # Try to install hyperliquid SDK separately
    try:
        print("⚙️ Installing hyperliquid-python-sdk...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "git+https://github.com/hyperliquid-dex/hyperliquid-python-sdk.git"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ hyperliquid-python-sdk installed successfully")
        else:
            print(f"⚠️ Failed to install hyperliquid SDK: {result.stderr}")
            print("💡 You may need to install it manually later")
            
    except Exception as e:
        print(f"❌ Error installing hyperliquid SDK: {e}")

def create_minimal_config():
    """Create minimal config file"""
    print("📝 Creating minimal config...")
    
    config = {
        "telegram": {
            "bot_token": "YOUR_BOT_TOKEN_HERE"
        },
        "base_url": "https://api.hyperliquid-testnet.xyz",
        "referral_code": "HYPERBOT",
        "hyperevm": {
            "network": "testnet"
        },
        "trading": {
            "max_position_size": 1000,
            "risk_level": "low"
        }
    }
    
    try:
        with open("config.json", "w") as f:
            json.dump(config, f, indent=2)
        print("✅ config.json created")
        return True
    except Exception as e:
        print(f"❌ Error creating config: {e}")
        return False

def test_imports():
    """Test if critical imports work"""
    print("🧪 Testing imports...")
    
    test_modules = [
        "telegram",
        "web3", 
        "eth_account",
        "numpy",
        "pandas",
        "requests"
    ]
    
    working = []
    failed = []
    
    for module in test_modules:
        try:
            __import__(module)
            working.append(module)
            print(f"✅ {module}")
        except ImportError:
            failed.append(module)
            print(f"❌ {module}")
    
    print(f"\n📊 Results: {len(working)}/{len(test_modules)} modules working")
    
    if failed:
        print(f"⚠️ Failed modules: {', '.join(failed)}")
    
    return len(failed) == 0

def main():
    """Main setup function"""
    print("🚀 HyperLiquid Bot - Fix & Setup")
    print("=" * 40)
    
    # Step 1: Fix pip
    if not fix_pip():
        print("❌ Could not fix pip. Try running as administrator.")
        return
    
    # Step 2: Install packages
    install_packages()
    
    # Step 3: Create config
    create_minimal_config()
    
    # Step 4: Test imports
    all_working = test_imports()
    
    print("\n" + "=" * 40)
    if all_working:
        print("✅ Setup complete! All modules working.")
        print("📝 Next steps:")
        print("1. Edit config.json with your Telegram bot token")
        print("2. Run: python main.py")
    else:
        print("⚠️ Setup partially complete.")
        print("Some modules failed to install. You may need to:")
        print("1. Run as administrator")
        print("2. Install failed modules manually")
        print("3. Check your Python installation")
    
    print("=" * 40)

if __name__ == "__main__":
    main()
