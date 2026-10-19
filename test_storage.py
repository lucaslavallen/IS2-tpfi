from storage import CORPORATE_DATA_FIELDS, MemoryCorporateDataGateway


def test_memory_gateway_merges_only_corporate_fields():
    MemoryCorporateDataGateway.reset()
    gateway = MemoryCorporateDataGateway.instance()

    created = gateway.merge_record(
        "A1",
        {"nombre": "Ana", "localidad": "Paraná", "unexpected": "ignored"},
    )
    updated = gateway.merge_record("A1", {"nombre": "Ana actualizada"})

    assert created["id"] == "A1"
    assert created["nombre"] == "Ana"
    assert "unexpected" not in created
    assert updated["nombre"] == "Ana actualizada"
    assert updated["localidad"] == "Paraná"
    assert set(updated) == CORPORATE_DATA_FIELDS | {"id"}
    MemoryCorporateDataGateway.reset()
