from singletonclient import normalize_request


def test_normaliza_set_con_campos_planos():
    request = {
        "UUID": "1234567890",
        "ID": "UADER-FCYT-IS2",
        "ACTION": "set",
        "localidad": "Concepción del Uruguay",
        "telefono": "03442 43-1442",
    }

    assert normalize_request(request) == {
        "UUID": "1234567890",
        "ID": "UADER-FCYT-IS2",
        "ACTION": "set",
        "id": "UADER-FCYT-IS2",
        "data": {
            "localidad": "Concepción del Uruguay",
            "telefono": "03442 43-1442",
        },
    }
    assert "id" not in request
    assert "data" not in request


def test_conserva_formato_set_anidado():
    request = {
        "ACTION": "set",
        "id": "A1",
        "data": {"nombre": "Ana"},
    }

    assert normalize_request(request) == request


def test_no_completa_set_sin_identificador_ni_datos():
    request = {"ACTION": "set"}

    assert normalize_request(request) == request
