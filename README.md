# swecc-core

Monorepo for SWECC's backend services.

## Services

| Service | Port | Description |
|---------|------|-------------|
| server | 8000 | Django API - handles auth, interviews, mentorship |
| sockets | 8004 | WebSocket server for real-time features |
| bot | - | Discord bot |
| ai | 8008 | AI/ML service (resume review, etc.) |
| chronos | 8002 | Metrics collection |
| scheduler | - | Cron job runner |

## Local Development

```bash
# Start everything
docker compose up

# Start specific services
docker compose up server bot

# With nginx reverse proxy
docker compose --profile with-nginx up
```

Needs a `.env` file in the root. Ask @elimelt for the file.

## Scripts

```bash
./s/ci/build.sh <service|all> [--push]   # Build Docker images
./s/ci/lint.sh <service|all> [--fix]     # Run linters
./s/ci/test.sh <service|all>             # Run tests
./s/ops/deploy.sh <service>              # Deploy to swarm (CI only)
```

## Deployment

Push to `main` triggers deployment for changed services. Each service deploys independently based on path filters.

To deploy everything manually: Actions → "Deploy All Services" → type `deploy-all` to confirm.

## Secrets

Managed via GitHub repository secrets. To update:

```bash
gh secret set SECRET_NAME --body "value"
```
