from dataclasses import dataclass, field
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

@dataclass
class TradingConfig:
    """Trading configuration based on actual Hyperliquid fee structure"""
    # Real Hyperliquid fee rates from knowledge doc
    base_taker_fee: float = 0.00035      # 0.035% for <$5M volume
    base_maker_fee: float = 0.0001       # 0.01% for <$5M volume
    
    # Maker rebate rates (negative = rebate)
    rebate_tier_1: float = -0.00001      # -0.001% for >0.5% maker volume
    rebate_tier_2: float = -0.00002      # -0.002% for >1.5% maker volume  
    rebate_tier_3: float = -0.00003      # -0.003% for >3% maker volume
    
    # Volume thresholds for fee tiers (14-day volume)
    tier_1_volume: float = 5000000       # $5M
    tier_2_volume: float = 25000000      # $25M
    tier_3_volume: float = 125000000     # $125M
    
    # Risk management
    max_position_size: float = 10000     # $10k max position
    min_profit_threshold: float = 0.001  # 0.1% minimum profit
    
    # Vault settings
    vault_profit_share: float = 0.10     # 10% profit share (actual rate)
    vault_minimum_capital: float = 100   # 100 USDC minimum
    vault_leader_min_ownership: float = 0.05  # 5% minimum ownership
    
    # Referral settings
    referral_commission_rate: float = 0.10    # 10% of referee fees
    referral_user_discount: float = 0.004    # 4% fee discount
    referral_volume_limit: float = 25000000  # $25M per referee

    # Trading settings
    max_position_size_usd: float = 10000.0
    default_slippage_pct: float = 0.005  # 0.5%
    risk_level: str = "medium"  # e.g., "low", "medium", "high"
    
    # Example strategy-specific configurations
    grid_trading_config: Dict[str, any] = field(default_factory=lambda: {
        "levels": 10,
        "spacing_pct": 0.002,  # 0.2% spacing between grid levels
        "enabled": True,
        "default_pair": "BTC-USD" # Example
    })
    
    dca_config: Dict[str, any] = field(default_factory=lambda: {
        "amount_per_buy_usd": 100.0,
        "interval_hours": 24, # Buy every 24 hours
        "enabled": False,
        "default_pair": "ETH-USD" # Example
    })

    # Add other trading-related configurations as needed
    def __post_init__(self):
        # Perform any validation or post-processing if necessary
        if self.risk_level not in ["low", "medium", "high"]:
            raise ValueError("Invalid risk level specified in TradingConfig. Must be 'low', 'medium', or 'high'.")
        if not 0 < self.default_slippage_pct < 0.1: # Example validation: 0% < slippage < 10%
             logger.warning(f"Default slippage {self.default_slippage_pct*100}% is unusual. Ensure this is intended.")
