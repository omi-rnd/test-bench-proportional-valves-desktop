"""
Interfaz gráfica para el banco de pruebas (Opta por Ethernet, TCP puerto 23).

Multiplataforma: Windows, Linux, Raspberry Pi y macOS con Python 3. Solo usa la
librería estándar (tkinter, socket, threading). Si falta tkinter:
    Raspberry Pi OS / Debian / Ubuntu:  sudo apt install python3-tk
    macOS (Homebrew):                   brew install python-tk
    Windows / macOS (python.org):       ya viene incluido

Uso:
    python main.py

Requiere en el Opta el sketch arduino/opta_sensor_ethernet del repo
test-bench-proportional-valves-control.
"""
import csv
import queue
import re
import socket
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

IP_DEFECTO = "192.168.10.2"
PUERTO_DEFECTO = 23

COLORES_ESTADO = {
    "DETENIDO": "#7F7F7F",
    "CORRIENDO": "#2E8B57",
    "PAUSA": "#E0A000",
    "PARO DE EMERGENCIA": "#E03C38",
    "SIN CONEXIÓN": "#B0B0B0",
}

RE_ESTADO = re.compile(r"==\s+(DETENIDO|CORRIENDO|PAUSA|PARO DE EMERGENCIA)")
RE_ESTADO_AYUDA = re.compile(r"Estado de (?:la )?prueba\s*:\s*(DETENIDO|CORRIENDO|PAUSA|PARO DE EMERGENCIA)")
RE_DETECTA = re.compile(r">>\s+DETECTA\s+#(\d+)")
RE_LIBRE = re.compile(r"<<\s+libre\s+#(\d+)\s+duracion:\s+([\d.]+)\s*(ms|s)?")
RE_SENSOR = re.compile(r"Sensor:\s+(DETECTA|libre)")


class Conexion:
    """Hilo que lee del socket y deja las líneas en una cola."""

    def __init__(self, cola):
        self.cola = cola
        self.sock = None
        self.activa = False

    def conectar(self, host, puerto):
        self.sock = socket.create_connection((host, puerto), timeout=3)
        self.sock.settimeout(None)
        self.activa = True
        threading.Thread(target=self._leer, daemon=True).start()
        self.enviar("\n")          # algunas versiones registran la conexión hasta recibir algo

    def _leer(self):
        resto = ""
        while self.activa:
            try:
                datos = self.sock.recv(1024)
            except OSError:
                break
            if not datos:
                break
            resto += datos.decode("utf-8", errors="replace")
            *lineas, resto = resto.replace("\r", "").split("\n")
            for l in lineas:
                self.cola.put(("linea", l))
        self.activa = False
        self.cola.put(("desconectado", None))

    def enviar(self, texto):
        if self.sock and self.activa:
            try:
                self.sock.sendall(texto.encode())
            except OSError:
                pass

    def cerrar(self):
        self.activa = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None


class Interfaz(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Banco de pruebas de válvulas – Opta")
        self.geometry("900x620")
        self.minsize(760, 520)

        self.cola = queue.Queue()
        self.conexion = Conexion(self.cola)
        self.eventos = []            # (hora PC, evento, número, duración_ms)
        self.conteo = 0

        self._construir()
        self._poner_estado("SIN CONEXIÓN")
        self.after(50, self._procesar_cola)
        self.protocol("WM_DELETE_WINDOW", self._salir)

    # ---------- Construcción de la ventana ----------
    def _construir(self):
        pad = {"padx": 8, "pady": 6}

        # Conexión
        fc = ttk.LabelFrame(self, text="Conexión")
        fc.pack(fill="x", **pad)
        ttk.Label(fc, text="IP:").pack(side="left", padx=(8, 2))
        self.var_ip = tk.StringVar(value=IP_DEFECTO)
        ttk.Entry(fc, textvariable=self.var_ip, width=16).pack(side="left")
        ttk.Label(fc, text="Puerto:").pack(side="left", padx=(10, 2))
        self.var_puerto = tk.StringVar(value=str(PUERTO_DEFECTO))
        ttk.Entry(fc, textvariable=self.var_puerto, width=6).pack(side="left")
        self.btn_conectar = ttk.Button(fc, text="Conectar", command=self._conectar)
        self.btn_conectar.pack(side="left", padx=10, pady=6)
        self.lbl_conexion = ttk.Label(fc, text="Desconectado")
        self.lbl_conexion.pack(side="left")

        # Estado + indicadores
        fe = ttk.Frame(self)
        fe.pack(fill="x", **pad)
        self.lbl_estado = tk.Label(fe, text="", font=("Arial", 20, "bold"), fg="white", width=22, pady=10)
        self.lbl_estado.pack(side="left")

        fi = ttk.Frame(fe)
        fi.pack(side="left", padx=20)
        ttk.Label(fi, text="Sensor:", font=("Arial", 11)).grid(row=0, column=0, sticky="w")
        self.lbl_sensor = tk.Label(fi, text="—", font=("Arial", 11, "bold"), width=10, bg="#E6E6E6")
        self.lbl_sensor.grid(row=0, column=1, padx=6, pady=2)
        ttk.Label(fi, text="Detecciones:", font=("Arial", 11)).grid(row=1, column=0, sticky="w")
        self.lbl_conteo = ttk.Label(fi, text="0", font=("Arial", 16, "bold"))
        self.lbl_conteo.grid(row=1, column=1, sticky="w", padx=6)
        ttk.Label(fi, text="Última duración:", font=("Arial", 11)).grid(row=2, column=0, sticky="w")
        self.lbl_duracion = ttk.Label(fi, text="—", font=("Arial", 11))
        self.lbl_duracion.grid(row=2, column=1, sticky="w", padx=6)

        # Botones de control
        fb = ttk.LabelFrame(self, text="Control de la prueba")
        fb.pack(fill="x", **pad)
        estilo = ttk.Style(self)
        estilo.configure("Grande.TButton", font=("Arial", 12, "bold"), padding=8)
        self.botones = []
        for texto, cmd in [("▶ Inicio", "i"), ("❚❚ Pausa", "p"), ("■ Stop", "s"),
                           ("Estadísticas", "e"), ("Reiniciar", "r")]:
            b = ttk.Button(fb, text=texto, style="Grande.TButton",
                           command=lambda c=cmd: self._comando(c))
            b.pack(side="left", padx=6, pady=8)
            self.botones.append(b)
        ttk.Button(fb, text="Guardar eventos CSV…", command=self._guardar_csv).pack(side="right", padx=6)
        ttk.Button(fb, text="Guardar registro…", command=self._guardar_log).pack(side="right", padx=6)

        ttk.Label(self, text="El paro de emergencia es solo el botón físico del tablero.",
                  foreground="#595959").pack(anchor="w", padx=12)

        # Registro
        fr = ttk.LabelFrame(self, text="Registro (lo mismo que el Serial Monitor)")
        fr.pack(fill="both", expand=True, **pad)
        self.txt = tk.Text(fr, font="TkFixedFont", wrap="none", state="disabled")
        sb = ttk.Scrollbar(fr, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)

        self._habilitar_botones(False)

    # ---------- Acciones ----------
    def _conectar(self):
        if self.conexion.activa:
            self.conexion.cerrar()
            return
        try:
            puerto = int(self.var_puerto.get())
            self.conexion.conectar(self.var_ip.get().strip(), puerto)
        except (OSError, ValueError) as e:
            messagebox.showerror("Conexión", f"No se pudo conectar:\n{e}")
            return
        self.lbl_conexion.config(text=f"Conectado a {self.var_ip.get()}:{puerto}")
        self.btn_conectar.config(text="Desconectar")
        self._habilitar_botones(True)
        self._log(f"# Conectado {datetime.now():%Y-%m-%d %H:%M:%S}")

    def _comando(self, c):
        self.conexion.enviar(c + "\n")

    def _habilitar_botones(self, si):
        for b in self.botones:
            b.state(["!disabled"] if si else ["disabled"])

    def _guardar_log(self):
        ruta = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile=f"registro_{datetime.now():%Y%m%d_%H%M%S}.txt")
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(self.txt.get("1.0", "end"))

    def _guardar_csv(self):
        if not self.eventos:
            messagebox.showinfo("CSV", "Todavía no hay eventos registrados.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv",
                                            initialfile=f"eventos_{datetime.now():%Y%m%d_%H%M%S}.csv")
        if ruta:
            with open(ruta, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["hora_pc", "evento", "numero", "duracion_ms"])
                w.writerows(self.eventos)

    def _salir(self):
        self.conexion.cerrar()
        self.destroy()

    # ---------- Recepción ----------
    def _procesar_cola(self):
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "linea":
                    self._log(dato)
                    self._interpretar(dato)
                elif tipo == "desconectado":
                    self._log("# Desconectado")
                    self.lbl_conexion.config(text="Desconectado")
                    self.btn_conectar.config(text="Conectar")
                    self._habilitar_botones(False)
                    self._poner_estado("SIN CONEXIÓN")
                    self.lbl_sensor.config(text="—", bg="#E6E6E6")
        except queue.Empty:
            pass
        self.after(50, self._procesar_cola)

    def _interpretar(self, linea):
        hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        m = RE_ESTADO.search(linea) or RE_ESTADO_AYUDA.search(linea)
        if m:
            self._poner_estado(m.group(1))
            if m.group(1) == "CORRIENDO" and "inicio" in linea:
                self.conteo = 0
                self.lbl_conteo.config(text="0")
            if RE_ESTADO.search(linea):
                self.eventos.append((hora, "ESTADO " + m.group(1), "", ""))
            return
        m = RE_DETECTA.search(linea)
        if m:
            self.conteo = int(m.group(1))
            self.lbl_conteo.config(text=str(self.conteo))
            self._poner_sensor(True)
            self.eventos.append((hora, "DETECTA", self.conteo, ""))
            return
        m = RE_LIBRE.search(linea)
        if m:
            dur = float(m.group(2)) * (1000 if m.group(3) == "s" else 1)
            self.lbl_duracion.config(text=f"{dur:.1f} ms")
            self._poner_sensor(False)
            self.eventos.append((hora, "libre", int(m.group(1)), f"{dur:.1f}"))
            return
        if "<< libre" in linea:
            self._poner_sensor(False)
            return
        m = RE_SENSOR.search(linea)
        if m:
            self._poner_sensor(m.group(1) == "DETECTA")

    def _poner_estado(self, estado):
        self.lbl_estado.config(text=estado, bg=COLORES_ESTADO.get(estado, "#7F7F7F"))

    def _poner_sensor(self, detecta):
        self.lbl_sensor.config(text="DETECTA" if detecta else "libre",
                               bg="#2E8B57" if detecta else "#E6E6E6",
                               fg="white" if detecta else "black")

    def _log(self, texto):
        self.txt.config(state="normal")
        self.txt.insert("end", texto + "\n")
        if int(self.txt.index("end-1c").split(".")[0]) > 5000:   # limita el tamaño
            self.txt.delete("1.0", "1000.0")
        self.txt.see("end")
        self.txt.config(state="disabled")


if __name__ == "__main__":
    Interfaz().mainloop()
