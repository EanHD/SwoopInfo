"""
STRICT Contamination Guard Tests

These tests MUST FAIL if:
- F-150 oil change contamination appears again in Aveo procedures
- New contaminated chunks can be saved
- The validator is bypassed
- Diesel template structure is broken

DO NOT mark as "clean" unless ALL tests pass.
"""

import pytest
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.supabase_client import supabase_service
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestBannedChunksAreNotServed:
    """
    Test 1: Banned chunks must NEVER show up as normal content.

    These specific chunks were contaminated with F-150 oil change content
    and must remain permanently banned.
    """

    CONTAMINATED_CHUNKS = [
        "cylinder_head_removal_steps",
        "oxygen_sensor_testing",
        "drum_brake_service",
        "air_filter_replacement",
    ]

    AVEO_VEHICLE_KEY = "2007_chevrolet_aveo(t200/t250)_16lecoteci4(108hp)"

    @pytest.mark.asyncio
    async def test_contaminated_chunks_are_banned_in_database(self):
        """Verify database marks these chunks as banned"""
        for content_id in self.CONTAMINATED_CHUNKS:
            chunk = await supabase_service.get_chunk(
                vehicle_key=self.AVEO_VEHICLE_KEY,
                content_id=content_id,
                chunk_type="procedure",
            )

            if chunk:
                # Must be banned
                assert (
                    chunk.verified_status == "banned"
                ), f"{content_id} is NOT banned (verified_status={chunk.verified_status})"
                assert (
                    chunk.qa_status == "fail"
                ), f"{content_id} does NOT have qa_status=fail (qa_status={chunk.qa_status})"

                # Must NOT contain F-150 oil change text in a servable state
                content = str(chunk.data).lower()
                if chunk.verified_status != "banned":
                    assert (
                        "drain oil" not in content
                    ), f"{content_id} contains 'drain oil' and is not banned!"
                    assert (
                        "motorcraft fl-500s" not in content
                    ), f"{content_id} contains 'motorcraft fl-500s' and is not banned!"

    def test_api_returns_unavailable_for_banned_chunks(self):
        """API must return unavailable status, not the contaminated content"""
        for content_id in self.CONTAMINATED_CHUNKS:
            response = client.get(
                f"/api/chunks/{content_id}",
                params={
                    "vehicle_key": self.AVEO_VEHICLE_KEY,
                    "chunk_type": "procedure",
                    "template_type": "ICE_GASOLINE",
                },
            )

            assert (
                response.status_code == 200
            ), f"API returned {response.status_code} for {content_id}"

            data = response.json()

            # MUST NOT show as ready/available
            assert (
                data["status"] == "unavailable"
            ), f"{content_id} shows status='{data['status']}', expected 'unavailable'"

            assert (
                data["visibility"] == "banned"
            ), f"{content_id} shows visibility='{data['visibility']}', expected 'banned'"

            assert (
                data["verified_status"] == "banned"
            ), f"{content_id} shows verified_status='{data['verified_status']}', expected 'banned'"

            # MUST NOT contain the contaminated oil change procedure
            response_str = str(data).lower()
            assert (
                "drain oil" not in response_str
            ), f"API response for {content_id} STILL contains 'drain oil'!"
            assert (
                "motorcraft fl-500s" not in response_str
            ), f"API response for {content_id} STILL contains 'motorcraft fl-500s'!"

            # MUST have a rejection message
            assert "data" in data
            assert (
                "message" in data["data"]
            ), f"{content_id} response missing rejection message"
            assert any(
                word in data["data"]["message"].lower()
                for word in ["rejected", "banned", "unavailable"]
            ), f"{content_id} message doesn't indicate rejection: {data['data']['message']}"


class TestContaminationValidatorBlocks:
    """
    Test 2: New contaminated content MUST be blocked before save.

    The validator must prevent ANY contaminated content from entering the database.
    """

    @pytest.mark.asyncio
    async def test_validator_blocks_ford_content_in_chevy(self):
        """Cross-brand contamination must be blocked"""
        contaminated_data = {
            "steps": [
                {
                    "title": "Step 1",
                    "text": "Use Motorcraft FL-500S oil filter and drain oil from F-150 pan",
                },
                {"title": "Step 2", "text": "Add 5W-20 oil per Ford specification"},
            ]
        }

        result = await supabase_service.save_chunk(
            vehicle_key="2007_chevrolet_aveo_test_validator",
            content_id="test_oxygen_sensor_contaminated",
            chunk_type="procedure",
            template_type="ICE_GASOLINE",
            title="Test Contaminated Oxygen Sensor",
            data=contaminated_data,
            sources=["Test"],
            content_text="Use Motorcraft FL-500S oil filter and drain oil from F-150 pan. Add 5W-20 oil per Ford specification.",
        )

        # Validator MUST block this (returns None)
        assert (
            result is None
        ), "Validator FAILED to block Ford-contaminated content in Chevy!"

        # Verify it was NOT saved as normal content
        chunk = await supabase_service.get_chunk(
            vehicle_key="2007_chevrolet_aveo_test_validator",
            content_id="test_oxygen_sensor_contaminated",
            chunk_type="procedure",
        )

        # If anything was created, it MUST be banned
        if chunk:
            assert (
                chunk.verified_status == "banned"
            ), "Contaminated chunk was saved but NOT banned!"
            assert (
                chunk.qa_status == "fail"
            ), "Contaminated chunk was saved but qa_status != fail!"

    @pytest.mark.asyncio
    async def test_validator_blocks_oil_change_in_brake_service(self):
        """Wrong procedure type must be blocked"""
        contaminated_data = {
            "steps": [
                {"title": "Prepare", "text": "Drain oil and locate oil drain plug"},
                {
                    "title": "Replace",
                    "text": "Replace oil filter and add new oil 5W-20",
                },
            ]
        }

        result = await supabase_service.save_chunk(
            vehicle_key="2012_honda_civic_test",
            content_id="drum_brake_service_test",
            chunk_type="procedure",
            template_type="ICE_GASOLINE",
            title="Drum Brake Service",
            data=contaminated_data,
            content_text="Drain oil and locate oil drain plug. Replace oil filter and add new oil 5W-20.",
        )

        assert (
            result is None
        ), "Validator FAILED to block oil-change text in drum_brake_service!"

    @pytest.mark.asyncio
    async def test_validator_blocks_missing_topic_keywords(self):
        """Content missing required topic keywords must be blocked"""
        # oxygen_sensor_testing without "oxygen", "o2", or "sensor"
        missing_keywords_data = {
            "steps": [
                {"title": "Step 1", "text": "Disconnect the electrical connector"},
                {"title": "Step 2", "text": "Remove the component from exhaust"},
            ]
        }

        result = await supabase_service.save_chunk(
            vehicle_key="2015_toyota_camry_test",
            content_id="oxygen_sensor_testing_test",
            chunk_type="procedure",
            template_type="ICE_GASOLINE",
            title="Oxygen Sensor Testing",
            data=missing_keywords_data,
            content_text="Disconnect the electrical connector. Remove the component from exhaust.",
        )

        assert (
            result is None
        ), "Validator FAILED to block oxygen_sensor content without topic keywords!"

    @pytest.mark.asyncio
    async def test_validator_blocks_too_short_content(self):
        """Stub-like content under 120 chars must be blocked"""
        stub_data = {"message": "Pending"}

        result = await supabase_service.save_chunk(
            vehicle_key="2020_ford_f150_test",
            content_id="test_short_content",
            chunk_type="spec",
            template_type="ICE_GASOLINE",
            title="Test Short",
            data=stub_data,
            sources=["Test"],
        )

        assert result is None, "Validator FAILED to block content under 120 characters!"


class TestCleanGenerationPasses:
    """
    Test 3: Valid content MUST NOT be blocked.

    Ensures the validator doesn't reject legitimate data.
    """

    @pytest.mark.asyncio
    async def test_valid_oxygen_sensor_content_passes(self):
        """Proper oxygen sensor content with keywords should pass"""
        clean_data = {
            "steps": [
                {
                    "title": "Locate Sensor",
                    "text": "Find the oxygen sensor (O2 sensor) on the exhaust manifold. The sensor has a wiring harness connector.",
                },
                {
                    "title": "Test Voltage",
                    "text": "Using a multimeter, test the oxygen sensor voltage output. Normal range is 0.1-0.9V during operation.",
                },
                {
                    "title": "Check Resistance",
                    "text": "Disconnect the O2 sensor and check heater element resistance. Should be 4-8 ohms for most sensors.",
                },
            ]
        }

        result = await supabase_service.save_chunk(
            vehicle_key="2007_chevrolet_aveo_test_clean",
            content_id="oxygen_sensor_testing_clean",
            chunk_type="procedure",
            template_type="ICE_GASOLINE",
            title="Oxygen Sensor Testing",
            data=clean_data,
            sources=["Test Clean Generation"],
            content_text="Find the oxygen sensor (O2 sensor) on the exhaust manifold. The sensor has a wiring harness connector. Using a multimeter, test the oxygen sensor voltage output. Normal range is 0.1-0.9V during operation.",
        )

        # Should NOT be blocked
        assert (
            result is not None
        ), "Validator incorrectly BLOCKED valid oxygen sensor content!"

        assert result.verified_status != "banned", "Valid content was marked as banned!"

        assert result.qa_status != "fail", "Valid content was marked as qa_status=fail!"

    @pytest.mark.asyncio
    async def test_valid_drum_brake_content_passes(self):
        """Proper drum brake content should pass"""
        clean_data = {
            "steps": [
                {
                    "title": "Remove Wheel",
                    "text": "Remove the wheel to access the drum brake assembly and backing plate.",
                },
                {
                    "title": "Remove Drum",
                    "text": "Remove brake drum. Inspect brake shoes and wheel cylinder for leaks.",
                },
                {
                    "title": "Replace Shoes",
                    "text": "Remove old brake shoes using spring tool. Install new shoes onto backing plate.",
                },
            ]
        }

        result = await supabase_service.save_chunk(
            vehicle_key="2005_ford_focus_test",
            content_id="drum_brake_service_clean",
            chunk_type="procedure",
            template_type="ICE_GASOLINE",
            title="Drum Brake Service",
            data=clean_data,
            sources=["Test"],
            content_text="Remove the wheel to access the drum brake assembly and backing plate. Remove brake drum. Inspect brake shoes and wheel cylinder for leaks.",
        )

        assert (
            result is not None
        ), "Validator incorrectly BLOCKED valid drum brake content!"


class TestNoRemainingContamination:
    """
    Test 4: Existing database chunks must not have silent contamination.

    Scans actual Aveo chunks to ensure none contain oil-change text
    unless they're properly banned.
    """

    AVEO_VEHICLE_KEY = "2007_chevrolet_aveo(t200/t250)_16lecoteci4(108hp)"

    @pytest.mark.asyncio
    async def test_oxygen_sensor_chunks_have_topic_keywords(self):
        """Oxygen sensor chunks must contain oxygen/o2/sensor keywords"""
        result = (
            supabase_service.client.table("chunks")
            .select("*")
            .ilike("content_id", "%oxygen%")
            .ilike("vehicle_key", "%aveo%")
            .execute()
        )

        for chunk in result.data:
            content = (
                str(chunk.get("data", "")).lower()
                + " "
                + str(chunk.get("content_text", "")).lower()
            )

            # If NOT banned, must have topic keywords
            if chunk.get("verified_status") != "banned":
                has_keywords = any(kw in content for kw in ["oxygen", "o2", "sensor"])
                assert (
                    has_keywords
                ), f"Oxygen sensor chunk {chunk['id']} missing topic keywords and NOT banned!"

            # Must NOT have oil-change contamination (even if banned, check it's marked correctly)
            has_oil = any(
                kw in content
                for kw in ["drain oil", "motorcraft fl-500s", "oil drain plug"]
            )
            if has_oil:
                assert (
                    chunk.get("verified_status") == "banned"
                ), f"Chunk {chunk['id']} has oil contamination but is NOT banned!"

    @pytest.mark.asyncio
    async def test_drum_brake_chunks_have_topic_keywords(self):
        """Drum brake chunks must contain drum/shoe/cylinder keywords"""
        result = (
            supabase_service.client.table("chunks")
            .select("*")
            .ilike("content_id", "%drum%")
            .ilike("vehicle_key", "%aveo%")
            .execute()
        )

        for chunk in result.data:
            content = (
                str(chunk.get("data", "")).lower()
                + " "
                + str(chunk.get("content_text", "")).lower()
            )

            if chunk.get("verified_status") != "banned":
                has_keywords = any(
                    kw in content
                    for kw in ["drum", "shoe", "wheel cylinder", "backing plate"]
                )
                assert (
                    has_keywords
                ), f"Drum brake chunk {chunk['id']} missing topic keywords and NOT banned!"

            has_oil = any(kw in content for kw in ["drain oil", "motorcraft fl-500s"])
            if has_oil:
                assert (
                    chunk.get("verified_status") == "banned"
                ), f"Chunk {chunk['id']} has oil contamination but NOT banned!"

    @pytest.mark.asyncio
    async def test_no_ford_keywords_in_chevy_chunks(self):
        """Chevy chunks must not contain Ford brand keywords"""
        result = (
            supabase_service.client.table("chunks")
            .select("*")
            .ilike("vehicle_key", "%chev%")
            .execute()
        )

        ford_keywords = ["motorcraft", "f-150", "f-250", "fomoco"]

        for chunk in result.data:
            content = (
                str(chunk.get("data", "")).lower()
                + " "
                + str(chunk.get("content_text", "")).lower()
            )

            found_ford = [kw for kw in ford_keywords if kw in content]
            if found_ford:
                assert (
                    chunk.get("verified_status") == "banned"
                ), f"Chevy chunk {chunk['id']} contains Ford keywords {found_ford} but NOT banned!"


class TestDieselTemplateBrakeStructure:
    """
    Test 5: Diesel template must have proper brake structure.

    Verifies the template fix was actually applied.
    """

    def test_diesel_template_has_disc_brake_service(self):
        """Diesel template must have disc_brake_service section"""
        import json

        with open("../swooptemplates/v3_ice_diesel_template.json", "r") as f:
            template = json.load(f)

        # Navigate to brakes section
        assert "systems" in template, "Template missing 'systems'"
        assert (
            "brakes_traction_control" in template["systems"]
        ), "Template missing 'brakes_traction_control'"

        brakes = template["systems"]["brakes_traction_control"]

        # MUST have disc_brake_service
        assert (
            "disc_brake_service" in brakes
        ), "Diesel template MISSING 'disc_brake_service' - the fix was not applied!"

        # Verify structure
        disc_brake = brakes["disc_brake_service"]
        assert "title" in disc_brake, "disc_brake_service missing 'title'"
        assert (
            "pad_rotor_replacement" in disc_brake
        ), "disc_brake_service missing 'pad_rotor_replacement'"

    def test_diesel_template_has_drum_brake_service(self):
        """Diesel template must have drum_brake_service section"""
        import json

        with open("../swooptemplates/v3_ice_diesel_template.json", "r") as f:
            template = json.load(f)

        brakes = template["systems"]["brakes_traction_control"]

        # MUST have drum_brake_service
        assert (
            "drum_brake_service" in brakes
        ), "Diesel template MISSING 'drum_brake_service' - the fix was not applied!"

        drum_brake = brakes["drum_brake_service"]
        assert "title" in drum_brake, "drum_brake_service missing 'title'"

    def test_diesel_template_no_old_disc_drum_service(self):
        """Diesel template must NOT have old combined disc_drum_service"""
        import json

        with open("../swooptemplates/v3_ice_diesel_template.json", "r") as f:
            template = json.load(f)

        brakes = template["systems"]["brakes_traction_control"]

        # Old incorrect key must NOT exist
        assert (
            "disc_drum_service" not in brakes
        ), "Diesel template STILL has old 'disc_drum_service' key - regression detected!"


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "-s"])
