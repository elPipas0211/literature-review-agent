# Auditoría — Literature Review Agent

Fecha: 2026-11-15 · Commit auditado: `029bfad` (abril 2026, 3 commits en total)

## 1. Qué es realmente

A pesar del nombre, **no es un "agente"**: es un *pipeline* determinista sin LLM en el ciclo. El único componente con Claude (`src/evaluation/claude_evaluator.py`) no se usa en ningún sitio.

```
Consulta ─┬─► Semantic Scholar ─┐
          └─► OpenAlex ─────────┴─► Filtro mecánico (abstract + DOI + nº de citas)
              ─► Dedup (DOI, título ≥0.90) ─► Dedup contra la biblioteca (por título)
              ─► "Citation floor" (<2015 necesita ≥500 citas; 2015–2020 ≥100)
              ─► [si hay contexto] score = 0.8·coseno(contexto, título+abstract) + 0.2·log(citas)
              ─► guarda solo los aceptados en papers.json + ChromaDB + master.bib
```

Además: importación de CSV de Scopus/WoS (mismo pipeline), clustering K-Means + KeyBERT, búsqueda semántica ("Ask") sobre ChromaDB y UI en React con logs en vivo (SSE).

**Estado general:** el código es limpio y legible, y la arquitectura (FastAPI + SSE + React) es razonable. El frontend compila sin errores (`vite build` OK, 171 kB). Los problemas fuertes no son de estilo: son **metodológicos** (para una tesis) y unos cuantos **bugs funcionales**.

---

## 2. Hallazgos verificados (probados, no solo leídos)

| # | Hallazgo | Evidencia |
|---|---|---|
| V1 | **Semantic Scholar no responde sin API key.** Tres peticiones seguidas devolvieron `HTTP 429`. El cliente no reintenta ([semantic_scholar.py:33-39](src/sources/semantic_scholar.py:33)), así que en la práctica **solo funciona OpenAlex** y la UI solo muestra un error. | `curl` a la API |
| V2 | OpenAlex funciona, pero en una consulta de prueba **20 de 100 resultados no tenían abstract y 8 no tenían DOI**: el filtro mecánico descarta ~25 % antes de evaluar nada. | `curl` a la API |
| V3 | **BibTeX roto con autores de Scopus** ("Smith J."): la clave queda `J.2021_…` y BibTeX interpreta "J." como apellido. `&` y `%` no se escapan, así que LaTeX falla al compilar ese título. | Prueba de [bibtex_exporter.py:26](src/utils/bibtex_exporter.py:26) |
| V4 | El "citation floor" descarta un paper de 2012 con 450 citas y uno de 2019 con 80; conserva uno de 2021 con 0. | Prueba de `apply_citation_floor` |
| V5 | Los DOI con prefijo `https://doi.org/` no se deduplican contra la misma DOI sin prefijo. | Prueba de `deduplicate_by_doi` |
| V6 | No tienes **conda** instalado en este equipo, así que `install.bat`/`start.bat` fallan de entrada. Sí tienes Python 3.12 y Node. | `which conda` |
| V7 | `npm audit`: 8 vulnerabilidades (5 altas) en dependencias de desarrollo (Vite 5, esbuild, postcss). Solo afectan al servidor de desarrollo local; en producción hay 0. | `npm audit` |

---

## 3. Bugs y defectos (backend)

**Altos**
1. **Lo que se descarta desaparece.** Los papers descartados por citas o por similitud semántica no se guardan en ningún sitio ([pipeline.py:129-132](backend/pipeline.py:129), [pipeline.py:291-292](backend/pipeline.py:291)). Consecuencias:
   - No puedes reportar exclusiones (PRISMA, ver §6).
   - Los sliders de "Filter settings" solo reclasifican papers que **ya fueron aceptados**: bajar el umbral nunca recupera nada. El README promete otra cosa.
2. **Semantic Scholar sin reintentos ni backoff** (V1). Falta manejar el 429 con `Retry-After` y backoff exponencial, y avisar claramente de que hace falta la key.
3. **Scores no comparables entre búsquedas.** Cada búsqueda usa el contexto que escribas *en ese momento*, y el `semantic_score` guardado es relativo a ese texto. Si cambias el contexto entre búsquedas, la biblioteca mezcla escalas distintas y el re-scoring del frontend las trata como si fueran iguales. Las búsquedas **sin** contexto aceptan todo y lo dejan sin evaluar.
4. **El modelo de embeddings se recarga en cada petición** ([pipeline.py:114](backend/pipeline.py:114), [chroma_store.py:63](src/embeddings/chroma_store.py:63), [clusters.py:112](backend/routers/clusters.py:112)). El README dice que "se queda en memoria", y no es así: cada búsqueda, pregunta o clustering paga la carga completa.

**Medios**
5. La importación devuelve `{"error": ...}` como resultado normal ([pipeline.py:178](backend/pipeline.py:178), [:186](backend/pipeline.py:186)), y las salidas tempranas (`:255`, `:266`) no emiten `done`.
6. `papers.json` se escribe con leer, modificar y escribir sin bloqueo ([project_manager.py:104](src/storage/project_manager.py:104)): una búsqueda y una importación a la vez pueden perder datos.
7. La categoría guardada en ChromaDB se congela al insertar ([chroma_store.py:112](src/embeddings/chroma_store.py:112)) y se desincroniza de `papers.json`.
8. La normalización de DOI es inconsistente: OpenAlex solo quita `https://doi.org/`, CSV quita tres variantes y la dedup no normaliza (V5).
9. Todas las entradas BibTeX son `@article`, incluidas las de conferencias. No se protegen mayúsculas (`{LSTM}`) y se elimina `\` de los títulos.

**Bajos**
10. `DELETE /api/projects/{name}` no valida el nombre (`..` apunta a la raíz del repo desde un cliente HTTP crudo). El servidor es local y está en 127.0.0.1, así que el riesgo es bajo, pero es fácil de cerrar.
11. El clustering re-entrena K-Means de k=2..8 cada vez sin semilla de muestreo documentada en la UI. KeyBERT solo lee los primeros 8 000 caracteres del clúster.

## 4. Bugs y defectos (frontend)

1. **El modal de importación se cierra solo al terminar** ([App.jsx:224](frontend/src/App.jsx:224) llama a `setShowImport(false)` desde `onDone`, que se dispara en [ImportModal.jsx:52](frontend/src/components/ImportModal.jsx:52)). Nunca ves el resumen y los errores se pierden.
2. **Dos generadores de BibTeX distintos**: el botón "Copy" de la UI ([client.js:119](frontend/src/api/client.js:119)) genera claves diferentes a las de `master.bib`. Si mezclas ambos en tu tesis, las citas no coinciden.
3. "Reset to defaults" usa valores fijos en el código ([Sidebar.jsx:111](frontend/src/components/Sidebar.jsx:111)), no los de `config.yaml` como dice el README. Los mismos valores están copiados en tres lugares.
4. El chip de filtro muestra "Cluster 3" en vez de la etiqueta del clúster ([PaperLibrary.jsx:25](frontend/src/components/PaperLibrary.jsx:25)).
5. Falta: buscar o filtrar dentro de la biblioteca, ordenar (solo por citas), descargar `master.bib` desde la UI, ver el historial de búsquedas y abrir el PDF (`openAccessPdf` se pide a la API pero no se usa).

---

## 5. Qué sobra

| Elemento | Motivo |
|---|---|
| `src/evaluation/claude_evaluator.py`, dependencias `anthropic` y `python-dotenv`, sección `claude:` de config | Código muerto; nadie lo llama. Decide si revivirlo (§7) o borrarlo. |
| `pandas`, `tqdm`, `bibtexparser` en `environment.yml` | No se importan en ningún sitio. |
| `base_url`, `max_results_per_query` en `config.yaml` | Nadie los lee: las URLs están fijas en el código. |
| `scripts/*.py` frente a `backend/pipeline.py` | La misma lógica está duplicada en dos sitios (unas 1 000 líneas) y ya divergen: el CLI guarda logs de importación y parsea autores de WoS; el backend no. Debería existir una sola implementación en `src/` que usen ambos. |
| `noise`, `noise_papers` en clusters, `getStats`, `threading.Event done` | Restos de versiones anteriores (HDBSCAN). |
| Afirmaciones del README ("100 % local", "el modelo queda en memoria", "reset desde config.yaml") | Son falsas o engañosas; en una tesis te las pueden señalar. |

---

## 6. Problemas metodológicos (lo más importante para la tesis)

1. **No es una revisión sistemática reproducible.** Una revisión defendible (PRISMA 2020 / PRISMA-S) necesita:
   - cadenas de búsqueda exactas, fecha, fuente y nº de resultados por fuente (solo se guarda parcialmente en `sessions/`);
   - **cada registro excluido con su motivo** (hoy se pierden; ver §3.1);
   - conteos para el diagrama de flujo PRISMA;
   - criterios de inclusión y exclusión explícitos, y **una persona que decida**. Hoy el umbral de coseno decide solo y no puedes incluir o excluir manualmente.
2. **El modelo de embeddings no encaja.** `all-MiniLM-L6-v2` es generalista y **solo en inglés**: si escribes el contexto en español, la similitud se degrada mucho. Para literatura científica existen modelos específicos (p. ej. SPECTER2 de AllenAI) y, si necesitas español, modelos multilingües (`paraphrase-multilingual-*`, e5/bge multilingual).
3. **Los umbrales (0.40 / 0.50 / 0.30) son arbitrarios** y nunca se validaron. Sin un conjunto etiquetado no puedes afirmar que la herramienta "encuentra lo relevante". Las métricas estándar en automatización de *screening* son el *recall* (que no se te escape nada) y el WSS@95 (*work saved over sampling*).
4. **Sesgo de popularidad y de antigüedad**: el *citation floor* y el peso del 20 % por citas favorecen lo muy citado y lo reciente (V4). Además, los conteos de citas de Semantic Scholar, OpenAlex y Scopus no son comparables entre sí.
5. **Sesgo de cobertura**: exigir DOI excluye preprints de arXiv y muchos papers de conferencias, y exigir abstract excluye ~20 % de OpenAlex (V2). Solo se usa la búsqueda por relevancia de cada API, sin filtros de año ni de tipo, y sin *snowballing* (seguir referencias y citas), que en revisiones de literatura suele aportar mucho.

---

## 7. Qué falta (priorizado)

**Prioridad 1: que sea usable y honesto**
- [ ] Guardar **todos** los registros con `stage` y `exclusion_reason`, y exportar los conteos PRISMA.
- [ ] Reintentos y backoff para Semantic Scholar; pedir la API key gratuita.
- [ ] Arreglar el modal de importación, unificar BibTeX (una sola fuente y escapar caracteres de LaTeX) y normalizar DOIs.
- [ ] Cargar el modelo una sola vez (singleton al arrancar FastAPI).
- [ ] Instalación sin conda: `requirements.txt` + `venv` con tu Python 3.12, y versiones fijadas.

**Prioridad 2: que sirva para una revisión real**
- [ ] *Screening* humano en la UI: incluir, excluir o dudoso, con motivo, notas y etiquetas. El score solo **ordena**; la decisión es tuya.
- [ ] Un contexto o protocolo **fijo por proyecto** (pregunta de investigación + criterios de inclusión y exclusión), guardado con cada sesión.
- [ ] Filtros de año y tipo de documento, y *snowballing* hacia atrás y hacia adelante (ambas APIs lo permiten).
- [ ] Exportar a CSV/RIS para Zotero o Rayyan, y enlace al PDF abierto.
- [ ] Cambiar a SPECTER2 o a un modelo multilingüe.

**Prioridad 3: si la herramienta es el tema de la tesis**
- [ ] Un conjunto etiquetado a mano (100–300 papers) y medir *recall*, precisión y WSS@95 para distintos modelos y umbrales.
- [ ] Revivir el evaluador con LLM, pero con criterios de inclusión explícitos y salida estructurada, y **compararlo** contra los embeddings (calidad frente a costo). El modelo configurado (`claude-sonnet-4-6`) es de una generación anterior.
- [ ] Tests (pytest para filtros, dedup, BibTeX y parsing de CSV) y CI.
- [ ] Ahí sí se justificaría llamarlo "agente": por ejemplo, que proponga consultas, itere según lo que encuentra y haga *snowballing* por su cuenta.

---

## 8. Cambios aplicados (2026-11-15)

Enfoque elegido: la herramienta se usa **solo para tu revisión** (recolección, deduplicación y ranking). El *screening* se hace en ASReview o Rayyan y las citas en Zotero.

| Problema | Estado |
|---|---|
| Hacía falta conda (V6) | ✅ `install.bat` / `install.sh` usan `.venv` + `requirements.txt` con versiones fijadas y PyTorch CPU. `environment.yml` eliminado. |
| Se perdían los descartados (§3.1) | ✅ Ya no se borra nada: los problemas de calidad son `flags` y la relevancia es un `score` para ordenar. El *citation floor* está desactivado por defecto. |
| Sin trazabilidad PRISMA (§6.1) | ✅ Cada búsqueda o importación guarda `sessions/<id>/session.json` (consulta, fecha, años, conteos por fuente, duplicados, errores, config). La barra lateral muestra identificados → duplicados → a revisar. |
| Semantic Scholar 429 (V1) | ✅ Semantic Scholar **eliminado** (ronda 2): sin API key fallaba casi siempre. OpenAlex cubre la búsqueda, es gratis y no pide key; tiene reintentos con backoff. |
| Modelo solo en inglés (§6.2) | ✅ `intfloat/multilingual-e5-small`: contexto o preguntas en español emparejan papers en inglés (medido: dentro del tema ≈0.85, fuera ≈0.75). |
| Scores no comparables (§3.3) | ✅ El contexto vive a nivel de proyecto; al cambiarlo se re-puntúa toda la biblioteca (262 papers en 0.3 s). |
| Modelo recargado en cada petición (§3.4) | ✅ Una sola instancia por proceso, precargada al arrancar. ChromaDB reemplazado por una caché `.npz` por proyecto. |
| BibTeX roto (V3, §4.2) | ✅ Un solo generador. Claves `smith2021deep` únicas. Autores "Apellido, Nombre". Escape de LaTeX. Siglas protegidas. `@inproceedings`, `@incollection`, etc. |
| DOIs sin normalizar (V5) | ✅ Normalización única; los duplicados se **fusionan** (fuentes, campos faltantes, procedencia). |
| Modal de importación (§4.1) | ✅ Ya no se cierra solo; muestra el resultado y los errores. Soporta Scopus, WoS (CSV o tabulado) y Zotero. |
| Exportar | ✅ CSV (Excel, ASReview, Rayyan), RIS (Zotero, Rayyan, ASReview) y BibTeX, de toda la biblioteca o de la vista filtrada. |
| Código muerto y duplicado (§5) | ✅ Eliminados el evaluador de Claude, ChromaDB, dependencias sin uso y la lógica duplicada entre `scripts/` y backend: ahora los scripts son envoltorios de `src/pipeline.py`. |
| Varios | ✅ Validación de nombres de proyecto (`..`), bloqueo por proyecto al escribir `papers.json`, escrituras atómicas, filtros por año, búsqueda de texto y orden en la UI, enlace a PDF abierto, procedencia de cada paper, 11 tests (`pytest`). |

**Pendiente o fuera de alcance (a propósito):** *screening* dentro de la app (usa ASReview o Rayyan) y validación formal de los umbrales. Los umbrales de categoría son heurísticos: úsalos para **ordenar**, no para excluir sin leer.

**Ojo con la ambigüedad de términos:** en la prueba, la consulta "transformer" trajo también papers de *transformadores eléctricos*. El ranking por contexto los baja, pero revisa siempre tus cadenas de búsqueda.


## 9. Ronda 2 (2026-11-15): exploración para elegir tema

Restricciones: interfaz en inglés, nada de pago (sin IA de pago); en lugar de resúmenes con IA, palabras clave locales con embeddings.

| Funcionalidad | Dónde |
|---|---|
| Semantic Scholar eliminado; solo OpenAlex (`sources.openalex.email` opcional para el *polite pool*) | `src/sources/openalex.py`, `config.yaml` |
| ***Snowballing*** (referencias, citantes o ambos) desde el detalle de un paper. PRISMA separa *databases* y *citation searching* | `run_snowball` en `src/pipeline.py`, `PaperDetail.jsx`, `Sidebar.jsx` |
| **Palabras clave por paper** (KeyBERT con el mismo modelo, local, ~6 s/100 papers). Se filtran frases de relleno ("datasets demonstrate") | `src/keywords.py`; chips clicables en tarjetas y detalle (filtran la biblioteca) |
| **Etiquetas de clusters** a partir de esas palabras clave: las más distintivas de cada cluster (TF-IDF entre clusters), así el tema común a todos ("anomaly detection") no repite en cada etiqueta | `label_from_keywords`, `src/clustering.py` |
| **Detección de surveys/reviews** (tipo de OpenAlex, tipo de documento de Scopus/WoS o título) | `detect_review`; badge *Review*, filtro *Surveys / reviews only*, tarjeta *Surveys* en la barra lateral |
| **Lista de lectura**: estrella ☆ y notas por paper; sobreviven a búsquedas nuevas y se exportan en CSV/RIS | `annotate`; filtro *Starred only*, tarjeta *Reading list* |
| **Pestaña Trends**: publicaciones por año en todo OpenAlex para un tema (con crecimiento últimos 3 años vs. 3 anteriores), tu biblioteca por año, tabla de temas por cluster (barras por año, % reciente, palabras clave emergentes, *read first*), palabras clave emergentes y surveys para leer primero | `TrendsView.jsx`, `GET /api/trend` |
| **Pestaña Map**: mapa 2D (t-SNE) de los papers agrupados; color por cluster y número como segunda codificación | `MapView.jsx`, `points` en `clusters.json` |
| **Reutilizar búsquedas** del historial (↻ reuse rellena el formulario) | `Sidebar.jsx`, `SearchPanel.jsx` |
| **Ajustes recordados por proyecto** (pestaña, filtros, orden, sliders) y último proyecto abierto, en `localStorage` | `frontend/src/prefs.js` |
| **Bibliotecas grandes**: se pintan 100 tarjetas y *Show more / Show all* | `PaperLibrary.jsx` |
| **Sin pantallas en blanco**: cada zona (búsqueda, pestaña, barra lateral, detalle) tiene un *error boundary* con *Try again* | `ErrorBoundary.jsx` |

**Cómo leer *Trends* para elegir tema:** el gráfico global mide cuánto se publica en todo OpenAlex (coincidencias en título y resumen); casi todo crece, así que compara temas entre sí, no contra cero. Lo de "tu biblioteca" depende de lo que buscaste. Las palabras clave emergentes son frases mucho más frecuentes en los últimos 3 años de tu biblioteca: son pistas, no conclusiones. Las secciones de *future work* de los surveys recientes son la mejor fuente de huecos de investigación.


## 10. Ronda 3 (2026-11-17): pruebas, validación y detalles

| Cambio | Detalle |
|---|---|
| **OpenAlex sin key: paginación** | OpenAlex empezó a exigir API key para paginar con `cursor`: sin key, toda búsqueda se cortaba en 200 resultados con un error. Ahora se pagina por número de página, que funciona sin key (probado: 450 resultados). El error 401/403 ya no dice "key rechazada" cuando no hay key. |
| **API key opcional** | Settings guarda `OPENALEX_API_KEY` / `OPENALEX_EMAIL` en `.env` (ignorado por git). Reintentos respetan `Retry-After`; errores legibles. |
| **`start.bat` / `stop.bat`** | `stop.bat` no detenía nada: el patrón de `findstr` usaba `\|`, que `findstr` no soporta, y no veía Vite en IPv6 (`[::1]:5173`). Reescrito. `start.bat` llamaba a `stop.bat`/`install.bat` sin ruta; ahora con ruta completa. Vite usa `strictPort` para no saltar a 5174 mientras el navegador abre 5173. |
| **Cancelar** | Botón *Cancel* en el log. Al cerrar el stream el backend detiene la ejecución en el siguiente evento; `papers.json` y `session.json` solo se escriben al final, y la carpeta de sesión a medias se borra, así PRISMA nunca cuenta media búsqueda. |
| **Validar el ranking (pestaña Validate)** | Muestra aleatoria simple, etiquetado ciego al score (R/N/U, Z deshace), AUC, recall/precisión por umbral con intervalo de Wilson, umbral que conserva ≥95 % de relevantes y párrafo para métodos. Esto convierte los umbrales heurísticos (§6) en umbrales justificados. |
| **Recalcular palabras clave** | Botón en la barra lateral; corre fuera del bloqueo del proyecto para no frenar estrellas/notas. |
| **Modo oscuro** | Tokens claros/oscuros; sigue al sistema o se elige en Settings. La paleta de gráficos usa los pasos oscuros validados (contraste ≥ 3:1 sobre el fondo oscuro). |
| **Botones `btn-ghost`** | Tenían texto crema pensado para el encabezado oscuro y casi no se veían en el resto de la app. Separado en variante de página y de encabezado. |
| **Tests** | Backend: 18 (`pytest`). Frontend: 8 (`npm test`, Vitest): rescoring, métricas de validación, palabras clave emergentes, preferencias. |
| **Inicio** | Pantalla de bienvenida con creación de proyecto y tarjetas, checklist en proyectos vacíos, encabezado compacto, pregunta de investigación plegable; títulos en Newsreader. |


## 11. Ronda 4 (2026-11-23): BibTeX, APA y diseño

| Cambio | Detalle |
|---|---|
| **Importar BibTeX** | Web of Science exporta en BibTeX. Nuevo lector propio, sin dependencias: llaves anidadas, valores entre comillas, `@string`, concatenación `#`, acentos LaTeX (`{\'{e}}`, `\v{s}`) y escapes (`\&`, `{[}`). Detecta Web of Science, Scopus o BibTeX genérico; PRISMA lo muestra como "Web of Science (BibTeX)". Acepta `.bib` y el `savedrecs.txt` de WoS. |
| **Citas APA 7** | Referencia por paper (copiar con cursivas para Word) y cita en texto (`(Smith et al., 2021)`); exportación `.rtf` en orden alfabético con sangría francesa. Títulos a *sentence case* conservando siglas. |
| **Volumen, número y páginas** | Se guardan desde OpenAlex, Scopus, WoS, Zotero y BibTeX. Para bibliotecas importadas antes, *Complete from OpenAlex* los rellena por DOI (probado en una copia de tu proyecto: 723 de 749). |
| **Revistas en mayúsculas** | WoS escribe "JOURNAL OF NETWORK SECURITY"; se pasa a "Journal of Network Security" conservando siglas (IEEE, ACM…). |
| **Diseño** | Encabezado con más aire; tarjetas de estadísticas con etiqueta y número separados y sin aspecto desactivado; botones de exportación centrados en 2 columnas. |


## 12. Ronda 5 (2026-11-23): resumen, CSV de lectura y favoritos

| Cambio | Detalle |
|---|---|
| **Favoritos primero** | Los papers con ★ salen siempre arriba en la lista, con cualquier orden. |
| **Cita APA visible** | La sección *Cite — APA 7* pasó justo debajo del título del paper. Si el backend no se ha reiniciado, avisa que hay que correr `stop.bat` y `start.bat` (era la causa de no verla). |
| **Pestaña Summary** | Resumen **extractivo** y local (sin IA de pago): por año, revistas, autores, más citados, y por tema las frases de los abstracts más cercanas al centro del cluster, cada una con su cita APA en texto; luego surveys, lista de lectura y una frase clave por paper. Descargable en `.html` (Word) o copiable como texto. Probado en una copia del proyecto: 642 papers en ~19 s. |
| **CSV de lectura** | *CSV · ★ starred + relevant*: título, abstract, frase clave (la más cercana a la pregunta de investigación), palabras clave, tema, notas y cita APA. Las frases clave se guardan en caché (se recalculan si cambia la pregunta). |
| **Copyright en abstracts** | Scopus/WoS pegan "© 2021 Elsevier…" a la última frase; se corta antes de dividir, para no perder esa frase. |
