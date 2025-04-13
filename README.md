# Project Name

## Overview

Multi-service, multi-tier, Kubernetes-based platform.

## Check `docs/` for README / docs

## Setup
- Setup `.env` file with correct values copying from `.env.sample`
```bash
- docker-compose -f docker-compose-dev.yml up --build
```
Go to [http://localhost:8000/docs]()

## Repo Structure

Key app/service paths:

- libs/src/* --> DB clients, redis, rabbitmq and DB setup with migrations etc
- services/kiwi_app --> core application
- services/kiwi_app/auth --> Auth service
- services/kiwi_app/workflow_app --> workflow backend with APIs
- services/workflow_service --> core workflow service
- services/workflow_service/services/worker.py --> prefect worker entrypoint for running workflows

## License

Copyright (c) [2025] [KiwiQ AI]





