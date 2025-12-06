#!/usr/bin/env python3
"""
Migrate Chunks to Clean Vehicle Keys

This script updates all existing chunks in the database to use the new 
normalized vehicle_key format.

OLD: "2007_chevrolet_aveo(t200/t250)_1.6lecoteci4(108hp)"
NEW: "2007_chevrolet_aveo_1.6l"

This is a ONE-TIME migration that should be run after deploying the new
normalize_vehicle_key() function.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import re
from services.supabase_client import supabase_service
from services.content_id_generator import normalize_vehicle_key


def parse_old_vehicle_key(old_key: str) -> dict:
    """
    Attempt to parse components from an old vehicle key.
    
    Old format: "{year}_{make}_{model}_{engine}"
    Where model/engine might have messy parenthetical content.
    """
    parts = old_key.split('_')
    
    if len(parts) < 3:
        return None
    
    year = parts[0]
    make = parts[1]
    
    # The rest could be model + engine mixed together
    # Try to find where model ends and engine begins
    rest = '_'.join(parts[2:])
    
    # Common patterns:
    # "aveo(t200/t250)_1.6lecoteci4(108hp)" 
    # "accord_2.0t"
    # "f-150_5.0l"
    
    # Try to extract engine (usually starts with a digit after underscore)
    engine_match = re.search(r'_(\d+\.?\d*[lt])', rest)
    if engine_match:
        engine_start = engine_match.start()
        model = rest[:engine_start]
        engine = rest[engine_start + 1:]  # Skip the underscore
    else:
        # No clear engine pattern, might be model only
        model = rest
        engine = None
    
    # Clean up model - remove parenthetical content
    model_clean = re.sub(r'\([^)]*\)', '', model).strip('_')
    
    # For engine, extract just the displacement
    engine_clean = None
    if engine:
        disp_match = re.search(r'(\d+\.?\d*)', engine)
        if disp_match:
            disp = disp_match.group(1)
            # Check if turbo
            if 't' in engine.lower() and 'ecotec' not in engine.lower():
                engine_clean = f"{disp}t"
            else:
                engine_clean = f"{disp}l"
    
    return {
        'year': year,
        'make': make,
        'model': model_clean,
        'engine': engine_clean,
    }


async def migrate_chunks():
    """Migrate all chunks to use clean vehicle keys."""
    print("\n" + "=" * 70)
    print("🔧 CHUNK MIGRATION: Clean Vehicle Keys")
    print("=" * 70)
    
    # Get all unique vehicle keys
    result = supabase_service.client.table('chunks').select('id, vehicle_key').execute()
    
    if not result.data:
        print("❌ No chunks found in database")
        return
    
    print(f"\n📊 Found {len(result.data)} chunks to check")
    
    # Group by vehicle_key
    vehicle_keys = {}
    for chunk in result.data:
        vk = chunk['vehicle_key']
        if vk not in vehicle_keys:
            vehicle_keys[vk] = []
        vehicle_keys[vk].append(chunk['id'])
    
    print(f"📋 Unique vehicle keys: {len(vehicle_keys)}")
    
    # Analyze each key
    migrations = []  # List of (old_key, new_key, chunk_ids)
    
    for old_key, chunk_ids in vehicle_keys.items():
        # Check if already clean (matches pattern: year_make_model_engine)
        # Clean keys don't have parentheses
        if '(' not in old_key and ')' not in old_key:
            # Might already be clean, but let's verify format
            parts = old_key.split('_')
            if len(parts) >= 3 and parts[0].isdigit():
                # Check if last part looks like clean engine (2.0l, 2.0t, etc)
                last = parts[-1] if len(parts) > 3 else ''
                if re.match(r'^\d+\.?\d*[lt](_ecoboost)?$', last) or not last:
                    print(f"   ✅ Already clean: {old_key}")
                    continue
        
        # Parse the old key
        parsed = parse_old_vehicle_key(old_key)
        if not parsed:
            print(f"   ⚠️ Could not parse: {old_key}")
            continue
        
        # Generate new clean key
        new_key = normalize_vehicle_key(
            int(parsed['year']),
            parsed['make'].title(),  # Capitalize make
            parsed['model'],
            parsed['engine']
        )
        
        if new_key != old_key:
            migrations.append((old_key, new_key, chunk_ids))
            print(f"   🔄 {old_key}")
            print(f"      → {new_key} ({len(chunk_ids)} chunks)")
    
    if not migrations:
        print("\n✅ All vehicle keys are already clean!")
        return
    
    print(f"\n{'=' * 70}")
    print(f"📝 MIGRATION PLAN")
    print(f"{'=' * 70}")
    print(f"Keys to update: {len(migrations)}")
    
    total_chunks = sum(len(ids) for _, _, ids in migrations)
    print(f"Chunks affected: {total_chunks}")
    
    # Ask for confirmation
    print("\n⚠️ This will update the database. Continue? [y/N]")
    response = input().strip().lower()
    
    if response != 'y':
        print("❌ Migration cancelled")
        return
    
    # Execute migrations
    print("\n🚀 Executing migrations...")
    
    success = 0
    failed = 0
    
    for old_key, new_key, chunk_ids in migrations:
        try:
            # Update all chunks with this vehicle_key
            result = supabase_service.client.table('chunks').update({
                'vehicle_key': new_key
            }).eq('vehicle_key', old_key).execute()
            
            print(f"   ✅ {old_key} → {new_key}")
            success += len(chunk_ids)
            
        except Exception as e:
            print(f"   ❌ Failed: {old_key} - {e}")
            failed += len(chunk_ids)
    
    print(f"\n{'=' * 70}")
    print(f"📊 MIGRATION RESULTS")
    print(f"{'=' * 70}")
    print(f"✅ Success: {success} chunks")
    print(f"❌ Failed: {failed} chunks")
    
    # Also update swoopinfo_vehicles registry if it exists
    try:
        print("\n🔄 Updating swoopinfo_vehicles registry...")
        for old_key, new_key, _ in migrations:
            supabase_service.client.table('swoopinfo_vehicles').update({
                'vehicle_key': new_key
            }).eq('vehicle_key', old_key).execute()
        print("   ✅ Registry updated")
    except Exception as e:
        print(f"   ⚠️ Registry update skipped: {e}")


async def preview_migrations():
    """Preview what migrations would be done without executing."""
    print("\n" + "=" * 70)
    print("👀 PREVIEW MODE - No changes will be made")
    print("=" * 70)
    
    # Get all unique vehicle keys
    result = supabase_service.client.table('chunks').select('vehicle_key').execute()
    
    if not result.data:
        print("❌ No chunks found")
        return
    
    # Get unique keys
    vehicle_keys = set(r['vehicle_key'] for r in result.data)
    
    print(f"\n📋 Analyzing {len(vehicle_keys)} unique vehicle keys:\n")
    
    needs_migration = 0
    already_clean = 0
    
    for old_key in sorted(vehicle_keys):
        # Check if needs migration
        if '(' in old_key or ')' in old_key:
            parsed = parse_old_vehicle_key(old_key)
            if parsed:
                new_key = normalize_vehicle_key(
                    int(parsed['year']),
                    parsed['make'].title(),
                    parsed['model'],
                    parsed['engine']
                )
                print(f"   🔄 {old_key}")
                print(f"      → {new_key}")
                needs_migration += 1
            else:
                print(f"   ⚠️ Cannot parse: {old_key}")
        else:
            print(f"   ✅ {old_key}")
            already_clean += 1
    
    print(f"\n📊 Summary:")
    print(f"   Already clean: {already_clean}")
    print(f"   Needs migration: {needs_migration}")


def main():
    """Main entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Migrate chunks to clean vehicle keys')
    parser.add_argument('--preview', action='store_true', help='Preview changes without executing')
    args = parser.parse_args()
    
    if args.preview:
        asyncio.run(preview_migrations())
    else:
        asyncio.run(migrate_chunks())


if __name__ == "__main__":
    main()
