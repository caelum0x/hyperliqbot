"""
Compliance and legal framework for the trading bot
Handles terms of service, risk warnings, and regulatory compliance
"""
import logging
from datetime import datetime
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .audit_logger import audit_logger

logger = logging.getLogger(__name__)

class ComplianceManager:
    """
    Manages compliance, risk warnings, and legal requirements
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.terms_version = "1.0"
        self.risk_warning_version = "1.0"
        
        # Environment settings
        self.is_testnet = config.get("hyperliquid", {}).get("api_url", "").find("testnet") != -1
        self.environment = "TESTNET" if self.is_testnet else "MAINNET"
        
        logger.info(f"ComplianceManager initialized for {self.environment}")
    
    def get_terms_of_service(self) -> str:
        """Get the current terms of service"""
        return f"""
**TERMS OF SERVICE v{self.terms_version}**

**Environment: {self.environment}**

**1. ACCEPTANCE OF TERMS**
By using this trading bot, you agree to these terms.

**2. DESCRIPTION OF SERVICE**
This bot provides automated trading services on the Hyperliquid DEX using agent wallets.

**3. RISK DISCLOSURE**
• Trading involves substantial risk of loss
• Past performance does not guarantee future results
• You may lose all deposited funds
• Market volatility can cause rapid losses
• Bot strategies may not perform as expected

**4. USER RESPONSIBILITIES**
• You must be legally able to trade derivatives
• You are responsible for all trading decisions
• You must secure your wallet and private keys
• You must comply with local laws and regulations

**5. LIMITATIONS OF LIABILITY**
• Service provided "AS IS" without warranties
• We are not liable for trading losses
• We are not liable for technical failures
• Maximum liability limited to service fees paid

**6. INTELLECTUAL PROPERTY**
All bot code and strategies are proprietary.

**7. TERMINATION**
We may terminate service at any time.

**8. GOVERNING LAW**
These terms are governed by applicable law.

**9. CONTACT**
For questions, contact our support team.

Last updated: {datetime.now().strftime('%Y-%m-%d')}
        """.strip()
    
    def get_risk_warning(self) -> str:
        """Get comprehensive risk warning"""
        env_warning = ""
        if self.is_testnet:
            env_warning = "⚠️ **TESTNET ENVIRONMENT** - This is for testing only with test funds.\n\n"
        else:
            env_warning = "🚨 **MAINNET ENVIRONMENT** - This involves real money and real risks.\n\n"
        
        return f"""
**RISK WARNING v{self.risk_warning_version}**

{env_warning}**IMPORTANT RISK DISCLOSURES:**

🔥 **HIGH RISK INVESTMENT**
• Cryptocurrency trading is highly speculative
• You can lose 100% of your invested capital
• Only invest what you can afford to lose

⚡ **MARKET RISKS**
• Extreme price volatility
• Market manipulation risks
• Liquidity risks
• Slippage and execution risks

🤖 **AUTOMATED TRADING RISKS**
• Algorithms may malfunction
• Market conditions may change rapidly
• Strategies may become unprofitable
• Technical failures can occur

🔐 **SECURITY RISKS**
• Smart contract risks
• Wallet security risks
• Exchange risks
• Network congestion risks

📊 **PERFORMANCE RISKS**
• No guarantee of profits
• Historical performance ≠ future results
• Drawdowns may be significant
• Recovery not guaranteed

⚖️ **REGULATORY RISKS**
• Regulatory changes may affect service
• Some jurisdictions may prohibit use
• Tax implications vary by location
• Compliance is your responsibility

**BY CONTINUING, YOU ACKNOWLEDGE:**
✅ You understand these risks
✅ You accept full responsibility for losses
✅ You have read and agree to Terms of Service
✅ You are legally permitted to use this service

**Environment: {self.environment}**
**Warning issued: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}**
        """.strip()
    
    async def show_compliance_agreement(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Show compliance agreement and get user acceptance
        
        Returns:
            bool: True if user should proceed to agreement, False if already handled
        """
        user_id = update.effective_user.id
        
        # Check if user has already agreed to current version
        # In production, you'd store this in database
        user_data = context.user_data
        agreed_terms_version = user_data.get("agreed_terms_version")
        agreed_risk_version = user_data.get("agreed_risk_version")
        
        if (agreed_terms_version == self.terms_version and 
            agreed_risk_version == self.risk_warning_version):
            return False  # User already agreed to current versions
        
        # Show risk warning first
        risk_warning = self.get_risk_warning()
        
        keyboard = [
            [InlineKeyboardButton("✅ I Understand the Risks", callback_data="compliance_accept_risk")],
            [InlineKeyboardButton("❌ Cancel", callback_data="compliance_cancel")]
        ]
        
        await update.effective_message.reply_text(
            risk_warning,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Log compliance display
        await audit_logger.log_user_action(
            user_id=user_id,
            username=update.effective_user.username,
            action="view_risk_warning",
            category="compliance",
            details={
                "risk_warning_version": self.risk_warning_version,
                "environment": self.environment
            }
        )
        
        return True
    
    async def handle_risk_acceptance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle risk warning acceptance"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        # Show terms of service
        terms = self.get_terms_of_service()
        
        keyboard = [
            [InlineKeyboardButton("✅ I Agree to Terms", callback_data="compliance_accept_terms")],
            [InlineKeyboardButton("📄 Read Again", callback_data="compliance_reread")],
            [InlineKeyboardButton("❌ I Do Not Agree", callback_data="compliance_cancel")]
        ]
        
        await query.edit_message_text(
            terms,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Log risk acceptance
        await audit_logger.log_user_action(
            user_id=user_id,
            username=query.from_user.username,
            action="accept_risk_warning",
            category="compliance",
            details={
                "risk_warning_version": self.risk_warning_version,
                "environment": self.environment,
                "timestamp": datetime.now().isoformat()
            }
        )
    
    async def handle_terms_acceptance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle terms of service acceptance"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        # Store acceptance
        context.user_data["agreed_terms_version"] = self.terms_version
        context.user_data["agreed_risk_version"] = self.risk_warning_version
        context.user_data["compliance_agreed_at"] = datetime.now().isoformat()
        
        # Log terms acceptance
        await audit_logger.log_user_action(
            user_id=user_id,
            username=query.from_user.username,
            action="accept_terms_of_service",
            category="compliance",
            details={
                "terms_version": self.terms_version,
                "risk_warning_version": self.risk_warning_version,
                "environment": self.environment,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        # Show confirmation and next steps
        env_note = ""
        if self.is_testnet:
            env_note = "\n\n🧪 **TESTNET MODE**: You are using test funds. No real money is at risk."
        else:
            env_note = "\n\n💰 **MAINNET MODE**: You are using real funds. All risks apply."
        
        await query.edit_message_text(
            f"✅ **Compliance Complete**\n\n"
            f"Thank you for accepting our Terms of Service and Risk Warning.\n\n"
            f"**What you agreed to:**\n"
            f"• Terms of Service v{self.terms_version}\n"
            f"• Risk Warning v{self.risk_warning_version}\n"
            f"• Environment: {self.environment}\n\n"
            f"You can now proceed to create your agent wallet.{env_note}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ Continue to Agent Creation", callback_data="compliance_continue")]
            ])
        )
    
    async def handle_compliance_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle compliance cancellation"""
        query = update.callback_query
        user_id = query.from_user.id
        
        await query.answer()
        
        # Log cancellation
        await audit_logger.log_user_action(
            user_id=user_id,
            username=query.from_user.username,
            action="cancel_compliance",
            category="compliance",
            details={
                "environment": self.environment,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        await query.edit_message_text(
            "❌ **Agreement Cancelled**\n\n"
            "You must agree to our Terms of Service and Risk Warning to use this bot.\n\n"
            "You can restart the process anytime with /create_agent.\n\n"
            "If you have questions about our terms, please contact support.",
            parse_mode='Markdown'
        )
    
    def check_compliance_status(self, context: ContextTypes.DEFAULT_TYPE) -> Dict[str, bool]:
        """
        Check user's compliance status
        
        Returns:
            Dict with compliance status
        """
        user_data = context.user_data
        
        agreed_terms = user_data.get("agreed_terms_version") == self.terms_version
        agreed_risk = user_data.get("agreed_risk_version") == self.risk_warning_version
        
        return {
            "terms_agreed": agreed_terms,
            "risk_agreed": agreed_risk,
            "fully_compliant": agreed_terms and agreed_risk,
            "environment": self.environment
        }

# Global compliance manager instance
compliance_manager = None

def initialize_compliance_manager(config: Dict) -> ComplianceManager:
    """Initialize the global compliance manager"""
    global compliance_manager
    compliance_manager = ComplianceManager(config)
    return compliance_manager
