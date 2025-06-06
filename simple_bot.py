"""
Simplified HyperLiquid Bot - Works with minimal dependencies
Run this if the full bot has import issues
"""

import asyncio
import json
import logging
import os
import signal
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test which modules are available"""
    modules = {
        'telegram': False,
        'web3': False, 
        'hyperliquid': False,
        'requests': False
    }
    
    # Test telegram
    try:
        import telegram
        modules['telegram'] = True
        print("✅ telegram module available")
    except ImportError:
        print("❌ telegram module missing - install with: pip install python-telegram-bot")
    
    # Test web3
    try:
        import web3
        modules['web3'] = True
        print("✅ web3 module available")
    except ImportError:
        print("❌ web3 module missing - install with: pip install web3")
    
    # Test hyperliquid
    try:
        from hyperliquid.info import Info
        modules['hyperliquid'] = True
        print("✅ hyperliquid module available")
    except ImportError:
        print("❌ hyperliquid module missing")
        print("   Install with: pip install git+https://github.com/hyperliquid-dex/hyperliquid-python-sdk.git")
    
    # Test requests
    try:
        import requests
        modules['requests'] = True
        print("✅ requests module available")
    except ImportError:
        print("❌ requests module missing - install with: pip install requests")
    
    return modules

class SimpleHyperLiquidBot:
    """Simplified bot that works with minimal dependencies"""
    
    def __init__(self):
        self.config = self.load_config()
        self.app = None
        
    def load_config(self):
        """Load config or create default"""
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                
            # Check if token is properly set
            bot_token = config.get("telegram", {}).get("bot_token", "")
            if bot_token in ["YOUR_BOT_TOKEN_HERE", "GET_TOKEN_FROM_BOTFATHER", ""]:
                print("\n🤖 BOT TOKEN SETUP REQUIRED")
                print("=" * 30)
                print("1. Message @BotFather on Telegram")
                print("2. Send /newbot")
                print("3. Follow the instructions")
                print("4. Copy your token")
                print("5. Update config.json")
                print()
                print("Current config.json location:", os.path.abspath("config.json"))
                
            return config
        except FileNotFoundError:
            default_config = {
                "telegram": {"bot_token": "GET_TOKEN_FROM_BOTFATHER"},
                "base_url": "https://api.hyperliquid-testnet.xyz"
            }
            with open("config.json", "w") as f:
                json.dump(default_config, f, indent=2)
            print("✅ Created default config.json")
            return default_config
    
    async def start_basic_bot(self):
        """Start bot with basic functionality"""
        try:
            from telegram import Update
            from telegram.ext import Application, CommandHandler, ContextTypes
            
            bot_token = self.config.get("telegram", {}).get("bot_token")
            
            if bot_token in ["YOUR_BOT_TOKEN_HERE", "GET_TOKEN_FROM_BOTFATHER", ""]:
                print("❌ Please set your bot token in config.json")
                print("Run: python quick_start.py for guided setup")
                return
            
            self.app = Application.builder().token(bot_token).build()
            
            # Add basic handlers
            self.app.add_handler(CommandHandler("start", self.start_command))
            self.app.add_handler(CommandHandler("help", self.help_command))
            self.app.add_handler(CommandHandler("status", self.status_command))
            
            print("🤖 Starting Simple HyperLiquid Bot...")
            print("✅ Bot is running! Send /start in Telegram.")
            
            # Properly start the bot
            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling()
            
            # Keep running until interrupted
            try:
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, SystemExit):
                print("\n🛑 Shutting down bot...")
            finally:
                # Proper cleanup
                await self.app.updater.stop()
                await self.app.stop()
                await self.app.shutdown()
                print("✅ Bot stopped cleanly")
            
        except ImportError as e:
            print(f"❌ Missing telegram module: {e}")
            print("Install with: pip install python-telegram-bot")
        except Exception as e:
            print(f"❌ Error starting bot: {e}")
            if self.app:
                try:
                    await self.app.updater.stop()
                    await self.app.stop()
                    await self.app.shutdown()
                except:
                    pass
    
    async def start_command(self, update, context):
        """Handle /start command"""
        await update.message.reply_text(
            "🚀 **Simple HyperLiquid Bot**\n\n"
            "This is a minimal version while we fix dependencies.\n\n"
            "Available commands:\n"
            "/help - Show help\n"
            "/status - Check bot status\n\n"
            "Full bot coming soon! 🔧"
        )
    
    async def help_command(self, update, context):
        """Handle /help command"""
        await update.message.reply_text(
            "📚 **Help**\n\n"
            "🔧 This is a simplified bot version.\n\n"
            "Once all dependencies are installed, you'll have access to:\n"
            "• Wallet connection\n"
            "• Trading strategies\n"
            "• Portfolio tracking\n"
            "• HyperEVM integration\n\n"
            "Check the setup logs for dependency status."
        )
    
    async def status_command(self, update, context):
        """Handle /status command"""
        modules = test_imports()
        
        status_text = "🔍 **Module Status**\n\n"
        for module, available in modules.items():
            emoji = "✅" if available else "❌"
            status_text += f"{emoji} {module}\n"
        
        working_count = sum(modules.values())
        total_count = len(modules)
        
        status_text += f"\n📊 {working_count}/{total_count} modules working"
        
        if working_count == total_count:
            status_text += "\n\n🎉 All dependencies ready! You can use the full bot."
        else:
            status_text += "\n\n⚠️ Some dependencies missing. Run fix_pip_and_setup.py"
        
        await update.message.reply_text(status_text)

def run_web_interface():
    """Simple web interface if telegram doesn't work"""
    try:
        import http.server
        import socketserver
        
        class SimpleHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                html = f"""
                <html>
                <head><title>HyperLiquid Bot Setup</title></head>
                <body style="font-family: Arial; margin: 40px;">
                <h1>🚀 HyperLiquid Bot Setup</h1>
                <h2>Quick Start:</h2>
                <ol>
                <li>Run: <code>python quick_start.py</code></li>
                <li>Follow the bot token setup</li>  
                <li>Run: <code>python main.py</code></li>
                </ol>
                
                <h2>Alternative:</h2>
                <ol>
                <li>Run: <code>python simple_bot.py</code> for basic version</li>
                </ol>
                
                <h2>Current Status:</h2>
                <p>Config file: {os.path.abspath("config.json")}</p>
                <p>Working directory: {os.getcwd()}</p>
                
                <h2>Need Help?</h2>
                <p>Check the setup instructions or run <code>python quick_start.py</code></p>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
        
        with socketserver.TCPServer(("", 8000), SimpleHandler) as httpd:
            print("🌐 Web interface started at http://localhost:8000")
            print("Visit this URL in your browser for setup instructions")
            httpd.serve_forever()
            
    except Exception as e:
        print(f"❌ Could not start web interface: {e}")

def setup_signal_handlers(bot_instance):
    """Setup signal handlers for graceful shutdown"""
    def signal_handler(signum, frame):
        print(f"\n🛑 Received signal {signum}, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

async def main():
    """Main entry point"""
    print("🚀 HyperLiquid Simple Bot")
    print("=" * 30)
    
    # Test what's available
    modules = test_imports()
    
    if modules.get('telegram', False):
        # Try to run telegram bot
        bot = SimpleHyperLiquidBot()
        setup_signal_handlers(bot)
        
        try:
            await bot.start_basic_bot()
        except KeyboardInterrupt:
            print("\n👋 Bot stopped by user")
        except Exception as e:
            print(f"❌ Bot error: {e}")
    else:
        print("\n💡 Telegram module not available.")
        print("Options:")
        print("1. Run: python quick_start.py (recommended)")
        print("2. Run: python fix_pip_and_setup.py")
        print("3. Install manually: pip install python-telegram-bot")
        print("4. Start web interface for help")
        
        choice = input("\nStart web interface? (y/n): ").lower()
        if choice == 'y':
            run_web_interface()

if __name__ == "__main__":
    try:
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            print("❌ Already running in an event loop. Please run this script directly.")
            sys.exit(1)
        except RuntimeError:
            # No running loop, we can proceed
            pass
        
        # Run the main function
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
