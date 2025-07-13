# Hyperliquid Trading Bot for Telegram

A next-generation trading bot for the Hyperliquid exchange, fully integrated with Telegram for seamless, secure, and automated crypto trading. 

---

## 🚀 Features
- **Trade on Hyperliquid via Telegram**: Place, monitor, and manage trades directly from your Telegram app.
- **Secure Agent Wallets**: Never share your private keys. All trading is done via secure agent wallets.
- **Automated Alpha Strategies**: Grid trading, maker rebate mining, HLP staking, arbitrage, and more.
- **Vault System**: Pool funds, earn from multiple strategies, and track your profits.
- **Real-Time Analytics**: Portfolio, P&L, and live market data at your fingertips.
- **Referral & Bonus System**: Earn rewards for inviting friends.
- **Advanced Risk Management**: Built-in controls for leverage, stop-loss, and position sizing.
- **Easy Onboarding**: Step-by-step tutorial and safety guidelines for new users.

---

## 🛠️ Getting Started

### Prerequisites
- Python 3.8+
- Telegram account ([create a bot](https://core.telegram.org/bots#6-botfather))
- Hyperliquid wallet (address & private key)

### Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/caelum0x/hyperliqbot
   cd hyperliqbot
   ```
2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Configure environment variables:**
   - Copy `.env.example` to `.env` and fill in your credentials:
     ```bash
     cp .env.example .env
     # Edit .env with your details
     ```

### Configuration
Edit the `.env` file with your:
- Telegram bot token
- Hyperliquid wallet address and private key
- (Optional) Vault and referral details
- Database and API settings

---

## ▶️ Running the Bot
```bash
python run_bot.py
```

---

## 💬 Usage & Commands
Interact with your bot on Telegram using these commands:

- `/start` — Welcome & onboarding
- `/help` — Full command list
- `/portfolio` — View your portfolio & P&L
- `/trade` — Open trading menu
- `/strategies` — List available strategies
- `/start_trading [strategy]` — Start a strategy (e.g. grid, momentum)
- `/stop_trading` — Stop all strategies
- `/deposit` — Add funds to vault
- `/withdraw` — Request withdrawal
- `/status` — Check wallet & trading status
- `/settings` — Adjust preferences
- `/hyperevm` — Explore HyperEVM opportunities
- `/analytics` — View detailed analytics
- `/emergency_stop` — Emergency stop all trading

*See `/help` in the bot for the latest commands and features!*

---

## 📁 Folder Structure
- `hyperliquid/` — Core Hyperliquid API integration
- `strategies/` — Automated trading strategies
- `telegram_bot/` — Telegram bot logic & onboarding
- `examples/` — Example scripts and usage
- `run_bot.py` — Main entry point

---

## 🔒 Security & Best Practices
- **Never share your private keys or secrets.**
- Use a secure environment for running the bot.
- All trades are executed via agent wallets, not your main wallet.
- Start with small amounts and use risk controls.
- Use `/emergency_stop` if you need to halt all trading immediately.

---

## 🤝 Contributing
Pull requests and issues are welcome! Please open an issue to discuss your ideas or report bugs.

---

## 📜 License
MIT License