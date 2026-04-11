# DaVinci Resolve MCP Server

> **English**: This documentation is available in English. **[Read README in English](./README.md)**

---

[![Versión](https://img.shields.io/badge/version-2.2.0-blue.svg)](https://github.com/DragonJAR/davinci-resolve-mcp/releases)
[![Cobertura API](https://img.shields.io/badge/API%20Coverage-100%25-brightgreen.svg)](#api-coverage)
[![Herramientas](https://img.shields.io/badge/MCP%20Tools-28%20(356%20completas)-blue.svg)](#server-modes)
[![Probado](https://img.shields.io/badge/Live%20Tested-93.3%25-green.svg)](#api-coverage)
[![DaVinci Resolve](https://img.shields.io/badge/DaVinci%20Resolve-18.5+-darkred.svg)](https://www.blackmagicdesign.com/products/davinciresolve)
[![Python](https://img.shields.io/badge/python-3.10--3.12-green.svg)](https://www.python.org/downloads/)
[![Licencia](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Un servidor MCP (Model Context Protocol) que proporciona **cobertura completa** de la API de Scripting de DaVinci Resolve. Conecta asistentes de IA (Claude, Cursor, Windsurf) a DaVinci Resolve y controla tu flujo de trabajo de post-producción con lenguaje natural.

## Inicio Rápido

```bash
# Clonar el repositorio
git clone https://github.com/DragonJAR/davinci-resolve-mcp.git
cd davinci-resolve-mcp

# Ejecutar el instalador (requiere que Resolve esté abierto)
python install.py
```

El instalador universal detecta automáticamente tu plataforma, encuentra tu instalación de DaVinci Resolve, crea un entorno virtual y configura tu cliente MCP — todo en un solo paso.

## Requisitos Previos

- **DaVinci Resolve Studio** 18.5+ (macOS, Windows o Linux) — la versión gratuita no soporta scripting externo
- **Python 3.10–3.12** recomendado (3.13+ puede tener incompatibilidades ABI con la librería de scripting de Resolve)
- DaVinci Resolve abierto con **Preferencias > General > "Scripting externo usando"** configurado en **Local**

## Instalación

### Opción A: Instalador Interactivo (Recomendado)

```bash
python install.py                              # Modo interactivo
python install.py --clients all                # Configurar todos los clientes
python install.py --clients opencode,cursor,claude-desktop  # Clientes específicos
python install.py --clients manual             # Solo mostrar config
python install.py --dry-run --clients all      # Vista previa sin escribir
python install.py --no-venv --clients cursor   # Saltar creación de venv
```

### Opción B: Configuración Manual

Agregá esto en la configuración de tu cliente MCP:

**OpenCode:**
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "davinci-resolve": {
      "type": "local",
      "command": ["/ruta/al/python", "/ruta/al/server.py"],
      "enabled": true,
      "environment": {
        "RESOLVE_SCRIPT_API": "/ruta/al/resolve/api",
        "PYTHONPATH": "/ruta/al/resolve/api/Modules"
      }
    }
  }
}
```

**Clientes MCP estándar (Claude Desktop, Cursor, Windsurf, VS Code, Zed):**
```json
{
  "mcpServers": {
    "davinci-resolve": {
      "command": "/ruta/al/venv/bin/python",
      "args": ["/ruta/al/davinci-resolve-mcp/src/server.py"]
    }
  }
}
```

## Clientes MCP Soportados

El instalador puede configurar automáticamente:

| Cliente | Ubicación de Config | Auto-Instalación |
|---------|---------------------|------------------|
| OpenCode | `~/.config/opencode/opencode.json` | ✅ |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` | ✅ |
| Claude Code | `.mcp.json` (raíz del proyecto) | ✅ |
| Cursor | `~/.cursor/mcp.json` | ✅ |
| VS Code (Copilot) | `.vscode/mcp.json` (workspace) | ✅ |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | ✅ |
| Zed | `~/.config/zed/settings.json` | ✅ |
| Continue | `~/.continue/config.json` | ✅ |

## Modos del Servidor

El servidor MCP viene en dos modos:

| Modo | Archivo | Herramientas | Caso de Uso |
|------|---------|--------------|-------------|
| **Compound** (default) | `src/server.py` | 28 | La mayoría — rápido, limpio, bajo uso de contexto |
| **Full** | `src/resolve_mcp_server.py` | 356 | Usuarios avanzados que quieren una herramienta por método API |

Para usar el servidor completo:
```bash
python src/server.py --full    # Lanzar servidor con 356 herramientas
```

## Cobertura API

Cada método no-deprecated en la API de Scripting de DaVinci Resolve está cubierto. El servidor compound por defecto expone **28 herramientas** que agrupan operaciones relacionadas. El servidor granular completo provee **356 herramientas individuales**.

| Clase | Métodos | Herramientas | Descripción |
|-------|---------|--------------|-------------|
| Resolve | 24 | 24 | Control de app, páginas, presets de layout, render |
| ProjectManager | 29 | 29 | CRUD de proyectos, carpetas, databases, cloud |
| Project | 47 | 47 | Timelines, render pipeline, settings, LUTs |
| MediaStorage | 12 | 12 | Volúmenes, browsing de archivos, import |
| MediaPool | 28 | 28 | Carpetas, clips, timelines, metadata |
| Folder | 11 | 11 | Listado de clips, export, transcripción |
| MediaPoolItem | 38 | 38 | Metadata, markers, flags, properties |
| Timeline | 60 | 60 | Tracks, markers, items, export, generators |
| TimelineItem | 88 | 88 | Properties, Fusion comps, versions, CDL, AI |
| Gallery | 9 | 9 | Albums, stills, power grades |
| Graph | 12 | 12 | Node operations, LUTs, cache, grades |
| FusionComp | 83 | ~20 | Full Fusion node graph API |
| **Total** | **454** | **356** | |

## Capacidades Validadas {#validated-capabilities}

Probado contra **DaVinci Resolve Studio 20.3.2.9** (Abril 2026).

| Categoría | Capacidad | Estado | Notas |
|-----------|-----------|--------|-------|
| **Timeline** | CRUD (crear, leer, actualizar, borrar) | ✅ | Via ProjectManager y Timeline |
| | Settings y formato de timeline | ✅ | Resolución, frame rate, entrelazado |
| | Gestión de tracks | ✅ | Agregar/borrar tracks, lock/unlock |
| **Clips** | Agregar al timeline | ✅ | AppendToTimeline() |
| | Borrar clips | ✅ | DeleteClips() con soporte ripple |
| | Link/unlink clips | ✅ | SetClipsLinked() |
| | Propiedades de clip | ✅ | GetStart, GetEnd, GetDuration |
| **Detección de Escena** | Auto-detectar cortes de escena | ✅ | DetectSceneCuts() |
| **Color** | Leer estructura de nodos | ✅ | GetNumNodes, GetNodeLabel |
| | Get/set valores CDL | ✅ | GetCDL, SetCDL (Slope, Offset, Power, Sat) |
| | Copiar grades entre clips | ✅ | CopyGrades() |
| | Versiones de color | ✅ | GetVersionNames, LoadVersion |
| | Exportar LUT | ✅ | ExportLUT() (requiere página Color) |
| **Media Pool** | Importar media | ✅ | ImportMedia() |
| | Navegación de carpetas | ✅ | GetRootFolder, GetCurrentFolder |
| | Metadata de clips | ✅ | GetName, GetDuration, GetFrameRate |
| **Render** | Render presets | ✅ | GetRenderPresetList, LoadRenderPreset |
| | Render jobs | ✅ | AddRenderJob, GetRenderJobList |
| | Quick export | ✅ | RenderWithQuickExport() |
| **Transforms** | Pan, Tilt, Zoom | ✅ | SetProperty() |
| | Crop | ✅ | SetProperty(CropLeft/Right/Top/Bottom) |
| | Rotación, Flip | ✅ | SetProperty() |
| | Modo composite | ✅ | SetProperty(CompositeMode) |
| **Fusion** | Crear composición | ✅ | CreateFusionClip, AddFusionComp |
| | Import/export composiciones | ✅ | ImportFusionComp, ExportFusionComp |
| **Audio** | Volumen y pan | ✅ | SetProperty(Volume, Pan) |
| | Voice isolation | ✅ | GetVoiceIsolationState, SetVoiceIsolationState |
| | Sync de audio | ✅ | Auto-sync audio a clip |
| **Gallery** | Stills y albums | ✅ | GetStills, GetAlbums |
| | Exportar PowerGrade LUT | ✅ | ExportCurrentGradeAsLUT() |
| **Markers** | Agregar/borrar markers | ✅ | AddMarker, DeleteMarkersByColor |
| **Subtítulos** | Crear desde audio | ✅ | CreateSubtitlesFromAudio() |
| | | | |
| **NO Disponible** | | | |
| Clip split/trim | Razor blade / split por frame | ❌ | API no expone esta capacidad |
| | Set inicio/fin de clip | ❌ | SetStart/SetEnd no funcional via API |
| | Dibujo directo en timeline | ❌ | No hay API para dibujar cortes |

> **Nota:** La API de Scripting de DaVinci Resolve provee capacidades de automatización
> pero no incluye características de edición frame-by-frame como razor tool o
> controles de trim directos. Para estas operaciones, usar la UI de DaVinci Resolve directamente.

## Ejemplos de Uso

Una vez conectado, controlá DaVinci Resolve con lenguaje natural:

```
"Crear un nuevo proyecto llamado 'Campaña_Marca_2024' en la carpeta 'Comerciales'"
→ En vez de: Clic derecho en lista de proyectos > Nuevo Proyecto, escribir nombre, arrastrar a carpeta

"Importar todos los archivos de '/Volumes/SSD/RAW_footage' al Media Pool"
→ En vez de: File > Import Media > Navegar > Seleccionar todo > Open

"Agregar 3 tracks de video y 2 de audio al timeline actual"
→ En vez de: Clic en header de track "+" 5 veces, alternando entre video/audio

"Detectar cortes de escena en el timeline actual y agregar markers rojos"
→ En vez de: Timeline menu > Scene Detect > Click Start > Wait > Review cuts manually

"Aplicar LUT 'LogC_to_Rec709' a todos los clips del grupo de color 'Entrevistas'"
→ En vez de: Clic derecho en cada clip > 3D LUT > Seleccionar LUT (repetir 20+ veces)

"Hacer quick export del timeline actual usando el preset 'YouTube_1080p'"
→ En vez de: Deliver page > Format > Codec > Resolution > Export > Browse > Render
```

## Estructura del Proyecto

```
davinci-resolve-mcp/
├── install.py                    # Instalador universal (macOS/Windows/Linux)
├── src/
│   ├── server.py                # Servidor compound — 28 herramientas
│   ├── resolve_mcp_server.py    # Servidor completo — 356 herramientas
│   └── granular/                # Servidor modular (356 tools en 10 módulos)
│       ├── resolve_control.py  # Control de app, presets, constants
│       ├── timeline.py          # Gestión de timeline
│       ├── timeline_item.py     # Operaciones de clips, keyframes, transforms
│       ├── media_pool.py       # Gestión del Media Pool
│       ├── media_pool_item.py  # Metadata y operaciones de clips
│       ├── project.py          # Gestión de proyecto
│       ├── folder.py          # Navegación de carpetas
│       ├── gallery.py          # Stills, albums, PowerGrade
│       ├── graph.py           # Color node graph
│       └── media_storage.py    # Browsing de storage
├── examples/                    # Ejemplos de uso (validados en Resolve 20.3.2.9)
├── docs/                      # Documentación
│   ├── MODULARIZATION.md      # Estructura del servidor granular
│   ├── PARAMETER_REFERENCE.md # Referencia de parámetros para IA
│   └── WORKAROUNDS.md        # Workarounds para bugs de API
└── scripts/                  # Scripts de utilidad
```

## Contributing / Contribuir

¡Las contribuciones son bienvenidas! Ver [CONTRIBUTING.md](./CONTRIBUTING.md) para guías sobre cómo contribuir.

## Troubleshooting

### "Not connected to DaVinci Resolve"

- Asegurate de que DaVinci Resolve Studio esté **abierto** (no solo instalado)
- Verificá que **Preferencias > General > "Scripting externo usando"** esté en **Local**
- Ejecutá `python src/server.py --full` para probar la conexión manualmente

### "Could not connect after auto-launch"

- La primera ejecución puede tardar hasta 60 segundos en que Resolve se abra
- Verificá que Resolve Studio (no la versión gratuita) esté instalado

### Los tools devuelven resultados inesperados

- Verificá que las rutas de la API de Resolve en tu config MCP coincidan con tu plataforma
- Algunas tools requieren estado específico del proyecto (ej: un timeline debe ser el actual para operaciones de timeline)

## Plataforma

| Plataforma | Estado | Notas |
|------------|--------|-------|
| macOS | ✅ Testeado | Desarrollo primario y plataforma de test |
| Windows | ✅ Soportado | Testeado por la comunidad |
| Linux | ⚠️ Experimental | Debería funcionar — feedback bienvenido |

---

## Links

- [English README](./README.md)
- [CHANGELOG](./CHANGELOG.md)
- [CONTRIBUTING](./CONTRIBUTING.md)
- [GitHub Repository](https://github.com/DragonJAR/davinci-resolve-mcp)
- [Releases](https://github.com/DragonJAR/davinci-resolve-mcp/releases)
- [Issues](https://github.com/DragonJAR/davinci-resolve-mcp/issues)

---

Última actualización: 2026-04-10
