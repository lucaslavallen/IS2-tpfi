from singletonproxyobserver import CorporateDataIterator


class FakeTable:
    """Simula una tabla DynamoDB con dos páginas."""

    def __init__(self):
        self.calls = []

    def scan(self, **kwargs):
        self.calls.append(kwargs)
        if not kwargs:
            return {"Items": [{"id": "1"}, {"id": "2"}],
                    "LastEvaluatedKey": {"id": "2"}}
        return {"Items": [{"id": "3"}]}


def test_es_iterador():
    it = CorporateDataIterator({})
    assert iter(it) is it
    assert hasattr(it, "__next__")


def test_dict_en_memoria():
    datos = {"a": {"id": "a"}, "b": {"id": "b"}}
    assert list(CorporateDataIterator(datos)) == [{"id": "a"}, {"id": "b"}]


def test_vacio():
    assert list(CorporateDataIterator({})) == []


def test_paginacion_dynamodb():
    tabla = FakeTable()
    assert list(CorporateDataIterator(tabla)) == [
        {"id": "1"}, {"id": "2"}, {"id": "3"}
    ]
    assert tabla.calls == [{}, {"ExclusiveStartKey": {"id": "2"}}]