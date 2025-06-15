#!/usr/bin/env python3
"""
Professional Trading Analytics for Hyperliquid Alpha Bot
Provides market analysis functions used by the advanced trading system
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class TradingAnalytics:
    """Advanced market analytics similar to professional trading bots"""
    
    @staticmethod
    async def identify_trending_pairs(info, lookback_hours=24, min_volume=1000000):
        """
        Identify trending pairs based on volume and price movement
        Similar to how Bonk Bot identifies momentum opportunities
        
        Args:
            info: Hyperliquid info client
            lookback_hours: Hours to look back for trend analysis
            min_volume: Minimum 24h volume in USD
            
        Returns:
            List of trending pair symbols
        """
        try:
            # Get all asset contexts for volume analysis
            meta_and_ctx = info.meta_and_asset_ctxs()
            if not meta_and_ctx or len(meta_and_ctx) < 2:
                return ['BTC', 'ETH', 'SOL']  # Fallback
            
            universe = meta_and_ctx[0].get('universe', [])
            contexts = meta_and_ctx[1] if len(meta_and_ctx) > 1 else []
            
            # Get current mids for price data
            mids = info.all_mids()
            
            # Calculate metrics for trending detection
            trending_scores = []
            
            for i, asset_ctx in enumerate(contexts):
                if i >= len(universe):
                    continue
                    
                asset_name = universe[i].get('name', '')
                if not asset_name or asset_name not in mids:
                    continue
                
                # Extract metrics
                volume_24h = float(asset_ctx.get('dayNtlVlm', 0))
                open_interest = float(asset_ctx.get('openInterest', 0))
                funding_rate = float(asset_ctx.get('funding', {}).get('fundingRate', 0))
                
                # Skip if volume too low
                if volume_24h < min_volume:
                    continue
                
                # Calculate volatility score (placeholder - would use actual price data in full implementation)
                volatility_score = 1.0
                
                # Calculate trending score (combination of metrics)
                # Higher volume, higher OI, and funding rate magnitude all contribute
                trend_score = (
                    volume_24h / 1000000 * 0.5 +  # Volume component
                    open_interest / 1000000 * 0.3 +  # Open interest component
                    abs(funding_rate) * 100 * 0.2  # Funding rate component (absolute value)
                )
                
                trending_scores.append({
                    "asset": asset_name,
                    "score": trend_score,
                    "volume_24h": volume_24h
                })
            
            # Sort by score descending
            trending_scores.sort(key=lambda x: x["score"], reverse=True)
            
            # Extract just the asset names
            trending_pairs = [item["asset"] for item in trending_scores[:20]]
            
            # Ensure major pairs are included
            for major in ['BTC', 'ETH', 'SOL']:
                if major not in trending_pairs and major in mids:
                    trending_pairs.append(major)
                    
            logger.info(f"Identified {len(trending_pairs)} trending pairs")
            return trending_pairs[:20]  # Return top 20 pairs
            
        except Exception as e:
            logger.error(f"Error identifying trending pairs: {e}")
            return ['BTC', 'ETH', 'SOL']  # Fallback to major pairs
    
    @staticmethod
    async def detect_volume_spikes(info, lookback_minutes=30, threshold=2.0):
        """
        Detect volume spikes across all pairs
        Similar to professional bot volume spike detection
        
        Args:
            info: Hyperliquid info client
            lookback_minutes: Minutes to look back for baseline volume
            threshold: Multiple of average volume to consider a spike
            
        Returns:
            List of pairs with volume spikes and their scores
        """
        try:
            # This would typically use time-series data from an actual market data feed
            # Here we'll implement a placeholder based on available data
            
            meta_and_ctx = info.meta_and_asset_ctxs()
            if not meta_and_ctx or len(meta_and_ctx) < 2:
                return []
                
            universe = meta_and_ctx[0].get('universe', [])
            contexts = meta_and_ctx[1] if len(meta_and_ctx) > 1 else []
            
            # Look for signs of unusual activity in trading metrics
            spikes = []
            
            for i, asset_ctx in enumerate(contexts):
                if i >= len(universe):
                    continue
                    
                asset_name = universe[i].get('name', '')
                if not asset_name:
                    continue
                
                # Calculate 24h average hourly volume
                volume_24h = float(asset_ctx.get('dayNtlVlm', 0))
                avg_hourly_volume = volume_24h / 24
                
                # Get mark price for % change calculation
                try:
                    mark_px = float(asset_ctx.get('markPx', 0))
                    index_px = float(asset_ctx.get('indexPx', mark_px))
                    
                    # Calculate price deviation
                    if index_px > 0:
                        price_deviation = abs(mark_px - index_px) / index_px
                    else:
                        price_deviation = 0
                        
                except (ValueError, TypeError):
                    price_deviation = 0
                
                # Get recent volume (if available - this is a placeholder)
                recent_volume = float(asset_ctx.get('hourlyVol', avg_hourly_volume))
                
                # Check if recent volume significantly exceeds hourly average
                if recent_volume > avg_hourly_volume * threshold or price_deviation > 0.01:
                    # Calculate spike score
                    if avg_hourly_volume > 0:
                        volume_ratio = recent_volume / avg_hourly_volume
                    else:
                        volume_ratio = 1
                    
                    spike_score = volume_ratio + price_deviation * 100
                    
                    spikes.append({
                        "asset": asset_name,
                        "score": spike_score,
                        "volume_ratio": volume_ratio,
                        "price_deviation": price_deviation
                    })
            
            # Sort by score descending
            spikes.sort(key=lambda x: x["score"], reverse=True)
            
            return spikes[:10]  # Return top 10 volume spikes
            
        except Exception as e:
            logger.error(f"Error detecting volume spikes: {e}")
            return []
    
    @staticmethod
    async def analyze_funding_rates(info, threshold=0.01):
        """
        Analyze funding rates for arbitrage opportunities
        
        Args:
            info: Hyperliquid info client
            threshold: Minimum funding rate magnitude to consider
            
        Returns:
            Dict mapping pairs to their funding rates
        """
        try:
            meta_and_ctx = info.meta_and_asset_ctxs()
            if not meta_and_ctx or len(meta_and_ctx) < 2:
                return {}
                
            universe = meta_and_ctx[0].get('universe', [])
            contexts = meta_and_ctx[1] if len(meta_and_ctx) > 1 else []
            
            funding_opportunities = {}
            
            for i, asset_ctx in enumerate(contexts):
                if i >= len(universe):
                    continue
                    
                asset_name = universe[i].get('name', '')
                if not asset_name:
                    continue
                
                # Get funding rate
                funding_info = asset_ctx.get('funding', {})
                funding_rate = float(funding_info.get('fundingRate', 0))
                
                # If funding rate exceeds threshold (positive or negative)
                if abs(funding_rate) >= threshold:
                    # Annualize the funding rate (8-hourly * 3 * 365)
                    annualized_rate = funding_rate * 3 * 365
                    
                    funding_opportunities[asset_name] = {
                        "rate": funding_rate,
                        "annualized": annualized_rate,
                        "next_funding": funding_info.get('nextFundingTime', 0)
                    }
            
            return funding_opportunities
            
        except Exception as e:
            logger.error(f"Error analyzing funding rates: {e}")
            return {}
    
    @staticmethod
    async def calculate_daily_volume(info, user_address):
        """
        Calculate user's daily trading volume
        
        Args:
            info: Hyperliquid info client
            user_address: User's wallet address
            
        Returns:
            Float representing daily volume in USD
        """
        try:
            # In a real implementation, this would analyze actual trade history
            # Here we'll just estimate from user state
            
            user_state = info.user_state(user_address)
            positions = user_state.get("assetPositions", [])
            
            # Estimate daily volume from position sizes
            estimated_volume = 0
            for pos_data in positions:
                pos = pos_data.get("position", {})
                if pos:
                    size = abs(float(pos.get("szi", 0)))
                    price = float(pos.get("entryPx", 0))
                    pos_value = size * price
                    # Assume positions are rolled over ~twice daily
                    estimated_volume += pos_value * 2
            
            # Add minimum baseline volume
            estimated_volume += 1000  # $1000 baseline
            
            return estimated_volume
            
        except Exception as e:
            logger.error(f"Error calculating daily volume: {e}")
            return 1000  # Default to $1000
    
    @staticmethod
    async def calculate_maker_ratio(info, user_address):
        """
        Calculate user's maker/taker ratio
        
        Args:
            info: Hyperliquid info client
            user_address: User's wallet address
            
        Returns:
            Float representing maker ratio (0.0-1.0)
        """
        try:
            # In a real implementation, this would analyze actual trade history
            # Here we'll return a sensible default
            return 0.7  # Assume 70% maker orders
            
        except Exception as e:
            logger.error(f"Error calculating maker ratio: {e}")
            return 0.5  # Default to 50%
    
    @staticmethod
    def calculate_optimal_grid_levels(account_value, price, volatility=None):
        """
        Calculate optimal grid trading levels based on account size and volatility
        
        Args:
            account_value: Account value in USD
            price: Current asset price
            volatility: Asset volatility (optional)
            
        Returns:
            Tuple of (grid_spacing_pct, num_levels, size_per_level)
        """
        try:
            # Scale grid spacing based on account size (smaller for larger accounts)
            if account_value >= 10000:  # $10k+
                spacing_pct = 0.003  # 0.3%
                levels = 6
            elif account_value >= 1000:  # $1k+
                spacing_pct = 0.005  # 0.5%
                levels = 5
            else:  # Smaller accounts
                spacing_pct = 0.008  # 0.8%
                levels = 4
            
            # Adjust grid spacing based on volatility if provided
            if volatility:
                # Scale spacing with volatility, min 0.2%, max 2%
                spacing_pct = max(0.002, min(0.02, volatility * 0.3))
            
            # Calculate size per level (% of account per side of the grid)
            # Use 2-8% of account depending on account size
            account_pct = 0.08 if account_value < 1000 else 0.05 if account_value < 10000 else 0.02
            total_grid_value = account_value * account_pct
            size_per_level = total_grid_value / levels / price
            
            return (spacing_pct, levels, size_per_level)
            
        except Exception as e:
            logger.error(f"Error calculating grid levels: {e}")
            return (0.005, 4, 0.001)  # Default values

# Global instance for easy access
trading_analytics = TradingAnalytics()