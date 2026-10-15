import socket
import threading
import json
import uuid
import logging
import decimal
from datetime import datetime

def default_converter(o):
    if isinstance(o, decimal.Decimal):
        return float(o)
    raise TypeError

class DynamoSingleton:
    _instance = None

    def __new__(cls, use_aws=False):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.use_aws = use_aws
            if use_aws:
                import boto3
                cls._instance.dynamodb = boto3.resource('dynamodb')
                cls._instance.corporate_data = cls._instance.dynamodb.Table('CorporateData')
                cls._instance.corporate_log = cls._instance.dynamodb.Table('CorporateLog')
            else:
                cls._instance.corporate_data = {}
                cls._instance.corporate_log = []
        return cls._instance

class CorporateDataIterator:
    """Patrón Iterator: recorre los registros de CorporateData de a uno.

    Oculta al proxy cómo se almacenan los datos (dict en memoria o tabla
    DynamoDB con paginación vía LastEvaluatedKey).
    """

    def __init__(self, corporate_data):
        self._source = corporate_data
        self._page = []
        self._last_key = None
        self._started = False

    def __iter__(self):
        return self

    def __next__(self):
        if isinstance(self._source, dict):
            if not self._started:
                self._page = list(self._source.values())
                self._started = True
        elif not self._page:
            if self._started and self._last_key is None:
                raise StopIteration
            kwargs = {"ExclusiveStartKey": self._last_key} if self._last_key else {}
            response = self._source.scan(**kwargs)
            self._page = list(response.get("Items", []))
            self._last_key = response.get("LastEvaluatedKey")
            self._started = True
        if not self._page:
            raise StopIteration
        return self._page.pop(0)

class DynamoProxy:
    def __init__(self, singleton_instance):
        self.db = singleton_instance
        self.observers = []

    def get(self, record_id, uuid_cliente=None):
        if not record_id:
            logging.error("Operación 'get' inválida: falta id.")
            return {"error": "Debe indicar un id para 'get'."}

        if isinstance(self.db.corporate_data, dict):
            record = self.db.corporate_data.get(record_id)
        else:
            response = self.db.corporate_data.get_item(
                Key={"id": record_id}
            )
            record = response.get("Item")

        self.log_action("get", record_id, uuid_cliente)

        if record is None:
            logging.warning("No se encontró el registro con id=%s", record_id)
            return {"error": f"No se encontró el registro '{record_id}'."}

        return record


    def list(self, uuid_cliente=None):
        records = list(CorporateDataIterator(self.db.corporate_data))
        self.log_action('list', None, uuid_cliente)
        return records

    # def set(self, record_id, data, uuid_cliente=None):
    #     if not record_id or not data:
    #         logging.error("Operación 'set' inválida: faltan id o datos.")
    #         return {"error": "Faltan campos obligatorios para 'set'."}
    #     if isinstance(self.db.corporate_data, dict):
    #         self.db.corporate_data[record_id] = data
    #     else:
    #         self.db.corporate_data.put_item(Item={'id': record_id, **data})
    #     self.log_action('set', None, uuid_cliente)
    #     self.notify_observers({'ACTION':'update','id':record_id,'data':data})
    #     return {"result": "Registro actualizado", "id": record_id, "data": data}
    
    def set(self, record_id, data, uuid_cliente=None):
        if not record_id or not isinstance(data, dict) or not data:
            logging.error("Operación 'set' inválida: faltan id o datos.")
            return {"error": "Faltan campos obligatorios para 'set'."}

        if isinstance(self.db.corporate_data, dict):
            # Al crear, inicializar campos omitidos como cadenas vacías.
            # Al actualizar, conservar los campos que ya existen.
            existing = self.db.corporate_data.get(record_id)
            if existing is None:
                updated_data = {key: "" for key in data.keys()}
            else:
                updated_data = dict(existing)

            updated_data.update(data)
            self.db.corporate_data[record_id] = updated_data
        else:
            table = self.db.corporate_data
            response = table.get_item(Key={"id": record_id})
            existing = response.get("Item")

            if existing is None:
                updated_data = {"id": record_id}
                updated_data.update({key: "" for key in data.keys()})
            else:
                updated_data = dict(existing)

            updated_data.update(data)
            updated_data["id"] = record_id
            table.put_item(Item=updated_data)

        self.log_action("set", None, uuid_cliente)

        notification = {
            "ACTION": "update",
            "id": record_id,
            "data": updated_data
        }
        self.notify_observers(notification)

        return {
            "result": "Registro actualizado",
            "id": record_id,
            "data": updated_data
        }

    
    def list_logs(self):
        if isinstance(self.db.corporate_log, list):
            logs = list(self.db.corporate_log)
        else:
            response = self.db.corporate_log.scan()
            logs = response.get("Items", [])

            while "LastEvaluatedKey" in response:
                response = self.db.corporate_log.scan(
                    ExclusiveStartKey=response["LastEvaluatedKey"]
                )
                logs.extend(response.get("Items", []))

        logging.info("Se recuperaron %d registros de CorporateLog.", len(logs))
        return logs

    def log_action(self, action, record_id=None, uuid_cliente=None):
        unique_id = str(uuid.uuid4())
        sessionid=str(uuid.uuid4())
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")

        if action == 'get':
            log_entry = {'id':unique_id, 'CPUid': uuid_cliente,'sessionid': sessionid, 'accion': action, 'idsolicitado': record_id ,'timestamp': ts}
        else:
           log_entry = {'id':unique_id, 'CPUid': uuid_cliente,'sessionid': sessionid, 'accion': action,'timestamp': ts}

        if isinstance(self.db.corporate_log, list):
            self.db.corporate_log.append(log_entry)
            last_log = log_entry
        else:
            self.db.corporate_log.put_item(Item=log_entry)
            response = self.db.corporate_log.get_item(Key={'id': unique_id})
            last_log = response.get('Item')

        if last_log:
            logging.info("Nuevo log insertado en CorporateLog: CPU=%s acción=%s session=%s time=%s", uuid_cliente, action, sessionid, ts)
        else:
            logging.warning("Advertencia: no se pudo verificar el registro en CorporateLog.")

    def add_observer(self, conn):
        self.observers.append(conn)

    def remove_observer(self, conn):
        if conn in self.observers:
            self.observers.remove(conn)

    def notify_observers(self, message):
        data = (json.dumps(message)+"\n").encode("utf-8")
        for obs in self.observers[:]:
            try:
                obs.sendall(data)
            except:
                self.observers.remove(obs)

        logging.debug("Notificando a %d observadores: %s", len(self.observers), message)

def handle_client(conn, proxy):
    try:
        buffer = b""
        while True:
            try:
                chunk = conn.recv(4096)
            except ConnectionResetError:
                logging.info("Conexión cerrada abruptamente por el cliente")
                break
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n",1)
                if not line.strip():
                    continue
                req = json.loads(line.decode('utf-8'))
                action = req.get('ACTION')
                uuid_cliente = req.get('UUID')
                logging.debug("Acción recibida: %s (UUID=%s)", action, uuid_cliente)

                if action == 'get':
                    record_id = req.get('id')
                    resp = proxy.get(record_id, uuid_cliente)
                elif action == 'list':
                    resp = proxy.list(uuid_cliente)
                elif action == 'set':
                    record_id = req.get('id')
                    data = req.get('data')
                    resp = proxy.set(record_id,data, uuid_cliente)
                elif action == 'list_logs':
                    resp = proxy.list_logs()
                elif action == 'subscribe':
                    proxy.add_observer(conn)
                    proxy.log_action('subscribe', None, uuid_cliente)
                    continue
                else:
                    resp = {'error':'acción desconocida'}
                conn.sendall((json.dumps(resp, default=default_converter) + "\n").encode('utf-8'))
    finally:
        proxy.remove_observer(conn)
        conn.close()
        logging.info("Cliente desconectado")

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-p", "--port", type=int, default=8080)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='[%(levelname)s] %(message)s'
    )

    HOST = "127.0.0.1"
    PORT = args.port
    singleton = DynamoSingleton(use_aws=True)
    proxy = DynamoProxy(singleton)

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((HOST, PORT))
    except OSError:
        logging.error("No se pudo iniciar el servidor: el puerto %d ya está en uso.", PORT)
        return

    s.listen(5)
    logging.info("Servidor escuchando en %s:%d", HOST, PORT)

    while True:
        conn, addr = s.accept()
        logging.info("Nueva conexión desde %s", addr)
        t = threading.Thread(target=handle_client,args=(conn,proxy),daemon=True)
        t.start()

if __name__=="__main__":
    main()
