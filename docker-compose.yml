services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: hallspan
      POSTGRES_PASSWORD: hallspan
      POSTGRES_DB: hallspan
    ports: ["5450:5432"]
    volumes: [hallspan_pg:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hallspan -d hallspan"]
      interval: 3s
      timeout: 5s
      retries: 20
  api:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+psycopg2://hallspan:hallspan@db:5432/hallspan
      SEED_ON_EMPTY: "true"
    ports: ["9900:9900"]
    depends_on:
      db:
        condition: service_healthy
  frontend:
    build: ./frontend
    ports: ["4900:80"]
    depends_on: [api]
volumes:
  hallspan_pg:
