"""
Terminal TCP para el Opta (equivalente al Serial Monitor, pero por Ethernet).
Funciona en Windows, Linux, Raspberry Pi y macOS con Python 3, sin librerías extra.

Uso:
    python main_terminal_tcp.py                 # 192.168.10.2:23 por defecto
    python main_terminal_tcp.py 192.168.10.2 23

Escribe un comando (i, p, s, e, r, c, h) y presiona Enter. Ctrl+C para salir.
"""
import socket
import sys
import threading

host = sys.argv[1] if len(sys.argv) > 1 else "192.168.10.2"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 23


def recibir(sock):
    while True:
        try:
            datos = sock.recv(1024)
        except OSError:
            break
        if not datos:
            print("\n# Conexión cerrada por el Opta")
            break
        sys.stdout.write(datos.decode("utf-8", errors="replace"))
        sys.stdout.flush()


try:
    sock = socket.create_connection((host, port), timeout=5)
except OSError as e:
    print(f"No se pudo conectar a {host}:{port} -> {e}")
    sys.exit(1)

sock.settimeout(None)
print(f"# Conectado a {host}:{port}. Ctrl+C para salir.\n")
threading.Thread(target=recibir, args=(sock,), daemon=True).start()

try:
    for linea in sys.stdin:
        sock.sendall(linea.encode())
except KeyboardInterrupt:
    pass
finally:
    sock.close()
