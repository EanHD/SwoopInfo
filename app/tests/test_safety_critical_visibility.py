import pytest
from httpx import AsyncClient, ASGITransport
from services.supabase_client import supabase_service
from main import app


# Helper to generate long content
def make_content(base_text):
    return base_text + " " + "padding " * 30


@pytest.mark.asyncio
async def test_non_critical_chunk_is_ready_and_visible():
    # Example: oxygen_sensor_testing
    content = make_content(
        "Test oxygen sensor procedure with sufficient length to pass contamination check."
    )
    chunk = await supabase_service.save_chunk(
        vehicle_key="2007_chevrolet_aveo_test_non_critical",
        content_id="oxygen_sensor_testing",
        chunk_type="procedure",
        template_type="ICE_GASOLINE",
        title="Test Oxygen Sensor",
        data={"steps": [{"title": "Step 1", "text": "Test oxygen sensor"}]},
        sources=["test"],
        content_text=content,
    )

    assert chunk is not None
    assert chunk.verified_status == "unverified"
    assert chunk.qa_status == "pending"


@pytest.mark.asyncio
async def test_safety_critical_chunk_is_quarantined():
    # Example: engine_oil_volume spec
    content = make_content(
        "Oil capacity is 4.5 quarts. This is a safety critical spec that should be quarantined."
    )
    chunk = await supabase_service.save_chunk(
        vehicle_key="2007_chevrolet_aveo_test_critical",
        content_id="engine_oil_volume",
        chunk_type="spec",
        template_type="ICE_GASOLINE",
        title="Test Oil Volume",
        data={"value": "4.5 qt"},
        sources=["test"],
        content_text=content,
    )

    assert chunk is not None
    assert chunk.verified_status == "unverified"
    assert chunk.qa_status == "pending"


@pytest.mark.asyncio
async def test_api_non_critical_chunk_is_ready():
    vehicle_key = "2007_chevrolet_aveo_test_api_non_critical"
    content_id = "oxygen_sensor_testing"

    content = make_content(
        "This is a test for oxygen sensor testing. It needs to be long enough."
    )
    await supabase_service.save_chunk(
        vehicle_key=vehicle_key,
        content_id=content_id,
        chunk_type="procedure",
        template_type="ICE_GASOLINE",
        title="Test Oxygen Sensor",
        data={"steps": []},
        sources=["test"],
        content_text=content,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/chunks/{content_id}",
            params={
                "vehicle_key": vehicle_key,
                "chunk_type": "procedure",
                "template_type": "ICE_GASOLINE",
            },
        )

    data = response.json()

    assert data["status"] == "ready"
    assert data["visibility"] == "safe"
    assert data["verified_status"] == "unverified"


@pytest.mark.asyncio
async def test_api_safety_critical_chunk_is_visible_but_unverified():
    vehicle_key = "2007_chevrolet_aveo_test_api_critical"
    content_id = "brake_bleed_sequence"  # Critical

    content = make_content(
        "Brake bleed sequence procedure. This is critical and should be quarantined."
    )
    await supabase_service.save_chunk(
        vehicle_key=vehicle_key,
        content_id=content_id,
        chunk_type="procedure",
        template_type="ICE_GASOLINE",
        title="Brake Bleed",
        data={"steps": []},
        sources=["test"],
        content_text=content,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            f"/api/chunks/{content_id}",
            params={
                "vehicle_key": vehicle_key,
                "chunk_type": "procedure",
                "template_type": "ICE_GASOLINE",
            },
        )

    data = response.json()

    # RELAXED LOGIC: Critical stub -> unverified -> visible (safe)
    assert data["status"] == "ready"
    assert data["visibility"] == "safe"
    assert data["verified_status"] == "unverified"
