import json, socket, argparse, uuid, logging, os

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def normalize_request(req):
    """Adapta los archivos set con campos planos al formato del servidor."""
    if req.get("ACTION") != "set":
        return req

    normalized = dict(req)
    if "id" not in normalized and "ID" in normalized:
        normalized["id"] = normalized["ID"]

    if "data" not in normalized:
        metadata = {"ACTION", "UUID", "ID", "id"}
        data = {key: value for key, value in normalized.items() if key not in metadata}
        if data:
            normalized = {
                key: value
                for key, value in normalized.items()
                if key in metadata
            }
            normalized["data"] = data

    return normalized


def cpu_uuid():
    return str(uuid.UUID(int=uuid.getnode()))


def main():
    p = argparse.ArgumentParser(description="Cliente principal del TPFI")
    p.add_argument("-s", "--server", default=DEFAULT_HOST, help="Host del servidor (default: localhost)")
    p.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="Puerto (default: 8080)")
    p.add_argument("-i", "--input", required=True, help="Archivo JSON de entrada (get/set/list)")
    p.add_argument("-o", "--output", help="Archivo JSON de salida")
    p.add_argument("-v", "--verbose", action="store_true", help="Mostrar información de depuración")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='[%(levelname)s] %(message)s'
    )

    if args.input and not os.path.exists(args.input):
        logging.error("El archivo indicado con -i no existe o el nombre está vacío: %s", args.input)
        return
    
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            req = json.load(f)
    except FileNotFoundError:
        logging.error("No se encontró el archivo indicado en -i.")
        return
    except json.JSONDecodeError:
        logging.error("El archivo de entrada no contiene un JSON válido.")
        return
    
    if not isinstance(req, dict):
        logging.error("El archivo de entrada debe contener un objeto JSON.")
        return

    req = normalize_request(req)
    req.setdefault("UUID", cpu_uuid())

    try:
        logging.info("Conectando a %s:%d", args.server, args.port)
        with socket.create_connection((args.server, args.port)) as s:
            s.sendall((json.dumps(req) + "\n").encode("utf-8"))
            buffer = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                if b"\n" in buffer:
                    break

            data, *_ = buffer.split(b"\n", 1)
            data = data.decode("utf-8").strip()
    except ConnectionRefusedError:
        logging.error("No se pudo conectar al servidor (%s:%d). ¿Está iniciado?", args.server, args.port)
        return
    except socket.timeout:
        logging.error("Tiempo de espera agotado al intentar conectar con el servidor.")
        return
    except OSError as e:
        logging.error("Error de conexión con el servidor: %s", e)
        return

    resp = json.loads(data)
    logging.info("Respuesta recibida del servidor")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(resp, f, ensure_ascii=False, indent=2)
        logging.info("Respuesta guardada en %s", args.output)
    else:
        print(json.dumps(resp, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
