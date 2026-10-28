# Análisis de Riesgos de Brickeo, Prevención y Procedimientos de Recuperación (Debricking)

Este documento técnico detalla los niveles de riesgo de fallo catastrófico (*brickeo*) en las cámaras **Fujifilm X-T10** y **FinePix X10**, las estrategias de diseño para prevenirlo y los procedimientos de recuperación tanto por software como por hardware externo.

---

## 1. Cadena de Arranque (*Boot Chain*) de Fujifilm

Para entender por qué se produce un brick y cómo solucionarlo, es necesario comprender la secuencia de inicialización del hardware:

```
[Encendido]
    │
    ▼
[Etapa 0: SoC Boot ROM] ────────── Hardwired dentro del procesador EXR / Milbeaut.
    │                               Inmutable, no se puede borrar ni corromper.
    ▼
[Etapa 1: Flash Bootloader / IPL] ─ Primeros 64 KB de la memoria Flash en la placa base.
    │                               Inicializa el controlador SDRAM y lee botones.
    ├── Si pulsas DISP/BACK ──────► Modo Recuperación / Firmware Update (SD Card).
    │
    ▼ Si arranque normal
[Etapa 2: RTOS Kernel] ──────────── Carga el sistema operativo (μITRON / Tron) en RAM.
    │
    ▼
[Etapa 3: Tareas de Usuario] ────── Menús OSD, GUI, SQLite, DSP de captura, Lentes.
```

---

## 2. Clasificación de Niveles de Brickeo

| Nivel | Tipo | Causa Técnica | Síntomas | Nivel de Riesgo | Método de Recuperación |
|---|---|---|---|---|---|
| **Nivel 1** | **Soft Brick** (Cuelgue de Tarea) | *Kernel panic* o *null pointer* en una función secundaria inyectada. | La cámara se congela al presionar un botón específico o entrar a un menú concreto. | **Bajo** | Retirar la batería. La cámara reinicia limpia porque la Flash no está dañada. |
| **Nivel 2** | **Semi-Brick** (Arranque Bloqueado) | Bucle infinito o corrupción de RAM en el inicio del RTOS (Etapa 2). | El LED parpadea o queda encendido, pero la pantalla no muestra imagen ni responde. | **Medio** | **Recuperación por Software (SD):** El Bootloader (Etapa 1) sigue vivo. Encender manteniendo `DISP/BACK` para reflashear firmware oficial. |
| **Nivel 3** | **Hard Brick** (Muerte Total) | Corrupción del sector de arranque (Etapa 1) o corte eléctrico a mitad del flasheo. | No enciende ningún LED, pantalla totalmente apagada, no responde a ninguna combinación. | **Crítico** | **Recuperación por Hardware:** Requiere programador externo (CH341A / SPI) o consola UART. |

---

## 3. Estrategias de Prevención (Diseño Defensivo de Código)

Para garantizar que un error en el código **nunca** escale a Nivel 3 (*Hard Brick*):

### Regla 1: Trampolín en Menú Manual Seguro (*Cold Hook*) {#cold-hooking}
- **Nunca tocar el arranque temprano (*early boot*):** No colocar ganchos ni instrucciones de salto en los vectores de reset (`0x00000000`), ni en las rutinas de inicialización de memoria SDRAM.
- **Inyectar solo en menús manuales secundarios:** Colocar el salto de ejecución en funciones que requieran interacción expresa del usuario (ejemplo: el submenú de *Impresión Instax*, *Notas de voz* o la pantalla de *Propiedades de foto*).
- **Ventaja de seguridad:** Si el payload contiene un error fatal de memoria, la cámara se reiniciará con normalidad al encenderla, permitiendo usarla o reflashearla sin problemas porque el usuario no entra en ese submenú.

### Regla 2: Inversión Atómica de Checksum
- Antes de escribir cualquier archivo en la tarjeta SD, el script `tools/fuji_fw.py` recalcula el checksum matemático exacto:
  $$\Delta = \sum \text{Payload}_{\text{nuevo}} - \sum \text{Payload}_{\text{original}}$$
  $$\text{Checksum}_{\text{nuevo}} = (\text{Checksum}_{\text{original}} - \Delta) \pmod{2^{32}}$$
- Si el checksum no coincide exactamente con el byte sum, el propio bootloader de la cámara rechazará el archivo con el mensaje `"FIRMWARE CORRUPTED"`, evitando que se inicie un flasheo defectuoso.

### Regla 3: Verificación de Batería y Tarjeta
- Usar siempre una batería original cargada al 100%. Un corte de energía durante la escritura de la memoria Flash es la causa número uno de *Hard Brick*.
- Tarjeta SD de calidad formateada previamente en la propia cámara en formato FAT16 / FAT32.

---

## 4. Procedimientos de Desbrickeo (*Debricking*)

### Procedimiento A: Rescate por Software (Niveles 1 y 2)

Si la cámara se congela o no muestra menús tras intentar cargar un mod:

1. Extraer la batería durante 30 segundos para purgar toda la memoria volátil RAM y condensadores de la placa base.
2. En el ordenador, preparar una tarjeta SD limpia formateada en FAT32.
3. Descargar el firmware original de fábrica sin modificar:
   ```bash
   # Para X-T10:
   python3 tools/fuji_fw.py download xt10
   # Copiar FWUP0007.DAT a la raíz de la tarjeta SD

   # Para X10:
   python3 tools/fuji_fw.py download x10
   # Copiar FPUPDATE.DAT a la raíz de la tarjeta SD
   ```
4. Insertar la tarjeta y una batería con carga máxima en la cámara.
5. Mantener presionado firmemente el botón **`DISP/BACK`** y encender la palanca/dial de encendido.
6. La cámara saltará directamente al bootloader de fábrica (Etapa 1), ignorando el kernel dañado, y mostrará la pantalla de actualización oficial:
   `"ACTUALIZAR FIRMWARE? SI / NO"`.
7. Confirmar y esperar a que complete el proceso (aprox. 2 a 4 minutos).

---

### Procedimiento B: Rescate por Hardware Externo (Nivel 3 / Hard Brick)

Si el bootloader interno quedó dañado o el flasheo se interrumpió a mitad de escritura, la cámara no puede arrancar por sí misma. La recuperación se realiza reescribiendo la memoria Flash desde el exterior:

```
[PC con Linux]
       │
  (USB)▼
[Programador SPI: CH341A / Raspberry Pi]
       │
       │ (Cables DuPont / Pinza SOIC-8)
       ▼
[Pines Flash de la Placa Madre de la Cámara]
 (VCC 3.3V, GND, CLK, CS, MISO, MOSI)
```

#### Material Necesario:
1. **Programador SPI de 3.3V:** Dispositivo USB económico como el **CH341A** (con selector a 3.3V, ¡cuidado con modelos configurados a 5V!), una **Raspberry Pi** o un **Bus Pirate**.
2. **Sonda de conexión:** Pinza de prueba SOIC-8 (Pomona 5250) o micro-sondas de contacto para puntos de test (Test Pads).
3. **Software:** Herramienta open-source `flashrom` en Linux:
   ```bash
   sudo pacman -S flashrom
   ```

#### Paso a Paso de Desbrickeo SPI:
1. **Desmontaje y aislamiento:**
   - Retirar la batería y la lente. Desmontar la carcasa trasera y delantera siguiendo el manual de servicio para acceder a la placa base (*mainboard*).
   - Localizar el chip de memoria Flash (generalmente un circuito integrado SPI de 8 o 16 pines, fabricante Winbond, Macronix o Spansion cerca del procesador EXR).
2. **Conexión del programador (sin encender la cámara):**
   - Conectar los 6 pines SPI:
     - `VCC` (3.3V) -> Pin de alimentación del chip.
     - `GND` -> Masa de la placa.
     - `CS` (Chip Select) -> Pin de habilitación.
     - `CLK` (Clock) -> Reloj SPI.
     - `MOSI` (Master Out) -> Entrada de datos del chip.
     - `MISO` (Master In) -> Salida de datos del chip.
3. **Detección del chip en Linux:**
   ```bash
   flashrom -p ch341a_spi
   ```
   *Debe responder identificando el modelo exacto (ej. `Found Winbond flash chip "W25Q64.V"`).*
4. **Copia de seguridad del chip dañado:**
   ```bash
   flashrom -p ch341a_spi -r backup_bricked.bin
   ```
5. **Flasheo del volcado limpio oficial:**
   ```bash
   flashrom -p ch341a_spi -w flash_image_oficial.bin
   ```
6. **Verificación:** `flashrom` lee automáticamente tras escribir para verificar la coincidencia byte por byte (`VERIFIED`).
7. Retirar la pinza y volver a montar la cámara. El bootloader vuelve a estar íntegro.

---

### Procedimiento C: Diagnóstico por Puerto Serie UART

En la placa madre existen puntos de prueba marcados como `TX`, `RX` y `GND` que operan a niveles lógicos de 3.3V/1.8V:
- Conectando un cable USB-TTL (FTDI / CP2102) a 115200 baudios:
  ```bash
  picocom -b 115200 /dev/ttyUSB0
  ```
- Al encender la cámara, el bootloader imprime el registro de errores, la causa exacta del bloqueo (ej. *Data Abort Exception* con dirección de memoria) y permite confirmar si la CPU sigue respondiendo.

---

## PTP RAM Recovery {#ptp-ram-recovery}

DRAM used by the PTP transport is **100% volatile**. A hung PTP execution clears immediately on power-cycle: pull the battery for 30 s, then re-insert and reboot. No flash is written during PTP RAM operations, so the 0% brick risk applies. See Procedimiento A.

## Firmware-Level Recovery {#firmware-level-recovery}

For firmware repacking/patching failures: use the DISP/BACK forced-update path (Procedimiento A) and increment the firmware version so the bootloader accepts the reflash. See Procedimiento A / B.

## Level 3 Hard Brick Recovery {#level-3-hard-brick--recovery}

For hardware-level bricks: external SPI flash with Pomona 5250 clip + CH341A programmer running `flashrom`. See Procedimiento B.

---

## Hardware Telemetry & Level 3 Recovery {#hardware-telemetry}

For physical UART telemetry tapping (3.3 V LVCMOS, 115200 8N1, TP_TX/TP_RX/GND) and in-circuit SPI flash dumping/debricking (Pomona 5250 + CH341A + flashrom), see [`docs/HARDWARE_TELEMETRY_AND_RECOVERY.md`](HARDWARE_TELEMETRY_AND_RECOVERY.md).

Mitigation anchors (stable):
- Volatile / PTP RAM: `#ptp-ram-recovery`
- Firmware repacking / patching: `#firmware-level-recovery`
- Hardware flashing (Level 3 Hard Brick): `#level-3-hard-brick--recovery`
