# hyperliquid-python-sdk

<div align="center">

[![Dependencies Status](https://img.shields.io/badge/dependencies-up%20to%20date-brightgreen.svg)](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/pulls?utf8=%E2%9C%93&q=is%3Apr%20author%3Aapp%2Fdependabot)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Security: bandit](https://img.shields.io/badge/security-bandit-green.svg)](https://github.com/PyCQA/bandit)
[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/.pre-commit-config.yaml)
[![Semantic Versions](https://img.shields.io/badge/%20%20%F0%9F%93%A6%F0%9F%9A%80-semantic--versions-e10079.svg)](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/releases)
[![License](https://img.shields.io/pypi/l/hyperliquid-python-sdk)](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/LICENSE.md)

SDK for Hyperliquid API trading with Python.

</div>

## Installation
```bash
pip install hyperliquid-python-sdk
```

## Telegram Trading Bot

This repository now includes a comprehensive Telegram trading bot that provides a user-friendly interface for trading on Hyperliquid.

### Bot Features

- 🔐 Secure wallet management
- 💰 Account balance checking
- 📊 Position monitoring
- 📋 Order management
- 🛒 Buy/Sell limit orders
- ⚡ Market orders
- ❌ Order cancellation

### Bot Setup

1. **Create a Telegram Bot**
   - Message @BotFather on Telegram
   - Create a new bot with `/newbot`
   - Save the bot token

2. **Configure the Bot**
   ```bash
   cp telegram_bot/bot_config.json.example telegram_bot/bot_config.json
   ```
   
   Edit `telegram_bot/bot_config.json`:
   ```json
   {
     "telegram": {
       "bot_token": "YOUR_BOT_TOKEN_HERE",
       "allowed_users": [123456789],
       "admin_users": [123456789]
     },
     "hyperliquid": {
       "base_url": "https://api.hyperliquid-testnet.xyz",
       "default_slippage": 0.05
     }
   }
   ```

3. **Install Dependencies**
   ```bash
   pip install python-telegram-bot
   ```

4. **Run the Bot**
   ```bash
   python -m telegram_bot.bot
   ```

### Bot Commands

- `/start` - Welcome message and command list
- `/register <private_key> [account_address]` - Register your wallet
- `/balance` - Check account balance
- `/positions` - View open positions
- `/orders` - View open orders
- `/buy <coin> <size> <price>` - Place buy limit order
- `/sell <coin> <size> <price>` - Place sell limit order
- `/market_buy <coin> <size> [slippage]` - Market buy order
- `/market_sell <coin> <size> [slippage]` - Market sell order
- `/cancel <coin> <order_id>` - Cancel order
- `/help` - Show help message

### Example Usage

```
/register 0x1234567890abcdef... 0xYourAccountAddress
/balance
/buy BTC 0.1 45000
/market_sell ETH 1 0.02
/positions
/cancel BTC 123456
```

### Security Notes

⚠️ **Important Security Considerations:**

- The bot stores private keys (should be encrypted in production)
- Use only in secure, private chats
- Consider using API wallets instead of main wallet keys
- Test on testnet first
- Never share your private keys

## Configuration 

- Set the public key as the `account_address` in examples/config.json.
- Set your private key as the `secret_key` in examples/config.json.
- See the example of loading the config in examples/example_utils.py

### [Optional] Generate a new API key for an API Wallet
Generate and authorize a new API private key on https://app.hyperliquid.xyz/API, and set the API wallet's private key as the `secret_key` in examples/config.json. Note that you must still set the public key of the main wallet *not* the API wallet as the `account_address` in examples/config.json

## Usage Examples
```python
from hyperliquid.info import Info
from hyperliquid.utils import constants

info = Info(constants.TESTNET_API_URL, skip_ws=True)
user_state = info.user_state("0xcd5051944f780a621ee62e39e493c489668acf4d")
print(user_state)
```
See [examples](examples) for more complete examples. You can also checkout the repo and run any of the examples after configuring your private key e.g. 
```bash
cp examples/config.json.example examples/config.json
vim examples/config.json
python examples/basic_order.py
```

## Getting started with contributing to this repo

1. Download `Poetry`: https://python-poetry.org/. 
   - Note that in the install script you might have to set `symlinks=True` in `venv.EnvBuilder`.
   - Note that Poetry v2 is not supported, so you'll need to specify a specific version e.g. curl -sSL https://install.python-poetry.org | POETRY_VERSION=1.4.1 python3 - 

2. Point poetry to correct version of python. For development we require python 3.10 exactly. Some dependencies have issues on 3.11, while older versions don't have correct typing support.
`brew install python@3.10 && poetry env use /opt/homebrew/Cellar/python@3.10/3.10.16/bin/python3.10`

3. Install dependencies:

```bash
make install
```

### Makefile usage

CLI commands for faster development. See `make help` for more details.

```bash
check-safety          Run safety checks on dependencies
cleanup               Cleanup project
install               Install dependencies from poetry.lock
install-types         Find and install additional types for mypy
lint                  Alias for the pre-commit target
lockfile-update       Update poetry.lock
lockfile-update-full  Fully regenerate poetry.lock
poetry-download       Download and install poetry
pre-commit            Run linters + formatters via pre-commit, run "make pre-commit hook=black" to run only black
test                  Run tests with pytest
update-dev-deps       Update development dependencies to latest versions
```

## Releases

You can see the list of available releases on the [GitHub Releases](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/releases) page.

We follow the [Semantic Versions](https://semver.org/) specification and use [`Release Drafter`](https://github.com/marketplace/actions/release-drafter). As pull requests are merged, a draft release is kept up-to-date listing the changes, ready to publish when you’re ready. With the categories option, you can categorize pull requests in release notes using labels.

### List of labels and corresponding titles

|               **Label**               |  **Title in Releases**  |
| :-----------------------------------: | :---------------------: |
|       `enhancement`, `feature`        |        Features         |
| `bug`, `refactoring`, `bugfix`, `fix` |  Fixes & Refactoring    |
|       `build`, `ci`, `testing`        |  Build System & CI/CD   |
|              `breaking`               |    Breaking Changes     |
|            `documentation`            |     Documentation       |
|            `dependencies`             |  Dependencies updates   |

### Building and releasing

Building a new version of the application contains steps:

- Bump the version of your package with `poetry version <version>`. You can pass the new version explicitly, or a rule such as `major`, `minor`, or `patch`. For more details, refer to the [Semantic Versions](https://semver.org/) standard.
- Make a commit to `GitHub`
- Create a `GitHub release`
- `poetry publish --build`

## License

This project is licensed under the terms of the `MIT` license. See [LICENSE](LICENSE.md) for more details.

```bibtex
@misc{hyperliquid-python-sdk,
  author = {Hyperliquid},
  title = {SDK for Hyperliquid API trading with Python.},
  year = {2024},
  publisher = {GitHub},
  journal = {GitHub repository},
  howpublished = {\url{https://github.com/hyperliquid-dex/hyperliquid-python-sdk}}
}
```

## Credits

This project was generated with [`python-package-template`](https://github.com/TezRomacH/python-package-template).
#   h y p e r l i q b o t  
 