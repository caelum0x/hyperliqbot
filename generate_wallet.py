from eth_account import Account
import secrets
import json

# Generate a random private key
private_key = "0x" + secrets.token_hex(32)

# Create an account from the private key
account = Account.from_key(private_key)

# Print wallet details
print(f"Address: {account.address}")
print(f"Private Key: {private_key}")

# Create config.json
config = {
    "secret_key": private_key,
    "account_address": ""
}

# Save to config.json
with open("config.json", "w") as f:
    json.dump(config, f, indent=2)

# Save to examples/config.json too
import os
os.makedirs("examples", exist_ok=True)
with open("examples/config.json", "w") as f:
    json.dump(config, f, indent=2)

print(f"\nConfiguration files created successfully:")
print(f"1. config.json")
print(f"2. examples/config.json")
print(f"\nIMPORTANT: Save your private key somewhere secure!")