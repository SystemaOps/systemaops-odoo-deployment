# SystemaOps Odoo Deployment

Repository structure for SystemaOps Odoo 18.0 deployment.

## Repository Structure

```text
parent/
│
├── addons/
│   ├── CRM
│   ├── Sales
│   ├── Inventory
│   ├── Accounting
│   ├── HR
│   ├── Manufacturing
│   ├── Custom Addons
│   └── ...
│
├── config/
│   └── odoo.conf
│
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
├── backup_odoo.sh
└── README.md
```

## Quick Start

```bash
cd parent
docker compose up -d
```
