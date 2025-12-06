#!/usr/bin/env python3
"""
Test Vehicle Key Normalization

Ensures vehicle keys are clean and consistent between 
vehicles.json format and SwoopInfo database keys.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.content_id_generator import (
    normalize_vehicle_key,
    _clean_model_name,
    _clean_engine_name
)


def test_model_name_cleaning():
    """Test model name normalization from vehicles.json format."""
    print("\n🚗 Testing Model Name Cleaning")
    print("=" * 50)
    
    test_cases = [
        # (input, expected)
        ("Aveo (T200/T250)", "aveo"),
        ("F-150 (Eleventh generation)", "f-150"),
        ("Civic (Eighth generation, North America)", "civic"),
        ("Accord", "accord"),
        ("Camry (XV40)", "camry"),
        ("CR-V (Third generation)", "cr-v"),
        ("RAV4 (XA40)", "rav4"),
        ("3 Series (E90)", "3_series"),
        ("Model 3", "model_3"),
        ("A4 (B8)", "a4"),
    ]
    
    passed = 0
    for input_val, expected in test_cases:
        result = _clean_model_name(input_val)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        print(f"  {status} '{input_val}' → '{result}' (expected: '{expected}')")
    
    print(f"\nModel Names: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_engine_name_cleaning():
    """Test engine name normalization from vehicles.json format."""
    print("\n⚙️ Testing Engine Name Cleaning")
    print("=" * 50)
    
    test_cases = [
        # (input, expected)
        ("1.6L Ecotec I4 (108 hp)", "1.6l"),  # Ecotec is GM, not turbo
        ("5.4L Triton V8", "5.4l"),
        ("2.0L K20Z3 i-VTEC I4 (Si)", "2.0l"),
        ("3.5L V6 EcoBoost", "3.5l_ecoboost"),
        ("2.0T", "2.0t"),
        ("2.7L EcoBoost V6", "2.7l_ecoboost"),
        ("5.0L Coyote V8", "5.0l"),
        ("1.5L Turbo", "1.5t"),
        ("2.4L 4-cylinder", "2.4l"),
        ("3.5L V6", "3.5l"),
        ("1.8L i-VTEC", "1.8l"),
        ("2.0L Turbo I4", "2.0t"),
        ("5.7L HEMI V8", "5.7l"),
        ("6.2L V8 Supercharged", "6.2l"),  # Supercharged is different from turbo
    ]
    
    passed = 0
    for input_val, expected in test_cases:
        result = _clean_engine_name(input_val)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        print(f"  {status} '{input_val}' → '{result}' (expected: '{expected}')")
    
    print(f"\nEngine Names: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_full_vehicle_key():
    """Test full vehicle key generation."""
    print("\n🔑 Testing Full Vehicle Key Generation")
    print("=" * 50)
    
    test_cases = [
        # (year, make, model, engine, expected_key)
        (2007, "Chevrolet", "Aveo (T200/T250)", "1.6L Ecotec I4 (108 hp)", "2007_chevrolet_aveo_1.6l"),
        (2019, "Honda", "Accord", "2.0T", "2019_honda_accord_2.0t"),
        (2018, "Ford", "F-150 (Thirteenth generation)", "5.0L Coyote V8", "2018_ford_f-150_5.0l"),
        (2020, "Toyota", "Camry (XV70)", "3.5L V6", "2020_toyota_camry_3.5l"),
        (2017, "Honda", "Civic (Tenth generation)", "1.5L Turbo", "2017_honda_civic_1.5t"),
        (2019, "Ford", "Mustang", "2.3L EcoBoost", "2019_ford_mustang_2.3l_ecoboost"),
        (2021, "Tesla", "Model 3", None, "2021_tesla_model_3"),  # No engine for EV
    ]
    
    passed = 0
    for year, make, model, engine, expected in test_cases:
        result = normalize_vehicle_key(year, make, model, engine)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        print(f"  {status} {year} {make} {model}")
        print(f"      Engine: {engine}")
        print(f"      Key: '{result}' (expected: '{expected}')")
        print()
    
    print(f"Full Keys: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🔧 VEHICLE KEY NORMALIZATION TESTS")
    print("=" * 60)
    
    results = []
    results.append(test_model_name_cleaning())
    results.append(test_engine_name_cleaning())
    results.append(test_full_vehicle_key())
    
    print("\n" + "=" * 60)
    if all(results):
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
        print("\n📋 NEXT STEPS:")
        print("1. Update swoop-app to use normalize_vehicle_key() when storing bookings")
        print("2. Create a migration to update existing chunks with clean keys")
        print("3. Regenerate chunks for vehicles with new clean keys")
        
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
