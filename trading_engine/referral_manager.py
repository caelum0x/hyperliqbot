import json
import time
import sqlite3
import logging
from typing import Dict, List, Optional, Tuple
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
        self.logger = logging.getLogger(__name__)
        
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
        
        # Add new tables for enhanced referral tracking and analytics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_leaderboard (
                period TEXT,
                referrer_id TEXT,
                rank INTEGER,
                volume REAL,
                commissions REAL,
                referrals INTEGER,
                updated_at REAL,
                PRIMARY KEY (period, referrer_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_tiers (
                tier_id INTEGER PRIMARY KEY,
                name TEXT,
                min_volume REAL,
                commission_rate REAL,
                benefits TEXT,
                color_code TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS referral_analytics (
                date TEXT,
                total_referrers INTEGER,
                active_referrers INTEGER,
                new_signups INTEGER,
                total_volume REAL,
                total_commission REAL,
                conversion_rate REAL,
                avg_value_per_referral REAL,
                PRIMARY KEY (date)
            )
        ''')
        
        # Populate default tier structure if not exists
        cursor.execute("SELECT COUNT(*) FROM referral_tiers")
        if cursor.fetchone()[0] == 0:
            # Insert default tiers
            tiers = [
                (1, "Bronze", 0, 0.10, "Base commission rate", "#CD7F32"),
                (2, "Silver", 1000000, 0.11, "11% commission + priority support", "#C0C0C0"),
                (3, "Gold", 5000000, 0.12, "12% commission + VIP dashboard", "#FFD700"),
                (4, "Platinum", 10000000, 0.15, "15% commission + custom links + VIP rewards", "#E5E4E2")
            ]
            cursor.executemany(
                "INSERT INTO referral_tiers (tier_id, name, min_volume, commission_rate, benefits, color_code) VALUES (?, ?, ?, ?, ?, ?)",
                tiers
            )
        
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
    
    def calculate_tiered_commission_rate(self, referrer_id: str, volume: float) -> float:
        """Calculate tiered commission rate based on referee volume"""
        try:
            cursor = self.conn.cursor()
            
            # Get referrer's total referred volume
            cursor.execute('''
                SELECT SUM(total_volume) as referred_volume
                FROM referral_users 
                WHERE referrer_id = ?
            ''', (referrer_id,))
            
            result = cursor.fetchone()
            total_referred_volume = result[0] or 0
            
            # Get tiers from database
            cursor.execute('''
                SELECT tier_id, min_volume, commission_rate
                FROM referral_tiers
                ORDER BY min_volume DESC
            ''')
            
            tiers = cursor.fetchall()
            
            # Find applicable tier
            for tier_id, min_volume, commission_rate in tiers:
                if total_referred_volume >= min_volume:
                    # Update referrer's tier if needed
                    cursor.execute('''
                        UPDATE referral_users
                        SET tier_level = ?
                        WHERE user_id = ? AND tier_level != ?
                    ''', (tier_id, referrer_id, tier_id))
                    
                    if cursor.rowcount > 0:
                        self.conn.commit()
                        self.logger.info(f"Upgraded referrer {referrer_id} to tier {tier_id}")
                    
                    return commission_rate
            
            # Default to base rate if no tier matches
            return self.base_commission_rate
                
        except Exception as e:
            self.logger.error(f"Error calculating tiered commission: {e}")
            return self.base_commission_rate  # Default to base rate
    
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
            
            referrer_id, old_commission_rate, total_volume = result
            
            # Calculate tiered commission rate based on updated volume
            commission_rate = self.calculate_tiered_commission_rate(referrer_id, volume)
            
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
            
            # Update leaderboards with the new volume and commission
            self._update_leaderboards(referrer_id, volume, commission)
            
            return {
                "status": "commission_calculated",
                "user_id": user_id,
                "referrer_id": referrer_id,
                "volume": volume,
                "commission": commission,
                "commission_rate": commission_rate,
                "total_volume": total_volume + volume,
                "tier_changed": commission_rate != old_commission_rate
            }
            
        except Exception as e:
            self.logger.error(f"Error tracking user volume: {e}")
            return {"status": "error", "message": str(e)}
    
    def _update_leaderboards(self, referrer_id: str, volume: float, commission: float):
        """Update referral leaderboards with new activity"""
        try:
            cursor = self.conn.cursor()
            now = time.time()
            today = time.strftime("%Y-%m-%d")
            week = time.strftime("%Y-W%W")  # Year-WeekNumber
            month = time.strftime("%Y-%m")
            
            # Update or create entries for daily, weekly, and monthly leaderboards
            for period in [today, week, month]:
                # Check if entry exists
                cursor.execute('''
                    SELECT volume, commissions, referrals 
                    FROM referral_leaderboard 
                    WHERE period = ? AND referrer_id = ?
                ''', (period, referrer_id))
                
                result = cursor.fetchone()
                
                if result:
                    # Update existing entry
                    cursor.execute('''
                        UPDATE referral_leaderboard
                        SET volume = volume + ?,
                            commissions = commissions + ?,
                            updated_at = ?
                        WHERE period = ? AND referrer_id = ?
                    ''', (volume, commission, now, period, referrer_id))
                else:
                    # Create new entry
                    cursor.execute('''
                        INSERT INTO referral_leaderboard
                        (period, referrer_id, rank, volume, commissions, referrals, updated_at)
                        VALUES (?, ?, 0, ?, ?, 0, ?)
                    ''', (period, referrer_id, volume, commission, now))
            
            # Recalculate ranks for each period
            for period in [today, week, month]:
                self._recalculate_leaderboard_ranks(period)
            
            self.conn.commit()
            
        except Exception as e:
            self.logger.error(f"Error updating leaderboards: {e}")
    
    def _recalculate_leaderboard_ranks(self, period: str):
        """Recalculate ranks for a specific leaderboard period"""
        try:
            cursor = self.conn.cursor()
            
            # Get all referrers sorted by commission
            cursor.execute('''
                SELECT referrer_id, commissions
                FROM referral_leaderboard
                WHERE period = ?
                ORDER BY commissions DESC
            ''', (period,))
            
            referrers = cursor.fetchall()
            
            # Update ranks
            for rank, (referrer_id, _) in enumerate(referrers, 1):
                cursor.execute('''
                    UPDATE referral_leaderboard
                    SET rank = ?
                    WHERE period = ? AND referrer_id = ?
                ''', (rank, period, referrer_id))
                
        except Exception as e:
            self.logger.error(f"Error recalculating leaderboard ranks: {e}")
    
    def get_leaderboard(self, period_type: str = "daily", limit: int = 10) -> List[Dict]:
        """Get referral leaderboard for specified period"""
        try:
            cursor = self.conn.cursor()
            
            # Determine period based on type
            if period_type == "daily":
                period = time.strftime("%Y-%m-%d")
            elif period_type == "weekly":
                period = time.strftime("%Y-W%W")
            elif period_type == "monthly":
                period = time.strftime("%Y-%m")
            elif period_type == "all_time":
                # For all time, we'll need to aggregate from user data
                cursor.execute('''
                    SELECT 
                        user_id as referrer_id, 
                        SUM(total_volume) as volume,
                        SUM(commission_earned) as commissions,
                        COUNT(*) as referrals
                    FROM referral_users
                    WHERE referrer_id IS NOT NULL
                    GROUP BY referrer_id
                    ORDER BY commissions DESC
                    LIMIT ?
                ''', (limit,))
                
                results = cursor.fetchall()
                leaders = []
                
                for i, (referrer_id, volume, commissions, referrals) in enumerate(results, 1):
                    # Get referrer's tier
                    cursor.execute("SELECT tier_level FROM referral_users WHERE user_id = ?", (referrer_id,))
                    tier_result = cursor.fetchone()
                    tier = tier_result[0] if tier_result else 1
                    
                    leaders.append({
                        "rank": i,
                        "referrer_id": referrer_id,
                        "volume": volume or 0,
                        "commissions": commissions or 0,
                        "referrals": referrals or 0,
                        "tier": tier
                    })
                
                return leaders
            else:
                # Get leaderboard for specific period
                cursor.execute('''
                    SELECT 
                        lb.rank,
                        lb.referrer_id,
                        lb.volume,
                        lb.commissions,
                        lb.referrals,
                        u.tier_level as tier
                    FROM referral_leaderboard lb
                    LEFT JOIN referral_users u ON lb.referrer_id = u.user_id
                    WHERE lb.period = ?
                    ORDER BY lb.rank ASC
                    LIMIT ?
                ''', (period, limit))
                
                results = cursor.fetchall()
                leaders = []
                
                for row in results:
                    leaders.append({
                        "rank": row[0],
                        "referrer_id": row[1],
                        "volume": row[2] or 0,
                        "commissions": row[3] or 0,
                        "referrals": row[4] or 0,
                        "tier": row[5] or 1
                    })
                
                return leaders
            
        except Exception as e:
            self.logger.error(f"Error getting leaderboard: {e}")
            return []
    
    def track_referral_click(self, link_id: str) -> Dict:
        """Track click on referral link"""
        try:
            cursor = self.conn.cursor()
            
            # Update click count
            cursor.execute('''
                UPDATE referral_links
                SET clicks = clicks + 1
                WHERE link_id = ?
            ''', (link_id,))
            
            if cursor.rowcount == 0:
                return {"status": "error", "message": "Invalid link ID"}
            
            self.conn.commit()
            return {"status": "click_tracked"}
            
        except Exception as e:
            self.logger.error(f"Error tracking referral click: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_referral_analytics_dashboard(self) -> Dict:
        """Get comprehensive referral analytics for dashboard"""
        try:
            cursor = self.conn.cursor()
            
            # Get general statistics
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_referrers,
                    COUNT(CASE WHEN tier_level > 1 THEN 1 END) as premium_referrers,
                    SUM(total_volume) as total_volume,
                    SUM(commission_earned) as total_commission
                FROM referral_users
                WHERE user_id IN (
                    SELECT DISTINCT referrer_id FROM referral_users WHERE referrer_id IS NOT NULL
                )
            ''')
            
            general_stats = cursor.fetchone()
            
            # Get tier distribution
            cursor.execute('''
                SELECT 
                    tier_level,
                    COUNT(*) as referrer_count,
                    t.name as tier_name,
                    t.commission_rate,
                    t.color_code
                FROM referral_users u
                JOIN referral_tiers t ON u.tier_level = t.tier_id
                WHERE u.user_id IN (
                    SELECT DISTINCT referrer_id FROM referral_users WHERE referrer_id IS NOT NULL
                )
                GROUP BY tier_level
                ORDER BY tier_level ASC
            ''')
            
            tier_distribution = [
                {
                    "tier": row[0],
                    "count": row[1],
                    "name": row[2],
                    "commission_rate": row[3],
                    "color": row[4]
                }
                for row in cursor.fetchall()
            ]
            
            # Get monthly performance trend
            cursor.execute('''
                SELECT 
                    strftime('%Y-%m', datetime(timestamp/1000, 'unixepoch')) as month,
                    SUM(commission_amount) as monthly_commission,
                    SUM(volume_basis) as monthly_volume,
                    COUNT(DISTINCT referrer_id) as active_referrers
                FROM commission_payments
                WHERE timestamp > ?
                GROUP BY month
                ORDER BY month DESC
                LIMIT 12
            ''', (time.time() - 86400 * 365,))  # Last 365 days
            
            monthly_trend = [
                {
                    "month": row[0],
                    "commission": row[1],
                    "volume": row[2],
                    "active_referrers": row[3]
                }
                for row in cursor.fetchall()
            ]
            
            # Get top performing campaigns
            cursor.execute('''
                SELECT 
                    campaign_name,
                    SUM(clicks) as total_clicks,
                    SUM(conversions) as total_conversions,
                    CASE WHEN SUM(clicks) > 0 
                        THEN CAST(SUM(conversions) AS FLOAT) / SUM(clicks) 
                        ELSE 0 
                    END as conversion_rate
                FROM referral_links
                GROUP BY campaign_name
                ORDER BY total_conversions DESC
                LIMIT 5
            ''')
            
            top_campaigns = [
                {
                    "name": row[0],
                    "clicks": row[1],
                    "conversions": row[2],
                    "conversion_rate": row[3]
                }
                for row in cursor.fetchall()
            ]
            
            return {
                "general_stats": {
                    "total_referrers": general_stats[0] or 0,
                    "premium_referrers": general_stats[1] or 0,
                    "premium_percentage": (general_stats[1] / general_stats[0] * 100) if general_stats[0] > 0 else 0,
                    "total_volume": general_stats[2] or 0,
                    "total_commission": general_stats[3] or 0
                },
                "tier_distribution": tier_distribution,
                "monthly_trend": monthly_trend,
                "top_campaigns": top_campaigns,
                "leaderboards": {
                    "daily": self.get_leaderboard("daily", 5),
                    "weekly": self.get_leaderboard("weekly", 5),
                    "monthly": self.get_leaderboard("monthly", 5)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error getting referral analytics: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_referrer_tier_info(self, referrer_id: str) -> Dict:
        """Get detailed information about referrer's current tier and next tier requirements"""
        try:
            cursor = self.conn.cursor()
            
            # Get referrer's current tier and volume
            cursor.execute('''
                SELECT r.tier_level, r.total_volume, t.name, t.commission_rate, t.benefits, t.color_code
                FROM referral_users r
                JOIN referral_tiers t ON r.tier_level = t.tier_id
                WHERE r.user_id = ?
            ''', (referrer_id,))
            
            referrer_data = cursor.fetchone()
            if not referrer_data:
                return {"status": "error", "message": "Referrer not found"}
            
            current_tier, current_volume, tier_name, commission_rate, benefits, color_code = referrer_data
            
            # Find next tier requirements
            cursor.execute('''
                SELECT tier_id, name, min_volume, commission_rate, benefits, color_code
                FROM referral_tiers
                WHERE min_volume > ?
                ORDER BY min_volume ASC
                LIMIT 1
            ''', (current_volume,))
            
            next_tier_data = cursor.fetchone()
            next_tier_info = None
            
            if next_tier_data:
                next_tier_id, next_tier_name, next_tier_min, next_tier_rate, next_tier_benefits, next_color = next_tier_data
                volume_needed = next_tier_min - current_volume
                
                next_tier_info = {
                    "tier_id": next_tier_id,
                    "name": next_tier_name,
                    "min_volume": next_tier_min,
                    "commission_rate": next_tier_rate,
                    "benefits": next_tier_benefits,
                    "color_code": next_color,
                    "volume_needed": volume_needed,
                    "progress_percentage": (current_volume / next_tier_min * 100) if next_tier_min > 0 else 0
                }
            
            # Get referrer statistics
            cursor.execute('''
                SELECT COUNT(*) as referred_count,
                       SUM(total_volume) as referred_volume
                FROM referral_users
                WHERE referrer_id = ?
            ''', (referrer_id,))
            
            stats_data = cursor.fetchone()
            referred_count = stats_data[0] or 0
            referred_volume = stats_data[1] or 0
            
            return {
                "referrer_id": referrer_id,
                "current_tier": {
                    "tier_id": current_tier,
                    "name": tier_name,
                    "commission_rate": commission_rate,
                    "benefits": benefits,
                    "color_code": color_code
                },
                "next_tier": next_tier_info,
                "stats": {
                    "referred_count": referred_count,
                    "referred_volume": referred_volume,
                    "average_volume": referred_volume / referred_count if referred_count > 0 else 0
                },
                "is_max_tier": next_tier_info is None
            }
            
        except Exception as e:
            self.logger.error(f"Error getting referrer tier info: {e}")
            return {"status": "error", "message": str(e)}
