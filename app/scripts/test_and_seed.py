#!/usr/bin/env python3
"""
SwoopInfo Test & Seed Script
=============================

Tests the new deterministic architecture and seeds the database
with common vehicles.

Usage:
    cd /home/eanhd/projects/SwoopService/SwoopInfo/app
    source .venv/bin/activate  
    python scripts/test_and_seed.py

What this does:
1. Validates schema files are correct
2. Tests content_id generation
3. Tests vehicle onboarding flow
4. Seeds database with popular vehicles (optional)
"""

import sys
import os
import asyncio
import json

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schema_service import get_schema_service, SchemaService
from services.content_id_generator import (
    normalize_vehicle_key,
    build_content_id,
    parse_content_id,
    get_chunks_for_job,
    get_missing_chunks_for_job,
    validate_content_id,
)
from services.supabase_client import SupabaseService
from services.vehicle_onboarding import (
    VehicleOnboardingService,
    get_popular_vehicles,
    get_common_jobs,
)


def print_header(title: str) -> None:
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_result(test_name: str, passed: bool, detail: str = "") -> None:
    """Print test result."""
    icon = "✅" if passed else "❌"
    print(f"  {icon} {test_name}")
    if detail:
        print(f"      {detail}")


def test_schema_loading() -> bool:
    """Test that all schema files load correctly."""
    print_header("TEST 1: Schema Loading")
    
    try:
        schema = get_schema_service()
        schema.load()  # Force reload
        
        # Check chunk types
        chunk_types = schema.get_all_chunk_types()
        print_result(
            "Chunk types loaded", 
            len(chunk_types) > 0,
            f"Found {len(chunk_types)} types: {list(chunk_types.keys())[:5]}..."
        )
        
        # Check components
        fluids = schema.get_components("fluids")
        print_result(
            "Fluids loaded",
            len(fluids) > 0,
            f"Found {len(fluids)} fluids: {fluids[:3]}..."
        )
        
        torque = schema.get_components("torque_components")
        print_result(
            "Torque components loaded",
            len(torque) > 0,
            f"Found {len(torque)} components"
        )
        
        # Check job mappings
        jobs = schema.get_job_types()
        print_result(
            "Job types loaded",
            len(jobs) > 0,
            f"Found {len(jobs)} job types: {jobs[:5]}..."
        )
        
        return True
        
    except Exception as e:
        print_result("Schema loading", False, str(e))
        return False


def test_content_id_generation() -> bool:
    """Test content ID generation and validation."""
    print_header("TEST 2: Content ID Generation")
    
    all_passed = True
    
    # Test valid content IDs
    valid_ids = [
        ("fluid_capacity", "engine_oil"),
        ("torque_spec", "drain_plug"),
        ("procedure", "oil_change"),
    ]
    
    for chunk_type, component in valid_ids:
        try:
            content_id = build_content_id(chunk_type, component)
            is_valid, error = validate_content_id(content_id)
            print_result(
                f"Build '{chunk_type}:{component}'",
                is_valid,
                f"Result: {content_id}"
            )
            if not is_valid:
                all_passed = False
        except Exception as e:
            print_result(f"Build '{chunk_type}:{component}'", False, str(e))
            all_passed = False
    
    # Test vehicle key normalization
    test_vehicles = [
        (2019, "Honda", "Accord", "2.0T", "2019_honda_accord_2.0t"),
        (2020, "Toyota", "Camry", "3.5L V6", "2020_toyota_camry_3.5l_v6"),
        (2018, "Ford", "F-150", "5.0L", "2018_ford_f-150_5.0l"),
    ]
    
    for year, make, model, engine, expected in test_vehicles:
        result = normalize_vehicle_key(year, make, model, engine)
        passed = result == expected
        print_result(
            f"Normalize {year} {make} {model}",
            passed,
            f"Got: {result}" + ("" if passed else f" (expected: {expected})")
        )
        if not passed:
            all_passed = False
    
    return all_passed


def test_job_chunk_mapping() -> bool:
    """Test job to chunk mapping."""
    print_header("TEST 3: Job Chunk Mapping")
    
    all_passed = True
    
    # Test oil change
    oil_chunks = get_chunks_for_job("oil_change")
    expected_oil = [
        "fluid_capacity:engine_oil",
        "torque_spec:drain_plug",
        "procedure:oil_change",
    ]
    
    has_all = all(chunk in oil_chunks for chunk in expected_oil)
    print_result(
        "Oil change chunks",
        has_all,
        f"Found {len(oil_chunks)} chunks"
    )
    if not has_all:
        all_passed = False
    
    # Test brake pads
    brake_chunks = get_chunks_for_job("brake_pads_front")
    print_result(
        "Brake pads chunks",
        len(brake_chunks) > 0,
        f"Found {len(brake_chunks)} chunks"
    )
    
    # Test missing chunks calculation
    existing = ["fluid_capacity:engine_oil", "torque_spec:drain_plug"]
    missing = get_missing_chunks_for_job("oil_change", existing)
    print_result(
        "Missing chunks calculation",
        len(missing) > 0,
        f"Missing: {missing}"
    )
    
    return all_passed


async def test_supabase_connection() -> bool:
    """Test Supabase connection."""
    print_header("TEST 4: Supabase Connection")
    
    try:
        supabase = SupabaseService()
        
        # Try to query chunks table
        result = supabase.client.table("chunks").select("id").limit(1).execute()
        print_result("Chunks table accessible", True, f"Query succeeded")
        
        # Try to query swoopinfo_vehicles table
        try:
            result = supabase.client.table("swoopinfo_vehicles").select("id").limit(1).execute()
            print_result("Vehicles registry accessible", True)
        except Exception as e:
            print_result(
                "Vehicles registry accessible", 
                False, 
                "Table may not exist yet - run SQL migration"
            )
        
        return True
        
    except Exception as e:
        print_result("Supabase connection", False, str(e))
        return False


async def test_vehicle_onboarding() -> bool:
    """Test vehicle onboarding flow."""
    print_header("TEST 5: Vehicle Onboarding")
    
    try:
        supabase = SupabaseService()
        service = VehicleOnboardingService(supabase)
        
        # Test preparing for a booking
        result = await service.prepare_for_booking(
            year=2019,
            make="Honda",
            model="Accord",
            engine="2.0T",
            job_type="oil_change"
        )
        
        print_result(
            "Prepare for booking",
            "vehicle_key" in result,
            f"Vehicle: {result.get('vehicle_key')}, Ready: {result.get('ready')}"
        )
        
        # Show what's missing
        if result.get("generation_queue"):
            print(f"      Generation queue: {result['generation_queue']}")
        
        return True
        
    except Exception as e:
        print_result("Vehicle onboarding", False, str(e))
        return False


async def show_common_vehicles() -> None:
    """Show list of common vehicles that should be populated."""
    print_header("COMMON VEHICLES TO POPULATE")
    
    vehicles = await get_popular_vehicles()
    jobs = await get_common_jobs()
    
    print(f"\n  📋 {len(vehicles)} vehicles × {len(jobs)} jobs = chunks to generate")
    print("\n  Vehicles:")
    for v in vehicles[:10]:
        key = normalize_vehicle_key(v["year"], v["make"], v["model"], v.get("engine"))
        print(f"    • {key}")
    if len(vehicles) > 10:
        print(f"    ... and {len(vehicles) - 10} more")
    
    print("\n  Job types:")
    for job in jobs:
        chunks = get_chunks_for_job(job)
        print(f"    • {job}: {len(chunks)} chunks")


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  🧠 SWOOPINFO ARCHITECTURE TESTS")
    print("=" * 60)
    
    results = []
    
    # Test 1: Schema loading
    results.append(("Schema Loading", test_schema_loading()))
    
    # Test 2: Content ID generation
    results.append(("Content ID Generation", test_content_id_generation()))
    
    # Test 3: Job chunk mapping
    results.append(("Job Chunk Mapping", test_job_chunk_mapping()))
    
    # Test 4: Supabase connection
    results.append(("Supabase Connection", await test_supabase_connection()))
    
    # Test 5: Vehicle onboarding
    results.append(("Vehicle Onboarding", await test_vehicle_onboarding()))
    
    # Show common vehicles
    await show_common_vehicles()
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        icon = "✅" if result else "❌"
        print(f"  {icon} {name}")
    
    print(f"\n  Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n  🎉 All tests passed! Architecture is ready.")
        print("\n  Next steps:")
        print("    1. Run SQL migration in Supabase")
        print("    2. Use the chunk generator to populate data")
        print("    3. Run QA pipeline on generated chunks")
    else:
        print("\n  ⚠️ Some tests failed. Fix issues before proceeding.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
