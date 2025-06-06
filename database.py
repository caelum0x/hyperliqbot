"""
Simple database module for tracking users and profits
Uses JSON for simplicity - upgrade to PostgreSQL for production
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
from decimal import Decimal

class BotDatabase:
    def __init__(self, db_file: str = "bot_data.json"):
        self.db_file = db_file
        self.data = self._load_data()
        self.lock = asyncio.Lock()
        
    def _load_data(self) -> Dict:
        """Load data from JSON file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return self._get_default_data()
        else:
            return self._get_default_data()
    
    def _get_default_data(self) -> Dict:
        """Get default database structure"""
        return {
            "users": {},
            "deposits": [],
            "withdrawals": [],
            "trades": [],
            "daily_stats": {},
            "referrals": {},
            "vault_performance": {},
            "user_profits": {}  # Track individual user profits
        }
            
    async def _save_data(self):
        """Save data to JSON file with backup"""
        async with self.lock:
            # Create backup
            if os.path.exists(self.db_file):
                backup_file = f"{self.db_file}.backup"
                with open(self.db_file, 'r') as src, open(backup_file, 'w') as dst:
                    dst.write(src.read())
            
            # Save new data
            with open(self.db_file, 'w') as f:
                json.dump(self.data, f, indent=2, default=str)
                
    async def add_user(self, telegram_id: int, wallet_address: str = None, referrer_id: int = None):
        """Add new user to database"""
        user_data = {
            "telegram_id": telegram_id,
            "wallet_address": wallet_address,
            "joined": datetime.now().isoformat(),
            "total_deposited": 0.0,
            "total_withdrawn": 0.0,
            "total_profit": 0.0,
            "current_balance": 0.0,
            "last_activity": datetime.now().isoformat(),
            "referred_by": referrer_id,
            "is_active": True
        }
        
        self.data["users"][str(telegram_id)] = user_data
        
        # Handle referral
        if referrer_id:
            await self.add_referral(referrer_id, telegram_id)
            
        await self._save_data()
        return user_data
        
    async def record_deposit(self, telegram_id: int, amount: float, tx_hash: str = None):
        """Record user deposit to vault"""
        deposit = {
            "id": len(self.data["deposits"]) + 1,
            "user_id": telegram_id,
            "amount": float(amount),
            "tx_hash": tx_hash,
            "timestamp": datetime.now().isoformat(),
            "status": "confirmed",
            "type": "deposit"
        }
        
        self.data["deposits"].append(deposit)
        
        # Update user stats
        user_id_str = str(telegram_id)
        if user_id_str not in self.data["users"]:
            await self.add_user(telegram_id)
            
        self.data["users"][user_id_str]["total_deposited"] += amount
        self.data["users"][user_id_str]["current_balance"] += amount
        self.data["users"][user_id_str]["last_activity"] = datetime.now().isoformat()
            
        await self._save_data()
        return deposit
        
    async def record_withdrawal(self, telegram_id: int, amount: float, tx_hash: str = None):
        """Record user withdrawal from vault"""
        withdrawal = {
            "id": len(self.data["withdrawals"]) + 1,
            "user_id": telegram_id,
            "amount": float(amount),
            "tx_hash": tx_hash,
            "timestamp": datetime.now().isoformat(),
            "status": "pending",
            "type": "withdrawal"
        }
        
        self.data["withdrawals"].append(withdrawal)
        
        # Update user stats
        user_id_str = str(telegram_id)
        if user_id_str in self.data["users"]:
            self.data["users"][user_id_str]["total_withdrawn"] += amount
            self.data["users"][user_id_str]["current_balance"] -= amount
            self.data["users"][user_id_str]["last_activity"] = datetime.now().isoformat()
            
        await self._save_data()
        return withdrawal
        
    async def record_trade(self, coin: str, side: str, size: float, price: float, pnl: float, 
                          fee: float, fee_type: str, vault_address: str = None):
        """Record executed trade from vault"""
        trade = {
            "id": len(self.data["trades"]) + 1,
            "coin": coin,
            "side": side,
            "size": float(size),
            "price": float(price),
            "notional": float(size * price),
            "pnl": float(pnl),
            "fee": float(fee),
            "fee_type": fee_type,  # "maker_rebate", "taker_fee"
            "vault_address": vault_address,
            "timestamp": datetime.now().isoformat()
        }
        
        self.data["trades"].append(trade)
        
        # Keep only last 5000 trades for performance
        if len(self.data["trades"]) > 5000:
            self.data["trades"] = self.data["trades"][-5000:]
            
        # Update daily volume and profits
        await self._update_daily_performance(trade)
        await self._save_data()
        return trade
        
    async def _update_daily_performance(self, trade: Dict):
        """Update daily performance metrics"""
        today = datetime.now().date().isoformat()
        
        if today not in self.data["vault_performance"]:
            self.data["vault_performance"][today] = {
                "volume": 0.0,
                "pnl": 0.0,
                "fees_paid": 0.0,
                "rebates_earned": 0.0,
                "trades_count": 0,
                "maker_trades": 0,
                "taker_trades": 0
            }
        
        daily_perf = self.data["vault_performance"][today]
        daily_perf["volume"] += trade["notional"]
        daily_perf["pnl"] += trade["pnl"]
        daily_perf["trades_count"] += 1
        
        if trade["fee_type"] == "maker_rebate":
            daily_perf["rebates_earned"] += abs(trade["fee"])
            daily_perf["maker_trades"] += 1
        else:
            daily_perf["fees_paid"] += trade["fee"]
            daily_perf["taker_trades"] += 1
        
    async def get_user_stats(self, telegram_id: int) -> Optional[Dict]:
        """Get comprehensive user statistics"""
        user_data = self.data["users"].get(str(telegram_id))
        if not user_data:
            return None
        
        # Calculate user's vault share
        total_vault_deposits = sum(d["amount"] for d in self.data["deposits"] 
                                 if d["status"] == "confirmed")
        user_deposits = user_data["total_deposited"]
        
        vault_share = user_deposits / total_vault_deposits if total_vault_deposits > 0 else 0
        
        # Calculate recent performance (last 7 days)
        week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
        recent_performance = {}
        
        for date, perf in self.data["vault_performance"].items():
            if date >= week_ago:
                for key, value in perf.items():
                    recent_performance[key] = recent_performance.get(key, 0) + value
        
        # Calculate user's share of profits
        vault_pnl = recent_performance.get("pnl", 0)
        user_profit_share = vault_pnl * vault_share * 0.9  # 90% after performance fee
        
        # Get user's total profit
        total_user_profit = user_data.get("total_profit", 0) + user_profit_share
        
        # Calculate ROI
        roi = (total_user_profit / user_deposits * 100) if user_deposits > 0 else 0
        
        return {
            "telegram_id": telegram_id,
            "wallet_address": user_data.get("wallet_address"),
            "joined": user_data["joined"],
            "days_active": (datetime.now() - datetime.fromisoformat(user_data["joined"])).days,
            "total_deposited": user_deposits,
            "total_withdrawn": user_data["total_withdrawn"],
            "current_balance": user_data["current_balance"],
            "vault_share_pct": vault_share * 100,
            "recent_profit": user_profit_share,
            "total_profit": total_user_profit,
            "roi_pct": roi,
            "recent_volume": recent_performance.get("volume", 0),
            "is_active": user_data.get("is_active", True),
            "last_activity": user_data.get("last_activity")
        }
        
    async def update_daily_stats(self, vault_address: str, account_value: float, 
                               total_pnl: float, volume_24h: float):
        """Update daily vault statistics"""
        today = datetime.now().date().isoformat()
        
        self.data["daily_stats"][today] = {
            "vault_address": vault_address,
            "account_value": float(account_value),
            "total_pnl": float(total_pnl),
            "volume_24h": float(volume_24h),
            "active_users": len([u for u in self.data["users"].values() 
                               if u.get("is_active", True)]),
            "total_deposits": sum(d["amount"] for d in self.data["deposits"] 
                                if d["status"] == "confirmed"),
            "performance_fee_earned": max(0, total_pnl * 0.1),
            "timestamp": datetime.now().isoformat()
        }
        
        await self._save_data()
        
    async def get_vault_stats(self) -> Dict:
        """Get comprehensive vault statistics"""
        total_deposits = sum(d["amount"] for d in self.data["deposits"] 
                           if d["status"] == "confirmed")
        total_withdrawals = sum(w["amount"] for w in self.data["withdrawals"] 
                              if w["status"] == "completed")
        
        # Calculate performance metrics
        all_trades = self.data["trades"]
        if all_trades:
            total_pnl = sum(t["pnl"] for t in all_trades)
            total_volume = sum(t["notional"] for t in all_trades)
            total_rebates = sum(abs(t["fee"]) for t in all_trades 
                              if t["fee_type"] == "maker_rebate")
            total_fees = sum(t["fee"] for t in all_trades 
                           if t["fee_type"] == "taker_fee")
            
            maker_trades = len([t for t in all_trades if t["fee_type"] == "maker_rebate"])
            maker_pct = (maker_trades / len(all_trades) * 100) if all_trades else 0
        else:
            total_pnl = total_volume = total_rebates = total_fees = maker_pct = 0
        
        # Recent performance (last 24h)
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        today = datetime.now().date().isoformat()
        
        recent_perf = {"volume": 0, "pnl": 0, "trades_count": 0}
        for date in [yesterday, today]:
            if date in self.data["vault_performance"]:
                perf = self.data["vault_performance"][date]
                recent_perf["volume"] += perf.get("volume", 0)
                recent_perf["pnl"] += perf.get("pnl", 0)
                recent_perf["trades_count"] += perf.get("trades_count", 0)
        
        return {
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "net_deposits": total_deposits - total_withdrawals,
            "total_pnl": total_pnl,
            "total_volume": total_volume,
            "total_rebates": total_rebates,
            "total_fees_paid": total_fees,
            "net_fees": total_rebates - total_fees,
            "total_trades": len(all_trades),
            "maker_percentage": maker_pct,
            "active_users": len([u for u in self.data["users"].values() 
                               if u.get("is_active", True)]),
            "performance_fees_earned": max(0, total_pnl * 0.1),
            "daily_volume": recent_perf["volume"],
            "daily_pnl": recent_perf["pnl"],
            "daily_trades": recent_perf["trades_count"]
        }
        
    async def add_referral(self, referrer_id: int, referred_id: int):
        """Track referral relationship"""
        referrer_str = str(referrer_id)
        
        if referrer_str not in self.data["referrals"]:
            self.data["referrals"][referrer_str] = {
                "total_referrals": 0,
                "total_earnings": 0.0,
                "referrals": []
            }
            
        self.data["referrals"][referrer_str]["referrals"].append({
            "user_id": referred_id,
            "timestamp": datetime.now().isoformat(),
            "bonus_paid": 0.0
        })
        
        self.data["referrals"][referrer_str]["total_referrals"] += 1
        
        # Update referred user
        if str(referred_id) in self.data["users"]:
            self.data["users"][str(referred_id)]["referred_by"] = referrer_id
            
        await self._save_data()
        
    async def pay_referral_bonus(self, referrer_id: int, referred_id: int, amount: float):
        """Pay referral bonus"""
        referrer_str = str(referrer_id)
        
        if referrer_str in self.data["referrals"]:
            # Update referral earnings
            self.data["referrals"][referrer_str]["total_earnings"] += amount
            
            # Find and update specific referral
            for ref in self.data["referrals"][referrer_str]["referrals"]:
                if ref["user_id"] == referred_id:
                    ref["bonus_paid"] += amount
                    break
            
            # Update referrer's user account
            if referrer_str in self.data["users"]:
                self.data["users"][referrer_str]["total_profit"] += amount
                
        await self._save_data()
        
    async def get_referral_stats(self, telegram_id: int) -> Dict:
        """Get user's referral statistics"""
        referrals_data = self.data["referrals"].get(str(telegram_id), {
            "total_referrals": 0,
            "total_earnings": 0.0,
            "referrals": []
        })
        
        # Calculate active referrals (users who deposited)
        active_referrals = 0
        for ref in referrals_data["referrals"]:
            user_data = self.data["users"].get(str(ref["user_id"]))
            if user_data and user_data["total_deposited"] > 0:
                active_referrals += 1
        
        return {
            "total_referrals": referrals_data["total_referrals"],
            "active_referrals": active_referrals,
            "total_earnings": referrals_data["total_earnings"],
            "referral_link": f"https://t.me/HyperLiquidBot?start=ref_{telegram_id}",
            "recent_referrals": referrals_data["referrals"][-5:]  # Last 5 referrals
        }
    
    async def get_leaderboard(self, metric: str = "profit", limit: int = 10) -> List[Dict]:
        """Get user leaderboard by different metrics"""
        users = []
        
        for telegram_id, user_data in self.data["users"].items():
            if not user_data.get("is_active", True):
                continue
                
            user_stats = await self.get_user_stats(int(telegram_id))
            if user_stats:
                users.append(user_stats)
        
        # Sort by metric
        if metric == "profit":
            users.sort(key=lambda x: x["total_profit"], reverse=True)
        elif metric == "deposits":
            users.sort(key=lambda x: x["total_deposited"], reverse=True)
        elif metric == "roi":
            users.sort(key=lambda x: x["roi_pct"], reverse=True)
        elif metric == "volume":
            users.sort(key=lambda x: x["recent_volume"], reverse=True)
        
        return users[:limit]
    
    async def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to keep database performant"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).date().isoformat()
        
        # Clean old daily stats
        old_dates = [date for date in self.data["vault_performance"].keys() 
                    if date < cutoff_date]
        for date in old_dates:
            del self.data["vault_performance"][date]
            
        # Clean old daily stats
        old_daily_dates = [date for date in self.data["daily_stats"].keys() 
                          if date < cutoff_date]
        for date in old_daily_dates:
            del self.data["daily_stats"][date]
        
        await self._save_data()
        

# Singleton instance
bot_db = BotDatabase()

# Utility functions
async def get_user_stats(telegram_id: int) -> Optional[Dict]:
    """Get user stats - convenience function"""
    return await bot_db.get_user_stats(telegram_id)

async def record_user_deposit(telegram_id: int, amount: float, tx_hash: str = None) -> Dict:
    """Record user deposit - convenience function"""
    return await bot_db.record_deposit(telegram_id, amount, tx_hash)

async def get_vault_performance() -> Dict:
    """Get vault performance - convenience function"""
    return await bot_db.get_vault_stats()


# Usage example and testing
async def test_database():
    """Test database functionality"""
    db = BotDatabase("test_bot_data.json")
    
    # Add users
    await db.add_user(123456789, "0x1234...", None)
    await db.add_user(987654321, "0x5678...", 123456789)  # Referred user
    
    # Record deposits
    await db.record_deposit(123456789, 1000.0, "0xabcd...")
    await db.record_deposit(987654321, 500.0, "0xefgh...")
    
    # Record some trades
    await db.record_trade("ETH", "buy", 0.5, 3000, 15.0, -0.03, "maker_rebate")
    await db.record_trade("BTC", "sell", 0.01, 65000, 25.0, 0.23, "taker_fee")
    
    # Update daily stats
    await db.update_daily_stats("0xVault...", 1600.0, 40.0, 125000.0)
    
    # Get stats
    user_stats = await db.get_user_stats(123456789)
    vault_stats = await db.get_vault_stats()
    referral_stats = await db.get_referral_stats(123456789)
    leaderboard = await db.get_leaderboard("profit", 5)
    
    print("=== User Stats ===")
    print(json.dumps(user_stats, indent=2, default=str))
    print("\n=== Vault Stats ===")
    print(json.dumps(vault_stats, indent=2, default=str))
    print("\n=== Referral Stats ===")
    print(json.dumps(referral_stats, indent=2, default=str))
    print("\n=== Leaderboard ===")
    print(json.dumps(leaderboard, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(test_database())
