"""
Admin panel for bot management and monitoring
Provides comprehensive admin controls and oversight
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .audit_logger import audit_logger
from .rate_limiter import rate_limiter

logger = logging.getLogger(__name__)

class AdminPanel:
    """
    Comprehensive admin panel for bot management
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.admin_users: Set[int] = set(config.get("telegram", {}).get("admin_users", []))
        self.super_admin: Optional[int] = config.get("telegram", {}).get("super_admin")
        
        # Admin permissions
        self.admin_permissions = {
            'view_users': True,
            'view_logs': True,
            'manage_rate_limits': True,
            'emergency_actions': True,
            'system_status': True,
        }
        
        # Super admin permissions (everything + user management)
        self.super_admin_permissions = {
            **self.admin_permissions,
            'add_admin': True,
            'remove_admin': True,
            'system_config': True,
            'user_deletion': True,
        }
        
        logger.info(f"AdminPanel initialized with {len(self.admin_users)} admin users")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.admin_users or user_id == self.super_admin
    
    def is_super_admin(self, user_id: int) -> bool:
        """Check if user is the super admin"""
        return user_id == self.super_admin
    
    def get_permissions(self, user_id: int) -> Dict[str, bool]:
        """Get permissions for a user"""
        if self.is_super_admin(user_id):
            return self.super_admin_permissions
        elif self.is_admin(user_id):
            return self.admin_permissions
        else:
            return {}
    
    async def handle_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /admin command"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ Access denied. You are not authorized to use admin commands.")
            await audit_logger.log_security_event(
                event_type="unauthorized_admin_access",
                severity="medium",
                description="Non-admin user attempted to access admin panel",
                user_id=user_id,
                username=update.effective_user.username
            )
            return
        
        # Log admin access
        await audit_logger.log_admin_action(
            admin_user_id=user_id,
            admin_username=update.effective_user.username,
            action="access_admin_panel"
        )
        
        permissions = self.get_permissions(user_id)
        admin_type = "Super Admin" if self.is_super_admin(user_id) else "Admin"
        
        # Create admin menu
        keyboard = []
        
        if permissions.get('system_status'):
            keyboard.append([InlineKeyboardButton("📊 System Status", callback_data="admin_system_status")])
        
        if permissions.get('view_users'):
            keyboard.append([InlineKeyboardButton("👥 User Management", callback_data="admin_user_management")])
        
        if permissions.get('view_logs'):
            keyboard.append([InlineKeyboardButton("📋 Audit Logs", callback_data="admin_audit_logs")])
        
        if permissions.get('manage_rate_limits'):
            keyboard.append([InlineKeyboardButton("⏱️ Rate Limits", callback_data="admin_rate_limits")])
        
        if permissions.get('emergency_actions'):
            keyboard.append([InlineKeyboardButton("🚨 Emergency Actions", callback_data="admin_emergency")])
        
        if permissions.get('system_config'):
            keyboard.append([InlineKeyboardButton("⚙️ System Config", callback_data="admin_system_config")])
        
        keyboard.append([InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")])
        
        await update.message.reply_text(
            f"🛡️ **Admin Panel** ({admin_type})\n\n"
            f"Welcome, {update.effective_user.first_name}!\n"
            f"Select an option below to manage the bot:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_system_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show system status"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            return
        
        query = update.callback_query
        await query.answer()
        
        try:
            # Get system statistics
            from database import bot_db
            
            # Get user count
            user_count = 0
            agent_count = 0
            active_users = 0
            
            try:
                async with bot_db.conn.cursor() as cursor:
                    # Total users
                    await cursor.execute("SELECT COUNT(*) FROM users")
                    result = await cursor.fetchone()
                    user_count = result[0] if result else 0
                    
                    # Users with agent wallets
                    await cursor.execute("SELECT COUNT(*) FROM users WHERE agent_wallet_address IS NOT NULL")
                    result = await cursor.fetchone()
                    agent_count = result[0] if result else 0
                    
                    # Active users (last 24 hours)
                    await cursor.execute(
                        "SELECT COUNT(*) FROM users WHERE last_active > datetime('now', '-1 day')"
                    )
                    result = await cursor.fetchone()
                    active_users = result[0] if result else 0
            except Exception as e:
                logger.error(f"Error getting user stats: {e}")
            
            # Get rate limiter stats
            rate_stats = {
                'blocked_users': len(rate_limiter.blocked_users),
                'active_sessions': len(rate_limiter.global_history)
            }
            
            # System uptime (approximate)
            uptime = "System started recently"  # You could track this more precisely
            
            status_message = (
                f"📊 **System Status**\n\n"
                f"**User Statistics:**\n"
                f"• Total Users: {user_count}\n"
                f"• Agent Wallets: {agent_count}\n"
                f"• Active (24h): {active_users}\n\n"
                f"**Rate Limiting:**\n"
                f"• Blocked Users: {rate_stats['blocked_users']}\n"
                f"• Active Sessions: {rate_stats['active_sessions']}\n\n"
                f"**System:**\n"
                f"• Uptime: {uptime}\n"
                f"• Status: ✅ Operational\n"
                f"• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="admin_system_status")],
                [InlineKeyboardButton("◀️ Back", callback_data="admin_refresh")]
            ]
            
            await query.edit_message_text(
                status_message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Error showing system status: {e}")
            await query.edit_message_text(
                f"❌ Error retrieving system status: {str(e)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back", callback_data="admin_refresh")]
                ])
            )
    
    async def handle_user_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show user management panel"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            return
        
        query = update.callback_query
        await query.answer()
        
        try:
            # Get recent users
            from database import bot_db
            
            recent_users = []
            try:
                async with bot_db.conn.cursor() as cursor:
                    await cursor.execute('''
                        SELECT telegram_id, telegram_username, status, created_at,
                               agent_wallet_address, last_active
                        FROM users
                        ORDER BY created_at DESC
                        LIMIT 10
                    ''')
                    rows = await cursor.fetchall()
                    
                    for row in rows:
                        recent_users.append({
                            'telegram_id': row[0],
                            'username': row[1] or 'Unknown',
                            'status': row[2] or 'unknown',
                            'created_at': row[3],
                            'has_agent': bool(row[4]),
                            'last_active': row[5]
                        })
            except Exception as e:
                logger.error(f"Error getting recent users: {e}")
            
            user_list = "**Recent Users:**\n\n"
            for user in recent_users[:5]:  # Show top 5
                status_emoji = "✅" if user['has_agent'] else "⚠️"
                user_list += (
                    f"{status_emoji} {user['username']} (ID: {user['telegram_id']})\n"
                    f"   Status: {user['status']}\n"
                    f"   Created: {user['created_at'][:10] if user['created_at'] else 'Unknown'}\n\n"
                )
            
            if not recent_users:
                user_list = "No users found."
            
            keyboard = [
                [InlineKeyboardButton("🔍 Search User", callback_data="admin_search_user")],
                [InlineKeyboardButton("📊 User Stats", callback_data="admin_user_stats")],
                [InlineKeyboardButton("◀️ Back", callback_data="admin_refresh")]
            ]
            
            await query.edit_message_text(
                f"👥 **User Management**\n\n{user_list}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Error in user management: {e}")
            await query.edit_message_text(
                f"❌ Error loading user management: {str(e)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back", callback_data="admin_refresh")]
                ])
            )
    
    async def handle_audit_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show audit logs"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            return
        
        query = update.callback_query
        await query.answer()
        
        try:
            # Get recent audit logs
            recent_logs = await audit_logger.get_admin_audit_log(limit=5)
            recent_security = await audit_logger.get_security_events(limit=5)
            
            log_text = "**Recent Admin Actions:**\n\n"
            for log in recent_logs:
                timestamp = datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %H:%M')
                log_text += f"• {timestamp} - {log['admin_username']} - {log['action']}\n"
            
            if not recent_logs:
                log_text += "No recent admin actions.\n"
            
            log_text += "\n**Recent Security Events:**\n\n"
            for event in recent_security:
                timestamp = datetime.fromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M')
                severity_emoji = {"low": "ℹ️", "medium": "⚠️", "high": "🚨", "critical": "🔥"}.get(event['severity'], "❓")
                log_text += f"{severity_emoji} {timestamp} - {event['event_type']}\n"
            
            if not recent_security:
                log_text += "No recent security events.\n"
            
            keyboard = [
                [InlineKeyboardButton("📋 Full Audit Log", callback_data="admin_full_audit")],
                [InlineKeyboardButton("🔐 Security Events", callback_data="admin_security_events")],
                [InlineKeyboardButton("◀️ Back", callback_data="admin_refresh")]
            ]
            
            await query.edit_message_text(
                f"📋 **Audit Logs**\n\n{log_text}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"Error showing audit logs: {e}")
            await query.edit_message_text(
                f"❌ Error loading audit logs: {str(e)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back", callback_data="admin_refresh")]
                ])
            )
    
    async def handle_emergency_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show emergency actions panel"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            return
        
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("🛑 Stop All Trading", callback_data="admin_emergency_stop_all")],
            [InlineKeyboardButton("🚫 Block User", callback_data="admin_block_user")],
            [InlineKeyboardButton("🔄 Reset Rate Limits", callback_data="admin_reset_limits")],
            [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("◀️ Back", callback_data="admin_refresh")]
        ]
        
        await query.edit_message_text(
            "🚨 **Emergency Actions**\n\n"
            "⚠️ **WARNING:** These actions affect all users or system operations.\n"
            "Use with extreme caution.\n\n"
            "Select an emergency action:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# Global admin panel instance
admin_panel = None

def initialize_admin_panel(config: Dict) -> AdminPanel:
    """Initialize the global admin panel"""
    global admin_panel
    admin_panel = AdminPanel(config)
    return admin_panel
