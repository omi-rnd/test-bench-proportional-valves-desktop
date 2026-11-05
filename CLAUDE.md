# Banco de pruebas de válvulas proporcionales – Interfaz de escritorio

Aplicación de escritorio para operar el banco de pruebas: se conecta al PLC Arduino Opta
por Ethernet, controla la prueba (Inicio/Pausa/Stop) y registra los datos.
Idioma de trabajo: **español** (código, comentarios e interfaz).

El firmware del Opta vive en el repo hermano **`test-bench-proportional-valves-control`**.
Este repo solo contiene el software de la PC.

## Plataformas

Debe funcionar igual en **Windows, Linux, Raspberry Pi OS y macOS**.

- Python 3 + **Tkinter** (librería estándar). Nada específico de un sistema operativo:
  rutas con `os.path`/`pathlib`, fuentes genéricas de Tk (`TkFixedFont`, `TkDefaultFont`),
  sin llamadas a `cmd`, PowerShell ni rutas tipo `C:\`.
- Dependencias en `requirements.txt` (hoy solo librería estándar). Cualquier paquete nuevo
  se agrega ahí y debe tener soporte en las cuatro plataformas (incluida ARM de Raspberry Pi).
- tkinter: incluido en Windows y en el instalador de python.org para macOS;
  `sudo apt install python3-tk` en Debian/Ubuntu/Raspberry Pi OS; `brew install python-tk` en macOS con Homebrew.
- Equipo destino del banco: **Raspberry Pi 5 8 GB** con pantalla táctil EDATEC 10.1"
  (1280×800). La interfaz debe verse bien a esa resolución y usarse con el dedo
  (botones grandes).

## Estructura

```
main.py               Script principal: interfaz gráfica Tkinter (conexión, Inicio/Pausa/Stop,
                      estado, sensor, conteo, registro y exportación a CSV)
main_terminal_tcp.py  Terminal TCP en consola (equivalente al Serial Monitor por Ethernet)
requirements.txt      Dependencias (hoy ninguna fuera de la librería estándar)
```

Los scripts principales van en la **raíz** del repo. Se ejecutan con `python main.py`.

## Comunicación con el Opta

- TCP, **IP 192.168.10.2, puerto 23** (la PC con IP fija 192.168.10.1/24 en conexión directa).
- Protocolo de texto línea por línea, el mismo que el monitor serie del sketch
  `arduino/opta_sensor_ethernet` del repo de control. **Si cambia el formato en el sketch,
  hay que actualizar las expresiones regulares de `main.py`, y viceversa.**
- Comandos (una letra + `\n`): `i` inicio/reanudar, `p` pausa, `s` stop, `e` estadísticas,
  `r` reiniciar, `c` modo CSV/texto, `h` ayuda. El paro de emergencia es solo físico.
- Líneas que interpreta la interfaz:
  - `== DETENIDO | CORRIENDO | PAUSA | PARO DE EMERGENCIA  (motivo)` → cambio de estado
  - `Estado de la prueba: <ESTADO>` → estado al conectar
  - `>> DETECTA  #n` / `<< libre    #n   duracion: X ms` → eventos del sensor
  - `Sensor: DETECTA | libre` → estado del sensor al conectar
- La interfaz trabaja con el modo **texto** del Opta; en modo CSV (`c`) los indicadores no se
  actualizan.
- Plan a futuro: migrar a **Modbus TCP** (`pymodbus`) cuando el Opta tenga servidor Modbus.

## Pendientes

- [ ] Probar la interfaz en la Raspberry Pi 5 con la pantalla EDATEC y en macOS.
- [ ] Agregar datos de la válvula cuando estén en el Opta: PWM, flujo y temperatura de la bobina.
- [ ] Curva PWM → flujo: gráfica en la interfaz y exportación a CSV.
- [ ] Escalar a **5 válvulas**: la interfaz debe mostrar N canales (configurables), no uno fijo.
