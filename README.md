# Project Name

## Overview

Multi-service, multi-tier, Kubernetes-based platform.

## Repository Structure

```text
.
├── services/      # Microservices
├── libs/         # Shared libraries
├── infra/        # Infrastructure code
├── scripts/      # Utility scripts
├── db/      # database
├── docs/         # Documentation
└── tests/        # Common test utilities
```

## Services

- Notifications Service: Real-time notifications and HITL
- Auth Service: Authentication and authorization
- LinkedIn Service: LinkedIn integration
- Billing Service: Payment processing and subscription management

## Getting Started

### Prerequisites

- Python 3.11+
- Poetry
- Docker & Docker Compose
- kubectl
- Helm

### Installation

1. Install Poetry:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Install dependencies:

```bash
poetry install
```

### Development

1. Start local services:

```bash
docker-compose up -d
```

2. Run tests:

```bash
poetry run pytest
```

## Contributing

1. Create branch from `develop`
2. Make changes
3. Submit pull request

## License

Copyright (c) [2025] [KiwiQ AI]

