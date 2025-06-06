import json
import time
import sqlite3
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ReferralUser:
    """Referral user data"""
    user_id: str
    referrer_id: Optional[str]
    signup_time: float
    total_volume: float
    commission_earned: float
    commission_rate: float

class ReferralCommissionManager:
    """
    Manages referral system with commission tracking and optimization
    """
    
    def __init__(self, base_commission_rate: float = 0.10):
        self.base_commission_rate = base_commission_rate  # 10% default
        self.referral_users = {}
        self.commission_history = []
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database for referral tracking"""
        self.conn = sqlite3.connect('referrals.db')
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_users (
                user_id TEXT PRIMARY KEY,
                referrer_id TEXT,
                signup_time REAL,
                total_volume REAL DEFAULT 0,
                commission_earned REAL DEFAULT 0,
                commission_rate REAL,
                tier_level INTEGER DEFAULT 1
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS commission_payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id TEXT,
                referred_user_id TEXT,
                commission_amount REAL,
                volume_basis REAL,
                timestamp REAL,
                FOREIGN KEY (referrer_id) REFERENCES referral_users (user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_links (
                link_id TEXT PRIMARY KEY,
                referrer_id TEXT,
                campaign_name TEXT,
                created_time REAL,
                clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                FOREIGN KEY (referrer_id) REFERENCES referral_users (user_id)
            )
        ''')
        
        self.conn.commit()
    
    def register_referral_user(
        self,
        user_id: str,
        referrer_id: Optional[str] = None,
        custom_commission_rate: Optional[float] = None
    ) -> Dict:
        """
        Register a new user with referral tracking
        """
        try:
            commission_rate = custom_commission_rate or self.base_commission_rate
            
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO referral_users 
                (user_id, referrer_id, signup_time, commission_rate)
                VALUES (?, ?, ?, ?)
            ''', (user_id, referrer_id, time.time(), commission_rate))
            self.conn.commit()
            
            # Update referral link conversion if applicable
            if referrer_id:
                cursor.execute('''
                    UPDATE referral_links 
                    SET conversions = conversions + 1
                    WHERE referrer_id = ?
                ''', (referrer_id,))
                self.conn.commit()
            
            return {
                "status": "user_registered",
                "user_id": user_id,
                "referrer_id": referrer_id,
                "commission_rate": commission_rate,
                "signup_time": time.time()
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def generate_referral_link(
        self,
        referrer_id: str,
        campaign_name: str = "default"
    ) -> Dict:
        """
        Generate a trackable referral link
        """
        try:
            import uuid
            link_id = f"ref_{uuid.uuid4().hex[:8]}"
            
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO referral_links 
                (link_id, referrer_id, campaign_name, created_time)
                VALUES (?, ?, ?, ?)
            ''', (link_id, referrer_id, campaign_name, time.time()))
            self.conn.commit()
            
            # Generate actual referral URL
            referral_url = f"https://app.hyperliquid.xyz/trade?ref={link_id}"
            
            return {
                "status": "link_generated",
                "link_id": link_id,
                "referral_url": referral_url,
                "campaign_name": campaign_name,
                "referrer_id": referrer_id
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def track_user_volume(self, user_id: str, volume: float) -> Dict:
        """
        Track trading volume for commission calculation
        """
        try:
            cursor = self.conn.cursor()
            
            # Update user's total volume
            cursor.execute('''
                UPDATE referral_users 
                SET total_volume = total_volume + ?
                WHERE user_id = ?
            ''', (volume, user_id))
            
            # Get user's referrer and commission rate
            cursor.execute('''
                SELECT referrer_id, commission_rate, total_volume
                FROM referral_users 
                WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            if not result or not result[0]:  # No referrer
                return {"status": "no_referrer"}
            
            referrer_id, commission_rate, total_volume = result
            
            # Calculate commission (assuming 0.03% base trading fee)
            base_fee = volume * 0.0003  # 0.03% trading fee
            commission = base_fee * commission_rate
            
            # Record commission payment
            cursor.execute('''
                INSERT INTO commission_payments 
                (referrer_id, referred_user_id, commission_amount, volume_basis, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (referrer_id, user_id, commission, volume, time.time()))
            
            # Update referrer's earned commission
            cursor.execute('''
                UPDATE referral_users 
                SET commission_earned = commission_earned + ?
                WHERE user_id = ?
            ''', (commission, referrer_id))
            
            self.conn.commit()
            
            return {
                "status": "commission_calculated",
                "user_id": user_id,
                "referrer_id": referrer_id,
                "volume": volume,
                "commission": commission,
                "commission_rate": commission_rate,
                "total_volume": total_volume + volume
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def get_referrer_performance(self, referrer_id: str) -> Dict:
        """
        Get comprehensive performance data for a referrer
        """
        try:
            cursor = self.conn.cursor()
            
            # Get basic referrer stats
            cursor.execute('''
                SELECT COUNT(*) as referred_users,
                       SUM(total_volume) as total_referred_volume,
                       SUM(commission_earned) as total_commission
                FROM referral_users 
                WHERE referrer_id = ?
            ''', (referrer_id,))
            
            stats = cursor.fetchone()
            
            # Get recent commission payments
            cursor.execute('''
                SELECT referred_user_id, commission_amount, volume_basis, timestamp
                FROM commission_payments 
                WHERE referrer_id = ?
                ORDER BY timestamp DESC
                LIMIT 20
            ''', (referrer_id,))
            
            recent_payments = cursor.fetchall()
            
            # Get referral link performance
            cursor.execute('''
                SELECT link_id, campaign_name, clicks, conversions, created_time
                FROM referral_links 
                WHERE referrer_id = ?
                ORDER BY created_time DESC
            ''', (referrer_id,))
            
            links = cursor.fetchall()
            
            # Calculate conversion rates
            total_clicks = sum(link[2] for link in links)
            total_conversions = sum(link[3] for link in links)
            conversion_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
            
            return {
                "referrer_id": referrer_id,
                "referred_users": stats[0] or 0,
                "total_referred_volume": stats[1] or 0,
                "total_commission_earned": stats[2] or 0,
                "conversion_rate": conversion_rate,
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "recent_payments": [
                    {
                        "user_id": payment[0],
                        "commission": payment[1],
                        "volume": payment[2],
                        "timestamp": payment[3]
                    }
                    for payment in recent_payments
                ],
                "referral_links": [
                    {
                        "link_id": link[0],
                        "campaign": link[1],
                        "clicks": link[2],
                        "conversions": link[3],
                        "created": link[4]
                    }
                    for link in links
                ]
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def optimize_commission_rates(self) -> Dict:
        """
        Optimize commission rates based on performance tiers
        """
        try:
            cursor = self.conn.cursor()
            
            # Get all referrers with their performance
            cursor.execute('''
                SELECT r.user_id,
                       COUNT(u.user_id) as referred_count,
                       SUM(u.total_volume) as total_volume,
                       r.commission_rate
                FROM referral_users r
                LEFT JOIN referral_users u ON r.user_id = u.referrer_id
                WHERE r.user_id IN (SELECT DISTINCT referrer_id FROM referral_users WHERE referrer_id IS NOT NULL)
                GROUP BY r.user_id
            ''')
            
            referrers = cursor.fetchall()
            optimizations = []
            
            for referrer_id, referred_count, total_volume, current_rate in referrers:
                total_volume = total_volume or 0
                
                # Determine optimal tier
                new_rate = self.base_commission_rate
                tier = 1
                
                if total_volume > 1000000:  # $1M+ volume
                    new_rate = 0.15  # 15%
                    tier = 4
                elif total_volume > 500000:  # $500K+ volume
                    new_rate = 0.13  # 13%
                    tier = 3
                elif total_volume > 100000:  # $100K+ volume
                    new_rate = 0.12  # 12%
                    tier = 2
                
                if new_rate != current_rate:
                    # Update commission rate
                    cursor.execute('''
                        UPDATE referral_users 
                        SET commission_rate = ?, tier_level = ?
                        WHERE user_id = ?
                    ''', (new_rate, tier, referrer_id))
                    
                    optimizations.append({
                        "referrer_id": referrer_id,
                        "old_rate": current_rate,
                        "new_rate": new_rate,
                        "tier": tier,
                        "total_volume": total_volume
                    })
            
            self.conn.commit()
            
            return {
                "status": "rates_optimized",
                "optimizations": optimizations,
                "total_referrers_updated": len(optimizations)
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def generate_referral_report(self, days_back: int = 30) -> Dict:
        """
        Generate comprehensive referral performance report
        """
        try:
            cursor = self.conn.cursor()
            start_time = time.time() - (days_back * 86400)
            
            # Total commission paid in period
            cursor.execute('''
                SELECT SUM(commission_amount) as total_commission,
                       COUNT(*) as payment_count
                FROM commission_payments 
                WHERE timestamp > ?
            ''', (start_time,))
            
            commission_stats = cursor.fetchone()
            
            # Top performing referrers
            cursor.execute('''
                SELECT referrer_id,
                       SUM(commission_amount) as period_commission,
                       SUM(volume_basis) as period_volume,
                       COUNT(*) as transactions
                FROM commission_payments 
                WHERE timestamp > ?
                GROUP BY referrer_id
                ORDER BY period_commission DESC
                LIMIT 10
            ''', (start_time,))
            
            top_referrers = cursor.fetchall()
            
            # New user signups
            cursor.execute('''
                SELECT COUNT(*) as new_users
                FROM referral_users 
                WHERE signup_time > ? AND referrer_id IS NOT NULL
            ''', (start_time,))
            
            new_signups = cursor.fetchone()[0]
            
            return {
                "period_days": days_back,
                "total_commission_paid": commission_stats[0] or 0,
                "total_payments": commission_stats[1] or 0,
                "new_referred_users": new_signups,
                "top_referrers": [
                    {
                        "referrer_id": ref[0],
                        "commission_earned": ref[1],
                        "volume_generated": ref[2],
                        "transactions": ref[3]
                    }
                    for ref in top_referrers
                ],
                "avg_commission_per_payment": (commission_stats[0] / commission_stats[1]) if commission_stats[1] > 0 else 0
            }
            
        except Exception as e:
            return {"status": "error", "message": str(e)}
