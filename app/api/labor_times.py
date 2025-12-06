"""
Smart Labor Time API - Vehicle-Specific Labor Estimates via Web Search

This endpoint searches for real-world labor times and difficulty assessments
for specific vehicle + service combinations. It understands that:
- A starter on a 4WD Colorado 8-speed = nightmare (drop axle, motor mount)
- A starter on a Camry = easy peasy
- An oil pan on a BMW N52 = might need to balance subframe on jack

Returns not just hours, but also:
- Mobile feasibility rating
- Difficulty notes
- Whether it requires sketchy tactics
- Recommended approach
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os
import httpx
import json
import re
from datetime import datetime

router = APIRouter(prefix="/api/labor", tags=["Labor Times"])

# Cache for labor lookups (in production, use Redis)
labor_cache: dict = {}
CACHE_DURATION_HOURS = 168  # 1 week - labor times don't change often


class VehicleInfo(BaseModel):
    year: int
    make: str
    model: str
    engine: Optional[str] = None
    transmission: Optional[str] = None
    drivetrain: Optional[str] = None  # 2WD, 4WD, AWD


class LaborRequest(BaseModel):
    vehicle: VehicleInfo
    service: str  # e.g., "starter_replacement", "oil_pan_gasket"
    service_name: Optional[str] = None  # Human readable


class MobileFeasibility(BaseModel):
    can_do_mobile: bool
    confidence: str  # "high", "medium", "low"
    reasoning: str
    sketchy_tactics_required: bool
    recommended_approach: Optional[str] = None


class LaborEstimate(BaseModel):
    base_hours: float
    adjusted_hours: float  # After vehicle-specific adjustments
    mobile_add_hours: float
    total_mobile_hours: float
    difficulty: str  # "easy", "moderate", "hard", "nightmare"
    mobile_feasibility: MobileFeasibility
    special_tools: List[str]
    gotchas: List[str]  # Things that could go wrong
    tips: List[str]  # Pro tips for this specific job
    source: str  # Where we got the info
    confidence: str  # "high", "medium", "low", "estimated"
    raw_search_context: Optional[str] = None


class LaborResponse(BaseModel):
    vehicle: str
    service: str
    estimate: LaborEstimate
    similar_vehicles: Optional[List[str]] = None
    cached: bool = False


def get_cache_key(vehicle: VehicleInfo, service: str) -> str:
    """Generate cache key for labor lookup."""
    return f"{vehicle.year}_{vehicle.make}_{vehicle.model}_{vehicle.engine or 'any'}_{service}".lower().replace(" ", "_")


def build_search_query(vehicle: VehicleInfo, service: str, service_name: Optional[str]) -> str:
    """Build an effective search query for labor time lookup."""
    vehicle_str = f"{vehicle.year} {vehicle.make} {vehicle.model}"
    if vehicle.engine:
        vehicle_str += f" {vehicle.engine}"
    if vehicle.drivetrain and vehicle.drivetrain.upper() in ["4WD", "AWD"]:
        vehicle_str += f" {vehicle.drivetrain}"
    
    service_str = service_name or service.replace("_", " ")
    
    # Search for labor time and difficulty info
    return f"{vehicle_str} {service_str} labor time hours difficulty DIY"


async def search_brave(query: str) -> Optional[dict]:
    """Search Brave for labor time information."""
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": api_key},
                params={
                    "q": query,
                    "count": 8,
                    "text_decorations": False,
                    "search_lang": "en",
                },
                timeout=10.0
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Brave search error: {e}")
    return None


def extract_labor_info_from_search(search_results: dict, vehicle: VehicleInfo, service: str) -> dict:
    """Extract labor time and difficulty info from search results."""
    
    context_texts = []
    hours_found = []
    difficulty_indicators = []
    gotchas = []
    tips = []
    special_tools = []
    mobile_concerns = []
    
    # Keywords that indicate difficulty
    nightmare_keywords = [
        "nightmare", "pain in the ass", "terrible", "worst", "hate", "awful", 
        "drop the subframe", "remove transmission", "engine out", "pull the engine",
        "don't even try", "dealer only", "shop only", "not diy", "impossible",
        "6+ hours", "8+ hours", "10+ hours", "all day job", "two day job"
    ]
    hard_keywords = [
        "difficult", "challenging", "pain", "tight space", "hard to reach", 
        "motor mount", "drop axle", "subframe", "hours of labor", "specialty tool",
        "dealer tool", "not recommended", "experienced only", "professional only",
        "lower the subframe", "support the engine", "remove intake manifold",
        "very tight", "no room", "cramped", "frustrating", "tedious"
    ]
    moderate_keywords = ["moderate", "some disassembly", "couple hours", "not too bad", "doable", "manageable"]
    easy_keywords = ["easy", "simple", "straightforward", "quick", "30 minutes", "basic", "beginner", "diy friendly"]
    
    # Mobile concern keywords - things that make mobile work sketchy/dangerous
    mobile_concern_keywords = [
        "lift required", "need a lift", "jack stands won't work", "drop subframe", 
        "transmission out", "engine support", "balance on jack", "sketchy",
        "lower subframe", "support engine", "engine hoist", "transmission jack",
        "need lift", "requires lift", "on a lift", "two post lift",
        "unbolt subframe", "disconnect steering", "power steering lines",
        "ac lines", "coolant lines", "fuel lines under pressure",
        "axle drop", "cv axle", "drop the front", "disconnect axle"
    ]
    
    # High labor hour thresholds that indicate complexity
    high_labor_indicators = []
    
    if "web" in search_results and "results" in search_results["web"]:
        for result in search_results["web"]["results"]:
            title = result.get("title", "").lower()
            description = result.get("description", "").lower()
            text = f"{title} {description}"
            context_texts.append(text)
            
            # Look for hour mentions
            hour_patterns = [
                r'(\d+\.?\d*)\s*(?:hours?|hrs?)\s*(?:of\s*)?(?:labor)?',
                r'book\s*time[:\s]*(\d+\.?\d*)',
                r'labor[:\s]*(\d+\.?\d*)\s*(?:hours?|hrs?)',
                r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*(?:hours?|hrs?)',  # Range like "2-3 hours"
            ]
            for pattern in hour_patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    if isinstance(match, tuple):
                        # It's a range, take the higher number
                        hours_found.append(float(match[1]))
                    else:
                        try:
                            h = float(match)
                            if 0.25 <= h <= 20:  # Sanity check
                                hours_found.append(h)
                                # Flag high labor as complexity indicator
                                if h >= 6:
                                    high_labor_indicators.append(f"{h} hours labor")
                        except:
                            pass
            
            # Check difficulty indicators
            for kw in nightmare_keywords:
                if kw in text:
                    difficulty_indicators.append("nightmare")
                    break
            for kw in hard_keywords:
                if kw in text:
                    difficulty_indicators.append("hard")
                    break
            for kw in moderate_keywords:
                if kw in text:
                    difficulty_indicators.append("moderate")
                    break
            for kw in easy_keywords:
                if kw in text:
                    difficulty_indicators.append("easy")
                    break
            
            # Mobile concerns
            for kw in mobile_concern_keywords:
                if kw in text:
                    mobile_concerns.append(kw)
            
            # Extract gotchas
            gotcha_patterns = [
                r'(?:watch out for|be careful|make sure|don\'t forget)[:\s]*([^.]+)',
                r'(?:common mistake|problem is)[:\s]*([^.]+)',
            ]
            for pattern in gotcha_patterns:
                matches = re.findall(pattern, text)
                gotchas.extend(matches[:2])
            
            # Extract tips
            tip_patterns = [
                r'(?:tip|trick|pro tip|helpful)[:\s]*([^.]+)',
                r'(?:easier if you|helps to)[:\s]*([^.]+)',
            ]
            for pattern in tip_patterns:
                matches = re.findall(pattern, text)
                tips.extend(matches[:2])
            
            # Special tools
            tool_patterns = [
                r'(?:need|require|use)[:\s]*(?:a\s+)?([^.]*(?:tool|puller|press|socket|wrench)[^.]*)',
            ]
            for pattern in tool_patterns:
                matches = re.findall(pattern, text)
                special_tools.extend(matches[:2])
    
    # Determine overall difficulty
    if difficulty_indicators:
        # Weight towards the worst indicators
        if "nightmare" in difficulty_indicators:
            difficulty = "nightmare"
        elif difficulty_indicators.count("hard") >= 2 or "hard" in difficulty_indicators:
            difficulty = "hard"
        elif "moderate" in difficulty_indicators:
            difficulty = "moderate"
        else:
            difficulty = "easy"
    else:
        difficulty = "moderate"  # Default assumption
    
    # Override difficulty based on labor hours found
    # If book time is very high, it's hard regardless of forum sentiment
    if hours_found and max(hours_found) >= 8:
        if difficulty not in ["nightmare", "hard"]:
            difficulty = "hard"
            high_labor_indicators.append(f"High book time: {max(hours_found)} hours")
    if hours_found and max(hours_found) >= 12:
        difficulty = "nightmare"
        high_labor_indicators.append(f"Very high book time: {max(hours_found)} hours")
    
    # Calculate average hours if found
    if hours_found:
        avg_hours = sum(hours_found) / len(hours_found)
        # Weight towards higher numbers for safety in quoting
        max_hours = max(hours_found)
        base_hours = (avg_hours + max_hours) / 2
    else:
        # Estimate based on difficulty
        base_hours = {
            "easy": 1.0,
            "moderate": 2.0,
            "hard": 3.5,
            "nightmare": 5.0
        }.get(difficulty, 2.0)
    
    # Add high labor indicators to mobile concerns
    mobile_concerns.extend(high_labor_indicators)
    
    return {
        "base_hours": round(base_hours, 1),
        "difficulty": difficulty,
        "gotchas": list(set(gotchas))[:5],
        "tips": list(set(tips))[:5],
        "special_tools": list(set(special_tools))[:5],
        "mobile_concerns": list(set(mobile_concerns)),
        "context": " | ".join(context_texts[:3])[:500],
        "confidence": "high" if hours_found and len(hours_found) >= 2 else ("medium" if hours_found else "low")
    }


def assess_mobile_feasibility(
    vehicle: VehicleInfo,
    service: str,
    difficulty: str,
    mobile_concerns: List[str],
    gotchas: List[str],
    base_hours: float = 0  # Add hours as a factor
) -> MobileFeasibility:
    """Determine if this job is feasible for mobile mechanic work."""
    
    # Services that are generally NOT mobile-friendly
    not_mobile_services = [
        "timing_belt", "timing_chain", "head_gasket", "transmission_rebuild",
        "engine_rebuild", "clutch", "wheel_alignment", "frame_repair"
    ]
    
    # Check if service is in the not-mobile list
    service_lower = service.lower()
    for nm in not_mobile_services:
        if nm in service_lower:
            return MobileFeasibility(
                can_do_mobile=False,
                confidence="high",
                reasoning=f"This service typically requires shop equipment and is not recommended for mobile work.",
                sketchy_tactics_required=False,
                recommended_approach="Refer to shop or tow to facility"
            )
    
    # Check difficulty and concerns
    sketchy_required = len(mobile_concerns) > 0 or difficulty == "nightmare"
    
    # High labor hours = sketchy mobile
    if base_hours >= 6:
        sketchy_required = True
        if f"High labor time: {base_hours}+ hours" not in mobile_concerns:
            mobile_concerns.append(f"High labor time: {base_hours}+ hours")
    
    # Combine all concerns
    all_concerns = mobile_concerns + [g for g in gotchas if any(kw in g.lower() for kw in ["lift", "subframe", "transmission", "engine"])]
    
    # Very high hours = probably not feasible mobile
    if base_hours >= 10:
        return MobileFeasibility(
            can_do_mobile=True,  # Technically possible...
            confidence="low",
            reasoning=f"This is a {base_hours}+ hour job. Mobile is technically possible but extremely challenging. Consider shop referral.",
            sketchy_tactics_required=True,
            recommended_approach="STRONGLY consider shop referral. This is a full-day+ job that will be much harder in a driveway."
        )
    
    if difficulty == "nightmare" or len(all_concerns) >= 3:
        return MobileFeasibility(
            can_do_mobile=True,  # Possible but...
            confidence="low",
            reasoning=f"Technically possible but extremely challenging mobile. Concerns: {', '.join(all_concerns[:3]) if all_concerns else 'High complexity'}",
            sketchy_tactics_required=True,
            recommended_approach="Consider shop referral. If doing mobile: ensure flat level surface, have extra support equipment, budget 1.5x normal time."
        )
    elif difficulty == "hard" or len(all_concerns) >= 1:
        return MobileFeasibility(
            can_do_mobile=True,
            confidence="medium",
            reasoning=f"Doable mobile with extra time and preparation. {', '.join(all_concerns[:2]) if all_concerns else ''}",
            sketchy_tactics_required=len(all_concerns) > 0,
            recommended_approach="Bring extra jack stands, allow buffer time, confirm flat work surface beforehand."
        )
    elif difficulty == "moderate":
        return MobileFeasibility(
            can_do_mobile=True,
            confidence="high",
            reasoning="Standard mobile job with typical equipment.",
            sketchy_tactics_required=False,
            recommended_approach=None
        )
    else:  # easy
        return MobileFeasibility(
            can_do_mobile=True,
            confidence="high",
            reasoning="Ideal for mobile service.",
            sketchy_tactics_required=False,
            recommended_approach=None
        )


def get_vehicle_multiplier(vehicle: VehicleInfo) -> float:
    """Get labor multiplier based on vehicle make/type."""
    make_lower = vehicle.make.lower()
    
    # European = more complex
    if make_lower in ["bmw", "mercedes", "mercedes-benz", "audi", "volkswagen", "porsche", "mini", "land rover", "jaguar", "volvo"]:
        return 1.3
    
    # Luxury Asian
    if make_lower in ["lexus", "acura", "infiniti", "genesis"]:
        return 1.15
    
    # Trucks with 4WD typically harder
    if vehicle.drivetrain and vehicle.drivetrain.upper() in ["4WD", "AWD"]:
        if make_lower in ["chevrolet", "gmc", "ford", "ram", "dodge", "toyota", "nissan"]:
            # Trucks
            return 1.2
    
    return 1.0


@router.post("/estimate", response_model=LaborResponse)
async def get_labor_estimate(request: LaborRequest):
    """
    Get smart labor time estimate for a specific vehicle + service.
    
    Uses web search to find real-world labor times and difficulty assessments,
    then adjusts for mobile work feasibility.
    
    Example nightmare jobs:
    - Starter on 4WD Colorado 8-speed (drop axle, motor mount)
    - Oil pan gasket on BMW N52 (subframe balancing)
    - Spark plugs on Ford 5.4L (2-piece plugs that break)
    """
    
    vehicle = request.vehicle
    service = request.service
    
    # Check cache
    cache_key = get_cache_key(vehicle, service)
    if cache_key in labor_cache:
        cached = labor_cache[cache_key]
        if (datetime.now() - cached["timestamp"]).total_seconds() < CACHE_DURATION_HOURS * 3600:
            cached["response"].cached = True
            return cached["response"]
    
    # Build search query
    query = build_search_query(vehicle, service, request.service_name)
    
    # Search for labor info
    search_results = await search_brave(query)
    
    if search_results:
        labor_info = extract_labor_info_from_search(search_results, vehicle, service)
    else:
        # Fallback to conservative estimates
        labor_info = {
            "base_hours": 2.0,
            "difficulty": "moderate",
            "gotchas": [],
            "tips": [],
            "special_tools": [],
            "mobile_concerns": [],
            "context": "No search results - using conservative estimate",
            "confidence": "estimated"
        }
    
    # Apply vehicle multiplier
    vehicle_multiplier = get_vehicle_multiplier(vehicle)
    adjusted_hours = labor_info["base_hours"] * vehicle_multiplier
    
    # Assess mobile feasibility (pass base hours for high-labor detection)
    mobile_feasibility = assess_mobile_feasibility(
        vehicle,
        service,
        labor_info["difficulty"],
        labor_info["mobile_concerns"],
        labor_info["gotchas"],
        labor_info["base_hours"]  # Pass hours for feasibility assessment
    )
    
    # Calculate mobile add time
    if mobile_feasibility.sketchy_tactics_required:
        mobile_add = adjusted_hours * 0.5  # 50% more time for sketchy jobs
    elif labor_info["difficulty"] == "hard":
        mobile_add = adjusted_hours * 0.3
    elif labor_info["difficulty"] == "moderate":
        mobile_add = adjusted_hours * 0.15
    else:
        mobile_add = 0
    
    # Round to nearest 0.25
    adjusted_hours = round(adjusted_hours * 4) / 4
    mobile_add = round(mobile_add * 4) / 4
    total_mobile = adjusted_hours + mobile_add
    
    estimate = LaborEstimate(
        base_hours=labor_info["base_hours"],
        adjusted_hours=adjusted_hours,
        mobile_add_hours=mobile_add,
        total_mobile_hours=total_mobile,
        difficulty=labor_info["difficulty"],
        mobile_feasibility=mobile_feasibility,
        special_tools=labor_info["special_tools"],
        gotchas=labor_info["gotchas"],
        tips=labor_info["tips"],
        source="brave_search" if search_results else "fallback_estimate",
        confidence=labor_info["confidence"],
        raw_search_context=labor_info["context"] if labor_info["confidence"] != "estimated" else None
    )
    
    vehicle_str = f"{vehicle.year} {vehicle.make} {vehicle.model}"
    if vehicle.engine:
        vehicle_str += f" ({vehicle.engine})"
    if vehicle.drivetrain:
        vehicle_str += f" {vehicle.drivetrain}"
    
    response = LaborResponse(
        vehicle=vehicle_str,
        service=request.service_name or service.replace("_", " ").title(),
        estimate=estimate,
        cached=False
    )
    
    # Cache the result
    labor_cache[cache_key] = {
        "response": response,
        "timestamp": datetime.now()
    }
    
    return response


@router.get("/nightmare-jobs")
async def get_nightmare_jobs():
    """
    Return a list of known nightmare jobs that should probably be declined
    or quoted with significant premium.
    """
    return {
        "nightmare_jobs": [
            {
                "vehicle": "Chevy Colorado/GMC Canyon 4WD with 8-speed",
                "service": "Starter Replacement",
                "reason": "Must drop front axle and remove motor mount. Absolute nightmare mobile.",
                "mobile_recommendation": "DECLINE or quote 2x normal labor"
            },
            {
                "vehicle": "BMW E90 328i N52 engine",
                "service": "Oil Pan Gasket",
                "reason": "Must balance subframe on jack, don't want to fully disconnect power steering. Very sketchy mobile.",
                "mobile_recommendation": "Shop referral preferred"
            },
            {
                "vehicle": "Ford 5.4L 3V (F-150, Expedition 2004-2010)",
                "service": "Spark Plugs",
                "reason": "2-piece plugs notorious for breaking during removal. Can turn 2hr job into 8hr extraction nightmare.",
                "mobile_recommendation": "Quote for potential extraction, carry lisle tool"
            },
            {
                "vehicle": "Subaru with FB/FA engine",
                "service": "Spark Plugs",
                "reason": "Boxer engine means removing intake for rear plugs.",
                "mobile_recommendation": "Doable but quote extra time"
            },
            {
                "vehicle": "Mini Cooper S",
                "service": "Starter Replacement",
                "reason": "Requires removing intake manifold for access.",
                "mobile_recommendation": "Doable mobile but 3+ hours"
            },
            {
                "vehicle": "Mercedes ML/GL/GLE",
                "service": "Alternator",
                "reason": "Lower position, often requires subframe work.",
                "mobile_recommendation": "Difficult mobile, consider shop"
            },
            {
                "vehicle": "Any transverse V6 with rear bank access issues",
                "service": "Valve Cover Gasket (rear)",
                "reason": "Firewall access, must remove plenum, wiring harnesses.",
                "mobile_recommendation": "Very tight mobile, quote extra time"
            }
        ],
        "general_rules": [
            "4WD trucks + starter = usually awful",
            "German cars + anything under engine = subframe probably involved",
            "Transverse V6 + rear components = intake manifold removal likely",
            "Anything requiring 'balancing' parts on jacks = sketchy mobile territory",
            "If forums say 'nightmare' - believe them and quote accordingly"
        ]
    }


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    brave_key = os.getenv("BRAVE_API_KEY")
    return {
        "status": "healthy",
        "service": "labor-times",
        "brave_api_configured": bool(brave_key),
        "cache_entries": len(labor_cache)
    }
