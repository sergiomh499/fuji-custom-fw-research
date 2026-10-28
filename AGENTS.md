# AGENTS.md - Protocolo y Directrices para Agentes de IA

Este archivo define las restricciones operativas, verificaciones de seguridad y controles legales obligatorios que **TODO agente de IA o proceso automatizado DEBE comprobar en todo momento** antes de realizar o sugerir cualquier cambio en este repositorio.

---

## 1. Regla Suprema de Cumplimiento Legal (España / UE)

Todo agente que interactúe con este repositorio debe garantizar el estricto cumplimiento del marco legal español (**Real Decreto Legislativo 1/1996 - Ley de Propiedad Intelectual**, Arts. 100.3, 100.4, 100.5) y comunitario (**Directiva 2009/24/CE**, TJUE Asunto C-406/10):

### Puerta de Verificación Pre-Commit (Pre-Commit Legal Gate)
Antes de ejecutar `git add` o `git commit`, el agente DEBE verificar:
1. **¿Hay binarios propietarios en el diff?**
   - Si un archivo termina en `.DAT`, `.bin`, `.dump`, `.hex` o contiene fragmentos del firmware extraído de Fujifilm: **ABORTAR INMEDIATAMENTE**.
   - Solo se permite código fuente original (`.py`, `.c`, `.h`, `.S`, `.md`, `.json` de configuración propia).
2. **¿El código genera o distribuye firmware protegido?**
   - El código debe seguir el **modelo clean-room local**: las herramientas descargan el firmware oficial directamente desde los servidores de Fujifilm al equipo del usuario y lo analizan en local. Nunca empaquetar firmware ajeno en el repositorio.
3. **¿La finalidad es de estudio o interoperabilidad?**
   - El código debe estar orientado a investigación técnica, interoperabilidad de montura/enfoque o estudio de formatos, amparado por los artículos 100.3 y 100.4 de la LPI.

---

## 2. Matriz de Validación Paso a Paso (Checklist para Agentes)

En cada paso del flujo de trabajo, el agente debe validar el estado de legalidad:

| Paso | Operación | Validación de Legalidad | Acción del Agente |
|---|---|---|---|
| **Paso 1** | Descarga de firmware oficial | **Permitido** (fuente oficial pública de Fuji). | Usar script para descarga directa al disco local del usuario. |
| **Paso 2** | Desobfuscación y extracción local | **Permitido** (Art. 100.3 LPI, derecho al estudio). | Operar en local; nunca compartir el binario resultante. |
| **Paso 3** | Mapeo de memoria y offsets | **Permitido** (Hechos técnicos y algoritmos sin copyright). | Documentar offsets numéricos y estructuras de datos en Markdown. |
| **Paso 4** | Creación de herramientas (CLI) | **Permitido** (Código 100% original con licencia MIT). | Programar herramientas limpias, modulares y con tests. |
| **Paso 5** | Generación de parches / hooks | **Permitido** (Código propio nuevo + deltas matemáticos). | Mantener el código inyectable en ensamblador/C propio. |
| **Paso 6** | Publicación / Push a GitHub | **Permitido con filtro estricto**. | Verificar que `.gitignore` bloquee binarios antes del push. |
| **Paso 7** | Flasheo en dispositivo físico | **Permitido** (Derecho de modificación de hardware propio). | Advertir siempre al usuario sobre el riesgo de brickeo. |

---

## 3. Acciones Prohibidas para Agentes (Hard Fails)

- ❌ **NUNCA** hacer commit de firmware de Fujifilm Corporation.
- ❌ **NUNCA** sugerir la distribución de imágenes de ROM completas ya parcheadas.
- ❌ **NUNCA** incluir herramientas que eludan mecanismos comerciales de pago o licencias de terceros.
- ❌ **NUNCA** eliminar las advertencias legales de `README.md` o `docs/LEGAL_AND_COMPLIANCE.md`.

---

## 4. Referencia Legal Completa
Para una explicación pormenorizada de los artículos de la Ley de Propiedad Intelectual, Código Penal español y sentencias del TJUE, consultar:
[`docs/LEGAL_AND_COMPLIANCE.md`](docs/LEGAL_AND_COMPLIANCE.md).

<!-- OPENWIKI:START -->

## OpenWiki

This repository has a generated `openwiki/` evidence index. It is optional just-in-time context, not required startup reading.

- Do not enumerate, preload, or search wikis at task start. Use retrieval when the user asks for it, when unfamiliar architecture or dependency behavior materially affects the task, or when source inspection leaves an important uncertainty. Stop once the question is grounded.
- When those conditions apply and OpenWiki retrieval tools are available, use `openwiki_search` for just-in-time context and `openwiki_read` for the relevant complete sections. If search returns `workspace_required`, ask which listed workspace to use and retry with its ID.
- Use `openwiki_list_workspaces` or `openwiki_list_wikis` when workspace membership itself needs to be discovered.
- If the retrieval tools are unavailable, read `openwiki/quickstart.md` and follow its links to the relevant pages.
- Treat source code and tests as authoritative. A brief's unknowns and review items are verification gaps, not automatic requirements.
- Prefer the narrowest quiet validation that proves the changed behavior. Preserve complete failure output.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->
