import json, socket, time, argparse, uuid, logging

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
RETRY_SECONDS = 30  

def cpu_uuid():
    return str(uuid.UUID(int=uuid.getnode()))


def main():
    p = argparse.ArgumentParser(description="Cliente observador del TPFI")
    p.add_argument("-s", "--server", default=DEFAULT_HOST, help="Host del servidor (default: localhost)")
    p.add_argument("-p", "--port", type=int, default=DEFAULT_PORT, help="Puerto (default: 8080)")
    p.add_argument("-o", "--output", help="Archivo donde guardar notificaciones")
    p.add_argument("-v", "--verbose", action="store_true", help="Mostrar información de depuración")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='[%(levelname)s] %(message)s'
    )    

    if args.output is not None and args.output.strip() == "":
        logging.error("Se indicó -o pero no se especificó archivo de salida.")
        return
    
    payload = {"UUID": cpu_uuid(), "ACTION": "subscribe"}

    while True:
        try:
            logging.info("Conectando a %s:%d", args.server, args.port)
            with socket.create_connection((args.server, args.port)) as s:
                s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                logging.info("Suscripto. Esperando actualizaciones...")

                buffer = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        logging.info("Conexión cerrada por el servidor")
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            msg = json.loads(line.decode("utf-8"))
                        except Exception as e:
                            logging.warning("Error decodificando JSON: %s", e)
                            continue

                        logging.debug("Notificación recibida: %s", msg)
                        text = json.dumps(msg, ensure_ascii=False, indent=2)
                        print(text)
                        if args.output:
                            try:
                                with open(args.output, "a", encoding="utf-8") as f:
                                    f.write(text + "\n")
                            except OSError as e:
                                logging.error("No se pudo escribir en el archivo de salida '%s': %s", args.output, e)

        except ConnectionRefusedError:
            logging.error("No se pudo conectar al servidor (%s:%d). ¿Está iniciado?", args.server, args.port)
        except socket.timeout:
            logging.error("Tiempo de espera agotado al intentar conectar con el servidor.")
        except OSError as e:
            logging.error("Error de conexión con el servidor: %s", e)
        except Exception as e:
            logging.warning("Error inesperado: %s", e)

        logging.info("Reintentando en %d segundos...", RETRY_SECONDS)
        time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    main()
