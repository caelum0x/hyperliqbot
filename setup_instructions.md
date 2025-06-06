# Hyperliquid Alpha Bot Setup

## 1. Configuration Files

### config.json (Main Configuration)
```json
{
  "account_address": "0xYOUR_WALLET_ADDRESS",
  "secret_key": "YOUR_PRIVATE_KEY",
  "mainnet": false,
  "vault_address": "0xYOUR_VAULT_ADDRESS_OPTIONAL",
  "referral_code": "YOUR_REFERRAL_CODE"
}
```

### .env (Environment Variables)
```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Hyperliquid Credentials
HL_ACCOUNT_ADDRESS=0xYOUR_WALLET_ADDRESS
HL_SECRET_KEY=YOUR_PRIVATE_KEY
HL_MAINNET=false

# Vault Configuration (Optional)
VAULT_ADDRESS=0xYOUR_VAULT_ADDRESS
VAULT_PRIVATE_KEY=YOUR_VAULT_PRIVATE_KEY

# Referral
REFERRAL_CODE=YOUR_REFERRAL_CODE
```

## 2. Getting Your Wallet Information

### From MetaMask:
1. Open MetaMask
2. Click account name → Account Details
3. Copy your address (account_address)
4. Export Private Key (secret_key)

### From Hyperliquid:
1. Go to https://app.hyperliquid.xyz
2. Connect your wallet
3. Your address is displayed in top right

## 3. Creating a Telegram Bot

1. Message @BotFather on Telegram
2. Send `/newbot`
3. Choose a name and username
4. Copy the bot token to .env file

## 4. Getting a Referral Code

1. Go to https://app.hyperliquid.xyz/referrals
2. Create your referral code
3. Add it to config.json

## 5. Vault Setup (Optional)

If you want to run a vault:
1. Create a new wallet for the vault
2. Add vault address and private key to config
3. Deposit initial capital (minimum 100 USDC)

## 6. Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python alpha_bot.py
```

## 7. Configuration Validation

The bot will validate your configuration on startup:
- ✅ Account address set
- ✅ Secret key set  
- ✅ Telegram token set
- ✅ Network configured

## 8. Security Notes

⚠️ **IMPORTANT:**
- Keep your private keys secure
- Use testnet for initial testing
- Never share your .env file
- Consider using separate wallets for bot trading

## 9. Supported Networks

- **Testnet**: Default, safe for testing
- **Mainnet**: Real trading with real money

Switch by setting `"mainnet": true` in config.json

## 10. Support

- Check logs for error messages
- Validate configuration with bot startup
- Join telegram support group for help
