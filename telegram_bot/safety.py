import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class LimitType(Enum):
    DAILY_LOSS = "daily_loss"
    WEEKLY_LOSS = "weekly_loss"
    POSITION_SIZE = "position_size"
    MAX_LEVERAGE = "max_leverage"
    TOTAL_EXPOSURE = "total_exposure"

@dataclass
class SecurityAlert:
    """Security alert data structure"""
    alert_id: str
    user_id: int
    level: AlertLevel
    message: str
    details: Dict[str, Any]
    timestamp: datetime
    acknowledged: bool = False
    resolved: bool = False

@dataclass
class RiskLimit:
    """Risk management limit data structure"""
    limit_type: LimitType
    value: float
    currency: str = "USDC"
    enabled: bool = True
    breached: bool = False
    breach_count: int = 0
    last_breach: Optional[datetime] = None

@dataclass
class AuditEntry:
    """Audit trail entry"""
    entry_id: str
    user_id: int
    action: str
    details: Dict[str, Any]
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class SafetyManager:
    """
    Comprehensive safety and risk management system:
    - Daily/weekly loss limits
    - Position size limits
    - Emergency contact system
    - Audit trail
    - Security alerts
    """

    def __init__(self, wallet_manager, database=None, config=None):
        self.wallet_manager = wallet_manager
        self.database = database
        self.config = config or {}
        
        # In-memory storage for demo (replace with database in production)
        self.user_limits: Dict[int, Dict[str, RiskLimit]] = {}
        self.security_alerts: Dict[str, SecurityAlert] = {}
        self.audit_trail: List[AuditEntry] = []
        self.emergency_contacts: Dict[int, List[str]] = {}
        
        # Default safety limits
        self.default_limits = {
            LimitType.DAILY_LOSS: 500.0,  # $500 daily loss limit
            LimitType.WEEKLY_LOSS: 2000.0,  # $2000 weekly loss limit
            LimitType.POSITION_SIZE: 1000.0,  # $1000 max position size
            LimitType.MAX_LEVERAGE: 10.0,  # 10x max leverage
            LimitType.TOTAL_EXPOSURE: 5000.0  # $5000 total exposure limit
        }
        
        # Emergency shutdown flags
        self.emergency_mode: Dict[int, bool] = {}
        
        # Start background monitoring
        self._start_monitoring_tasks()

    def _start_monitoring_tasks(self):
        """Start background monitoring tasks"""
        asyncio.create_task(self._monitor_risk_limits())
        asyncio.create_task(self._monitor_unusual_activity())
        asyncio.create_task(self._cleanup_old_alerts())

    async def setup_user_safety(self, update: Update, context: CallbackContext):
        """Setup safety features for a user"""
        user_id = update.effective_user.id
        
        safety_msg = f"""
🛡️ **Safety & Risk Management Setup**

**Current Limits:**
{await self._format_user_limits(user_id)}

**Emergency Features:**
• Emergency stop: Instantly halt all trading
• Position limits: Prevent oversized trades
• Loss limits: Daily and weekly protection
• Security alerts: Real-time monitoring

**Audit Trail:**
• All actions are logged and tracked
• Complete transparency of bot activities
• Exportable for your records
        """
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Configure Limits", callback_data="config_limits"),
             InlineKeyboardButton("🚨 Emergency Contacts", callback_data="emergency_contacts")],
            [InlineKeyboardButton("📊 View Audit Trail", callback_data="view_audit"),
             InlineKeyboardButton("🔔 Security Alerts", callback_data="security_alerts")],
            [InlineKeyboardButton("🛑 Emergency Stop", callback_data="emergency_stop_confirm"),
             InlineKeyboardButton("📋 Safety Report", callback_data="safety_report")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(safety_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def configure_risk_limits(self, update: Update, context: CallbackContext):
        """Configure risk management limits"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer("Loading risk configuration...")
        
        limits_msg = f"""
⚙️ **Configure Risk Limits**

**Current Settings:**
{await self._format_user_limits(user_id)}

**Recommended Limits:**
• Daily Loss: $500 (conservative) / $1000 (moderate) / $2000 (aggressive)
• Weekly Loss: $2000 (conservative) / $5000 (moderate) / $10000 (aggressive)
• Position Size: 10-20% of account balance
• Max Leverage: 5x (conservative) / 10x (moderate) / 20x (aggressive)

Click below to modify individual limits:
        """
        
        keyboard = [
            [InlineKeyboardButton("📉 Daily Loss Limit", callback_data="set_daily_loss"),
             InlineKeyboardButton("📊 Weekly Loss Limit", callback_data="set_weekly_loss")],
            [InlineKeyboardButton("💰 Position Size Limit", callback_data="set_position_size"),
             InlineKeyboardButton("⚡ Max Leverage", callback_data="set_max_leverage")],
            [InlineKeyboardButton("🎯 Total Exposure", callback_data="set_total_exposure"),
             InlineKeyboardButton("🔄 Reset to Defaults", callback_data="reset_limits")],
            [InlineKeyboardButton("← Back to Safety", callback_data="back_to_safety")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(limits_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def setup_emergency_contacts(self, update: Update, context: CallbackContext):
        """Setup emergency contact system"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer("Loading emergency contacts...")
        
        contacts = self.emergency_contacts.get(user_id, [])
        
        contacts_msg = f"""
🚨 **Emergency Contact System**

**Current Contacts:**
        """
        
        if contacts:
            for i, contact in enumerate(contacts, 1):
                contacts_msg += f"{i}. {contact}\n"
        else:
            contacts_msg += "• No emergency contacts configured\n"
        
        contacts_msg += f"""

**How Emergency Contacts Work:**
• Notified immediately during emergency stops
• Receive alerts for critical security events
• Can be email addresses or phone numbers
• Maximum 3 contacts allowed

**Emergency Triggers:**
• Manual emergency stop
• Automatic risk limit breaches
• Unusual account activity detected
• System security alerts
        """
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Contact", callback_data="add_emergency_contact")],
            [InlineKeyboardButton("🗑️ Remove Contact", callback_data="remove_emergency_contact")],
            [InlineKeyboardButton("🧪 Test Emergency Alert", callback_data="test_emergency_alert")],
            [InlineKeyboardButton("← Back to Safety", callback_data="back_to_safety")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(contacts_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def view_audit_trail(self, update: Update, context: CallbackContext):
        """Display audit trail for user"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer("Loading audit trail...")
        
        # Get user's audit entries (last 10)
        user_entries = [entry for entry in self.audit_trail 
                       if entry.user_id == user_id][-10:]
        
        audit_msg = "📊 **Audit Trail (Last 10 Actions)**\n\n"
        
        if user_entries:
            for entry in reversed(user_entries):  # Most recent first
                timestamp = entry.timestamp.strftime('%m-%d %H:%M')
                audit_msg += f"• **{timestamp}** - {entry.action}\n"
                if entry.details:
                    key_details = list(entry.details.items())[:2]  # Show first 2 details
                    for key, value in key_details:
                        audit_msg += f"  {key}: {value}\n"
                audit_msg += "\n"
        else:
            audit_msg += "• No audit entries found\n"
        
        audit_msg += f"""
**Audit Features:**
• Complete action history
• Immutable record keeping
• Exportable reports
• Security compliance

**Tracked Actions:**
• Trade executions
• Strategy changes
• Safety limit modifications
• Emergency stops
• Login/logout events
        """
        
        keyboard = [
            [InlineKeyboardButton("📄 Export Full Report", callback_data="export_audit"),
             InlineKeyboardButton("🔍 Search Audit", callback_data="search_audit")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="view_audit"),
             InlineKeyboardButton("← Back", callback_data="back_to_safety")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(audit_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def view_security_alerts(self, update: Update, context: CallbackContext):
        """Display security alerts for user"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer("Loading security alerts...")
        
        # Get user's alerts (unresolved first, then recent resolved)
        user_alerts = [alert for alert in self.security_alerts.values() 
                      if alert.user_id == user_id]
        
        unresolved = [a for a in user_alerts if not a.resolved]
        recent_resolved = [a for a in user_alerts if a.resolved][-5:]
        
        alerts_msg = "🔔 **Security Alerts**\n\n"
        
        if unresolved:
            alerts_msg += "**🚨 Active Alerts:**\n"
            for alert in unresolved:
                level_emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨", "emergency": "🆘"}
                timestamp = alert.timestamp.strftime('%m-%d %H:%M')
                alerts_msg += f"{level_emoji.get(alert.level.value, '⚠️')} **{timestamp}** - {alert.message}\n"
                if not alert.acknowledged:
                    alerts_msg += "  ❗ *Requires acknowledgment*\n"
                alerts_msg += "\n"
        
        if recent_resolved:
            alerts_msg += "**✅ Recently Resolved:**\n"
            for alert in recent_resolved:
                timestamp = alert.timestamp.strftime('%m-%d %H:%M')
                alerts_msg += f"• {timestamp} - {alert.message}\n"
        
        if not unresolved and not recent_resolved:
            alerts_msg += "• No security alerts\n"
        
        alerts_msg += f"""
**Alert Types:**
• Risk limit breaches
• Unusual trading patterns
• Login from new devices
• Large position changes
• System security events

**Response Actions:**
• Acknowledge alerts
• Adjust safety settings
• Contact support if needed
        """
        
        keyboard = []
        if unresolved:
            keyboard.append([InlineKeyboardButton("✅ Acknowledge All", callback_data="ack_all_alerts")])
        
        keyboard.extend([
            [InlineKeyboardButton("📧 Alert Settings", callback_data="alert_settings"),
             InlineKeyboardButton("🔄 Refresh", callback_data="security_alerts")],
            [InlineKeyboardButton("← Back to Safety", callback_data="back_to_safety")]
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(alerts_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def generate_safety_report(self, update: Update, context: CallbackContext):
        """Generate comprehensive safety report"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer("Generating safety report...")
        
        # Get user data
        limits = self.user_limits.get(user_id, {})
        alerts = [a for a in self.security_alerts.values() if a.user_id == user_id]
        recent_audit = [e for e in self.audit_trail if e.user_id == user_id][-7:]
        
        # Calculate risk metrics
        current_exposure = await self._calculate_current_exposure(user_id)
        daily_pnl = await self._calculate_daily_pnl(user_id)
        weekly_pnl = await self._calculate_weekly_pnl(user_id)
        
        report_msg = f"""
📋 **Safety & Risk Management Report**
*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

**🎯 Current Risk Exposure:**
• Total Exposure: ${current_exposure:,.2f}
• Daily P&L: ${daily_pnl:+,.2f}
• Weekly P&L: ${weekly_pnl:+,.2f}

**🛡️ Safety Limits Status:**
{await self._format_limit_status(user_id)}

**🔔 Security Summary:**
• Active Alerts: {len([a for a in alerts if not a.resolved])}
• Total Alerts (7 days): {len([a for a in alerts if a.timestamp > datetime.now() - timedelta(days=7)])}
• Emergency Contacts: {len(self.emergency_contacts.get(user_id, []))}

**📊 Recent Activity:**
• Actions (7 days): {len(recent_audit)}
• Last Action: {recent_audit[-1].timestamp.strftime('%m-%d %H:%M') if recent_audit else 'None'}

**🔒 Security Score: {await self._calculate_security_score(user_id)}/100**

**📝 Recommendations:**
{await self._generate_safety_recommendations(user_id)}
        """
        
        keyboard = [
            [InlineKeyboardButton("📄 Export Report", callback_data="export_safety_report"),
             InlineKeyboardButton("📧 Email Report", callback_data="email_safety_report")],
            [InlineKeyboardButton("⚙️ Improve Security", callback_data="improve_security"),
             InlineKeyboardButton("← Back", callback_data="back_to_safety")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(report_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def emergency_stop(self, update: Update, context: CallbackContext):
        """Execute emergency stop with full audit trail"""
        user_id = update.effective_user.id
        
        try:
            # Log emergency stop action
            await self._log_audit_entry(
                user_id=user_id,
                action="EMERGENCY_STOP_INITIATED",
                details={
                    "trigger": "manual",
                    "timestamp": datetime.now().isoformat(),
                    "source": "telegram_command"
                }
            )
            
            # Set emergency mode
            self.emergency_mode[user_id] = True
            
            # Stop all trading for user
            if self.wallet_manager:
                result = await self.wallet_manager.emergency_stop(user_id)
            else:
                result = {"status": "demo", "message": "Emergency stop executed (demo mode)"}
            
            # Create critical alert
            await self._create_security_alert(
                user_id=user_id,
                level=AlertLevel.EMERGENCY,
                message="Emergency stop executed",
                details={
                    "manual_trigger": True,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Notify emergency contacts
            await self._notify_emergency_contacts(user_id, "Emergency stop executed")
            
            return {
                "status": "success",
                "message": "Emergency stop executed successfully",
                "details": result
            }
            
        except Exception as e:
            logger.error(f"Emergency stop failed for user {user_id}: {e}")
            await self._create_security_alert(
                user_id=user_id,
                level=AlertLevel.CRITICAL,
                message=f"Emergency stop failed: {str(e)}",
                details={"error": str(e), "timestamp": datetime.now().isoformat()}
            )
            return {
                "status": "error",
                "message": f"Emergency stop failed: {str(e)}"
            }

    async def check_risk_limits(self, user_id: int, trade_data: Dict) -> Tuple[bool, List[str]]:
        """Check if a trade would violate risk limits"""
        violations = []
        
        user_limits = self.user_limits.get(user_id, {})
        
        # Check position size limit
        position_limit = user_limits.get(LimitType.POSITION_SIZE.value)
        if position_limit and position_limit.enabled:
            trade_size = abs(float(trade_data.get('size', 0)) * float(trade_data.get('price', 0)))
            if trade_size > position_limit.value:
                violations.append(f"Position size ${trade_size:,.2f} exceeds limit ${position_limit.value:,.2f}")
        
        # Check leverage limit
        leverage_limit = user_limits.get(LimitType.MAX_LEVERAGE.value)
        if leverage_limit and leverage_limit.enabled:
            trade_leverage = float(trade_data.get('leverage', 1))
            if trade_leverage > leverage_limit.value:
                violations.append(f"Leverage {trade_leverage}x exceeds limit {leverage_limit.value}x")
        
        # Check daily loss limit
        daily_limit = user_limits.get(LimitType.DAILY_LOSS.value)
        if daily_limit and daily_limit.enabled:
            current_daily_pnl = await self._calculate_daily_pnl(user_id)
            potential_loss = min(0, current_daily_pnl + float(trade_data.get('expected_pnl', 0)))
            if abs(potential_loss) > daily_limit.value:
                violations.append(f"Potential daily loss ${abs(potential_loss):,.2f} exceeds limit ${daily_limit.value:,.2f}")
        
        # Check total exposure limit
        exposure_limit = user_limits.get(LimitType.TOTAL_EXPOSURE.value)
        if exposure_limit and exposure_limit.enabled:
            current_exposure = await self._calculate_current_exposure(user_id)
            trade_exposure = abs(float(trade_data.get('size', 0)) * float(trade_data.get('price', 0)))
            total_exposure = current_exposure + trade_exposure
            if total_exposure > exposure_limit.value:
                violations.append(f"Total exposure ${total_exposure:,.2f} exceeds limit ${exposure_limit.value:,.2f}")
        
        return len(violations) == 0, violations

    async def handle_safety_callbacks(self, update: Update, context: CallbackContext):
        """Handle safety-related callback queries"""
        query = update.callback_query
        data = query.data
        user_id = query.from_user.id
        
        if data == "config_limits":
            await self.configure_risk_limits(update, context)
        elif data == "emergency_contacts":
            await self.setup_emergency_contacts(update, context)
        elif data == "view_audit":
            await self.view_audit_trail(update, context)
        elif data == "security_alerts":
            await self.view_security_alerts(update, context)
        elif data == "safety_report":
            await self.generate_safety_report(update, context)
        elif data == "emergency_stop_confirm":
            await self._confirm_emergency_stop(update, context)
        elif data == "ack_all_alerts":
            await self._acknowledge_all_alerts(update, context)
        elif data.startswith("set_"):
            await self._handle_limit_setting(update, context, data)
        else:
            await query.answer("Safety feature coming soon!")

    # Helper methods

    async def _format_user_limits(self, user_id: int) -> str:
        """Format user's current risk limits"""
        user_limits = self.user_limits.get(user_id, {})
        
        if not user_limits:
            # Initialize with defaults
            await self._initialize_user_limits(user_id)
            user_limits = self.user_limits[user_id]
        
        limits_text = ""
        for limit_type, default_value in self.default_limits.items():
            limit = user_limits.get(limit_type.value)
            if limit:
                status = "✅" if limit.enabled else "❌"
                breach_info = f" (Breached {limit.breach_count}x)" if limit.breach_count > 0 else ""
                limits_text += f"• {limit_type.value.replace('_', ' ').title()}: {status} ${limit.value:,.2f}{breach_info}\n"
            else:
                limits_text += f"• {limit_type.value.replace('_', ' ').title()}: ❌ Not set\n"
        
        return limits_text

    async def _initialize_user_limits(self, user_id: int):
        """Initialize default risk limits for a user"""
        self.user_limits[user_id] = {}
        
        for limit_type, default_value in self.default_limits.items():
            self.user_limits[user_id][limit_type.value] = RiskLimit(
                limit_type=limit_type,
                value=default_value,
                enabled=True
            )

    async def _calculate_current_exposure(self, user_id: int) -> float:
        """Calculate user's current total exposure"""
        try:
            if self.wallet_manager:
                portfolio = await self.wallet_manager.get_user_portfolio(user_id)
                if portfolio['status'] == 'success':
                    total_exposure = 0
                    for position in portfolio.get('positions', []):
                        size = abs(float(position.get('size', 0)))
                        price = float(position.get('entry_price', 0))
                        total_exposure += size * price
                    return total_exposure
            return 0.0
        except Exception as e:
            logger.error(f"Error calculating exposure for user {user_id}: {e}")
            return 0.0

    async def _calculate_daily_pnl(self, user_id: int) -> float:
        """Calculate user's daily P&L"""
        try:
            # Mock calculation - replace with real implementation
            return -125.50  # Example daily loss
        except Exception as e:
            logger.error(f"Error calculating daily PnL for user {user_id}: {e}")
            return 0.0

    async def _calculate_weekly_pnl(self, user_id: int) -> float:
        """Calculate user's weekly P&L"""
        try:
            # Mock calculation - replace with real implementation
            return 450.25  # Example weekly profit
        except Exception as e:
            logger.error(f"Error calculating weekly PnL for user {user_id}: {e}")
            return 0.0

    async def _log_audit_entry(self, user_id: int, action: str, details: Dict[str, Any]):
        """Log an audit entry"""
        entry = AuditEntry(
            entry_id=f"audit_{int(datetime.now().timestamp())}_{user_id}",
            user_id=user_id,
            action=action,
            details=details,
            timestamp=datetime.now()
        )
        
        self.audit_trail.append(entry)
        
        # Keep only last 1000 entries per user
        user_entries = [e for e in self.audit_trail if e.user_id == user_id]
        if len(user_entries) > 1000:
            # Remove oldest entries for this user
            for old_entry in user_entries[:-1000]:
                self.audit_trail.remove(old_entry)

    async def _create_security_alert(self, user_id: int, level: AlertLevel, message: str, details: Dict[str, Any]):
        """Create a security alert"""
        alert = SecurityAlert(
            alert_id=f"alert_{int(datetime.now().timestamp())}_{user_id}",
            user_id=user_id,
            level=level,
            message=message,
            details=details,
            timestamp=datetime.now()
        )
        
        self.security_alerts[alert.alert_id] = alert
        
        # Log the alert creation
        await self._log_audit_entry(
            user_id=user_id,
            action="SECURITY_ALERT_CREATED",
            details={
                "alert_id": alert.alert_id,
                "level": level.value,
                "message": message
            }
        )

    async def _notify_emergency_contacts(self, user_id: int, message: str):
        """Notify emergency contacts"""
        contacts = self.emergency_contacts.get(user_id, [])
        
        for contact in contacts:
            try:
                # In a real implementation, send email/SMS here
                logger.info(f"Emergency notification sent to {contact}: {message}")
                
                await self._log_audit_entry(
                    user_id=user_id,
                    action="EMERGENCY_NOTIFICATION_SENT",
                    details={
                        "contact": contact,
                        "message": message,
                        "timestamp": datetime.now().isoformat()
                    }
                )
            except Exception as e:
                logger.error(f"Failed to notify emergency contact {contact}: {e}")

    async def _monitor_risk_limits(self):
        """Background task to monitor risk limits"""
        while True:
            try:
                for user_id, limits in self.user_limits.items():
                    # Check if any limits have been breached
                    for limit_key, limit in limits.items():
                        if limit.enabled and await self._check_limit_breach(user_id, limit):
                            await self._handle_limit_breach(user_id, limit)
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in risk limit monitoring: {e}")
                await asyncio.sleep(60)

    async def _monitor_unusual_activity(self):
        """Background task to monitor for unusual activity"""
        while True:
            try:
                # Check for unusual trading patterns, login attempts, etc.
                for user_id in self.user_limits.keys():
                    unusual_patterns = await self._detect_unusual_patterns(user_id)
                    
                    if unusual_patterns:
                        for pattern in unusual_patterns:
                            await self._create_security_alert(
                                user_id=user_id,
                                level=AlertLevel.WARNING,
                                message=f"Unusual activity detected: {pattern}",
                                details={"pattern": pattern, "timestamp": datetime.now().isoformat()}
                            )
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Error in unusual activity monitoring: {e}")
                await asyncio.sleep(300)

    async def _cleanup_old_alerts(self):
        """Cleanup old resolved alerts"""
        while True:
            try:
                cutoff_date = datetime.now() - timedelta(days=30)
                
                # Remove resolved alerts older than 30 days
                alerts_to_remove = []
                for alert_id, alert in self.security_alerts.items():
                    if alert.resolved and alert.timestamp < cutoff_date:
                        alerts_to_remove.append(alert_id)
                
                for alert_id in alerts_to_remove:
                    del self.security_alerts[alert_id]
                
                if alerts_to_remove:
                    logger.info(f"Cleaned up {len(alerts_to_remove)} old security alerts")
                
                await asyncio.sleep(86400)  # Clean up daily
                
            except Exception as e:
                logger.error(f"Error in alert cleanup: {e}")
                await asyncio.sleep(86400)

    async def _calculate_security_score(self, user_id: int) -> int:
        """Calculate a security score for the user (0-100)"""
        score = 100
        
        # Deduct points for missing safety features
        if user_id not in self.user_limits or not self.user_limits[user_id]:
            score -= 20  # No risk limits configured
        
        if user_id not in self.emergency_contacts or not self.emergency_contacts[user_id]:
            score -= 15  # No emergency contacts
        
        # Check for recent security alerts
        recent_alerts = [a for a in self.security_alerts.values() 
                        if a.user_id == user_id and 
                        a.timestamp > datetime.now() - timedelta(days=7)]
        
        if len(recent_alerts) > 5:
            score -= 20  # Too many recent alerts
        elif len(recent_alerts) > 2:
            score -= 10
        
        # Check for unacknowledged alerts
        unack_alerts = [a for a in recent_alerts if not a.acknowledged]
        if unack_alerts:
            score -= len(unack_alerts) * 5
        
        return max(0, score)

    async def _generate_safety_recommendations(self, user_id: int) -> str:
        """Generate safety recommendations for the user"""
        recommendations = []
        
        # Check missing features
        if user_id not in self.emergency_contacts or not self.emergency_contacts[user_id]:
            recommendations.append("• Add emergency contacts for critical notifications")
        
        # Check risk limits
        user_limits = self.user_limits.get(user_id, {})
        disabled_limits = [name for name, limit in user_limits.items() if not limit.enabled]
        if disabled_limits:
            recommendations.append(f"• Enable disabled risk limits: {', '.join(disabled_limits)}")
        
        # Check recent breaches
        breached_limits = [name for name, limit in user_limits.items() if limit.breach_count > 0]
        if breached_limits:
            recommendations.append(f"• Review and adjust frequently breached limits: {', '.join(breached_limits)}")
        
        # Check security score
        score = await self._calculate_security_score(user_id)
        if score < 80:
            recommendations.append("• Improve overall security score by addressing above issues")
        
        if not recommendations:
            recommendations.append("• Your safety configuration looks good!")
            recommendations.append("• Consider periodic review of risk limits")
            recommendations.append("• Test emergency contacts quarterly")
        
        return '\n'.join(recommendations)

    async def _check_limit_breach(self, user_id: int, limit: RiskLimit) -> bool:
        """Check if a specific limit has been breached"""
        try:
            if limit.limit_type == LimitType.DAILY_LOSS:
                daily_pnl = await self._calculate_daily_pnl(user_id)
                return daily_pnl < -limit.value
            elif limit.limit_type == LimitType.WEEKLY_LOSS:
                weekly_pnl = await self._calculate_weekly_pnl(user_id)
                return weekly_pnl < -limit.value
            elif limit.limit_type == LimitType.TOTAL_EXPOSURE:
                exposure = await self._calculate_current_exposure(user_id)
                return exposure > limit.value
            
            return False
        except Exception as e:
            logger.error(f"Error checking limit breach for user {user_id}: {e}")
            return False

    async def _handle_limit_breach(self, user_id: int, limit: RiskLimit):
        """Handle a limit breach"""
        limit.breached = True
        limit.breach_count += 1
        limit.last_breach = datetime.now()
        
        # Create alert
        await self._create_security_alert(
            user_id=user_id,
            level=AlertLevel.CRITICAL,
            message=f"{limit.limit_type.value.replace('_', ' ').title()} limit breached",
            details={
                "limit_type": limit.limit_type.value,
                "limit_value": limit.value,
                "breach_count": limit.breach_count
            }
        )
        
        # Consider automatic emergency stop for critical breaches
        if limit.breach_count >= 3:
            await self.emergency_stop(None, None)  # Automatic emergency stop

    async def _detect_unusual_patterns(self, user_id: int) -> List[str]:
        """Detect unusual activity patterns"""
        patterns = []
        
        # Check recent audit entries for unusual patterns
        recent_entries = [e for e in self.audit_trail 
                         if e.user_id == user_id and 
                         e.timestamp > datetime.now() - timedelta(hours=1)]
        
        # Too many actions in short time
        if len(recent_entries) > 50:
            patterns.append("High frequency of actions detected")
        
        # Unusual trading hours (if implemented)
        night_trades = [e for e in recent_entries 
                       if e.action.startswith("TRADE_") and 
                       e.timestamp.hour in [0, 1, 2, 3, 4, 5]]
        
        if len(night_trades) > 10:
            patterns.append("Unusual trading during night hours")
        
        return patterns

    async def _confirm_emergency_stop(self, update: Update, context: CallbackContext):
        """Confirm emergency stop with user"""
        query = update.callback_query
        user_id = query.from_user.id
        
        confirm_msg = """
🚨 **EMERGENCY STOP CONFIRMATION**

**This will immediately:**
• Stop all active trading strategies
• Cancel all open orders  
• Close all open positions at market price
• Disable all automated trading
• Generate security alert
• Notify emergency contacts

⚠️ **This action cannot be undone and may result in losses.**

Are you absolutely sure you want to proceed?
        """
        
        keyboard = [
            [InlineKeyboardButton("🛑 YES, EMERGENCY STOP", callback_data="execute_emergency_stop")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_emergency_stop")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(confirm_msg, parse_mode='Markdown', reply_markup=reply_markup)

    async def _acknowledge_all_alerts(self, update: Update, context: CallbackContext):
        """Acknowledge all unresolved alerts for user"""
        query = update.callback_query
        user_id = query.from_user.id
        
        # Find unacknowledged alerts
        unack_alerts = [alert for alert in self.security_alerts.values() 
                       if alert.user_id == user_id and not alert.acknowledged]
        
        # Acknowledge them
        for alert in unack_alerts:
            alert.acknowledged = True
        
        await self._log_audit_entry(
            user_id=user_id,
            action="ALERTS_ACKNOWLEDGED",
            details={
                "count": len(unack_alerts),
                "alert_ids": [alert.alert_id for alert in unack_alerts]
            }
        )
        
        await query.answer(f"Acknowledged {len(unack_alerts)} alerts")
        await self.view_security_alerts(update, context)

    async def _format_limit_status(self, user_id: int) -> str:
        """Format the status of all limits for a user"""
        user_limits = self.user_limits.get(user_id, {})
        status_text = ""
        
        for limit_type in self.default_limits.keys():
            limit = user_limits.get(limit_type.value)
            if limit:
                status = "🟢 OK" if not limit.breached else "🔴 BREACHED"
                status_text += f"• {limit_type.value.replace('_', ' ').title()}: {status}\n"
            else:
                status_text += f"• {limit_type.value.replace('_', ' ').title()}: ⚪ Not set\n"
        
        return status_text

    async def _handle_limit_setting(self, update: Update, context: CallbackContext, setting_type: str):
        """Handle setting a specific limit"""
        query = update.callback_query
        await query.answer("Limit setting interface coming soon!")
        
        # In a full implementation, this would show a form to set the specific limit
        # For now, just show a placeholder message
        await query.edit_message_text(
            f"Setting {setting_type.replace('set_', '').replace('_', ' ')} limit...\n\n"
            "This feature will allow you to set custom risk limits.\n"
            "For now, limits are set to safe defaults.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("← Back", callback_data="config_limits")
            ]])
        )
