# ComfyUI Flow Agent — Flow / Nano Banana

Custom node para ejecutar generación de imágenes de Google Flow desde un ComfyUI remoto en RunPod, usando Flow Agent en una PC local y un túnel HTTPS de ngrok.

Implementación verificada contra `kodelyx/flow-agent` en la revisión:

```text
206285a47d15018765df5b16bce1d72198b1bb29
```

## 1. Contratos confirmados en el repositorio

### `GET /health`

No requiere el Bearer token en la revisión analizada. Sus dos formas observables son:

```json
{"status":"starting","connected":false,"transport":"none"}
```

o, con el bridge inicializado:

```json
{
  "status": "healthy",
  "extension_connected": true,
  "has_flow_key": true,
  "transport": "http"
}
```

El nodo exige `healthy`, `extension_connected=true` y `has_flow_key=true` antes de generar.

### `GET /v1/models`

Requiere `Authorization: Bearer <SERVER_API_KEY>` si `SERVER_API_KEY` está configurado. Devuelve formato OpenAI:

```json
{
  "object": "list",
  "data": [
    {"id":"harbor_seal","object":"model","created":0,"owned_by":"google"},
    {"id":"narwhal","object":"model","created":0,"owned_by":"google"},
    {"id":"gem_pix_2","object":"model","created":0,"owned_by":"google"}
  ]
}
```

Alias confirmados por el código:

| Modelo canónico | Alias aceptados | Nombre comentado en el repo |
|---|---|---|
| `harbor_seal` | `lite` | Nano Banana 2 Lite |
| `narwhal` | `standard`, `nano_banana_2` en el engine | Nano Banana |
| `gem_pix_2` | `pro`; el servidor también normaliza `nano_banana_2` a este valor en otro helper | Nano Banana Pro |

El nodo solo muestra los tres IDs canónicos publicados por `/v1/models`.

**Discrepancia upstream:** el README del repo declara `IMAGE_MODEL=narwhal` como default, pero `ImageGenerationRequest.model` usa `gem_pix_2`. Además, el alias `nano_banana_2` no se normaliza igual en `flow_engine/config.py` y `flow_server/config.py`. El nodo evita ambos puntos ambiguos enviando siempre uno de los tres IDs canónicos.

### `POST /v1/upload`

Body JSON real:

```json
{"image_base64":"data:image/png;base64,..."}
```

Respuesta real:

```json
{"media_id":"...","url":"https://.../download/archivo.png"}
```

El campo se llama `image_base64` incluso si el servidor también acepta video. No es `file`, multipart ni `media`.

### `POST /v1/images/generations`

Esquema Pydantic confirmado:

| Campo | Tipo/default | Validación confirmada |
|---|---|---|
| `prompt` | string, requerido | — |
| `model` | string, `gem_pix_2` | el nodo usa ID canónico explícito |
| `n` | int, `1` | 1 a 20 |
| `size` | string, `1024x1024` | se interpreta por proporción |
| `response_format` | string, `url` | el handler trata `b64_json` de forma especial; otro valor cae en URL |
| `user` | string opcional | no utilizado por este nodo |
| `image_base64` | string opcional | referencia inline alternativa |
| `ref_media_ids` | lista de strings opcional | descripción indica hasta 10; no hay constraint Pydantic explícito |
| `seed` | int opcional | 0 a 4294967295 |

El nodo usa la ruta subida: primero `/v1/upload`, después `ref_media_ids`.

Ejemplo de body enviado:

```json
{
  "prompt": "product photo on a clean studio background",
  "model": "gem_pix_2",
  "n": 2,
  "size": "1792x1024",
  "response_format": "url",
  "seed": 42,
  "ref_media_ids": ["MEDIA_ID_DEVUELTO_POR_UPLOAD"]
}
```

Respuesta confirmada:

```json
{
  "created": 1770000000,
  "data": [
    {
      "url": "https://tu-tunel.ngrok-free.app/download/flowagent_img_....png",
      "media_id": "...",
      "client_id": "..."
    }
  ]
}
```

Si la descarga local dentro de Flow Agent falla, el item puede contener la URL remota de Google y un `warning`. Si se pide `b64_json`, el item contiene `b64_json`. El cliente soporta defensivamente ambas formas aunque solicita `url`.

El endpoint acepta `Idempotency-Key`. El cliente crea una clave por ejecución y la reutiliza en reintentos/transitorios, para evitar duplicar una generación si se corta el túnel mientras Flow sigue trabajando.

### Ratios de imagen

El endpoint de imagen **no tiene un campo `aspect`**. Recibe `size` y `map_size_to_aspect()` clasifica la proporción:

| Opción del nodo | `size` enviado | Clasificación real |
|---|---:|---|
| square (1:1) | `1024x1024` | `square` |
| landscape (16:9) | `1792x1024` | `landscape` |
| portrait (9:16) | `1024x1792` | `portrait` |
| landscape (4:3) | `1365x1024` | `4x3` |
| portrait (3:4) | `1024x1365` | `3x4` |

Esos valores numéricos seleccionan una categoría; el código inspeccionado no promete que las dimensiones finales sean exactamente esos píxeles.

### `GET /download/{filename}`

Devuelve un `FileResponse` con el MIME detectado desde `FLOW_OUTPUT_DIR`, o `404` con un `detail` claro. La ruta no tiene `Depends(verify_api_key)` en la revisión analizada: `SERVER_API_KEY` protege generación/upload/modelos, pero **no protege `/download` ni `/health`**. Considérese al definir el acceso público de ngrok.

## 2. Arquitectura

```text
ComfyUI en RunPod
  Flow / Nano Banana
    ├─ GET  https://TU_NGROK/health
    ├─ POST https://TU_NGROK/v1/upload          (solo con IMAGE de referencia)
    ├─ POST https://TU_NGROK/v1/images/generations
    └─ GET  URL devuelta por Flow Agent
             ↓ túnel HTTPS
Flow Agent :8001 en la PC
             ↓ bridge/extensión
Chrome con Google Flow abierto y autenticado
```

## 3. Configurar Flow Agent y ngrok en la PC

En `Y:\ChatGPT\google_flow_automate\flow-agent\flow-agent\.env`:

```env
OPENAI_API_HOST=127.0.0.1
OPENAI_API_PORT=8001
SERVER_API_KEY=GENERA_UNA_CLAVE_LARGA_Y_ALEATORIA
PUBLIC_BASE_URL=https://TU_SUBDOMINIO.ngrok-free.app
```

`PUBLIC_BASE_URL` debe ser la URL que RunPod puede alcanzar. Si queda como `http://localhost:8001`, las URLs de descarga apuntarán al propio pod, no a la PC.

Inicia Flow Agent, carga la extensión unpacked del repo en Chrome, abre Google Flow y confirma localmente:

```powershell
flow status
```

Los dos indicadores deben estar listos:

```text
extension_connected: True
has_flow_key:        True
```

Después abre el túnel hacia el puerto local:

```powershell
ngrok http 8001
```

Si ngrok asigna un dominio nuevo, actualiza `PUBLIC_BASE_URL`, reinicia Flow Agent y actualiza `FLOW_AGENT_BASE_URL` en RunPod.

## 4. Instalar el nodo en RunPod

Desde la carpeta raíz de ComfyUI:

```bash
cd custom_nodes
git clone TU_REPOSITORIO/comfyui-flow-agent.git
python -m pip install -r comfyui-flow-agent/requirements.txt
```

Si vas a copiar esta carpeta directamente en vez de usar Git:

```text
ComfyUI/
└── custom_nodes/
    └── comfyui-flow-agent/
        ├── __init__.py
        ├── nodes.py
        ├── flow_agent_client.py
        ├── image_utils.py
        └── requirements.txt
```

Configura en RunPod **antes** de iniciar ComfyUI:

```bash
export FLOW_AGENT_BASE_URL="https://TU_SUBDOMINIO.ngrok-free.app"
export FLOW_AGENT_API_KEY="LA_MISMA_CLAVE_QUE_SERVER_API_KEY"
```

Variables opcionales:

```bash
export FLOW_AGENT_CONNECT_TIMEOUT_SECONDS="10"
export FLOW_AGENT_MAX_DOWNLOAD_MB="64"
```

No guardes la clave en el workflow JSON ni dentro del nodo. Las variables de entorno evitan que aparezca en capturas o workflows compartidos.

Reinicia ComfyUI. Busca el nodo en:

```text
Flow Agent → Flow / Nano Banana
```

## 5. Uso

Entradas:

- `prompt`: prompt de Google Flow.
- `model`: uno de los tres IDs canónicos reales.
- `aspect_ratio`: las cinco categorías confirmadas.
- `count`: 1 a 20. Flow Agent divide internamente en chunks de hasta 4.
- `seed`: 0 a 4294967295.
- `timeout_seconds`: presupuesto total para healthcheck, uploads, generación y descargas.
- `reference_image`: opcional; un batch sube hasta 10 referencias.

Salidas:

- `images`: batch `IMAGE` en rango `[0,1]` y formato `[B,H,W,3]`.
- `media_ids_json`: IDs reutilizables de las imágenes generadas.
- `source_urls_json`: URLs exactas devueltas por Flow Agent.

El nodo no cachea la generación: cada nueva ejecución de la cola genera otra vez. El `seed` se envía al API, pero la reproducibilidad final depende de Google Flow.

## 6. Pruebas por capas

### Capa A — PC local, sin ngrok

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

Resultado esperado: `healthy`, extensión conectada y Flow key presente.

Prueba los modelos con autenticación:

```powershell
$headers = @{ Authorization = "Bearer $env:SERVER_API_KEY" }
Invoke-RestMethod http://127.0.0.1:8001/v1/models -Headers $headers
```

### Capa B — túnel desde otra red o desde RunPod

```bash
curl -fsS \
  -H 'ngrok-skip-browser-warning: comfyui-flow-agent' \
  "$FLOW_AGENT_BASE_URL/health"
```

Después:

```bash
curl -fsS \
  -H "Authorization: Bearer $FLOW_AGENT_API_KEY" \
  -H 'ngrok-skip-browser-warning: comfyui-flow-agent' \
  "$FLOW_AGENT_BASE_URL/v1/models"
```

### Capa C — generación HTTP sin ComfyUI

```bash
curl -fsS \
  -H "Authorization: Bearer $FLOW_AGENT_API_KEY" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: prueba-manual-001' \
  -H 'ngrok-skip-browser-warning: comfyui-flow-agent' \
  -d '{"prompt":"a red ceramic cup on a table","model":"narwhal","n":1,"size":"1024x1024","response_format":"url","seed":42}' \
  "$FLOW_AGENT_BASE_URL/v1/images/generations"
```

Repite exactamente la misma petición con la misma clave: debe reutilizar la respuesta. No reutilices la clave con un payload distinto; el repo devuelve `409`.

### Capa D — tests del paquete

Desde `comfyui-flow-agent/tests` (se ejecuta desde esa carpeta porque el nombre
instalable del custom node contiene un guion):

```bash
python -m pip install pytest
python -m pytest -q
```

Los tests no llaman Google Flow. Verifican:

- tensor → PNG data URI → tensor;
- límite de referencias y tamaños incompatibles;
- headers Bearer y ngrok;
- payloads reales de upload/generation;
- no filtrar el Bearer token a URLs externas de Google/R2;
- healthcheck y errores FastAPI;
- ejecución completa del nodo con cliente simulado.

### Capa E — ComfyUI real

1. Reinicia ComfyUI y confirma que no aparece `IMPORT FAILED` para `comfyui-flow-agent`.
2. Ejecuta sin referencia, `count=1`, `square`, `narwhal`.
3. Conecta una imagen de referencia y confirma que la subida ocurre antes de generar.
4. Prueba `count=2` y verifica que `images` contiene un batch de 2.
5. Detén ngrok y confirma que el nodo entrega un error de conexión claro.
6. Cambia temporalmente la API key y confirma el `HTTP 401`.

## 7. Robustez y límites conocidos

- La autenticación se adjunta solo a URLs del mismo origen que `FLOW_AGENT_BASE_URL`; nunca se envía a una URL fallback de Google o R2.
- Los GET de descarga tienen reintentos seguros. `/v1/upload` no se reintenta automáticamente porque el repo no ofrece idempotencia para upload.
- La generación sí reintenta con una única `Idempotency-Key` ante timeout, `429`, `502`, `503`, `504` o `409 already processing`.
- El cuerpo descargado se limita a 64 MiB por defecto para evitar agotar RAM con una respuesta incorrecta del túnel.
- Pillow valida los bytes antes de crear el tensor.
- Si varias imágenes vuelven con dimensiones distintas, el nodo falla con las dimensiones observadas en lugar de redimensionarlas silenciosamente.
- `ref_media_ids` dice “up to 10” en la descripción del modelo, pero la lista no tiene `max_length` en Pydantic. El nodo aplica 10 de forma conservadora conforme a esa descripción.
- `response_format` no es un `Literal`; el handler solo distingue exactamente `b64_json` y trata el resto como URL. El nodo envía siempre `url`.
- La revisión analizada no autentica `/download/{filename}`. Si necesitas aislamiento fuerte, añade una política de acceso en el túnel/reverse proxy o modifica Flow Agent para proteger esa ruta; el Bearer actual por sí solo no la cierra.

## 8. Diagnóstico rápido

| Síntoma | Causa probable | Verificación |
|---|---|---|
| `FLOW_AGENT_BASE_URL is not configured` | Variable no llegó al proceso de ComfyUI | imprimirla en la shell que lanza ComfyUI y reiniciar |
| `HTTP 401` | Las claves no coinciden | comparar `FLOW_AGENT_API_KEY` con `SERVER_API_KEY` sin pegarlas en logs |
| `reachable but not ready` | extensión desconectada o Flow key ausente | `flow status`, abrir/recargar la pestaña de Flow |
| respuesta HTML/no JSON | URL de ngrok equivocada o página de advertencia | probar `/health`; el cliente ya envía `ngrok-skip-browser-warning` |
| URL de descarga contiene localhost | `PUBLIC_BASE_URL` incorrecta | corregirla en la PC y reiniciar Flow Agent |
| timeout durante generación | túnel interrumpido o Flow lento | aumentar `timeout_seconds`; los reintentos conservan la misma idempotency key |
| bytes no son imagen | ngrok/proxy devolvió otra respuesta o URL caducó | revisar status/content-type y repetir por capas |

## Archivos upstream que resuelven cualquier duda futura

Si Flow Agent cambia, compara estos archivos exactos antes de modificar el nodo:

```text
flow-agent/flow_server/models.py
flow-agent/flow_server/routes/generation.py
flow-agent/flow_server/routes/media.py
flow-agent/flow_server/routes/system.py
flow-agent/flow_server/state.py
flow-agent/flow_server/config.py
flow-agent/flow_engine/config.py
flow-agent/flow_engine/generators/t2i.py
```
