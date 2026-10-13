# WB Servicios — Central API (base de despliegue)

Proyecto inicial para GitHub y Docker Compose. Incluye API FastAPI, PostgreSQL, registro de empresas, generación de API Keys por agente, heartbeat y estados de documentos. **No incluye todavía una interfaz web administrativa, integración DIAN, motor de firma, SMTP, ni el agente Windows completo.** No usar en producción sin controles adicionales.

## Instalación

```bash
cp .env.example .env
# Cambiar POSTGRES_PASSWORD y ADMIN_TOKEN por valores fuertes y únicos
# No publicar .env en GitHub
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8080/health
```

API local: `http://127.0.0.1:8080/docs`. El puerto solo escucha en localhost. Para acceso remoto configure un proxy inverso HTTPS con autenticación y controles de acceso; no exponga directamente la API ni /docs a Internet.

## Registrar una empresa y un agente

```bash
export ADMIN_TOKEN='el_mismo_token_de_.env'
curl -X POST http://127.0.0.1:8080/admin/companies \
 -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
 -d '{"name":"WIBER SAS","nit":"900843080"}'

curl -X POST http://127.0.0.1:8080/admin/agents \
 -H "Authorization: Bearer $ADMIN_TOKEN" -H 'Content-Type: application/json' \
 -d '{"company_id":1,"name":"WIBERB-01"}'
```

La respuesta del segundo comando incluye `api_key`, visible solo una vez. Guardarla de forma segura en el agente Windows.

## Heartbeat desde agente

```bash
curl -X POST http://127.0.0.1:8080/agent/heartbeat -H 'X-API-Key: REEMPLAZAR_CON_API_KEY'
```

## Notas técnicas

- En SAINT, `TipoFac=A` representa factura y `TipoFac=B` nota crédito. Los códigos internos se traducirán a nombres legibles en la interfaz.
- Las resoluciones, prefijos, rangos, consecutivos y vigencias serán configuraciones por empresa/documento; no están implementados en este esqueleto.
- La central almacena únicamente SHA-256 de las API Keys. Falta rotación/revocación, auditoría, rate limits, permisos y migraciones antes de producción.
- El agente Windows debe mantener localmente el certificado PKCS#12, su contraseña cifrada con DPAPI, las credenciales SQL y la cola de procesamiento.
- La central nunca debe volver a enviar a DIAN un documento aceptado solo porque falló su correo.
