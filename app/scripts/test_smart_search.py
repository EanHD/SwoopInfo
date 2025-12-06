#!/usr/bin/env python3
"""
Test Smart Search Optimization

Compares the OLD approach (12 Brave queries + Tavily) vs NEW approach (1-2 smart queries).
Verifies cost savings without sacrificing data quality.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from models.vehicle import Vehicle


async def test_smart_search():
    """Test the optimized smart search service."""
    from services.smart_search import smart_search, SourceTier
    
    print("\n" + "=" * 70)
    print("🔍 SMART SEARCH OPTIMIZATION TEST")
    print("=" * 70)
    
    # Test vehicle
    test_vehicle = Vehicle(
        year="2019",
        make="Honda",
        model="Accord",
        engine="2.0T"
    )
    
    print(f"\n🚗 Test Vehicle: {test_vehicle.year} {test_vehicle.make} {test_vehicle.model} {test_vehicle.engine}")
    
    # Test different chunk types
    test_cases = [
        ("fluid_capacity", "engine_oil"),
        ("torque_spec", "drain_plug"),
        ("procedure", "oil_change"),
        ("known_issue", "turbo_failure"),
    ]
    
    total_cost = 0.0
    
    for chunk_type, component in test_cases:
        print(f"\n{'─' * 50}")
        print(f"📦 Testing: {chunk_type}:{component}")
        
        result = await smart_search.search_for_chunk(
            test_vehicle, chunk_type, component
        )
        
        print(f"   💰 Cost: ${result.get('cost', 0):.4f}")
        print(f"   📊 Sources Found: {result.get('sources_found', 0)}")
        print(f"   🎯 Confidence: {result.get('confidence', 0):.2f}")
        print(f"   💾 Cached: {result.get('cached', False)}")
        
        if result.get('consensus'):
            print(f"   📋 Consensus Data:")
            for key, val in result['consensus'].items():
                print(f"      • {key}: {val.get('value')} (confidence: {val.get('confidence', 0):.2f})")
        
        total_cost += result.get('cost', 0)
    
    # Test caching - run same query again
    print(f"\n{'─' * 50}")
    print("⚡ Testing CACHE HIT (same query again)...")
    
    cached_result = await smart_search.search_for_chunk(
        test_vehicle, "fluid_capacity", "engine_oil"
    )
    
    print(f"   💾 Cached: {cached_result.get('cached', False)}")
    print(f"   💰 Cost: ${cached_result.get('cost', 0):.4f} (should be $0.0000)")
    
    # Session stats
    print(f"\n{'=' * 70}")
    print("📊 SESSION STATISTICS")
    print("=" * 70)
    
    stats = smart_search.get_session_stats()
    print(f"   Total Cost: ${stats['total_cost']:.4f}")
    print(f"   Total Queries: {stats['total_queries']}")
    print(f"   Avg Cost/Query: ${stats['avg_cost_per_query']:.4f}")
    
    # Cost comparison
    print(f"\n{'=' * 70}")
    print("💰 COST COMPARISON")
    print("=" * 70)
    
    old_cost_per_vehicle = 0.012 + 0.005  # 12 Brave queries + 1 Tavily
    new_cost_per_vehicle = stats['avg_cost_per_query']
    
    print(f"   OLD Approach (12 Brave + Tavily): ~${old_cost_per_vehicle:.4f}/vehicle")
    print(f"   NEW Approach (Smart Search):      ~${new_cost_per_vehicle:.4f}/vehicle")
    
    if new_cost_per_vehicle > 0:
        savings_pct = (1 - new_cost_per_vehicle / old_cost_per_vehicle) * 100
        print(f"\n   💸 SAVINGS: {savings_pct:.1f}%")
    else:
        print(f"\n   💸 SAVINGS: 100% (all cached!)")
    
    # Estimate monthly savings
    vehicles_per_month = 500  # Estimate
    old_monthly = vehicles_per_month * old_cost_per_vehicle
    new_monthly = vehicles_per_month * new_cost_per_vehicle
    
    print(f"\n   📅 At {vehicles_per_month} vehicles/month:")
    print(f"      OLD: ${old_monthly:.2f}/month")
    print(f"      NEW: ${new_monthly:.2f}/month")
    print(f"      SAVED: ${old_monthly - new_monthly:.2f}/month")
    
    print(f"\n{'=' * 70}")
    print("✅ SMART SEARCH TEST COMPLETE")
    print("=" * 70)


async def test_source_classification():
    """Test URL classification into quality tiers."""
    from services.smart_search import SmartSearchService, SourceTier
    
    service = SmartSearchService()
    
    print("\n" + "=" * 70)
    print("🏷️ SOURCE CLASSIFICATION TEST")
    print("=" * 70)
    
    test_urls = [
        ("https://www.ford.com/service/manual/", SourceTier.OEM),
        ("https://nhtsa.gov/recalls/123", SourceTier.OFFICIAL),
        ("https://www.alldata.com/procedure/oil", SourceTier.LICENSED),
        ("https://repairpal.com/cost-estimate", SourceTier.TECHNICAL),
        ("https://reddit.com/r/MechanicAdvice/tips", SourceTier.COMMUNITY_HIGH),
        ("https://bobistheoilguy.com/forums/thread", SourceTier.COMMUNITY_HIGH),
        ("https://reddit.com/r/cars/random", SourceTier.COMMUNITY_LOW),
        ("https://randomsite.com/stuff", SourceTier.UNKNOWN),
    ]
    
    passed = 0
    for url, expected_tier in test_urls:
        result = service._classify_source(url)
        status = "✅" if result == expected_tier else "❌"
        if result == expected_tier:
            passed += 1
        print(f"   {status} {url[:50]}...")
        print(f"      Expected: {expected_tier.name}, Got: {result.name}")
    
    print(f"\n   Results: {passed}/{len(test_urls)} passed")


async def main():
    """Run all tests."""
    await test_source_classification()
    await test_smart_search()


if __name__ == "__main__":
    asyncio.run(main())
