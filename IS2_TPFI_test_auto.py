import subprocess
import time
import json
import socket
try:
    import psutil
except ImportError:
    psutil = None
    print("Aviso: módulo 'psutil' no disponible. Algunas funcionalidades de limpieza de procesos quedarán deshabilitadas. Para habilitarlas, instalá psutil: pip install psutil")

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080
CLIENT = "python singletonclient.py"
OBSERVER = "python observerclient.py"
OUTPUT = "test_output.json"

# Funciones auxiliares
def run_command(cmd):
    print(f"\n>>> Ejecutando: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout.strip() or "(sin salida)")
    if result.stderr:
        print("STDERR:", result.stderr.strip())
    return result.returncode


def check_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((SERVER_HOST, port)) == 0


# Casos de prueba
def iniciar_observer():
    print("\n=== Iniciando observer ===")
    obs = subprocess.Popen(
        f"{OBSERVER} -o observer_output.json",
        shell=True, text=True
    )
    time.sleep(3) 
    return obs


def test_camino_feliz():
    print("\n=== Caso 1: Camino feliz ===")

    # set.json
    with open("set.json", "w", encoding="utf-8") as f:
        json.dump({
            "ACTION": "set",
            "id": "registro_test",
            "data": {"nombre": "Empresa Demo", "telefono": "111222333"}
        }, f, indent=2)
    run_command(f"{CLIENT} -i set.json -v")

    # list.json
    with open("list.json", "w", encoding="utf-8") as f:
        json.dump({"ACTION": "list"}, f)
    run_command(f"{CLIENT} -i list.json -v")

    # get.json
    with open("get.json", "w", encoding="utf-8") as f:
        json.dump({"ACTION": "get", "id": "registro_test"}, f)
    run_command(f"{CLIENT} -i get.json -v")


def test_argumentos_malformados():
    print("\n=== Caso 2: Argumentos malformados ===")
    run_command(f"{CLIENT} --input= ")      
    run_command(f"{CLIENT} -x archivo.json") 
    run_command(f"{OBSERVER} --output")  
    run_command(f"{OBSERVER} -x archivo.json")  


def test_datos_incompletos():
    print("\n=== Caso 3: Datos incompletos ===")
    with open("incompleto.json", "w", encoding="utf-8") as f:
        json.dump({"ACTION": "set"}, f)  
    run_command(f"{CLIENT} -i incompleto.json -v")


def test_server_caido():
    print("\n=== Caso 4: Servidor caído ===")

    # asegurarse que no haya servidor activo
    if check_port_in_use(SERVER_PORT):
        print("Servidor activo.")
        return

    try:
        result = subprocess.run(
            f"{CLIENT} -i list.json -v",
            shell=True, capture_output=True, text=True, timeout=5
        )
        print(result.stdout.strip() or "(sin salida)")
        print(result.stderr.strip() or "(sin errores)")
        if result.returncode != 0:
            print("Resultado esperado: error de conexión al servidor (servidor caído).")
    except subprocess.TimeoutExpired:
        print("Timeout: no se recibió respuesta (esperado).")
    except Exception as e:
        print(f"Excepción capturada: {e}")


def test_doble_servidor():
    print("\n=== Caso 5: Doble servidor ===")

    if not check_port_in_use(SERVER_PORT):
        print("Primero ejecutá el servidor principal antes de esta prueba.")
        return

    # intentar iniciar otro servidor en el mismo puerto
    code = run_command("python singletonproxyobserver.py -p 8080")
    if code != 0:
        print("Resultado esperado: puerto ya en uso.")


if __name__ == "__main__":
    print("=== INICIO DE TEST AUTOMATIZADO DEL TPFI ===")
    time.sleep(2)

    observer_proc = iniciar_observer()
    test_camino_feliz()
    observer_proc.kill()
    print("Observer detenido forzadamente.")
    time.sleep(2)
    if psutil:
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = p.info.get('cmdline') or []
                if isinstance(cmdline, list):
                    joined = " ".join(cmdline)
                else:
                    joined = str(cmdline)
                if "observerclient.py" in joined:
                    print(f"Eliminando observer remanente (PID {p.pid})...")
                    p.kill()
            except Exception:
                pass
    else:
        print("No se puede eliminar observers remanentes: psutil no está instalado.")

    input("\n*** Presioná ENTER para continuar con el Caso 2 (Argumentos malformados)...")
    test_argumentos_malformados()

    input("\n*** Presioná ENTER para continuar con el Caso 3 (Datos incompletos)...")
    test_datos_incompletos()

    input("\n*** Apagá el servidor y presioná ENTER para continuar con el Caso 4 (Servidor caído)...")
    test_server_caido()

    input("\n*** Volvé a levantar el servidor y presioná ENTER para continuar con el Caso 5 (Doble servidor)...")
    test_doble_servidor()

    print("\n=== FIN DE TEST AUTOMATIZADO ===")
