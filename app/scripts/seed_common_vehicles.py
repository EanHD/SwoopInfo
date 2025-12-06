#!/usr/bin/env python3
"""
Seed Common Vehicles
====================

Populates the SwoopInfo database with chunks for common vehicles
in the Central Valley / Los Baños service area.

Usage:
    cd /home/eanhd/projects/SwoopService/SwoopInfo/app
    source .venv/bin/activate
    python scripts/seed_common_vehicles.py

Options:
    --vehicle "2019 Honda Accord 2.0T"  # Seed specific vehicle
    --job oil_change                     # Seed specific job type
    --all                                # Seed all vehicles × all jobs
    --dry-run                            # Show what would be generated
"""

import sys
import os
import asyncio
import argparse
from datetime import datetime

# Add app directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.deterministic_generator import get_deterministic_generator, DeterministicChunkGenerator
from services.content_id_generator import normalize_vehicle_key, get_chunks_for_job
from services.vehicle_onboarding import get_popular_vehicles, get_common_jobs
from services.supabase_client import supabase_service


# =========================================================
# COMMON VEHICLES FOR CENTRAL VALLEY
# =========================================================

COMMON_VEHICLES = [
    # Honda - Very popular in the area
    {"year": 2019, "make": "honda", "model": "accord", "engine": "2.0t"},
    {"year": 2019, "make": "honda", "model": "accord", "engine": "1.5t"},
    {"year": 2020, "make": "honda", "model": "civic", "engine": "2.0l"},
    {"year": 2018, "make": "honda", "model": "cr-v", "engine": "1.5t"},
    
    # Toyota - Most common brand
    {"year": 2018, "make": "toyota", "model": "camry", "engine": "2.5l"},
    {"year": 2019, "make": "toyota", "model": "camry", "engine": "3.5l_v6"},
    {"year": 2017, "make": "toyota", "model": "corolla", "engine": "1.8l"},
    {"year": 2019, "make": "toyota", "model": "rav4", "engine": "2.5l"},
    {"year": 2016, "make": "toyota", "model": "tacoma", "engine": "3.5l_v6"},
    
    # Ford - Trucks popular in rural area
    {"year": 2018, "make": "ford", "model": "f-150", "engine": "5.0l"},
    {"year": 2019, "make": "ford", "model": "f-150", "engine": "3.5l_ecoboost"},
    {"year": 2017, "make": "ford", "model": "escape", "engine": "1.5l_ecoboost"},
    
    # Chevrolet
    {"year": 2018, "make": "chevrolet", "model": "silverado", "engine": "5.3l"},
    {"year": 2020, "make": "chevrolet", "model": "equinox", "engine": "1.5t"},
    {"year": 2019, "make": "chevrolet", "model": "malibu", "engine": "1.5t"},
    
    # Nissan
    {"year": 2019, "make": "nissan", "model": "altima", "engine": "2.5l"},
    {"year": 2018, "make": "nissan", "model": "rogue", "engine": "2.5l"},
    {"year": 2017, "make": "nissan", "model": "sentra", "engine": "1.8l"},
    
    # Hyundai/Kia
    {"year": 2019, "make": "hyundai", "model": "sonata", "engine": "2.4l"},
    {"year": 2018, "make": "kia", "model": "optima", "engine": "2.4l"},
]

PRIORITY_JOBS = [
    "oil_change",           # Most common service
    "brake_pads_front",     # Common service
    "brake_pads_rear",      # Common service
]

ALL_JOBS = [
    "oil_change",
    "brake_pads_front",
    "brake_pads_rear",
    "brake_pads_rotors_front",
    "brake_pads_rotors_rear",
    "spark_plugs",
    "coolant_flush",
    "transmission_service",
]


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


async def seed_vehicle(
    generator: DeterministicChunkGenerator,
    vehicle: dict,
    job_types: list,
    dry_run: bool = False
) -> dict:
    """Seed chunks for a single vehicle."""
    
    vehicle_key = normalize_vehicle_key(
        vehicle["year"],
        vehicle["make"],
        vehicle["model"],
        vehicle.get("engine")
    )
    
    stats = {
        "vehicle_key": vehicle_key,
        "jobs": {},
        "total_cached": 0,
        "total_generated": 0,
        "total_failed": 0,
    }
    
    for job_type in job_types:
        required_chunks = get_chunks_for_job(job_type)
        
        if dry_run:
            print(f"  📋 {job_type}: {len(required_chunks)} chunks")
            stats["jobs"][job_type] = {"would_generate": len(required_chunks)}
            continue
        
        # Generate chunks for this job
        result = await generator.generate_for_job(vehicle_key, job_type)
        
        stats["jobs"][job_type] = {
            "cached": result.cached,
            "generated": result.generated,
            "failed": result.failed,
        }
        stats["total_cached"] += result.cached
        stats["total_generated"] += result.generated
        stats["total_failed"] += result.failed
        
        # Show progress
        status = "✅" if result.failed == 0 else "⚠️"
        print(f"  {status} {job_type}: {result.cached} cached, {result.generated} new, {result.failed} failed")
    
    return stats


async def seed_all(dry_run: bool = False, jobs: list = None):
    """Seed all common vehicles with priority jobs."""
    
    print_header("🚗 SWOOPINFO DATABASE SEEDER")
    
    generator = get_deterministic_generator()
    job_types = jobs or PRIORITY_JOBS
    
    print(f"\n  Vehicles: {len(COMMON_VEHICLES)}")
    print(f"  Job types: {job_types}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    
    if dry_run:
        # Calculate totals
        total_chunks = 0
        for job_type in job_types:
            chunks = get_chunks_for_job(job_type)
            total_chunks += len(chunks)
        
        print(f"\n  Would generate up to {len(COMMON_VEHICLES)} × {total_chunks} = {len(COMMON_VEHICLES) * total_chunks} chunks")
        print("  (Existing chunks would be cached, not regenerated)")
        return
    
    # Track overall stats
    overall = {
        "vehicles_processed": 0,
        "total_cached": 0,
        "total_generated": 0,
        "total_failed": 0,
    }
    
    start_time = datetime.utcnow()
    
    for i, vehicle in enumerate(COMMON_VEHICLES):
        vehicle_key = normalize_vehicle_key(
            vehicle["year"],
            vehicle["make"],
            vehicle["model"],
            vehicle.get("engine")
        )
        
        print(f"\n[{i+1}/{len(COMMON_VEHICLES)}] {vehicle_key}")
        
        stats = await seed_vehicle(generator, vehicle, job_types, dry_run)
        
        overall["vehicles_processed"] += 1
        overall["total_cached"] += stats["total_cached"]
        overall["total_generated"] += stats["total_generated"]
        overall["total_failed"] += stats["total_failed"]
    
    # Summary
    duration = (datetime.utcnow() - start_time).total_seconds()
    
    print_header("📊 SEEDING COMPLETE")
    print(f"""
  Vehicles processed: {overall['vehicles_processed']}
  Chunks cached:      {overall['total_cached']}
  Chunks generated:   {overall['total_generated']}
  Chunks failed:      {overall['total_failed']}
  Duration:           {duration:.1f} seconds
""")


async def seed_single_vehicle(vehicle_str: str, job_type: str = None):
    """Seed a single vehicle from command line."""
    
    # Parse vehicle string like "2019 Honda Accord 2.0T"
    parts = vehicle_str.split()
    if len(parts) < 3:
        print(f"❌ Invalid vehicle format: {vehicle_str}")
        print("   Expected: '2019 Honda Accord 2.0T'")
        return
    
    year = int(parts[0])
    make = parts[1].lower()
    model = parts[2].lower()
    engine = parts[3].lower() if len(parts) > 3 else None
    
    vehicle = {
        "year": year,
        "make": make,
        "model": model,
        "engine": engine,
    }
    
    vehicle_key = normalize_vehicle_key(year, make, model, engine)
    print_header(f"🚗 Seeding: {vehicle_key}")
    
    generator = get_deterministic_generator()
    job_types = [job_type] if job_type else PRIORITY_JOBS
    
    await seed_vehicle(generator, vehicle, job_types)
    
    print("\n✅ Done!")


async def show_status():
    """Show current database status."""
    
    print_header("📊 DATABASE STATUS")
    
    # Get all chunks
    chunks = supabase_service.client.table("chunks").select("vehicle_key, content_id, verified_status").execute()
    
    if chunks.data:
        from collections import Counter
        vehicle_counts = Counter(c["vehicle_key"] for c in chunks.data)
        verified_counts = Counter(c["verified_status"] for c in chunks.data)
        
        print(f"\n  Total chunks: {len(chunks.data)}")
        print(f"  Unique vehicles: {len(vehicle_counts)}")
        
        print("\n  Verification status:")
        for status, count in verified_counts.most_common():
            print(f"    • {status or 'unverified'}: {count}")
        
        print("\n  Top vehicles by chunk count:")
        for vehicle, count in vehicle_counts.most_common(10):
            print(f"    • {vehicle}: {count} chunks")
    else:
        print("\n  No chunks in database yet.")


def main():
    parser = argparse.ArgumentParser(description="Seed SwoopInfo database with vehicle data")
    parser.add_argument("--vehicle", type=str, help="Seed specific vehicle (e.g., '2019 Honda Accord 2.0T')")
    parser.add_argument("--job", type=str, help="Seed specific job type")
    parser.add_argument("--all", action="store_true", help="Seed all common vehicles")
    parser.add_argument("--all-jobs", action="store_true", help="Include all job types (not just priority)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--status", action="store_true", help="Show database status")
    
    args = parser.parse_args()
    
    if args.status:
        asyncio.run(show_status())
    elif args.vehicle:
        asyncio.run(seed_single_vehicle(args.vehicle, args.job))
    elif args.all:
        jobs = ALL_JOBS if args.all_jobs else PRIORITY_JOBS
        asyncio.run(seed_all(dry_run=args.dry_run, jobs=jobs))
    else:
        # Default: show help
        parser.print_help()
        print("\n  Examples:")
        print("    python scripts/seed_common_vehicles.py --all --dry-run")
        print("    python scripts/seed_common_vehicles.py --all")
        print("    python scripts/seed_common_vehicles.py --vehicle '2019 Honda Accord 2.0T'")
        print("    python scripts/seed_common_vehicles.py --status")


if __name__ == "__main__":
    main()
