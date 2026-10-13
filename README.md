# WB Servicios — Central web (MVP)

Central web multiempresa con FastAPI, PostgreSQL y panel HTML, lista para Docker Compose.

## Instalación

```bash
cp .env.example .env
# Cambiar POSTGRES_PASSWORD y ADMIN_TOKEN por secretos largos y aleatorios
docker compose up -d --build
```

La interfaz se abre en **http://localhost:8080/** desde el servidor. La documentación API está en **http://localhost:8080/docs**. Por seguridad, Compose publica solo en 127.0.0.1:8080; para acceso externo use un proxy HTTPS autenticado.

## Funciones incluidas

- Panel web con resumen, empresas, agentes, estados y filtros de documentos.
- Generación de API Key por agente (solo se muestra una vez, se guarda hash SHA-256).
- Configuración por empresa de prefijos, resolución, rangos y consecutivos para factura y nota crédito.
- Cola de órdenes para consultar estado DIAN o reenviar correo de documentos aceptados.
- API para heartbeat, reporte de estados, lectura y confirmación de órdenes por el agente.
- PostgreSQL persistente en volumen Docker.

## Límites de esta entrega

**No es una solución de facturación DIAN lista para producción.** El agente Windows actual debe adaptarse para recoger y ejecutar órdenes, generar XML firmado, consultar DIAN y enviar correos. La central solo registra solicitudes. La numeración se configura para supervisión, pero no modifica SAINT. La interfaz usa un token administrativo compartido en sessionStorage; antes de producción hay que implementar usuarios/roles, sesiones seguras, auditoría, CSRF y rate limiting. No exponga directamente el puerto HTTP a Internet. No suba `.env`, certificados ni claves a GitHub.

Para publicar en GitHub, suba el contenido de esta carpeta y no el archivo ZIP.
