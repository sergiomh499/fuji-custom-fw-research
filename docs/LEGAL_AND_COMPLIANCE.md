# Marco Legal y Protocolo de Cumplimiento Normativo (España y Unión Europea)

Este documento detalla la fundamentación jurídica bajo el ordenamiento jurídico español y comunitario que ampara la investigación, ingeniería inversa y desarrollo de herramientas en este repositorio, así como la lista de control de legalidad paso a paso (*Compliance Checklist*).

---

## 1. Fundamentación Jurídica en España (Ley de Propiedad Intelectual)

El desarrollo e investigación de software en España se rige por el **Real Decreto Legislativo 1/1996, de 12 de abril**, por el que se aprueba el texto refundido de la **Ley de Propiedad Intelectual (LPI)**, transposición directa de la **Directiva Europea 2009/24/CE**:

### A. Derecho a Observar, Estudiar y Verificar el Software (Art. 100.3 LPI)
> *"La persona que tenga derecho a utilizar el programa de ordenador podrá, sin autorización del titular, observar, estudiar o verificar su funcionamiento, con el fin de determinar las ideas y principios implícitos en cualquier elemento del programa, siempre que lo haga con ocasión de la realización de cualquiera de las operaciones de carga, visualización, ejecución, transmisión o almacenamiento del programa que tiene derecho a hacer."*

**Aplicación:** El usuario legítimo que adquiere una cámara Fujifilm tiene derecho legal a inspeccionar el software y las funciones de su dispositivo.

### B. Descompilación para Interoperabilidad (Art. 100.4 LPI y Art. 6 Directiva 2009/24/CE)
> *"No será necesaria la autorización del titular cuando la reproducción del código y la traducción de su forma [...] sea indispensable para obtener la información necesaria para la interoperabilidad de un programa de ordenador creado de forma independiente con otros programas [...]."*

**Aplicación:** La creación de software de terceros para comunicarse con los menús de la cámara, los motores de la montura X o las estructuras internas de recetas persigue una finalidad de interoperabilidad técnica amparada por la ley.

### C. Nulidad de Cláusulas Contractuales Restrictivas (Art. 100.5 LPI)
> *"Las disposiciones contenidas en los apartados 2, 3 y 4 del presente artículo serán nulas y sin efecto cuando se pacte lo contrario."*

**Aplicación:** Las cláusulas estándar de los contratos de licencia (EULA) de Fujifilm que declaran *"prohibida la descompilación o ingeniería inversa"* son **nulas de pleno derecho** en España y la Unión Europea cuando la actividad se realiza con fines de estudio o interoperabilidad.

### D. Jurisprudencia del Tribunal de Justicia de la Unión Europea (TJUE)
En la **Sentencia del TJUE de 2 de mayo de 2012 (Asunto C-406/10, *SAS Institute Inc. c. World Programming Ltd*)**, el tribunal sentenció de forma vinculante que:
1. Las funcionalidades de un programa de ordenador, sus interfaces y los formatos de archivo **no constituyen una forma de expresión protegida por los derechos de autor**.
2. Quien tiene derecho a usar un programa tiene derecho a estudiarlo para reproducir sus efectos con un código independiente.

---

## 2. Código Penal Español (LO 10/1995)

- **Art. 270 del Código Penal (Propiedad Intelectual):** Exige expresamente *"ánimo de obtener un beneficio económico directo o indirecto y en perjuicio de tercero"* mediante la reproducción o distribución ilegítima. El desarrollo de herramientas open-source de análisis sin redistribuir el binario propietario de Fujifilm no encaja en el tipo penal.
- **Art. 197 bis y 264 del Código Penal (Delitos Informáticos):** Se refieren a intrusiones informáticas no autorizadas sobre sistemas o datos ajenos. La manipulación del propio hardware adquirido legítimamente por el propietario está fuera del ámbito penal.

---

## 3. Lista de Control de Legalidad Paso a Paso (Step-by-Step Checklist)

Cualquier colaborador o agente automatizado debe verificar la legalidad de cada fase:

| Paso | Acción Técnica | ¿Es Legal? | Requisitos Obligatorios |
|---|---|---|---|
| **1** | Descargar el firmware oficial (`FWUPxxxx.DAT` / `FPUPDATE.DAT`) | **SÍ (100% Legal)** | Debe descargarse directamente de los servidores públicos de Fujifilm en el equipo local del usuario. |
| **2** | Desempaquetar y desobfuscar (`~byte`) en el PC local | **SÍ (100% Legal)** | Amparado por Art. 100.3 LPI (estudio del funcionamiento). Debe realizarse en local. |
| **3** | Mapear memoria, identificar tablas (menús, simulaciones, SQLite) | **SÍ (100% Legal)** | Las direcciones de memoria (offsets) e identificadores son hechos funcionales, no propiedad intelectual protegible (TJUE C-406/10). |
| **4** | Escribir herramientas propias (Python/C/ASM) | **SÍ (100% Legal)** | Es código 100% original con derechos de autor del propio creador del repositorio. |
| **5** | Generar parches diferenciales (`.diff`, offsets de inyección) | **SÍ (100% Legal)** | Los parches contienen únicamente código nuevo propio y deltas matemáticos de checksum. |
| **6** | Subir el código a GitHub | **SÍ (100% Legal)** | **REGLA CRÍTICA:** Solo scripts, tests y documentación. **NUNCA subir `.DAT`, `.bin` ni volcados de ROM**. |
| **7** | Flashear firmware modificado en tu cámara física | **SÍ (100% Legal)** | Modificación de hardware propio. El riesgo técnico de fallo (brick) lo asume el propietario. |

---

## 4. Líneas Rojas: Acciones Estrictamente Prohibidas en este Repositorio

1. **NO redistribuir binarios de Fujifilm:** Nunca hacer commit ni distribuir archivos `.DAT`, `.bin`, volcados de memoria NAND/SPI o código objeto propietario de Fujifilm Corporation.
2. **NO comercializar:** No vender el software ni cobrar por parches de firmware para evitar cualquier controversia respecto al Art. 270 del Código Penal.
3. **NO suplantar ni eludir controles de acceso de pago:** No eludir sistemas de pago ni funciones bajo licencia de terceros (las cámaras analizadas no contienen DRM de pago).
4. **Cumplimiento estricto del `.gitignore`:** Mantener siempre bloqueados todos los binarios y artefactos de memoria.
