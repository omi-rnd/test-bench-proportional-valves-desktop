"""
Interfaz de la prueba de DURABILIDAD (1 slot) del banco de válvulas.

Se conecta por TCP al Opta con el sketch arduino/opta_durabilidad del repo
test-bench-proportional-valves-control (IP 192.168.10.2, puerto 23).

Multiplataforma: Windows, Linux, Raspberry Pi y macOS con Python 3 (solo librería
estándar). Pensada para la pantalla táctil de 1280x800 del banco: botones grandes.

Uso:
    python durabilidad.py

Qué hace:
  - Inicia, pausa, reanuda y detiene la prueba; reanuda desde un ciclo tras un corte.
  - Deslizador del PWM de la válvula (duty_on, comando pwm N): se aplica en vivo si P1 está
    encendida. Botón de salida manual (manual 1/0, solo en REPOSO) para probar P1 con un LED.
  - Muestra el estado, el ciclo actual, la presencia de válvula (SPV), el paro y V / I / T.
  - Muestra las leyendas del Opta ("Ajuste presión...", "Cierre suministro neumático")
    con un botón para retirarlas (comando k, igual que el botón B1).
  - Lee, edita y envía los parámetros de la prueba; los guarda y carga en un archivo JSON
    (el Opta no guarda nada: al reiniciarse vuelve a los valores de fábrica).
  - Al iniciar pide el nombre del archivo y guarda un CSV por prueba en la carpeta logs/ con una
    fila por ciclo registrado (líneas D del Opta), las fallas y el resultado. Si el archivo ya
    existe, los datos se agregan al final (útil al reanudar tras un corte).
"""
import csv
import json
import queue
import re
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from main import Conexion   # misma conexión TCP que la interfaz del sensor

IP_DEFECTO = "192.168.10.2"
PUERTO_DEFECTO = 23
CARPETA_LOGS = Path(__file__).resolve().parent / "logs"

# Estados que manda el Opta (nombreEstado() en opta_durabilidad.ino)
ESTADOS = ["REPOSO", "VERIFICACION", "FALLA DE VERIFICACION", "NO LISTO", "PURGA",
           "AJUSTE DE PRESION", "CORRIENDO", "PAUSA", "CIERRE NEUMATICO"]
ESTADOS_LEYENDA = {"AJUSTE DE PRESION", "CIERRE NEUMATICO", "FALLA DE VERIFICACION"}
COLORES_ESTADO = {
    "REPOSO": "#7F7F7F",
    "VERIFICACION": "#3A7BD5",
    "FALLA DE VERIFICACION": "#E03C38",
    "NO LISTO": "#E0A000",
    "PURGA": "#3A7BD5",
    "AJUSTE DE PRESION": "#E0A000",
    "CORRIENDO": "#2E8B57",
    "PAUSA": "#E0A000",
    "CIERRE NEUMATICO": "#E0A000",
    "SIN CONEXIÓN": "#B0B0B0",
}

_ALT = "|".join(re.escape(e) for e in sorted(ESTADOS, key=len, reverse=True))
RE_ESTADO = re.compile(r"==\s+(" + _ALT + r")(?:\s+\((.*)\))?\s*$")
RE_ESTADO_INFO = re.compile(r"Estado(?: de la prueba)?\s*:\s*(" + _ALT + r")\s*$")
RE_CICLO_INFO = re.compile(r"^\s*Ciclo\s*:\s*(\d+)\s*/\s*(\d+)")
RE_LEYENDA = re.compile(r"!!\s*LEYENDA:\s*(.*?)\s*(?:->.*)?$")
RE_AVISO = re.compile(r"!!\s*(FALLA|NO LISTO):\s*(.*)$")
RE_PRUEBA = re.compile(r"#\s*Prueba (nueva|reanudada)")
RE_NOMBRE_INVALIDO = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
ENVIO_PWM_MS = 150          # al arrastrar el deslizador se manda como máximo un "pwm" cada 150 ms

# Columnas de las líneas D / D0 (registrarCiclo() en el sketch)
COLUMNAS_D = ["ciclo", "v_on", "i_on", "i_on_min", "i_on_max", "v_off", "i_off", "t"]


def numero(texto):
    """'nan' o texto vacío -> None; si no, float."""
    try:
        v = float(texto)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


class Durabilidad(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Prueba de durabilidad – Banco de válvulas")
        self.geometry("1280x800")
        self.minsize(1000, 680)

        base = tkfont.nametofont("TkDefaultFont")
        self.f_normal = base.copy(); self.f_normal.configure(size=12)
        self.f_negrita = base.copy(); self.f_negrita.configure(size=12, weight="bold")
        self.f_grande = base.copy(); self.f_grande.configure(size=22, weight="bold")
        self.f_ciclo = base.copy(); self.f_ciclo.configure(size=30, weight="bold")
        self.f_leyenda = base.copy(); self.f_leyenda.configure(size=18, weight="bold")

        self.cola = queue.Queue()
        self.conexion = Conexion(self.cola)
        self.estado = "SIN CONEXIÓN"
        self.ciclo = 0
        self.objetivo = 0
        self.ultimo_ciclo_registrado = None
        self.params = {}            # nombre -> (valor_texto, unidad)
        self.filas_param = {}       # nombre -> (StringVar, Label unidad)
        self.csv_ruta = None
        self.csv_archivo = None
        self.csv_writer = None
        self.nombre_csv = None      # nombre elegido por el operador para la siguiente prueba
        self.manual = False
        self.pwm_enviado = None
        self.pwm_pendiente = None
        self._ajustando_pwm = False

        self._construir()
        self._poner_estado("SIN CONEXIÓN")
        self.after(50, self._procesar_cola)
        self.protocol("WM_DELETE_WINDOW", self._salir)

    # =================================================================
    #  Construcción de la ventana
    # =================================================================
    def _construir(self):
        estilo = ttk.Style(self)
        estilo.configure("Grande.TButton", font=self.f_negrita, padding=(14, 12))
        estilo.configure("TLabelframe.Label", font=self.f_negrita)
        pad = {"padx": 8, "pady": 4}

        # --- Conexión ---
        fc = ttk.Frame(self)
        fc.pack(fill="x", **pad)
        ttk.Label(fc, text="IP:", font=self.f_normal).pack(side="left")
        self.var_ip = tk.StringVar(value=IP_DEFECTO)
        ttk.Entry(fc, textvariable=self.var_ip, width=15, font=self.f_normal).pack(side="left", padx=4)
        ttk.Label(fc, text="Puerto:", font=self.f_normal).pack(side="left", padx=(8, 0))
        self.var_puerto = tk.StringVar(value=str(PUERTO_DEFECTO))
        ttk.Entry(fc, textvariable=self.var_puerto, width=6, font=self.f_normal).pack(side="left", padx=4)
        self.btn_conectar = ttk.Button(fc, text="Conectar", style="Grande.TButton", command=self._conectar)
        self.btn_conectar.pack(side="left", padx=8)
        self.lbl_conexion = ttk.Label(fc, text="Desconectado", font=self.f_normal)
        self.lbl_conexion.pack(side="left")
        self.lbl_csv = ttk.Label(fc, text="", font=self.f_normal, foreground="#595959")
        self.lbl_csv.pack(side="right")

        cuerpo = ttk.Frame(self)
        cuerpo.pack(fill="both", expand=True)
        der = ttk.LabelFrame(cuerpo, text="Parámetros de la prueba")
        der.pack(side="right", fill="y", padx=8, pady=4)      # primero: reserva su ancho
        izq = ttk.Frame(cuerpo)
        izq.pack(side="left", fill="both", expand=True)

        # --- Estado y ciclo ---
        fe = ttk.Frame(izq)
        fe.pack(fill="x", **pad)
        self.lbl_estado = tk.Label(fe, text="", font=self.f_grande, fg="white", width=22, pady=12)
        self.lbl_estado.pack(side="left")
        fcic = ttk.Frame(fe)
        fcic.pack(side="left", padx=16)
        ttk.Label(fcic, text="Ciclo", font=self.f_normal).pack(anchor="w")
        self.lbl_ciclo = ttk.Label(fcic, text="0 / —", font=self.f_ciclo)
        self.lbl_ciclo.pack(anchor="w")
        self.barra = ttk.Progressbar(fcic, length=260, maximum=1)
        self.barra.pack(anchor="w", pady=2)

        # --- Indicadores ---
        fi = ttk.Frame(izq)
        fi.pack(fill="x", **pad)
        self.ind = {}
        for col, (clave, titulo) in enumerate([("spv", "Válvula"), ("stop", "Paro"),
                                                ("v", "Voltaje"), ("i", "Corriente"), ("t", "Temperatura")]):
            caja = ttk.Frame(fi)
            caja.grid(row=0, column=col, padx=6, sticky="w")
            ttk.Label(caja, text=titulo, font=self.f_normal).pack(anchor="w")
            lbl = tk.Label(caja, text="—", font=self.f_negrita, width=13, pady=6, bg="#E6E6E6")
            lbl.pack()
            self.ind[clave] = lbl

        # --- PWM de la válvula ---
        fpwm = ttk.LabelFrame(izq, text="PWM de la válvula (salida P1)")
        fpwm.pack(fill="x", **pad)
        self.escala_pwm = tk.Scale(fpwm, from_=1, to=100, orient="horizontal", resolution=1,
                                   length=380, width=34, sliderlength=46, showvalue=False,
                                   font=self.f_normal, command=self._pwm_movido, state="disabled")
        self.escala_pwm.pack(side="left", padx=(8, 4), pady=6)
        self.lbl_pwm = tk.Label(fpwm, text="— %", font=self.f_grande, width=6)
        self.lbl_pwm.pack(side="left")
        self.btn_manual = tk.Button(fpwm, text="Salida manual\nAPAGADA", font=self.f_negrita, width=14,
                                    bg="#E6E6E6", activebackground="#D0D0D0", relief="raised", bd=2,
                                    command=self._alternar_manual, state="disabled")
        self.btn_manual.pack(side="left", padx=8, pady=6, ipady=4)
        ttk.Label(fpwm, text="Solo en REPOSO. Se apaga\ncon el paro o al iniciar.",
                  font=self.f_normal, foreground="#595959").pack(side="left", padx=4)

        # --- Leyenda (oculta hasta que el Opta mande una) ---
        self.frm_leyenda = tk.Frame(izq, bg="#FFD24D", padx=12, pady=10)
        self.lbl_leyenda = tk.Label(self.frm_leyenda, text="", font=self.f_leyenda, bg="#FFD24D",
                                    wraplength=520, justify="left")
        self.lbl_leyenda.pack(side="left", fill="x", expand=True)
        ttk.Button(self.frm_leyenda, text="✔ Retirar leyenda", style="Grande.TButton",
                   command=lambda: self._comando("k")).pack(side="right")

        # --- Último aviso (falla / no listo / resultado) ---
        self.lbl_aviso = tk.Label(izq, text="", font=self.f_negrita, fg="#B00020", anchor="w",
                                  justify="left", wraplength=760)
        self.lbl_aviso.pack(fill="x", padx=12)

        # --- Botones de control ---
        fb = ttk.Frame(izq)
        fb.pack(fill="x", **pad)
        self.botones = []
        for texto, accion in [("▶ Iniciar / Reanudar", self._iniciar), ("❚❚ Pausa", lambda: self._comando("p")),
                              ("■ Detener", lambda: self._comando("s"))]:
            b = ttk.Button(fb, text=texto, style="Grande.TButton", command=accion)
            b.pack(side="left", padx=4)
            self.botones.append(b)
        b = ttk.Button(fb, text="Reanudar desde ciclo…", style="Grande.TButton", command=self._reanudar_desde)
        b.pack(side="left", padx=4)
        self.botones.append(b)
        b = ttk.Button(fb, text="Estado", style="Grande.TButton", command=lambda: self._comando("e"))
        b.pack(side="left", padx=4)
        self.botones.append(b)
        ttk.Label(izq, text="El paro de emergencia es solo el botón físico del tablero.",
                  foreground="#595959", font=self.f_normal).pack(anchor="w", padx=12)

        # --- Registro ---
        fr = ttk.LabelFrame(izq, text="Registro")
        fr.pack(fill="both", expand=True, **pad)
        barra_reg = ttk.Frame(fr)
        barra_reg.pack(fill="x")
        self.var_ver_d = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra_reg, text="Mostrar registro por ciclo (D)", variable=self.var_ver_d).pack(side="left")
        ttk.Button(barra_reg, text="Guardar registro…", command=self._guardar_log).pack(side="right", padx=4)
        self.txt = tk.Text(fr, font="TkFixedFont", wrap="none", state="disabled", height=8)
        sb = ttk.Scrollbar(fr, command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)

        # --- Parámetros ---
        self.frm_params = ttk.Frame(der)
        self.frm_params.pack(fill="both", expand=True, padx=6, pady=4)
        ttk.Label(self.frm_params, text="Conectar para leer los parámetros del Opta.",
                  font=self.f_normal, foreground="#595959").grid(row=0, column=0, columnspan=3)
        fp = ttk.Frame(der)
        fp.pack(fill="x", padx=6, pady=6)
        self.botones_param = []
        for texto, accion in [("Enviar al Opta", self._enviar_params), ("Leer del Opta", lambda: self._comando("params")),
                              ("Valores de fábrica", self._fabrica)]:
            b = ttk.Button(fp, text=texto, command=accion)
            b.pack(fill="x", pady=2)
            self.botones_param.append(b)
        fa = ttk.Frame(der)
        fa.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(fa, text="Guardar archivo…", command=self._guardar_params).pack(side="left", expand=True, fill="x")
        ttk.Button(fa, text="Cargar archivo…", command=self._cargar_params).pack(side="left", expand=True, fill="x")
        ttk.Label(der, text="Solo se aceptan en REPOSO.", font=self.f_normal,
                  foreground="#595959").pack(pady=(0, 6))

        self._habilitar_botones(False)

    # =================================================================
    #  Acciones
    # =================================================================
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
        self._comando("params")

    def _comando(self, c):
        self.conexion.enviar(c + "\n")

    def _reanudar_desde(self):
        sugerido = self.ultimo_ciclo_registrado or self.ciclo or 1
        n = simpledialog.askinteger("Reanudar", "Reanudar la prueba desde el ciclo:",
                                    initialvalue=sugerido, minvalue=1, parent=self)
        if not n:
            return
        anterior = self.csv_ruta.stem if self.csv_ruta else None
        if self._pedir_nombre(anterior):
            self._comando(f"reanudar {n}")

    def _iniciar(self):
        """En REPOSO pide el nombre del archivo de datos antes de iniciar; en PAUSA solo reanuda."""
        if self.estado == "REPOSO" and not self._pedir_nombre():
            return
        self._comando("i")

    def _pedir_nombre(self, sugerido=None):
        """Pregunta con qué nombre guardar el CSV de la prueba. Devuelve False si se cancela."""
        sugerido = sugerido or f"durabilidad_{datetime.now():%Y%m%d_%H%M%S}"
        while True:
            nombre = simpledialog.askstring("Guardar datos de la prueba",
                                            "¿Con qué nombre se guardan los datos de esta prueba?\n"
                                            "(se guardan en la carpeta logs/ como .csv)",
                                            initialvalue=sugerido, parent=self)
            if nombre is None:
                return False
            nombre = RE_NOMBRE_INVALIDO.sub("_", nombre).strip().strip(".")
            if nombre.lower().endswith(".csv"):
                nombre = nombre[:-4].strip()
            if not nombre:
                messagebox.showwarning("Nombre", "Escribir un nombre para el archivo.", parent=self)
                continue
            ruta = CARPETA_LOGS / f"{nombre}.csv"
            if ruta.exists() and not messagebox.askyesno(
                    "El archivo ya existe",
                    f"logs/{ruta.name} ya existe.\n\n¿Agregar los datos de esta prueba al final?\n"
                    "(No = elegir otro nombre)", parent=self):
                sugerido = nombre
                continue
            self.nombre_csv = nombre
            return True

    # ---------- PWM ----------
    def _pwm_movido(self, valor):
        v = int(float(valor))
        self.lbl_pwm.config(text=f"{v} %")
        if self._ajustando_pwm:            # el cambio vino del Opta, no del operador
            return
        if self.pwm_pendiente is None:
            self.after(ENVIO_PWM_MS, self._enviar_pwm)
        self.pwm_pendiente = v

    def _enviar_pwm(self):
        v, self.pwm_pendiente = self.pwm_pendiente, None
        if v is not None and v != self.pwm_enviado and self.conexion.activa:
            self._comando(f"pwm {v}")
            self.pwm_enviado = v

    def _alternar_manual(self):
        if not self.manual and self.estado != "REPOSO":
            messagebox.showinfo("Salida manual", "La salida manual solo se usa en REPOSO.", parent=self)
            return
        self._comando("manual 0" if self.manual else "manual 1")

    def _poner_pwm(self, valor):
        if valor is None:
            return
        v = int(round(valor))
        self.pwm_enviado = v
        if self.pwm_pendiente is not None:  # el operador lo está moviendo: no pelear con el deslizador
            return
        self._ajustando_pwm = True
        self.escala_pwm.set(v)
        self.lbl_pwm.config(text=f"{v} %")
        self.update_idletasks()
        self._ajustando_pwm = False

    def _poner_manual(self, on):
        self.manual = on
        self.btn_manual.config(text="Salida manual\nENCENDIDA" if on else "Salida manual\nAPAGADA",
                               bg="#2E8B57" if on else "#E6E6E6", fg="white" if on else "black",
                               activebackground="#277A4C" if on else "#D0D0D0",
                               relief="sunken" if on else "raised")

    def _habilitar_botones(self, si):
        for b in self.botones + self.botones_param:
            b.state(["!disabled"] if si else ["disabled"])
        self.escala_pwm.config(state="normal" if si else "disabled")
        self.btn_manual.config(state="normal" if si else "disabled")
        if not si:
            self._poner_manual(False)
            self.lbl_pwm.config(text="— %")

    def _enviar_params(self):
        if self.estado != "REPOSO":
            messagebox.showwarning("Parámetros", "Los parámetros solo se pueden cambiar en REPOSO.")
            return
        enviados = 0
        for nombre, (var, _) in self.filas_param.items():
            texto = var.get().strip().replace(",", ".")
            actual = self.params.get(nombre, ("", ""))[0]
            if numero(texto) is None:
                messagebox.showerror("Parámetros", f"Valor no válido para {nombre}: {texto!r}")
                return
            if actual == "" or numero(texto) != numero(actual):
                self._comando(f"set {nombre} {texto}")
                enviados += 1
        self._log(f"# {enviados} parámetro(s) enviados" if enviados else "# Sin cambios en los parámetros")

    def _fabrica(self):
        if messagebox.askyesno("Parámetros", "¿Regresar el Opta a los parámetros de fábrica?"):
            self._comando("defaults")

    def _guardar_params(self):
        if not self.filas_param:
            messagebox.showinfo("Parámetros", "Todavía no hay parámetros leídos del Opta.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".json",
                                            initialfile=f"parametros_{datetime.now():%Y%m%d_%H%M%S}.json",
                                            filetypes=[("JSON", "*.json")])
        if ruta:
            datos = {n: v.get().strip() for n, (v, _) in self.filas_param.items()}
            Path(ruta).write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")

    def _cargar_params(self):
        ruta = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not ruta:
            return
        try:
            datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            messagebox.showerror("Parámetros", f"No se pudo leer el archivo:\n{e}")
            return
        for nombre, valor in datos.items():
            if nombre not in self.filas_param:
                self._fila_param(nombre, "", "")
            self.filas_param[nombre][0].set(str(valor))
        self._log(f"# Parámetros cargados de {Path(ruta).name}: revisar y presionar 'Enviar al Opta'")

    def _guardar_log(self):
        ruta = filedialog.asksaveasfilename(defaultextension=".txt",
                                            initialfile=f"registro_{datetime.now():%Y%m%d_%H%M%S}.txt")
        if ruta:
            Path(ruta).write_text(self.txt.get("1.0", "end"), encoding="utf-8")

    def _salir(self):
        self._cerrar_csv()
        self.conexion.cerrar()
        self.destroy()

    # =================================================================
    #  CSV automático por prueba
    # =================================================================
    def _abrir_csv(self, tipo):
        self._cerrar_csv()
        CARPETA_LOGS.mkdir(exist_ok=True)
        # Nombre elegido al presionar Iniciar; si la prueba se inició con el botón B1, nombre automático
        nombre = self.nombre_csv or f"durabilidad_{datetime.now():%Y%m%d_%H%M%S}"
        self.nombre_csv = None
        self.csv_ruta = CARPETA_LOGS / f"{nombre}.csv"
        nuevo = not self.csv_ruta.exists()
        self.csv_archivo = open(self.csv_ruta, "a", newline="", encoding="utf-8")
        self.csv_writer = csv.writer(self.csv_archivo)
        if nuevo:
            self.csv_writer.writerow(["hora_pc", "tipo"] + COLUMNAS_D + ["detalle"])
        self._csv_fila("INICIO", detalle=f"prueba {tipo}")
        for nombre, (valor, unidad) in self.params.items():
            self._csv_fila("PARAM", detalle=f"{nombre}={valor} {unidad}")
        self.lbl_csv.config(text=f"Guardando en logs/{self.csv_ruta.name}")

    def _csv_fila(self, tipo, datos=None, detalle=""):
        if not self.csv_writer:
            return
        hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        datos = datos or [""] * len(COLUMNAS_D)
        self.csv_writer.writerow([hora, tipo] + list(datos) + [detalle])
        self.csv_archivo.flush()       # que no se pierda nada si se corta la energía

    def _cerrar_csv(self):
        if self.csv_archivo:
            self.csv_archivo.close()
        self.csv_archivo = self.csv_writer = None

    # =================================================================
    #  Recepción
    # =================================================================
    def _procesar_cola(self):
        while True:
            try:
                tipo, dato = self.cola.get_nowait()
            except queue.Empty:
                break
            if tipo == "linea":
                try:
                    self._interpretar(dato)
                except Exception as e:   # noqa: BLE001 - una línea rara no debe tumbar la interfaz
                    self._log(f"# Error al interpretar {dato!r}: {e}")
            elif tipo == "desconectado":
                self._log("# Desconectado")
                self.lbl_conexion.config(text="Desconectado")
                self.btn_conectar.config(text="Conectar")
                self._habilitar_botones(False)
                self._poner_estado("SIN CONEXIÓN")
                for lbl in self.ind.values():
                    lbl.config(text="—", bg="#E6E6E6", fg="black")
        self.after(50, self._procesar_cola)

    def _interpretar(self, linea):
        s = linea.strip()

        if s.startswith("M,"):                       # monitor 1 Hz: no se muestra en el registro
            p = s.split(",")
            if len(p) >= 8:
                if p[1] in ESTADOS and p[1] != self.estado:
                    self._poner_estado(p[1])
                self._poner_ciclo(int(p[2]) if p[2].isdigit() else self.ciclo)
                self._poner_medicion("v", numero(p[3]), "V", 2)
                self._poner_medicion("i", numero(p[4]), "mA", 0)
                self._poner_medicion("t", numero(p[5]), "°C", 1)
                self._poner_spv(p[6] == "1")
                self._poner_paro(p[7] == "1")
                if len(p) >= 10:
                    if (p[8] == "1") != self.manual:
                        self._poner_manual(p[8] == "1")
                    self._poner_pwm(numero(p[9]))
            return

        if s.startswith("MANUAL,"):
            self._poner_manual(s.split(",")[1][:1] == "1")
            self._log(linea)
            return

        if s.startswith("D,") or s.startswith("D0,"):
            p = s.split(",")
            datos = p[1:1 + len(COLUMNAS_D)]
            self._csv_fila("VERIFICACION" if p[0] == "D0" else "CICLO", datos)
            if p[0] == "D" and datos and datos[0].isdigit():
                self.ultimo_ciclo_registrado = int(datos[0])
            if self.var_ver_d.get():
                self._log(linea)
            return

        if not s.startswith("P,"):                  # los parámetros ya se ven en su panel
            self._log(linea)

        if s.startswith("P,"):
            p = s.split(",")
            if len(p) >= 4:
                nombre, valor, unidad = p[1], p[2], p[3]
                self.params[nombre] = (valor, unidad)
                if nombre not in self.filas_param:
                    self._fila_param(nombre, valor, unidad)
                else:
                    self.filas_param[nombre][0].set(self._limpio(valor))
                if nombre == "ciclos" and numero(valor):
                    self.objetivo = int(numero(valor))
                    self._poner_ciclo(self.ciclo)
                if nombre == "duty_on":
                    self._poner_pwm(numero(valor))
                    if self.csv_writer and self.estado != "REPOSO":
                        self._csv_fila("PWM", detalle=f"duty_on={self._limpio(valor)} %")
            return

        if s.startswith("RESULTADO,"):
            p = s.split(",", 4)
            if len(p) >= 5:
                self._csv_fila("RESULTADO", [p[2]] + [""] * (len(COLUMNAS_D) - 1), f"{p[1]}: {p[4]}")
                color = "#2E8B57" if p[1] == "COMPLETADA" else "#B00020"
                self.lbl_aviso.config(text=f"Resultado: {p[1]} – {p[2]} de {p[3]} ciclos – {p[4]}", fg=color)
                self._cerrar_csv()
                if self.csv_ruta:
                    self.lbl_csv.config(text=f"Guardado: logs/{self.csv_ruta.name}")
            return

        m = RE_PRUEBA.search(s)
        if m:
            self._abrir_csv(m.group(1))
            self.lbl_aviso.config(text="")
            return

        m = RE_ESTADO.search(s)
        if m:
            self._poner_estado(m.group(1))
            self._csv_fila("ESTADO", detalle=m.group(1) + (f" ({m.group(2)})" if m.group(2) else ""))
            return
        m = RE_ESTADO_INFO.search(s)
        if m:
            self._poner_estado(m.group(1))
            return
        m = RE_CICLO_INFO.search(linea)
        if m:
            self.objetivo = int(m.group(2))
            self._poner_ciclo(int(m.group(1)))
            return

        m = RE_LEYENDA.search(s)
        if m:
            self.lbl_leyenda.config(text=m.group(1))
            if not self.frm_leyenda.winfo_ismapped():
                self.frm_leyenda.pack(fill="x", padx=8, pady=4, before=self.lbl_aviso)
            return

        m = RE_AVISO.search(s)
        if m:
            self.lbl_aviso.config(text=f"{m.group(1)}: {m.group(2)}",
                                  fg="#B00020" if m.group(1) == "FALLA" else "#8A6D00")
            if m.group(1) == "FALLA":
                self._csv_fila("FALLA", detalle=m.group(2))

    # =================================================================
    #  Indicadores
    # =================================================================
    @staticmethod
    def _limpio(valor):
        v = numero(valor)
        if v is None:
            return valor
        return str(int(v)) if v == int(v) else f"{v:g}"

    def _fila_param(self, nombre, valor, unidad):
        if not self.filas_param:
            for w in self.frm_params.winfo_children():
                w.destroy()
        fila = len(self.filas_param)
        ttk.Label(self.frm_params, text=nombre, font=self.f_normal).grid(row=fila, column=0, sticky="w", pady=1)
        var = tk.StringVar(value=self._limpio(valor))
        ttk.Entry(self.frm_params, textvariable=var, width=10, font=self.f_normal,
                  justify="right").grid(row=fila, column=1, padx=4, pady=1)
        lbl = ttk.Label(self.frm_params, text=unidad, font=self.f_normal, foreground="#595959")
        lbl.grid(row=fila, column=2, sticky="w")
        self.filas_param[nombre] = (var, lbl)

    def _poner_estado(self, estado):
        self.estado = estado
        self.lbl_estado.config(text=estado, bg=COLORES_ESTADO.get(estado, "#7F7F7F"))
        if estado not in ESTADOS_LEYENDA and self.frm_leyenda.winfo_ismapped():
            self.frm_leyenda.pack_forget()

    def _poner_ciclo(self, n):
        self.ciclo = n
        obj = self.objetivo or 0
        self.lbl_ciclo.config(text=f"{n} / {obj if obj else '—'}")
        self.barra.config(maximum=max(obj, 1), value=min(n, max(obj, 1)))

    def _poner_medicion(self, clave, valor, unidad, dec):
        texto = "—" if valor is None else f"{valor:.{dec}f} {unidad}"
        self.ind[clave].config(text=texto, bg="#E6E6E6", fg="black")

    def _poner_spv(self, presente):
        self.ind["spv"].config(text="PRESENTE" if presente else "sin válvula",
                               bg="#2E8B57" if presente else "#E6E6E6",
                               fg="white" if presente else "black")

    def _poner_paro(self, presionado):
        self.ind["stop"].config(text="PRESIONADO" if presionado else "libre",
                                bg="#E03C38" if presionado else "#E6E6E6",
                                fg="white" if presionado else "black")

    def _log(self, texto):
        self.txt.config(state="normal")
        self.txt.insert("end", texto + "\n")
        if int(self.txt.index("end-1c").split(".")[0]) > 5000:   # limita el tamaño
            self.txt.delete("1.0", "1000.0")
        self.txt.see("end")
        self.txt.config(state="disabled")


if __name__ == "__main__":
    Durabilidad().mainloop()
