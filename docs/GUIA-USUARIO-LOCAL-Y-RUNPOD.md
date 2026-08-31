# Guía de usuario: ComfyUI local y RunPod

Esta guía explica cómo usar los nodos **ComfyUI Flow Agent** en dos escenarios:

- **Local:** ComfyUI y Flow Agent funcionan en la misma computadora Windows.
- **RunPod:** ComfyUI funciona en un Pod remoto y Flow Agent permanece en la computadora Windows donde están Chrome y la sesión de Google Flow.

No mezcles los lanzadores de ambos modos. Elige uno según dónde esté funcionando ComfyUI.

## 1. ¿Qué modo debo elegir?

| Situación | Modo | Lanzador diario |
|---|---|---|
| ComfyUI está instalado en esta computadora | Local | `04.1-START-FLOW-LOCAL.cmd` |
| ComfyUI está dentro de RunPod | RunPod | `04-START-FLOW-RUNPOD.cmd` |

En ambos casos, Chrome, la extensión de Flow Agent y la sesión de Google Flow permanecen en la computadora Windows.

### Diferencia principal

| Local | RunPod |
|---|---|
| Se conecta directamente a `http://127.0.0.1:8001` | Se conecta mediante una URL HTTPS de ngrok |
| No utiliza un túnel de internet | Necesita ngrok mientras el Pod esté trabajando |
| Las variables se configuran automáticamente en Windows | Las variables se guardan en la configuración del Pod |
| El nodo se instala en ComfyUI Desktop | El nodo se instala en `/workspace/ComfyUI/custom_nodes` |

## 2. Elementos que siempre deben permanecer disponibles

La integración tiene tres partes:

1. **Google Flow en Chrome:** contiene la cuenta, el proyecto y los créditos.
2. **Flow Agent en Windows:** comunica Google Flow con los nodos.
3. **El custom node de ComfyUI:** puede estar en Windows o en RunPod.

Mientras se genera una imagen o un video:

- Mantén encendida la computadora Windows.
- Mantén Chrome abierto con la cuenta correcta de Google.
- Mantén abierto el proyecto configurado de Google Flow.
- Confirma que la extensión Flow Agent esté activada y conectada.
- No cierres la ventana que inició Flow Agent hasta que el trabajo termine.

## 3. Instalación común en Windows

Este paso se realiza antes de elegir Local o RunPod.

1. Abre la carpeta `scripts`.
2. Ejecuta `01-INSTALL-FLOW.cmd`.
3. Permite que instale Git, uv, ngrok y Chrome si faltan.
4. Cuando se abra la página de extensiones:
   - Activa **Modo de desarrollador**.
   - Pulsa **Cargar descomprimida**.
   - Selecciona la carpeta de la extensión que el instalador copió al portapapeles.
5. Inicia sesión en Google Flow.
6. Crea o abre el proyecto que utilizarás.
7. Copia la URL completa del proyecto y pégala cuando el instalador la solicite.
8. Pega tu authtoken de ngrok cuando lo solicite. La entrada se oculta por seguridad.

El instalador crea dos accesos directos en el escritorio:

- `START FLOW AGENT - LOCAL`
- `START FLOW AGENT - RUNPOD`

> Aunque el modo Local no usa ngrok durante el trabajo diario, el instalador común actualmente configura ngrok para que la misma instalación también pueda utilizar RunPod.

---

# Parte A: usar ComfyUI local

## A1. Primera instalación

Antes de continuar, cierra completamente ComfyUI Desktop.

1. Ejecuta `01-INSTALL-FLOW.cmd` si aún no completaste la instalación común.
2. Ejecuta `03.1-INSTALL-OR-UPDATE-CUSTOM-NODE-LOCAL.cmd`.
3. El instalador localizará ComfyUI Desktop y colocará el nodo en su carpeta `custom_nodes`.
4. Ejecuta `04.1-START-FLOW-LOCAL.cmd`.
5. Espera el mensaje `READY - Local MODE`.
6. Cierra completamente ComfyUI Desktop si estaba abierto y vuelve a iniciarlo.

Ese reinicio es obligatorio la primera vez porque ComfyUI debe leer estas variables de Windows:

- `FLOW_AGENT_BASE_URL=http://127.0.0.1:8001`
- `FLOW_AGENT_API_KEY` con la clave privada creada por el instalador.

La clave no se muestra en pantalla ni debe escribirse dentro de un workflow.

## A2. Uso diario

Normalmente solo necesitas:

1. Ejecutar `04.1-START-FLOW-LOCAL.cmd` o el acceso directo `START FLOW AGENT - LOCAL`.
2. Esperar `READY - Local MODE`.
3. Abrir ComfyUI Desktop.
4. Cargar el workflow y generar.

No necesitas RunPod, ngrok ni copiar una URL para trabajar en Local.

## A3. Actualizar el nodo local

1. Cierra completamente ComfyUI Desktop.
2. Ejecuta `03.1-INSTALL-OR-UPDATE-CUSTOM-NODE-LOCAL.cmd`.
3. Si la actualización incluye correcciones del backend Flow Agent, ejecuta también `01-INSTALL-FLOW.cmd` para instalarlas.
4. Cuando termine, ejecuta `04.1-START-FLOW-LOCAL.cmd`.
5. Abre nuevamente ComfyUI Desktop.

Si el nodo contiene modificaciones locales, el actualizador las guarda en un `git stash` recuperable antes de actualizar. No las elimina silenciosamente.

El paso 3.1 actualiza el custom node de ComfyUI, pero no modifica por sí solo el backend guardado en `C:\Users\<usuario>\FlowAgent`. El lanzador comprueba los parches obligatorios antes de iniciar y te indicará cuándo debes repetir el paso 1.

## A4. Comprobar el estado local

Ejecuta `05-STATUS-FLOW.cmd`. Un estado correcto debe mostrar:

- `Mode: local`
- `status: healthy`
- `extension_connected: True`
- `has_flow_key: True`
- `Windows local configuration: True`
- `ngrok: not used in Local mode`

---

# Parte B: usar ComfyUI en RunPod

## B1. Primera instalación en RunPod

Primero completa `01-INSTALL-FLOW.cmd` en Windows. Después:

1. Ejecuta `02-COPY-API-KEY.cmd`. La clave real se copiará al portapapeles sin mostrarse.
2. En RunPod, crea un secreto privado llamado exactamente:

   ```text
   flow_agent_api_key
   ```

3. Usa como valor del secreto la clave real que copiaste en el paso anterior.
4. Ejecuta `03-SHOW-RUNPOD-INSTALL.cmd` en Windows.
5. Pega el comando copiado en la terminal del Pod, no en PowerShell de Windows.
6. Espera `RUNPOD INSTALLATION COMPLETE`.

El comando instala o actualiza el nodo en:

```text
/workspace/ComfyUI/custom_nodes/comfyui-flow-agent
```

## B2. Configurar las variables del Pod

Ejecuta `04-START-FLOW-RUNPOD.cmd` en Windows. Cuando aparezca `READY - RunPod MODE`, configura estas dos variables en RunPod:

| Key | Value |
|---|---|
| `FLOW_AGENT_BASE_URL` | La URL HTTPS de ngrok que imprimió el lanzador |
| `FLOW_AGENT_API_KEY` | `{{ RUNPOD_SECRET_flow_agent_api_key }}` |

La expresión `{{ RUNPOD_SECRET_flow_agent_api_key }}` es una referencia al secreto. **No** debe guardarse como el contenido del propio secreto.

Después de guardar las variables:

1. Reinicia el Pod o el proceso de ComfyUI.
2. Espera a que ComfyUI termine de cargar.
3. Abre el workflow y verifica que aparezcan los nodos `Flow / ...`.

## B3. Uso diario con RunPod

1. En Windows, ejecuta `04-START-FLOW-RUNPOD.cmd` o el acceso directo `START FLOW AGENT - RUNPOD`.
2. Espera `READY - RunPod MODE`.
3. Compara la URL mostrada con `FLOW_AGENT_BASE_URL` en RunPod.
4. Si cambió, reemplázala y reinicia el Pod o ComfyUI.
5. Confirma que Chrome abrió el proyecto correcto y que la extensión está conectada.
6. Genera desde ComfyUI.

Las URL gratuitas de ngrok pueden cambiar después de detener o reiniciar el túnel. RunPod no podrá conectarse mientras conserve una URL antigua.

## B4. Actualizar el nodo en RunPod

1. Ejecuta `03-SHOW-RUNPOD-INSTALL.cmd` en Windows.
2. Pega nuevamente el comando en la terminal de RunPod.
3. Espera a que termine la actualización.
4. Reinicia ComfyUI dentro del Pod.

Si existen modificaciones dentro del custom node, el instalador crea un respaldo recuperable antes de actualizar.

## B5. Comprobar el estado de RunPod

En Windows, ejecuta `05-STATUS-FLOW.cmd`. Un estado correcto debe mostrar:

- `Mode: runpod`
- `status: healthy`
- `extension_connected: True`
- `has_flow_key: True`
- Una URL HTTPS en `ngrok:`

Esto confirma la parte de Windows. También verifica que RunPod tenga esa misma URL en `FLOW_AGENT_BASE_URL`.

---

# 4. Cambiar entre Local y RunPod

Puedes usar la misma instalación de Flow Agent para ambos modos:

- Para cambiar a Local, ejecuta `04.1-START-FLOW-LOCAL.cmd`.
- Para cambiar a RunPod, ejecuta `04-START-FLOW-RUNPOD.cmd`.

El lanzador reinicia únicamente los procesos administrados cuando necesita cambiar la dirección. Al entrar en modo Local también cierra el túnel ngrok administrado, porque ya no es necesario.

Después de cambiar:

- **Local:** reinicia ComfyUI Desktop si todavía no había leído las variables locales.
- **RunPod:** actualiza la URL del Pod si cambió y reinicia ComfyUI remoto.

# 5. Detener y desinstalar

## Detener

Ejecuta `06-STOP-FLOW.cmd`.

El script solicita permiso de administrador y cierra:

- Flow Agent.
- El puente de la extensión.
- El túnel ngrok administrado, si existe.

No cierra procesos ajenos que estén utilizando otros puertos.

## Desinstalar

Ejecuta `07-UNINSTALL-FLOW.cmd` y escribe exactamente `UNINSTALL` cuando se solicite.

La desinstalación no elimina:

- ComfyUI, modelos, workflows o resultados.
- Chrome, cuentas o proyectos de Google Flow.
- Git, uv o ngrok compartidos.
- Instalaciones manuales que no tengan la marca de propiedad del instalador.

# 6. Cambiar la cuenta o el proyecto de Google Flow

La cuota y los créditos pertenecen a la cuenta de Google abierta en Chrome, no a ComfyUI ni a la API key local.

Para cambiar de cuenta:

1. Detén Flow Agent con `06-STOP-FLOW.cmd`.
2. En Chrome, cambia a la cuenta de Google deseada.
3. Abre un proyecto de Flow perteneciente a esa cuenta.
4. Vuelve a ejecutar `01-INSTALL-FLOW.cmd` y proporciona la URL del nuevo proyecto cuando la solicite.
5. Confirma que la extensión esté activada y actualiza su sesión o token si lo solicita.
6. Inicia el modo correspondiente con el lanzador 4 o 4.1.

La API key de Flow Agent protege la conexión entre ComfyUI y el servicio local. No representa la cuenta de Google y normalmente no cambia al cambiar de cuenta.

# 7. Uso correcto de imágenes y video

## Personajes y ropa

`Flow / Custom Character Creator` acepta:

- `reference_image`: identidad principal.
- `top_reference`: parte superior de la ropa.
- `bottom_reference`: parte inferior.
- `accessories_reference`: accesorios.
- `shoes_reference`: calzado.

El límite combinado es de 10 imágenes de referencia. Las imágenes idénticas pueden reutilizar su `media_id` sin volver a subirse.

## Referencias para video

- `start image to video`: conecta una sola imagen a `start_image`.
- `first + last frame`: conecta `start_image` y `end_image`.
- `ingredients / reference images`: conecta imágenes individuales a las entradas de referencia.
- `edit source video`: proporciona `source_video_media_id` o un archivo de video accesible desde el sistema donde corre ComfyUI.

Para conservar mejor la identidad, utiliza las imágenes individuales del personaje. Un contact sheet es una sola imagen compuesta y no equivale a seis referencias independientes.

## Resolución, cantidad y créditos

- `count` permite de 1 a 4 videos.
- La generación base admite 360p y 720p.
- Al seleccionar 1080p, Flow genera primero 720p y después hace el upscale.
- El nodo muestra una estimación de créditos antes de enviar la solicitud.
- El upscale puede crear un segundo recurso dentro del historial de Google Flow, aunque ComfyUI entregue solamente el resultado final solicitado.

Antes de generar, confirma siempre `count`, duración y resolución.

# 8. Solución rápida de problemas

| Mensaje o síntoma | Causa probable | Qué hacer |
|---|---|---|
| `FLOW_AGENT_BASE_URL is not configured` | ComfyUI se abrió antes de configurar el modo | Ejecuta el lanzador correcto y cierra completamente/reabre ComfyUI |
| `Flow Agent did not respond` | El servicio no inició o un puerto quedó ocupado | Ejecuta `06-STOP-FLOW.cmd`, luego el lanzador correcto; revisa `%LOCALAPPDATA%\ComfyUIFlowAgent\flow-agent.stderr.log` |
| `Chrome extension is not ready` | Proyecto cerrado, extensión apagada o sesión vencida | Abre el proyecto configurado, activa la extensión, actualiza su token y ejecuta otra vez el lanzador |
| `HTTP 401` | La API key no coincide | En RunPod, vuelve a copiar la clave con `02-COPY-API-KEY.cmd` y actualiza el secreto privado |
| RunPod no conecta después de reiniciar | La URL gratuita de ngrok cambió | Ejecuta el lanzador RunPod, actualiza `FLOW_AGENT_BASE_URL` y reinicia ComfyUI remoto |
| Los nodos `Flow / ...` no aparecen | El custom node no está instalado o ComfyUI no se reinició | Ejecuta el instalador 3.1 en Local o el comando 3 en RunPod y reinicia ComfyUI |
| `Invalid image file` en Local | El workflow apunta a un archivo que solo existía en otra instalación | Carga nuevamente la imagen con `Load Image` en el ComfyUI actual |
| `Requested entity was not found` | Un `media_id` pertenece a otro proyecto, cuenta o recurso eliminado | Vuelve a cargar la referencia en el proyecto y cuenta actuales; no reutilices IDs antiguos |
| Solo se genera la primera toma y las demás indican `Media not found in history.json` | Falta el parche de reutilización de medios en el backend local | Ejecuta `06-STOP-FLOW.cmd`, después `01-INSTALL-FLOW.cmd` y finalmente el lanzador Local o RunPod |
| La referencia no se parece al personaje | Se usó texto, un contact sheet o el modo equivocado | Usa imágenes individuales y selecciona `ingredients / reference images` |
| Aparecen dos recursos al pedir 1080p | Uno es el 720p base y el otro su upscale | Es el proceso esperado; verifica que `count` esté en 1 |
| Google Flow bloquea la generación | Política o seguridad de Google | Cambia la referencia o la solicitud; repetir la misma entrada normalmente produce el mismo bloqueo |
| Cuota agotada | La cuenta de Google no tiene créditos disponibles | Cambia a una cuenta autorizada o espera la renovación de cuota; cambiar la API key local no agrega créditos |

# 9. Archivos de diagnóstico

Los archivos de ejecución se guardan en:

```text
%LOCALAPPDATA%\ComfyUIFlowAgent
```

Los más útiles son:

- `flow-agent.stdout.log`: actividad normal.
- `flow-agent.stderr.log`: errores de inicio o ejecución.
- `ngrok.log`: problemas del túnel RunPod.
- `flow-local-state.json`: modo y dirección actuales.
- `flow-local.config.json`: ubicación de la instalación, sin necesidad de guardar secretos en el repositorio.

No publiques el contenido de `.env`, `SERVER_API_KEY`, `FLOW_AGENT_API_KEY`, cookies, tokens o claves de Google.

# 10. Resumen de lanzadores

| Archivo | Cuándo usarlo |
|---|---|
| `01-INSTALL-FLOW.cmd` | Primera instalación o cambio del proyecto configurado |
| `02-COPY-API-KEY.cmd` | Copiar la clave real para crear/actualizar el secreto de RunPod |
| `03-SHOW-RUNPOD-INSTALL.cmd` | Instalar o actualizar el custom node dentro de RunPod |
| `03.1-INSTALL-OR-UPDATE-CUSTOM-NODE-LOCAL.cmd` | Instalar o actualizar el custom node de ComfyUI Desktop |
| `04-START-FLOW-RUNPOD.cmd` | Iniciar la conexión para ComfyUI en RunPod |
| `04.1-START-FLOW-LOCAL.cmd` | Iniciar la conexión para ComfyUI local |
| `05-STATUS-FLOW.cmd` | Revisar modo, conexión, extensión y ngrok |
| `06-STOP-FLOW.cmd` | Detener de forma segura los procesos administrados |
| `07-UNINSTALL-FLOW.cmd` | Desinstalar los componentes locales administrados |

## Lista de comprobación antes de generar

- [ ] Elegí el lanzador correcto: Local o RunPod.
- [ ] El estado muestra `healthy`.
- [ ] La extensión muestra conexión activa.
- [ ] Chrome está usando la cuenta y el proyecto correctos.
- [ ] En RunPod, `FLOW_AGENT_BASE_URL` coincide con la URL actual.
- [ ] Seleccioné el modo correcto del nodo.
- [ ] Revisé `count`, duración, resolución y estimación de créditos.
- [ ] No incluí claves ni tokens dentro del workflow.
