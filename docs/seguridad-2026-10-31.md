# Seguridad: revisión del 2026-10-31

Contexto: revisión de seguridad de todos los repos tras el «octubre negro» (la IA abarata el ataque: se asume que todo repo, endpoint y clave se escanea en minutos). Este documento recoge lo aplicado a este repo y lo que queda pendiente; el estado vive en `docs/`, no en la conversación.

> Repo **público**: los pendientes se describen por categoría y acción, sin detalles explotables.

## Cambios aplicados

Ninguno en esta tanda.

## Pendientes

- [ ] **Baja** · `.devcontainer/devcontainer.json` (AW-01): Quitar los flags que desactivan CORS/XSRF del comando de arranque en Codespaces.
- [ ] **Baja** · `.streamlit/config.toml`, `Dockerfile`, `requirements.txt` (AW-02): Contenedor sin usuario no root, dependencias sin versión máxima ni hashes. Usar `USER` no root, `pip-compile --generate-hashes` y la configuración CORS por defecto.
- [ ] **Info** · Ajustes de Pages (AW-04): Revisar en Settings → Pages de dónde se publica el sitio y que no sirva la rama principal entera.
- [ ] **Baja** · `.gitignore` (E-28): Añadir regla `.env*`.

## Reglas nuevas para agentes de este repo

- Cadena de suministro: lockfile siempre (con hashes en Python), `npm ci` en CI, no instalar versiones de menos de 7 días, Actions fijadas por SHA con `permissions:` mínimo, y CDN solo con SRI y versión exacta (o servir el fichero propio).
- En repos públicos, commits con el email `noreply` de GitHub.
- Dependabot (npm y github-actions) y alertas de seguridad activas, incluso en repos estáticos.
- La app guarda datos de salud solo en el navegador del usuario: mantenerlo así; cualquier backend futuro exige minimización y base legal.
- .gitignore base: `.env*`, `*.pem`, `*.key`, `*.sqlite*`, `*.db`, `.wrangler/`, y `*.xlsx`/`*.docx`/`*.pdf` en repos con material de cliente. Ejecutar `gitleaks detect --log-opts=--all` antes de hacer público un repo.
