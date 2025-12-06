"""
Parts Pricing API - Real-time pricing via web search
=====================================================

Gets current parts prices from O'Reilly, AutoZone, RockAuto via Brave Search.
Caches results for 24 hours to minimize API costs.

Pricing Strategy:
1. Search O'Reilly/AutoZone for the specific part + vehicle
2. Extract price range from search results
3. Apply small markup for sourcing/handling
4. Return min/mid/max estimates

This gives customers realistic expectations and protects you from:
- Quoting $300 when the alternator is actually $500
- Underpricing luxury/European vehicle parts
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import re
import httpx
import hashlib
import json
from config import settings

router = APIRouter(prefix="/api/parts", tags=["parts"])


# ============================================================================
# MODELS
# ============================================================================

class PartPriceRequest(BaseModel):
    """Request for part pricing"""
    year: int
    make: str
    model: str
    engine: Optional[str] = None
    part_name: str  # e.g., "alternator", "brake pads front", "starter"
    
class PriceRange(BaseModel):
    """Price range for a part"""
    low: float       # Budget/economy option
    mid: float       # Standard/recommended
    high: float      # Premium/OEM
    currency: str = "USD"
    
class PartPriceResult(BaseModel):
    """Result with price range and sources"""
    part_name: str
    vehicle: str
    price_range: PriceRange
    our_price_range: PriceRange  # With markup
    sources: List[str]
    confidence: float  # 0-1, based on how many sources agree
    cached: bool
    cache_age_hours: Optional[float] = None
    notes: Optional[str] = None
    
class PartPriceResponse(BaseModel):
    """API response"""
    success: bool
    data: Optional[PartPriceResult] = None
    error: Optional[str] = None


# ============================================================================
# CACHE (in-memory, use Redis in production)
# ============================================================================

_price_cache: Dict[str, tuple[datetime, PartPriceResult]] = {}
CACHE_TTL = timedelta(hours=24)

def _cache_key(year: int, make: str, model: str, part: str) -> str:
    """Generate cache key"""
    raw = f"{year}_{make}_{model}_{part}".lower()
    return hashlib.md5(raw.encode()).hexdigest()

def _get_cached(key: str) -> Optional[tuple[PartPriceResult, float]]:
    """Get cached result if valid, returns (result, age_hours)"""
    if key in _price_cache:
        cached_time, result = _price_cache[key]
        age = datetime.now() - cached_time
        if age < CACHE_TTL:
            return result, age.total_seconds() / 3600
    return None

def _set_cache(key: str, result: PartPriceResult):
    """Cache result"""
    _price_cache[key] = (datetime.now(), result)


# ============================================================================
# PRICE EXTRACTION
# ============================================================================

def extract_prices_from_text(text: str) -> List[float]:
    """
    Extract price values from search result text.
    Handles formats like: $199.99, $199, 199.99, "199 dollars"
    """
    prices = []
    
    # Pattern: $XXX.XX or $XXX
    dollar_pattern = r'\$\s*(\d{1,4}(?:\.\d{2})?)'
    matches = re.findall(dollar_pattern, text)
    prices.extend([float(m) for m in matches])
    
    # Pattern: XXX.XX (near price-related words)
    price_context_pattern = r'(?:price|cost|sale|was|now|only|from|starting)\s*:?\s*\$?(\d{1,4}\.\d{2})'
    matches = re.findall(price_context_pattern, text.lower())
    prices.extend([float(m) for m in matches])
    
    # Filter reasonable auto parts prices ($5 - $2000)
    prices = [p for p in prices if 5 <= p <= 2000]
    
    return prices


def calculate_price_range(prices: List[float]) -> Optional[PriceRange]:
    """Calculate low/mid/high from collected prices"""
    if not prices:
        return None
    
    prices = sorted(set(prices))  # Remove duplicates, sort
    
    if len(prices) == 1:
        # Single price found - create range around it
        p = prices[0]
        return PriceRange(
            low=round(p * 0.85, 2),
            mid=round(p, 2),
            high=round(p * 1.25, 2)
        )
    elif len(prices) == 2:
        return PriceRange(
            low=round(prices[0], 2),
            mid=round((prices[0] + prices[1]) / 2, 2),
            high=round(prices[1], 2)
        )
    else:
        # Multiple prices - use quartiles
        n = len(prices)
        return PriceRange(
            low=round(prices[n // 4], 2),
            mid=round(prices[n // 2], 2),
            high=round(prices[int(n * 0.75)], 2)
        )


def apply_markup(price_range: PriceRange) -> PriceRange:
    """
    Apply markup for parts sourcing/handling.
    
    Markup tiers:
    - Under $50: +15% (small parts, worth the convenience)
    - $50-150: +12%
    - $150-400: +10%
    - Over $400: +8% (high-cost items, keep competitive)
    """
    def get_markup(price: float) -> float:
        if price < 50:
            return 1.15
        elif price < 150:
            return 1.12
        elif price < 400:
            return 1.10
        else:
            return 1.08
    
    return PriceRange(
        low=round(price_range.low * get_markup(price_range.low), 2),
        mid=round(price_range.mid * get_markup(price_range.mid), 2),
        high=round(price_range.high * get_markup(price_range.high), 2)
    )


# ============================================================================
# WEB SEARCH
# ============================================================================

async def search_parts_prices(
    year: int, 
    make: str, 
    model: str, 
    part_name: str,
    engine: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search O'Reilly, AutoZone, RockAuto for part prices.
    Returns extracted prices and source URLs.
    """
    api_key = settings.brave_api_key
    if not api_key or api_key == "your_brave_key_here":
        return {"success": False, "error": "Brave API not configured"}
    
    # Build search queries - focus on retailers
    vehicle_str = f"{year} {make} {model}"
    if engine:
        vehicle_str += f" {engine}"
    
    queries = [
        # O'Reilly (primary - you mentioned they're nearby)
        f'site:oreillyauto.com {vehicle_str} {part_name} price',
        # AutoZone (secondary - also nearby)
        f'site:autozone.com {vehicle_str} {part_name}',
        # RockAuto (good price baseline, often cheapest)
        f'site:rockauto.com {vehicle_str} {part_name}',
        # General retailer search
        f'{vehicle_str} {part_name} price buy autozone OR oreilly OR advance auto',
    ]
    
    all_prices = []
    sources = []
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for query in queries:
            try:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": api_key
                    },
                    params={
                        "q": query,
                        "count": 10,
                        "search_lang": "en"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                results = data.get("web", {}).get("results", [])
                for r in results:
                    url = r.get("url", "")
                    title = r.get("title", "")
                    snippet = r.get("description", "")
                    
                    # Extract prices from title and snippet
                    text = f"{title} {snippet}"
                    prices = extract_prices_from_text(text)
                    
                    if prices:
                        all_prices.extend(prices)
                        # Track source
                        if "oreilly" in url.lower():
                            sources.append("O'Reilly Auto Parts")
                        elif "autozone" in url.lower():
                            sources.append("AutoZone")
                        elif "rockauto" in url.lower():
                            sources.append("RockAuto")
                        elif "advanceauto" in url.lower():
                            sources.append("Advance Auto Parts")
                        else:
                            sources.append("Other Retailer")
                            
            except Exception as e:
                print(f"Search error for '{query}': {e}")
                continue
    
    return {
        "success": True,
        "prices": all_prices,
        "sources": list(set(sources)),  # Dedupe
        "query_count": len(queries)
    }


# ============================================================================
# FALLBACK PRICING
# ============================================================================

# Fallback base prices when search fails (conservative estimates)
FALLBACK_PRICES = {
    "alternator": PriceRange(low=150, mid=250, high=450),
    "starter": PriceRange(low=120, mid=200, high=350),
    "battery": PriceRange(low=100, mid=160, high=250),
    "brake pads": PriceRange(low=35, mid=60, high=120),
    "brake pads front": PriceRange(low=35, mid=60, high=120),
    "brake pads rear": PriceRange(low=35, mid=60, high=120),
    "brake rotors": PriceRange(low=45, mid=80, high=150),
    "water pump": PriceRange(low=60, mid=120, high=200),
    "thermostat": PriceRange(low=15, mid=35, high=70),
    "radiator": PriceRange(low=120, mid=200, high=350),
    "serpentine belt": PriceRange(low=25, mid=45, high=80),
    "timing belt": PriceRange(low=50, mid=100, high=180),
    "spark plugs": PriceRange(low=3, mid=8, high=15),  # Per plug
    "ignition coil": PriceRange(low=40, mid=70, high=130),
    "fuel pump": PriceRange(low=100, mid=180, high=320),
    "oxygen sensor": PriceRange(low=40, mid=80, high=150),
    "catalytic converter": PriceRange(low=200, mid=400, high=800),
    "cv axle": PriceRange(low=80, mid=140, high=240),
    "wheel bearing": PriceRange(low=60, mid=120, high=200),
    "tie rod end": PriceRange(low=25, mid=50, high=90),
    "ball joint": PriceRange(low=35, mid=70, high=130),
    "control arm": PriceRange(low=80, mid=150, high=280),
    "strut": PriceRange(low=80, mid=150, high=280),
    "shock": PriceRange(low=50, mid=100, high=180),
    "ac compressor": PriceRange(low=200, mid=350, high=550),
    "blower motor": PriceRange(low=60, mid=110, high=180),
    "mass airflow sensor": PriceRange(low=70, mid=130, high=220),
    "fuel injector": PriceRange(low=50, mid=100, high=180),
}

# Vehicle class multipliers (luxury/European parts cost more)
VEHICLE_MULTIPLIERS = {
    # Luxury/European
    "bmw": 1.5,
    "mercedes": 1.6,
    "mercedes-benz": 1.6,
    "audi": 1.5,
    "porsche": 2.0,
    "land rover": 1.7,
    "range rover": 1.7,
    "jaguar": 1.6,
    "volvo": 1.4,
    "lexus": 1.3,
    "infiniti": 1.25,
    "acura": 1.15,
    # Trucks (often slightly higher)
    "ram": 1.1,
    # Standard
    "toyota": 1.0,
    "honda": 1.0,
    "ford": 1.0,
    "chevrolet": 1.0,
    "chevy": 1.0,
    "gmc": 1.05,
    "nissan": 1.0,
    "hyundai": 0.95,
    "kia": 0.95,
}

def get_fallback_price(part_name: str, make: str) -> Optional[PriceRange]:
    """Get fallback price with vehicle multiplier"""
    # Normalize part name
    part_key = part_name.lower().strip()
    
    # Find matching fallback
    base_price = None
    for key, price in FALLBACK_PRICES.items():
        if key in part_key or part_key in key:
            base_price = price
            break
    
    if not base_price:
        return None
    
    # Apply vehicle multiplier
    multiplier = VEHICLE_MULTIPLIERS.get(make.lower(), 1.0)
    
    return PriceRange(
        low=round(base_price.low * multiplier, 2),
        mid=round(base_price.mid * multiplier, 2),
        high=round(base_price.high * multiplier, 2)
    )


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/price", response_model=PartPriceResponse)
async def get_part_price(request: PartPriceRequest) -> PartPriceResponse:
    """
    Get real-time price estimate for a part.
    
    Uses web search to find current O'Reilly/AutoZone prices,
    then applies a small markup for sourcing/handling.
    
    Results are cached for 24 hours to minimize API costs.
    """
    try:
        # Check cache first
        cache_key = _cache_key(
            request.year, 
            request.make, 
            request.model, 
            request.part_name
        )
        
        cached = _get_cached(cache_key)
        if cached:
            result, age_hours = cached
            result.cached = True
            result.cache_age_hours = round(age_hours, 1)
            return PartPriceResponse(success=True, data=result)
        
        # Search for prices
        search_result = await search_parts_prices(
            request.year,
            request.make,
            request.model,
            request.part_name,
            request.engine
        )
        
        vehicle_str = f"{request.year} {request.make} {request.model}"
        
        if search_result["success"] and search_result["prices"]:
            # Got real prices from search
            price_range = calculate_price_range(search_result["prices"])
            sources = search_result["sources"]
            confidence = min(1.0, len(sources) / 3)  # More sources = higher confidence
            notes = f"Based on {len(search_result['prices'])} prices found online"
        else:
            # Fallback to estimates
            price_range = get_fallback_price(request.part_name, request.make)
            if not price_range:
                # Generic fallback
                price_range = PriceRange(low=50, mid=100, high=200)
                notes = "Using generic estimate - part not in database"
            else:
                notes = "Using estimated pricing (web search unavailable)"
            sources = ["Swoop Estimate"]
            confidence = 0.5
        
        # Apply our markup
        our_price_range = apply_markup(price_range)
        
        result = PartPriceResult(
            part_name=request.part_name,
            vehicle=vehicle_str,
            price_range=price_range,
            our_price_range=our_price_range,
            sources=sources,
            confidence=confidence,
            cached=False,
            notes=notes
        )
        
        # Cache the result
        _set_cache(cache_key, result)
        
        return PartPriceResponse(success=True, data=result)
        
    except Exception as e:
        return PartPriceResponse(
            success=False, 
            error=f"Failed to get price: {str(e)}"
        )


@router.post("/prices/batch")
async def get_parts_prices_batch(
    parts: List[PartPriceRequest]
) -> Dict[str, Any]:
    """
    Get prices for multiple parts at once.
    Useful for generating complete job estimates.
    """
    results = []
    total_low = 0
    total_mid = 0
    total_high = 0
    
    for part_req in parts:
        response = await get_part_price(part_req)
        if response.success and response.data:
            results.append(response.data)
            total_low += response.data.our_price_range.low
            total_mid += response.data.our_price_range.mid
            total_high += response.data.our_price_range.high
    
    return {
        "success": True,
        "parts": results,
        "total_range": {
            "low": round(total_low, 2),
            "mid": round(total_mid, 2),
            "high": round(total_high, 2)
        }
    }


@router.get("/health")
async def parts_pricing_health():
    """Check if parts pricing API is operational"""
    has_brave = bool(settings.brave_api_key and settings.brave_api_key != "your_brave_key_here")
    return {
        "status": "ok",
        "brave_search_enabled": has_brave,
        "cache_entries": len(_price_cache),
        "fallback_parts_count": len(FALLBACK_PRICES)
    }
