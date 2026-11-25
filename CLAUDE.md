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
durabilidad.py        Interfaz de la prueba de durabilidad (sketch arduino/opta_durabilidad):
                      estados, leyendas, parámetros (JSON), monitor y CSV automático en logs/
requirements.txt      Dependencias (hoy ninguna fuera de la librería estándar)
README.md             Documentación para personas (instalación, conexión y uso)
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

### Protocolo de `durabilidad.py` (sketch `arduino/opta_durabilidad`)

Cada interfaz habla con su sketch: `main.py` ↔ `opta_sensor_ethernet`, `durabilidad.py` ↔
`opta_durabilidad`. Ambas usan la clase `Conexion` de `main.py`.
- Comandos: `i`, `p`, `s`, `k` (retirar leyenda), `reanudar N`, `set <param> <valor>`, `params`,
  `defaults`, `e`. Los parámetros solo se aceptan en REPOSO, excepto `pwm N` (duty_on, en
  cualquier estado; lo manda el deslizador, máximo uno cada 150 ms) y `manual 1|0` (solo REPOSO).
- Líneas: `== <ESTADO>  (detalle)`, `!! LEYENDA: <texto>  -> ...`, `!! FALLA: ...`, `!! NO LISTO: ...`,
  `RESULTADO,<tipo>,<ciclos>,<objetivo>,<causa>`, `P,param,valor,unidad`,
  `M,estado,ciclo,v,i,t,spv,stop,manual,duty_on` (1 Hz, no se muestra en el registro), `MANUAL,<1|0>`,
  `D,ciclo,v_on,i_on,i_on_min,i_on_max,v_off,i_off,t` y `D0,...` (verificación inicial).
- Estados: REPOSO, VERIFICACION, FALLA DE VERIFICACION, NO LISTO, PURGA, AJUSTE DE PRESION,
  CORRIENDO, PAUSA, CIERRE NEUMATICO.
- El Opta no guarda nada: la PC guarda el CSV de cada prueba y los parámetros en JSON. Al presionar
  Iniciar (o "Reanudar desde ciclo…") se pide el nombre del archivo (`logs/<nombre>.csv`); si ya
  existe se agrega al final. Una fila por línea D / falla / resultado / cambio de PWM, con `flush`.
  Si la prueba se inicia con el botón B1 del tablero, el nombre es automático (`durabilidad_<fecha>`).
  Tras un corte de energía se reanuda con "Reanudar desde ciclo…" (último ciclo D registrado).

## Pendientes

- [ ] Probar la interfaz en la Raspberry Pi 5 con la pantalla EDATEC y en macOS.
- [ ] Agregar datos de la válvula cuando estén en el Opta: PWM, flujo y temperatura de la bobina.
- [ ] Curva PWM → flujo: gráfica en la interfaz y exportación a CSV.
- [x] Pantalla para la **prueba de durabilidad**: `durabilidad.py` (probada contra un Opta simulado).
- [ ] Probar `durabilidad.py` con el Opta real y en la Raspberry Pi 5 (pantalla 1280×800).
- [ ] Escalar a **5 válvulas**: la interfaz debe mostrar N canales (configurables), no uno fijo.
