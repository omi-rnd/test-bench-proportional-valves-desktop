# Banco de pruebas de válvulas proporcionales – Interfaz de escritorio

Aplicación de escritorio para operar el banco de pruebas: se conecta al PLC Arduino Opta por
Ethernet, controla la prueba (Inicio / Pausa / Stop) y registra los datos.

Funciona en **Windows, Linux, Raspberry Pi OS y macOS**.

El firmware del Opta está en el repo
**[test-bench-proportional-valves-control](../test-bench-proportional-valves-control)**
(sketch `arduino/opta_sensor_ethernet`).

## Requisitos

- **Python 3.8 o más reciente.**
- **Tkinter** (viene con Python en la mayoría de los casos):

| Sistema | Tkinter |
|---|---|
| Windows | Incluido con el instalador de python.org |
| macOS | Incluido con el instalador de python.org; con Homebrew: `brew install python-tk` |
| Raspberry Pi OS / Debian / Ubuntu | `sudo apt install python3-tk` |

- No hay paquetes de pip por ahora; `requirements.txt` está listo para cuando se agreguen.

## Instalación

```bash
git clone <url-del-repo> test-bench-proportional-valves-desktop
cd test-bench-proportional-valves-desktop
python -m venv venv
```

Activar el entorno virtual:

- Windows: `venv\Scripts\activate`
- Linux / macOS / Raspberry Pi: `source venv/bin/activate`

```bash
pip install -r requirements.txt
```

## Conexión con el Opta

1. Conectar un cable de red directo entre la PC y el Opta.
2. Poner a la PC una IP fija: **192.168.10.1**, máscara **255.255.255.0**.
   - Windows: Configuración → Red → Ethernet → Editar asignación de IP → Manual.
   - Linux / Raspberry Pi: `sudo ip addr add 192.168.10.1/24 dev eth0`
     (revisar el nombre de la interfaz con `ip a`).
   - macOS: Ajustes del Sistema → Red → Ethernet → Detalles → TCP/IP → Manualmente.
3. Comprobar: `ping 192.168.10.2`.

El Opta debe tener cargado el sketch `opta_sensor_ethernet` (IP 192.168.10.2, puerto 23).

## Uso

### Interfaz gráfica

```bash
python main.py
```

1. Revisar IP (`192.168.10.2`) y puerto (`23`) y presionar **Conectar**.
2. Usar **Inicio**, **Pausa** y **Stop** para controlar la prueba. **Estadísticas** y
   **Reiniciar** consultan o borran los datos del Opta.
3. La pantalla muestra:
   - el estado de la prueba (gris = detenido, verde = corriendo, ámbar = pausa,
     rojo = paro de emergencia);
   - si el sensor detecta, el número de detecciones y la duración de la última;
   - el registro completo, igual que el monitor serie.
4. **Guardar registro…** guarda el texto completo; **Guardar eventos CSV…** guarda una fila por
   evento con la hora de la PC:

```
hora_pc,evento,numero,duracion_ms
2026-11-05 10:15:02.123,ESTADO CORRIENDO,,
2026-11-05 10:15:04.560,DETECTA,1,
2026-11-05 10:15:05.750,libre,1,1190.0
```

El **paro de emergencia es solo el botón físico** del tablero; la interfaz únicamente muestra
su estado.

### Prueba de durabilidad

Para el sketch `opta_durabilidad` (ciclos ON/OFF de una válvula en un slot):

```bash
python durabilidad.py
```

1. **Conectar**: la interfaz lee los parámetros del Opta y los muestra a la derecha.
2. Ajustar los parámetros y presionar **Enviar al Opta** (solo en REPOSO). **Guardar archivo…** /
   **Cargar archivo…** los guardan en JSON: el Opta vuelve a los valores de fábrica al reiniciarse.
3. **PWM de la válvula**: el deslizador fija el ciclo de trabajo en ON (1–100 %); si la válvula
   está encendida el cambio se aplica al momento. **Salida manual** (solo en REPOSO) deja P1
   encendida fija para probar la salida, por ejemplo con un LED; se apaga sola con el paro o al
   iniciar la prueba.
4. **Iniciar**: pide el **nombre del archivo** donde se guardarán los datos; después el Opta
   verifica, espera la válvula, purga y muestra la leyenda
   *Ajuste presión al valor deseado*; al terminar de ajustar, **Retirar leyenda**.
5. Durante la prueba se ven el ciclo, la presencia de válvula, el paro y V / I / T
   ("—" = medición desactivada). Al terminar o fallar aparece *Cierre suministro neumático*.
6. Los datos se guardan en `logs/<nombre>.csv` (una fila por ciclo registrado, fallas, cambios de
   PWM y resultado). Si el nombre ya existe, se agregan al final. Si se cortó la energía:
   **Reanudar desde ciclo…** (pide el ciclo y el nombre; sugiere el del archivo anterior).

### Terminal en consola

Para ver los mensajes del Opta sin interfaz gráfica:

```bash
python main_terminal_tcp.py                  # usa 192.168.10.2:23
python main_terminal_tcp.py 192.168.10.2 23
```

Escribir un comando (`i`, `p`, `s`, `e`, `r`, `c`, `h`) y presionar Enter. `Ctrl+C` para salir.

## Estructura

```
main.py               Interfaz gráfica (Tkinter)
main_terminal_tcp.py  Terminal TCP en consola
durabilidad.py        Interfaz de la prueba de durabilidad
requirements.txt      Dependencias de Python
```

## Problemas comunes

| Síntoma | Qué revisar |
|---|---|
| "No se pudo conectar" | Cable de red, IP fija de la PC y `ping 192.168.10.2`. Que el Opta tenga el sketch `opta_sensor_ethernet`. |
| Conecta pero no aparece nada | Presionar Inicio o mandar `h`; algunas versiones registran la conexión hasta recibir el primer dato. |
| Los indicadores no se actualizan | El Opta está en modo CSV; mandar `c` para volver a modo texto. |
| `No module named tkinter` | Instalar Tkinter según la tabla de requisitos. |
