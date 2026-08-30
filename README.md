# ComfyUI Flow Agent

Nodos de ComfyUI para usar Google Flow desde un RunPod remoto mediante Flow Agent y ngrok.

Contratos verificados contra `kodelyx/flow-agent` revisión:

```text
206285a47d15018765df5b16bce1d72198b1bb29 (Flow Agent 2.0.7)
```

## Nodos incluidos

| Nodo | Función |
|---|---|
| `Flow / Nano Banana` | Texto o ingredientes/referencias → imágenes |
| `Flow / Omni Flash Video` | Texto, imagen inicial, fotograma inicial/final, ingredientes o edición → video |
| `Flow / Upload Media` | Sube una imagen o archivo de imagen/video y devuelve un `media_id` reutilizable |
| `Flow / Upsample Video` | Convierte un video ya generado a 1080p o 4K mediante Flow |

## Capacidades y límites confirmados

### Imágenes

- Modelos publicados: `harbor_seal`, `narwhal`, `gem_pix_2`.
- Ratios: 1:1, 16:9, 9:16, 4:3 y 3:4.
- `count`: 1–20; Flow Agent divide internamente en llamadas de hasta 4.
- Ingredientes/referencias: hasta 10 imágenes mediante `ref_media_ids`.
- Seed: 0–4294967295.

`gem_pix_2` puede devolver varias candidatas para una sola solicitud. Este cliente aplica el contrato solicitado y corta la respuesta a `count`; por tanto `count=1` entrega exactamente una imagen a ComfyUI. Google Flow puede seguir mostrando candidatas adicionales creadas internamente en su proyecto.

### Videos (Omni Flash)

- Texto → video.
- Una imagen inicial → video.
- Un fotograma inicial + un fotograma final → video.
- Ingredientes/referencias → video: hasta 10 imágenes.
- Edición: un video fuente y, opcionalmente, hasta 10 imágenes de referencia.
- Duraciones: 4, 6, 8 o 10 segundos.
- Ratios: landscape o portrait.
- Entrega: 720p nativo, 1080p mediante upsample gratuito y 4K mediante upsample de pago sujeto al nivel/créditos de la cuenta.
- `count`: 1–20 para generación; la edición de video produce un resultado por petición.
- Modelo automático: Flow Agent usa `abra_t2v_<duration>s`. El campo avanzado `video_model_override` permite enviar otro `videoModelKey` exacto si el upstream lo documenta en el futuro.

El esquema actual de Flow Agent **no soporta una lista de varios videos de referencia**. Admite un solo video fuente para edición. No se inventa un campo para una capacidad que el backend no ofrece.

## Esquemas HTTP utilizados

- `GET /health`
- `GET /v1/models`
- `POST /v1/upload` con `{"image_base64":"data:...;base64,..."}` para imagen o video
- `POST /v1/images/generations`
- `POST /v1/videos/generations`
- `GET /v1/videos/generations/{job_id}`
- `POST /v1/videos/upsample`
- `GET /download/{filename}`

Generación y upsample usan una sola `Idempotency-Key` durante todos los reintentos. Los trabajos de video se consultan hasta `succeeded` o `failed`.

## Configuración de RunPod

Variables de entorno del pod:

```env
FLOW_AGENT_BASE_URL=https://tu-tunel.ngrok-free.app
FLOW_AGENT_API_KEY=misma-clave-que-SERVER_API_KEY
```

Opcionales:

```env
FLOW_AGENT_CONNECT_TIMEOUT_SECONDS=10
FLOW_AGENT_MAX_DOWNLOAD_MB=64
FLOW_AGENT_MAX_VIDEO_DOWNLOAD_MB=2048
FLOW_AGENT_MAX_UPLOAD_MB=2048
```

Instalación/actualización:

```bash
cd /workspace/ComfyUI/custom_nodes
git -C comfyui-flow-agent pull --ff-only
python -m pip install -r comfyui-flow-agent/requirements.txt
```

Reinicia ComfyUI y comprueba:

```bash
python - <<'PY'
import requests
for node in ("FlowNanoBanana", "FlowOmniFlashVideo", "FlowUploadMedia", "FlowVideoUpsample"):
    response = requests.get(f"http://127.0.0.1:8188/object_info/{node}", timeout=15)
    print(node, response.status_code, list(response.json()))
PY
```

Los videos se descargan en `ComfyUI/output/flow_agent` y el nodo devuelve:

- vista previa de video en la interfaz;
- `VHS_FILENAMES`, compatible con Video Helper Suite;
- rutas, `media_id`, URLs y respuesta del job como JSON.

`source_video_path` se refiere a una ruta dentro de RunPod, no a una ruta de Windows del PC local.

## Arranque local automático en Windows

### Instalación inicial guiada

Para una computadora nueva, descarga o clona este repositorio y haz doble clic en:

```text
scripts\INSTALAR-FLOW.cmd
```

El asistente:

1. instala Git, uv, ngrok y Google Chrome cuando falten;
2. clona y prepara `kodelyx/flow-agent` con su Python aislado;
3. abre ngrok para guardar el authtoken;
4. abre la página de extensiones y copia la carpeta correcta al portapapeles;
5. abre Google Flow y extrae el ID desde la URL del proyecto;
6. genera una API key criptográficamente aleatoria sin imprimirla;
7. conserva la key existente si el instalador vuelve a ejecutarse;
8. crea el `.env`, la configuración local y un acceso directo en el escritorio;
9. inicia Flow Agent y ngrok, y deja la URL pública en el portapapeles.

Por seguridad, el usuario todavía debe completar cuatro acciones:

- iniciar sesión en Google y disponer de acceso a Flow;
- pulsar **Cargar descomprimida** en el navegador;
- copiar el authtoken desde su propia cuenta de ngrok;
- guardar la API key como secreto y la URL como variable del Pod en RunPod.

En RunPod, después de clonar este repositorio, la instalación puede hacerse con:

```bash
bash /workspace/ComfyUI/custom_nodes/comfyui-flow-agent/scripts/INSTALAR-RUNPOD.sh
```

El instalador de RunPod utiliza automáticamente el mismo Python que ejecuta ComfyUI.

El `.env` local de Flow Agent necesita como mínimo:

```env
OPENAI_API_HOST=127.0.0.1
OPENAI_API_PORT=8001
SERVER_API_KEY=tu-clave
DEFAULT_PROJECT=id-real-de-tu-proyecto
```

Desde una copia local de este repositorio, ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-flow-local.ps1
```

O haz doble clic en:

```text
scripts\INICIAR-FLOW.cmd
```

El script:

1. inicia o reutiliza ngrok;
2. obtiene su URL HTTPS desde el panel local de ngrok;
3. actualiza automáticamente `PUBLIC_BASE_URL` en el `.env` de Flow Agent;
4. reinicia Flow Agent solamente cuando hace falta;
5. abre el proyecto configurado en `DEFAULT_PROJECT`;
6. copia la nueva URL de ngrok al portapapeles.

Después solo pega esa URL en `FLOW_AGENT_BASE_URL` de RunPod y reinicia ComfyUI. La clave no cambia.

Estado y apagado:

```powershell
.\scripts\status-flow-local.ps1
.\scripts\stop-flow-local.ps1
```

### Desinstalacion local segura

Haz doble clic en:

```text
scripts\DESINSTALAR-FLOW.cmd
```

El desinstalador exige escribir `DESINSTALAR` y solo borra la copia de Flow Agent cuando una marca privada demuestra que fue creada por este instalador. Dentro de esa copia se eliminan su `.env`, el `.venv` privado, cache, salidas locales del backend, logs y estado. Tambien elimina la configuracion privada y el acceso directo que apunta a este proyecto.

No desinstala ni modifica Python de Windows, entornos virtuales externos, paquetes o caches compartidas, Google Chrome, perfiles, historial, cookies, configuracion de extensiones, proyectos de Google Flow, Git, uv, ngrok, credenciales compartidas de ngrok, ComfyUI, modelos, workflows ni archivos generados por ComfyUI. La entrada de la extension desempaquetada se conserva en el navegador; el usuario puede quitarla manualmente si lo desea.

Las instalaciones manuales o anteriores que no tengan una marca verificable se conservan completas. Esto evita borrar una carpeta que el usuario haya creado o reutilizado por su cuenta.

Si Flow Agent está en otra carpeta:

```powershell
.\scripts\start-flow-local.ps1 -FlowAgentDir "D:\ruta\flow-agent\flow-agent"
```

## Uso de referencias

- En `Flow / Nano Banana`, usa `reference_image` y los sockets `reference_image_2`…`reference_image_10`. Cada socket también puede recibir un batch; el total combinado nunca puede superar 10.
- En `Flow / Omni Flash Video`, selecciona primero `mode`:
  - `start image to video`: requiere `start_image`;
  - `first + last frame`: requiere `start_image` y `end_image`;
  - `ingredients / reference images`: requiere al menos uno de los 10 sockets de referencia;
  - `edit source video`: requiere `source_video_media_id` o `source_video_path`, y permite `reference_images` adicionales.
- Para reutilizar un video sin volver a subirlo, conserva su `media_id`.

## Pruebas

Los tests de red simulada no llaman Google Flow:

```bash
cd tests
python -m pytest -q
```

Verifican autenticación, payloads reales, idempotencia, polling, límite estricto de `count`, referencias y conversiones de imágenes. Los tests de tensor requieren el Python de ComfyUI, que ya incluye PyTorch.

## Seguridad

- El Bearer token solo se envía al mismo origen que `FLOW_AGENT_BASE_URL`; nunca a URLs firmadas externas.
- `/v1/upload` no se reintenta automáticamente porque upstream no define idempotencia para uploads.
- Descargas y uploads tienen límites de memoria configurables.
- No guardes `FLOW_AGENT_API_KEY` en el workflow ni en Git.
