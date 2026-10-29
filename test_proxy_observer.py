import json
from types import SimpleNamespace

import pytest

from singletonproxyobserver import DynamoProxy


class FakeObserver:
    """Simula un cliente suscripto al Observer."""

    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail

    def sendall(self, data):
        if self.fail:
            raise OSError("Conexión cerrada")
        self.messages.append(data)


@pytest.fixture
def proxy():
    """Crea un Proxy aislado, sin conexión con AWS."""
    db = SimpleNamespace(
        corporate_data={
            "A1": {
                "id": "A1",
                "nombre": "Ana",
                "localidad": "Paraná",
            }
        },
        corporate_log=[],
    )
    return DynamoProxy(db)

def test_get_registro_existente(proxy):
    result = proxy.get("A1")
    assert result["nombre"] == "Ana"
    assert result["localidad"] == "Paraná"


def test_get_sin_id(proxy):
    result = proxy.get("")
    assert "error" in result


def test_get_registro_inexistente(proxy):
    result = proxy.get("NO-EXISTE")
    assert isinstance(result, dict)
    assert "error" in result


def test_list_devuelve_registros(proxy):
    result = proxy.list()
    assert len(result) == 1
    assert result[0]["id"] == "A1"


def test_set_crea_registro(proxy):
    result = proxy.set(
        "A2",
        {"nombre": "Luis", "localidad": "Concepción del Uruguay"},
    )

    assert result["id"] == "A2"
    assert proxy.db.corporate_data["A2"]["nombre"] == "Luis"


def test_set_actualizacion_parcial(proxy):
    proxy.set("A1", {"nombre": "Ana actualizada"})

    record = proxy.db.corporate_data["A1"]
    assert record["nombre"] == "Ana actualizada"
    assert record["localidad"] == "Paraná"


@pytest.mark.parametrize(
    ("record_id", "data"),
    [
        ("", {"nombre": "Ana"}),
        ("A1", {}),
        ("A1", None),
        ("A1", ["dato"]),
    ],
)
def test_set_rechaza_datos_invalidos(proxy, record_id, data):
    result = proxy.set(record_id, data)
    assert "error" in result


def test_set_registra_auditoria(proxy):
    proxy.set("A2", {"nombre": "Luis"})

    assert len(proxy.db.corporate_log) == 1
    log = proxy.db.corporate_log[0]
    assert log["accion"] == "set"
    assert log["id"]
    assert log["sessionid"]
    assert log["timestamp"]


def test_observer_notifica_a_dos_suscriptores(proxy):
    observer1 = FakeObserver()
    observer2 = FakeObserver()
    proxy.add_observer(observer1)
    proxy.add_observer(observer2)

    proxy.set("A1", {"nombre": "Nuevo nombre"})

    assert len(observer1.messages) == 1
    assert len(observer2.messages) == 1

    message = json.loads(observer1.messages[0].decode("utf-8"))
    assert message["ACTION"] == "update"
    assert message["id"] == "A1"
    assert message["data"]["nombre"] == "Nuevo nombre"


def test_observer_elimina_conexion_fallida(proxy):
    observer_bad = FakeObserver(fail=True)
    observer_good = FakeObserver()
    proxy.add_observer(observer_bad)
    proxy.add_observer(observer_good)

    proxy.set("A1", {"nombre": "Actualizada"})

    assert observer_bad not in proxy.observers
    assert observer_good in proxy.observers
    assert len(observer_good.messages) == 1


def test_remove_observer(proxy):
    observer = FakeObserver()
    proxy.add_observer(observer)
    proxy.remove_observer(observer)

    assert observer not in proxy.observers



def test_get_registra_auditoria(proxy):
    proxy.get("A1")
    log = proxy.db.corporate_log[-1]

    assert log["accion"] == "get"
    assert log["idsolicitado"] == "A1"
    assert log["id"]
    assert log["sessionid"]
    assert log["timestamp"]


def test_list_registra_auditoria(proxy):
    proxy.list()
    log = proxy.db.corporate_log[-1]

    assert log["accion"] == "list"
    assert log["id"]
    assert log["sessionid"]
    assert log["timestamp"]


def test_list_logs_recupera_eventos(proxy):
    proxy.set("A2", {"nombre": "Luis"})

    logs = proxy.list_logs()

    assert len(logs) == 1
    assert logs[0]["accion"] == "set"


def test_auditoria_usa_ids_unicos(proxy):
    proxy.get("A1")
    proxy.list()

    logs = proxy.db.corporate_log
    ids = [log["id"] for log in logs]

    assert len(ids) == len(set(ids))
