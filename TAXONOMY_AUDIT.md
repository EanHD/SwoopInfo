# 🔍 SwoopInfo Taxonomy Audit Report
**Date:** January 2025  
**Purpose:** Ensure 99.99% request coverage without AI hallucination

---

## 📊 EXECUTIVE SUMMARY

### Current State
| Asset | Location | Purpose | Lines |
|-------|----------|---------|-------|
| `nav_tree.json` | `/assets/data/` | Frontend navigation hierarchy | 841 |
| `service_templates.json` | `/assets/data/` | Chunk type mapping for nav nodes | 40 |
| `chunk_types.json` | `/assets/data/` | Schema definitions for each chunk | 320 |
| `job_chunk_map.json` | `/assets/data/` | Job → required chunks mapping | 325 |
| `swooptemplates/` | `/SwoopInfo/` | **EMPTY** - v3 templates missing | 0 |

### Key Findings
1. ✅ **nav_tree.json** - Comprehensive (15 root categories, 200+ leaf nodes)
2. ✅ **chunk_types.json** - Well-structured (22 chunk types with strict schemas)
3. ✅ **job_chunk_map.json** - Good coverage (30+ job types mapped to chunks)
4. ⚠️ **service_templates.json** - Generic, not node-specific
5. ❌ **swooptemplates/** - Empty directory (v3 templates never created)
6. ⚠️ **Diagnostic wizard categories** - Need explicit mapping to nav_tree

---

## 📁 NAV_TREE.JSON ANALYSIS

### Root Categories (15 Total)
```
├── Quick Reference
├── Engine
├── Fuel System
├── Ignition System
├── Cooling System
├── Transmission & Driveline
├── Brakes & Traction Control
├── Steering & Suspension
├── Exhaust & Emissions
├── HVAC
├── Electrical & Lighting
├── Body & Interior
├── Wheels & Tires
├── Hybrid/EV Systems
└── ADAS & Driver Assistance
```

### Coverage Analysis by Category

#### ✅ EXCELLENT COVERAGE
| Category | Leaf Nodes | Assessment |
|----------|------------|------------|
| Engine | 25+ | Oil, timing, gaskets, sensors, internals |
| Brakes & Traction | 15+ | Pads, rotors, calipers, ABS, TCS |
| Electrical & Lighting | 30+ | Battery, alternator, starter, all bulbs |
| Transmission & Driveline | 20+ | Auto, manual, CVT, AWD, axles |
| Cooling System | 10+ | Radiator, hoses, thermostat, water pump |

#### ⚠️ NEEDS EXPANSION
| Category | Gap Identified | Recommended Additions |
|----------|----------------|----------------------|
| ADAS | Generic nodes only | Lane Keep, ACC, Blind Spot calibration procedures |
| Hybrid/EV | Basic structure | Battery conditioning, regen calibration, HV safety procedures |
| Body & Interior | Missing common repairs | Window regulators, door handles, seat adjustments |

#### ❌ CRITICAL GAPS
| Missing Item | Impact | Priority |
|--------------|--------|----------|
| Diagnostic Flows | No structured DTC → cause → fix trees | HIGH |
| TSB Integration | TSBs referenced but not in nav_tree | MEDIUM |
| Symptom-Based Navigation | Only component-based | HIGH |

---

## 📋 CHUNK_TYPES.JSON ANALYSIS

### Defined Chunk Types (22)
```python
CHUNK_TYPES = {
    # Data Chunks (specs)
    "fluid_capacity",     # ✅ Well-defined
    "torque_spec",        # ✅ Well-defined
    "brake_spec",         # ✅ Safety-critical marked
    "battery_spec",       # ✅ Well-defined
    "tire_spec",          # ✅ Well-defined
    "bulb_spec",          # ✅ Well-defined
    "filter_spec",        # ✅ Well-defined
    "wiper_spec",         # ✅ Well-defined
    "firing_order",       # ✅ Well-defined
    "belt_routing",       # ✅ Well-defined
    "labor_time",         # ✅ Well-defined
    "part_number",        # ✅ Well-defined
    "jacking_point",      # ✅ Safety-critical marked
    "service_interval",   # ✅ Well-defined
    "diagnostic_info",    # ✅ OBD location, protocols
    
    # Knowledge Chunks
    "procedure",          # ✅ Steps, tools, warnings
    "part_location",      # ✅ Where to find components
    "known_issue",        # ✅ Common failures
    "dtc",                # ✅ P/B/C/U codes
    "tsb",                # ✅ Technical Service Bulletins
    "recall",             # ✅ NHTSA recalls
    "wiring",             # ✅ Pin assignments
    "reset_procedure",    # ✅ Service light resets
}
```

### Missing Chunk Types (RECOMMENDED ADDITIONS)
```python
MISSING_CHUNK_TYPES = {
    "symptom_flow": {
        # Symptom → diagnostic tree
        "fields": {
            "symptom": "string",  # "Engine runs rough"
            "possible_causes": ["array"],
            "diagnostic_steps": ["array"],
            "likely_solutions": ["array"]
        }
    },
    "component_test": {
        # How to test a specific component
        "fields": {
            "component": "string",
            "test_equipment": ["array"],
            "test_procedure": ["array"],
            "pass_criteria": "string",
            "fail_criteria": "string"
        }
    },
    "calibration_procedure": {
        # Post-repair calibrations
        "fields": {
            "system": "string",
            "tool_required": "string",
            "steps": ["array"],
            "validation": "string"
        }
    },
    "special_tool": {
        # Tool requirements
        "fields": {
            "tool_name": "string",
            "tool_number": "string",
            "application": "string",
            "alternative": "string"
        }
    }
}
```

---

## 🔗 JOB_CHUNK_MAP.JSON ANALYSIS

### Defined Jobs (30+)
```
MAINTENANCE:
├── oil_change              ✅ 6 chunks
├── transmission_service    ✅ 4 chunks
├── coolant_flush           ✅ 3 chunks
├── air_filter              ✅ 2 chunks
├── cabin_filter            ✅ 2 chunks
├── spark_plugs             ✅ 4 chunks
├── serpentine_belt         ✅ 3 chunks
├── tire_rotation           ✅ 3 chunks
├── wiper_blades            ✅ 1 chunk

BRAKES:
├── brake_pads_front        ✅ 4 chunks
├── brake_pads_rear         ✅ 4 chunks
├── brake_pads_rotors_front ✅ 6 chunks
├── brake_pads_rotors_rear  ✅ 6 chunks

ELECTRICAL:
├── battery_replacement     ✅ 3 chunks
├── alternator              ✅ 4 chunks
├── starter                 ✅ 3 chunks
├── headlight_bulb          ✅ 2 chunks

ENGINE:
├── valve_cover_gasket      ✅ 2 chunks
├── timing_chain            ✅ 3 chunks
├── timing_belt             ✅ 3 chunks
├── water_pump              ✅ 4 chunks
├── thermostat              ✅ 4 chunks

SUSPENSION:
├── struts_front            ✅ 4 chunks
├── control_arm             ✅ 4 chunks
├── wheel_bearing           ✅ 3 chunks

DIAGNOSTIC:
├── diagnostic              ✅ 3 chunks
├── check_engine_light      ✅ 1 chunk (dynamic DTCs)

SWOOP BUNDLES:
├── driveway_diagnostic     ✅ 5 chunks
├── safety_check            ✅ 9 chunks
├── road_trip_ready         ✅ 12 chunks
├── pre_purchase_inspection ✅ 10 chunks
```

### Missing Jobs (RECOMMENDED)
```
MISSING_JOBS = {
    # Common customer requests
    "ac_recharge",
    "ac_compressor",
    "power_steering_pump",
    "power_steering_fluid_flush",
    "fuel_pump",
    "fuel_filter",
    "oxygen_sensor",
    "catalytic_converter",
    "exhaust_leak_repair",
    "cv_axle",
    "tie_rod_end",
    "ball_joint",
    "sway_bar_link",
    "shock_absorber",
    
    # Diagnostic-specific
    "no_start_diagnosis",
    "overheating_diagnosis",
    "vibration_diagnosis",
    "noise_diagnosis",
    "electrical_drain_diagnosis",
    "transmission_slipping_diagnosis",
    
    # EV/Hybrid specific
    "ev_battery_health_check",
    "hybrid_battery_test",
    "ev_charging_port_inspection",
}
```

---

## 🎯 DIAGNOSTIC WIZARD → NAV_TREE MAPPING

### Current Wizard Categories (from swoop-app)
```typescript
const DIAG_CATEGORIES = [
  "noise",
  "performance", 
  "warning_light",
  "leak",
  "climate",
  "electrical",
  "transmission",
  "brakes"
];
```

### Mapping Table
| Wizard Category | Nav Tree Path(s) | Status |
|-----------------|------------------|--------|
| `noise` | Engine/*, Brakes/*, Steering & Suspension/* | ⚠️ Need symptom nodes |
| `performance` | Engine/*, Fuel System/*, Ignition System/* | ⚠️ Need symptom nodes |
| `warning_light` | **NOT IN NAV_TREE** | ❌ CRITICAL GAP |
| `leak` | Engine/Gaskets/*, Cooling/* | ⚠️ Need leak nodes |
| `climate` | HVAC/* | ✅ Good coverage |
| `electrical` | Electrical & Lighting/* | ✅ Good coverage |
| `transmission` | Transmission & Driveline/* | ✅ Good coverage |
| `brakes` | Brakes & Traction Control/* | ✅ Good coverage |

### CRITICAL: Warning Lights Not Mapped!
The most common customer query "my [X] light is on" has NO nav_tree representation.

**Recommended Addition:**
```json
{
  "title": "Warning Lights & Indicators",
  "id": "warning_lights",
  "children": [
    {"title": "Check Engine Light (MIL)", "id": "check_engine_light", "tags": ["diagnostic", "dtc"]},
    {"title": "ABS Warning", "id": "abs_warning", "tags": ["diagnostic", "brake"]},
    {"title": "Airbag (SRS) Warning", "id": "srs_warning", "tags": ["diagnostic", "safety"]},
    {"title": "TPMS Warning", "id": "tpms_warning", "tags": ["diagnostic", "tire"]},
    {"title": "Oil Pressure Warning", "id": "oil_pressure_warning", "tags": ["engine", "critical"]},
    {"title": "Temperature Warning", "id": "temp_warning", "tags": ["cooling", "critical"]},
    {"title": "Battery/Charging Warning", "id": "charging_warning", "tags": ["electrical"]},
    {"title": "Brake Warning", "id": "brake_warning", "tags": ["brake", "safety"]},
    {"title": "Transmission Temperature", "id": "trans_temp_warning", "tags": ["transmission"]},
    {"title": "Traction Control Off", "id": "traction_control_warning", "tags": ["diagnostic"]},
    {"title": "Power Steering Warning", "id": "power_steering_warning", "tags": ["steering"]}
  ]
}
```

---

## 🚨 CRITICAL ISSUES

### 1. `swooptemplates/` Directory is EMPTY
**Impact:** `template_loader.py` falls back to nav_tree.json for everything  
**Code Path:**
```python
# template_loader.py line 40
def _load_templates_from_file(self, filename: str):
    # Falls back to nav_tree.json when swooptemplates/* doesn't exist
```

**Risk Level:** MEDIUM - Works but not optimized  
**Action Required:** Decide if v3 templates are needed or remove the feature

### 2. service_templates.json is Generic
**Issue:** Same template applied to ALL nav_tree nodes regardless of type
```json
{
  "default_chunks": ["overview", "parts_required", "location", "removal_steps", "specifications", "common_problems"],
  "conditional_chunks": {
    "electrical": ["wiring_diagram", "connector_pinout"],
    "sensor": ["relearn_procedure"],
    "fluid": ["fluid_capacity"]
  }
}
```

**Impact:** A "Spark Plugs" node generates same chunk types as "Cabin Filter"  
**Action Required:** Create component-specific templates OR enhance tag system

### 3. No Symptom-Based Navigation
**Issue:** Customers describe SYMPTOMS, nav_tree is COMPONENT-based  
**Example:** Customer says "car shakes at highway speed"
- Current: No direct path
- Needed: Symptom → possible causes → diagnostic flow

**Action Required:** Add symptom trees OR create mapping layer

---

## ✅ ACTION ITEMS

### HIGH PRIORITY
1. **Add Warning Lights category to nav_tree.json**
   - 11 common dashboard warnings
   - Map to diagnostic chunks

2. **Create diagnostic wizard → nav_tree mapping function**
   ```python
   def map_concern_to_nav_paths(concern: VehicleConcern) -> list[str]:
       """Map customer concern to relevant nav_tree node IDs"""
   ```

3. **Add missing chunk types**
   - `symptom_flow` - Diagnostic decision trees
   - `component_test` - How to test parts
   - `calibration_procedure` - Post-repair calibrations

### MEDIUM PRIORITY
4. **Expand job_chunk_map.json**
   - Add 20+ missing common jobs
   - Include diagnostic jobs

5. **Decide on swooptemplates/**
   - Either populate with v3 templates OR remove feature
   - Currently unused complexity

6. **Add symptom-based entries to nav_tree**
   - "Noises" subcategory under Quick Reference
   - "Leaks" subcategory
   - "Performance Issues" subcategory

### LOW PRIORITY
7. **Enhance service_templates.json**
   - Add component-specific templates
   - Better tag → chunk type mapping

8. **Add EV/Hybrid coverage**
   - Battery health chunks
   - HV safety procedures
   - Regen system diagnostics

---

## 📈 COVERAGE METRICS

### Current Coverage Estimate
| Request Type | Coverage | Gap |
|--------------|----------|-----|
| Maintenance jobs | 95% | Minor gaps |
| Brake repairs | 98% | ✅ |
| Electrical issues | 90% | Missing some sensors |
| Engine repairs | 85% | Missing some gaskets |
| Diagnostic requests | 60% | ⚠️ Symptom mapping weak |
| Warning light queries | 30% | ❌ Critical gap |
| EV/Hybrid | 40% | Needs expansion |
| ADAS calibration | 20% | ❌ Critical gap |

### Target Coverage: 99.99%
**Estimated Work:**
- Add warning lights category: +15%
- Add symptom mapping: +10%
- Add missing jobs: +5%
- Expand ADAS/EV: +5%
- **Total projected: 95%+**

---

## 🔧 IMPLEMENTATION NOTES

### Where Chunks Are Generated
```
chunk_generator.py:generate_chunk()
  └── identify_needed_chunks() - Uses LLM to pick chunk types
  └── fetch_real_data() - Gets data from APIs
  └── generate via LLM with prompt

chunk_generator.py:generate_leaf_bundle()  
  └── Called from chat.py
  └── Uses service_templates.json for chunk type selection
```

### How Nav Tree is Used
```
Frontend (Flutter): Uses nav_tree.json directly for navigation
Backend (chat.py): template_service.search_candidates() 
  └── Keyword search against nav_tree nodes
  └── Returns matching nodes
```

### Database Schema (Supabase)
```sql
chunks:
  id, vehicle_key, chunk_type, content_id, 
  content (HTML), qa_status, verified_status, visibility
```

---

*This audit was generated automatically. Review and update regularly.*
