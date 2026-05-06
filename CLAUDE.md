# DSY1103 Evaluador — Arquitectura del Sistema

## Propósito

Herramienta para evaluar proyectos semestrales de la asignatura **DSY1103 (Full Stack I)**.
Los estudiantes construyen sistemas con 10+ microservicios Spring Boot. Este sistema los clona,
compila, levanta y ejecuta escenarios de prueba automatizados (fácil / mediano / difícil).

---

## Estructura del repositorio

```
dsy1103_frontend/
├── frontend/                    # React + Vite — dashboard de evaluación
├── backend/                     # Python FastAPI — orquestador
├── groups/                      # YAML por grupo de alumnos
│   └── grupo4.yaml
├── projects/                    # Banco de proyectos: definición + escenarios
│   └── retail_dondragon.yaml
├── secrets/                     # Credenciales opcionales (gitignoreado)
│   └── grupo4-user-service.properties
├── clones/                      # Repos clonados en tiempo de ejecución (gitignoreado)
├── Dockerfile.spring-runner     # Imagen genérica: compila y corre cualquier uS del alumno
├── Dockerfile.evaluator         # Imagen del orquestador (FastAPI + React build)
└── docker-compose.yml           # Solo levanta el evaluador; él levanta el resto
```

---

## Flujo de uso (perspectiva del profesor)

```
1. docker-compose up evaluator
2. Abrir localhost:3000
3. Seleccionar grupo de alumnos
4. [Clonar y Compilar]   → git clone × 10 + mvn package × 10
5. [Levantar Servicios]  → docker run × 10 (spring-runner)
6. Esperar health checks → GET /actuator/health × 10
7. [Evaluar Fácil / Mediano / Difícil]
8. Ver log en tiempo real → pass/fail por step
```

---

## Contenedores en tiempo de ejecución

```
Host Docker
├── evaluador         (Dockerfile.evaluator)
│   ├── FastAPI :8000 — orquesta clonado, compilación, Docker, escenarios
│   ├── React   :3000 — dashboard
│   └── monta /var/run/docker.sock para controlar Docker del host
│
├── user-service      (spring-runner — instancia 1)
├── product-service   (spring-runner — instancia 2)
├── ...               (hasta 10)
└── order-service     (spring-runner — instancia 10)
```

Todos en la red Docker `dsy1103-eval-net`.

---

## Imagen `spring-runner` (Dockerfile.spring-runner)

Imagen única basada en `eclipse-temurin:21-jdk-alpine`.
- El código del alumno se **monta como volumen** en `/app`
- El puerto se inyecta como variable de entorno `PORT`
- Ejecuta: `./mvnw package -DskipTests && java -jar target/*.jar --server.port=$PORT`
- El caché Maven del host (`~/.m2`) se monta para acelerar compilaciones posteriores

### Secretos opcionales

Si el alumno usa `application-secrets.properties` y lo tiene en `.gitignore`,
el profesor puede entregarlos por separado. El sistema los monta en `/secrets/`
e inyecta `--spring.config.additional-location=file:/secrets/...` al arrancar.

Si no se proveen secretos, se asume que las credenciales están hardcodeadas
en el `application.properties` del repo (caso más común entre los alumnos).

---

## Config de grupo (groups/grupo4.yaml)

```yaml
group_name: "Grupo 4"
project: retail_dondragon          # apunta a projects/retail_dondragon.yaml
students: ["Ana López", "Pedro Soto"]

services:
  - name: user-service
    repo: https://github.com/alumno/grupo4-user-service
    port: 8081                     # leído del application.properties del alumno

  - name: product-service
    repo: https://github.com/alumno/grupo4-product-service
    port: 8082
  # ... × 10
```

El puerto siempre debe estar definido en el `application.properties` del alumno
(requisito de la entrega — sin puerto definido hay choque y mala nota).

---

## Banco de proyectos + escenarios (projects/retail_dondragon.yaml)

```yaml
project: RetailDonDragon

scenarios:
  easy:
    - name: "Registro y Login"
      steps:
        - name: "Registrar cliente"
          service: user-service
          method: POST
          path: /api/users/register
          body:
            username: "testuser"
            email: "test@eval.com"
            password: "Test1234"
          expect_status: 201
          extract:
            user_id: "$.id"           # disponible en steps siguientes como {{user_id}}

        - name: "Login"
          service: user-service
          method: POST
          path: /api/users/login
          body:
            email: "test@eval.com"
            password: "Test1234"
          expect_status: 200
          extract:
            token: "$.token"          # puede estar ausente si no implementaron JWT

  medium:
    - name: "Compra de producto"
      steps: []                       # usa {{token}}, {{user_id}} de steps previos

  hard:
    - name: "..."
      steps: []
```

Los valores extraídos (`extract`) se pasan como contexto entre steps y entre escenarios
dentro de la misma sesión de evaluación.

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Dashboard | React + Vite |
| Orquestador | Python + FastAPI |
| Streaming de logs | SSE (Server-Sent Events) |
| Control de Docker | Python `docker` SDK (vía socket del host) |
| Servicios del alumno | Spring Boot 3.x + Maven + Java 21 |
| Base de datos alumnos | PostgreSQL en NeonDB (cloud — no requiere DB local) |
| Imagen base servicios | `eclipse-temurin:21-jdk-alpine` |

---

## Proyectos en el banco (a desarrollar)

El banco debe tener ~10 propuestas con escenarios distintos (todos involucran
registro, login, operaciones CRUD y flujos de negocio específicos del dominio):

- Banco XXX
- Retail DonDragon
- Logística ElRapido
- *(agregar más según semestre)*

---

## Notas de diseño importantes

- **Un solo comando para el profesor**: `docker-compose up evaluator`
- **Sin Dockerfile de los alumnos**: ellos solo necesitan `pom.xml` o `build.gradle`
- **Caché Maven compartido**: `~/.m2` del host se monta → primera compilación lenta,
  las siguientes ~30 segundos
- **Health check**: `GET /actuator/health` en cada servicio antes de iniciar escenarios
- **Sin JWT obligatorio**: los escenarios manejan la ausencia de token graciosamente
- **Reporte**: log de texto con pass/fail por step; exportable a `.txt` / `.json`
  para luego convertir a rúbrica y planilla de notas (tarea futura)
