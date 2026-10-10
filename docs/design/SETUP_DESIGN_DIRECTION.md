# Base de diseño: asistente de preparación de SD

Dirección aceptada el 10 de octubre de 2026. Referencia del usuario: composición
con tarjeta SD ilustrada, destino agrupado, estado dominante, respaldo secundario
y pie de acciones. El contrato ejecutable está en `setup-direction.json`.
La imagen original se conserva sin edición en el archivo local indicado allí,
con SHA256; no depende de la carpeta temporal ni se publica como recurso de la app.

## Qué se adopta

Una presentación cálida, con carácter Dreamcast, hecha por fans para fans.
El naranja da identidad; verde, azul informativo, ámbar y rojo explican estados.
El color siempre se acompaña de texto y símbolo. La ilustración puede ser más
expresiva y grande que un icono, pero no tiene comportamiento de botón.
Las acciones siguen siendo Tabler outline con métricas compartidas.

Orden: título e introducción breve → destino y comprobación → tarjeta de estado
con motivo y siguiente paso → respaldo cuando corresponde → pie estable.
La tarjeta muestra una ilustración SD/Dreamcast a un lado, estado legible al otro,
nota breve del alcance de comprobación y detalles técnicos desplegables.
El contenido dicta la altura; no se rellena la ventana con un gran espacio vacío.

## Correcciones obligatorias respecto de la imagen

- Vacía y apta: **Instalar OpenMenu**, confirmación y resultado visible antes de
  continuar. No ofrecer respaldo de una tarjeta sin contenido.
- Lista: **Usar destino**. La comprobación es de estructura y permisos, no un test
  físico de la SD ni garantía de que los juegos arrancan.
- Menú antiguo o desconocido migrable: **Revisar actualización**. Abre la revisión
  original de respaldo y actualización; no promete mostrar una colección que
  el controlador original bloquea hasta actualizar. Cancelar no escribe.
- Solo lectura sin migración: **Ver colección**, solo si el diagnóstico permite
  escanear. Este estado de presentación se prueba con permisos simulados: hoy el
  diagnóstico real emite los casos de lectura bloqueada como menús migrables.
  No se declara un flujo real nuevo de inspección de menús antiguos.
- Inaccesible: **Seleccionar otro destino**; sin respaldo ni continuación.
- Bloqueada por seguridad: carpeta legible con contenido ajeno; explicar que
  se protege ese contenido. Es diferente de un error de acceso. El respaldo
  puede ofrecerse si los servicios originales lo permiten, nunca una escritura.
- El respaldo respeta el registro y las decisiones previas. La casilla de no
  recordar se limita a ese destino, conserva la confirmación y no desactiva
  diagnósticos ni avisos de seguridad. No persistir por marcar antes de confirmar.
- Trabajo activo: progreso, sin cambios de destino ni cierre que abandonen al
  trabajador. Error: motivo y reintento si procede; no avanzar como si funcionara.
- Instalación correcta: mostrar éxito y **Continuar** como decisión explícita.

## Arquitectura Qt y adaptación

La referencia no implica adoptar HTML, Tailwind ni un navegador. Usar los tokens
existentes, los controles compartidos y composiciones Qt pequeñas:
`Header`, `PathStrip`, `StatusCard`, tarjeta de recomendación, `footer` y
`Confirmation` en `ui/v2/preparation.py`.
Separar iconos de acción, insignias de estado e ilustraciones decorativas.
Las composiciones presentan datos/emiten intenciones; `SetupWizardV2` conserva
las decisiones y servicios originales. No duplicar lógica de permisos o respaldo.
Los templates podrán cambiar arte y paleta, nunca permisos, significado o flujos.

En 640×420 y 720×500 puntos lógicos, reducir/ocultar primero la ilustración.
No recortar botones para mantener decoración. Detalles dentro de un área con
scroll, pie alcanzable, texto de ruta inspeccionable y foco visible. Comprobar
900×620, ES/EN, claro/oscuro y 1/1.25/1.5/DPI real de Windows. Las capturas
funcionales existentes no acreditan toda esta matriz visual por sí solas.

## Alcance y estado

**Adaptación nativa implementada para preparación y respaldo.** La aprobación
independiente de esta revisión se registra por separado en SETUP_DESIGN_VALIDATION.md;
la aceptación humana y las pruebas de hardware siguen pendientes. La aprobación
histórica del asistente compacto no aprueba por sí sola esta nueva dirección. Colección, detalle de carátulas (seis alternativas,
paginación, ampliación/comparación), importación y diálogos restantes conservan
sus contratos; no se rediseñan mediante esta referencia. El diálogo original
BackupPromptDialog se reemplaza visualmente por BackupPromptV2, conservando su
trabajador y servicio; permanece disponible en --legacy-ui.

## Arnés y revisión

`python scripts/validate_v2.py` regenera evidencia funcional y el informe
`docs/SETUP_DESIGN_VALIDATION.md`. `--check-docs` verifica también ese informe.
`python scripts/check_setup_design.py --require-approval` falla mientras falte
adaptación/revisión; un PASS de pytest no elimina esos pendientes.

Una vez implementado, cambiar explícitamente `implementation_status` a
`implemented`, ejecutar el arnés y revisar las capturas. El informe genera una
plantilla privada `build/v2-validation/setup-design-review.template.json`.
Un auditor independiente completa una copia `setup-design-review.json`, con
cada criterio revisado, capturas PNG distintas por muestra, rutas relativas al
repositorio, SHA256, estado, idioma, tema, tamaño lógico, escala, DPR y despliegue
de detalles. El gate comprueba formato/dimensiones, cobertura de cada eje y la
huella de la referencia local; no interpreta visualmente el contenido ni ejecuta
las interacciones. La cobertura de ejes no equivale al producto cartesiano completo.
La revisión está ligada a las huellas del contrato y las fuentes. Cambios en el
contrato, código o capturas invalidan la aprobación; el arnés nunca la concede
por sí mismo ni sustituye la aceptación humana o las pruebas en Dreamcast.

## Respaldo integrado en la misma dirección

La segunda referencia del usuario, respaldo con selección, confirmación y cuatro
resultados, está preservada sin edición y con SHA256 en `related_references`.
Origen y destino son campos inspeccionables/copíables de solo lectura. Elegir
carpeta se sitúa junto al destino. Las tres decisiones permanecen disponibles
en compacto: Cancelar, Continuar sin respaldo y Respaldar ahora; un respaldo
obligatorio oculta la omisión. El pie queda fuera del contenido desplazable.

La casilla no persiste por marcarla: la confirmación explica si se omite esta
vez o se recuerda para ese destino y estructura de colección. En el asistente,
la preferencia se guarda únicamente tras confirmación explícita. Los registros
de respaldo existentes conservan la política original.

Preparación muestra el trabajo real de enumeración del servicio, sin pasos de
verificación ficticios. La copia muestra archivos copiados y tiempo transcurrido;
no inventa bytes, velocidad ni tiempo restante. La barra representa archivos,
no porcentaje de bytes. El servicio actual no admite cancelación segura: ruta,
acciones y cierre permanecen bloqueados hasta la limpieza del trabajador.
Éxito conserva ubicación, Abrir carpeta y Continuar. Error conserva explicación,
detalles desplegables, Elegir carpeta y Reintentar; puede haber copia parcial,
pero no se registra éxito. La instalación conserva su confirmación original y
muestra resultado antes de salir. Los selectores de archivos son nativos del SO.

Diagnóstico e instalación conservan los servicios originales ejecutados en un
QThread; un bucle Qt atiende eventos mientras el controlador mantiene las acciones
protegidas. Tab desplaza la vista hasta todos los controles enfocados, incluida la
casilla. Enter en el campo de ruta solo comprueba; no ejecuta la acción principal.
Un resultado de instalación desconocido no se anuncia como éxito. Una copia completa
sin registro en origen se distingue de un fallo de copia y se conserva su ubicación.
