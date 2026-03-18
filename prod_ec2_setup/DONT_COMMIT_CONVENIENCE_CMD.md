# WEAVIATE CLEANUP
docker-compose -f docker-compose-dev.yml exec weaviate \
  sh -c "find /var/lib/weaviate -type f -name '*.db.tmp' -exec rm -f {} \;"

docker-compose -f docker-compose.prod.yml exec weaviate \
  sh -c "find /var/lib/weaviate -type f -name '*.db.tmp' -exec rm -f {} \;"

## Find weaviate volume correct
docker volume ls

`kiwiq-backend_weaviate_data`

docker run --rm \
  -v weaviate_data:/var/lib/weaviate \
  alpine:3.18 \
  sh -c "find /var/lib/weaviate \
    -type f \
    \\( -name 'segment-*.db' -o -name '*.db.tmp' \\) \
    -exec rm -f {} +"

# SSH / SCP

ec2-user@<YOUR_SERVER_IP>

ssh -i "~/.ssh/your-key.pem" ec2-user@<YOUR_SERVER_IP>

scp -i ~/.ssh/your-key.pem -r "/path/to/your/project/.env.prod" ec2-user@<YOUR_SERVER_IP>:/home/ec2-user/stealth-backend/
scp -i ~/.ssh/your-key.pem -r "/path/to/your/project/secrets" ec2-user@<YOUR_SERVER_IP>:/home/ec2-user/stealth-backend/secrets

## Copy server file
scp -i ~/.ssh/your-key.pem -r ec2-user@<YOUR_SERVER_IP>:/home/ec2-user/stealth-backend/services/workflow_service/services/scraping/browsers/scrapeless/data/scrapeless_profiles_cache.json .

## Copy to server file
scp -i ~/.ssh/your-key.pem -r "/path/to/your/project/services/workflow_service/services/scraping/browsers/scrapeless/data/scrapeless_profiles_cache.json.backup" ec2-user@<YOUR_SERVER_IP>:/home/ec2-user/stealth-backend/services/workflow_service/services/scraping/browsers/scrapeless/data/ && scp -i ~/.ssh/your-key.pem -r "/path/to/your/project/services/workflow_service/services/scraping/browsers/scrapeless/data/scrapeless_profiles_cache.json" ec2-user@<YOUR_SERVER_IP>:/home/ec2-user/stealth-backend/services/workflow_service/services/scraping/browsers/scrapeless/data/

# docker compose

## bash / sh exec
docker-compose -f docker-compose.prod.yml exec nginx sh
docker-compose -f docker-compose.prod.yml exec app bash

```bash
docker-compose -f docker-compose.prod.yml exec prefect-agent bash
echo $RAPID_API_HOST
```

### DEV exec
docker-compose -f docker-compose-dev.yml exec prefect-agent bash

## DEV YML
./scripts/graceful_flow_cancel_prefect_agent_dev.sh && docker-compose -f docker-compose-dev.yml up -d --build
./scripts/graceful_flow_cancel_prefect_agent_dev.sh && docker-compose -f docker-compose-dev.yml up -d --build app prefect-agent
./scripts/graceful_flow_cancel_prefect_agent_dev.sh && docker-compose -f docker-compose-dev.yml up -d --build prefect-agent
docker-compose -f docker-compose-dev.yml up -d --build weaviate

./scripts/graceful_flow_cancel_prefect_agent_dev.sh && docker-compose -f docker-compose-dev.yml down

## PROD YML!
./scripts/graceful_flow_cancel_prefect_agent.sh && sudo docker-compose -f docker-compose.prod.yml up -d --build app prefect-agent prefect-server nginx
./scripts/graceful_flow_cancel_prefect_agent.sh && sudo docker-compose -f docker-compose.prod.yml up -d --build prefect-server
sudo docker-compose -f docker-compose.prod.yml up -d --build nginx

./scripts/graceful_flow_cancel_prefect_agent.sh && sudo docker-compose -f docker-compose.prod.yml up -d --build prefect-agent

## NGINX RELOAD (after config changes)
# Reload nginx config without restarting container
sudo docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
# Or restart nginx container if needed
sudo docker-compose -f docker-compose.prod.yml restart nginx

docker-compose -f docker-compose.prod.yml exec prefect-agent bash


./scripts/graceful_flow_cancel_prefect_agent.sh && sudo docker-compose -f docker-compose.prod.yml up -d --build
### NOTE: when upgrading server, you may have to run below CMD to make nginx sync with app new IP!
docker restart kiwiq_prod_nginx

./scripts/graceful_flow_cancel_prefect_agent.sh && docker-compose -f docker-compose.prod.yml down

### Build only APP!
sudo docker-compose -f docker-compose.prod.yml up app --build -d
### Build only worker
./scripts/graceful_flow_cancel_prefect_agent.sh && sudo docker-compose -f docker-compose.prod.yml up prefect-agent --build -d

docker-compose -f docker-compose.prod.yml up -d --force-recreate prefect-server

TEMP_SERVICE_VAR=prefect-agent


# LOGS
docker-compose -f docker-compose.prod.yml logs $TEMP_SERVICE_VAR

docker-compose -f docker-compose.prod.yml logs app -f
docker-compose -f docker-compose.prod.yml logs --since 5m app -f
docker-compose -f docker-compose.prod.yml logs --since 20m app -f
docker-compose -f docker-compose.prod.yml logs --since 20m app
docker-compose -f docker-compose.prod.yml logs --since 20m prefect-agent -f
docker-compose -f docker-compose.prod.yml logs --since 20m prefect-server -f
docker-compose -f docker-compose.prod.yml logs --since 5m nginx -f


## Logs search with `less`
docker-compose -f docker-compose.prod.yml logs --since 10h prefect-agent 2>&1 | less

`As vim fan I prefer to use less and search with / (or ? for backwards search)`
[https://www.cyberciti.biz/faq/find-a-word-in-vim-or-vi-text-editor/](https://www.cyberciti.biz/faq/find-a-word-in-vim-or-vi-text-editor/)


## DEV LOGS
docker-compose -f docker-compose-dev.yml logs --since 20m app

docker-compose -f docker-compose-dev.yml logs --since 5m app -f

docker-compose -f docker-compose-dev.yml logs --since 5m prefect-agent -f

## NOTE: PROD APP LOGS IN FILES

cd ./logs
tail -n 200 kiwiq_backend.log

## COPY LOG FILE:
docker cp $(docker-compose -f docker-compose.prod.yml ps -q app):/app/logs ./logs



-- REMOVE ALL! -> dev docker compose file somehow removes both prod?? --

### RESTART PREFECT_AGENT AFTER CODE CHANGES:
#### DEV
./scripts/graceful_flow_cancel_prefect_agent_dev.sh && docker-compose -f docker-compose-dev.yml restart prefect-agent app
docker-compose -f docker-compose-dev.yml restart app

#### PROD
./scripts/graceful_flow_cancel_prefect_agent.sh && docker-compose -f docker-compose.prod.yml restart prefect-agent
docker-compose -f docker-compose.prod.yml restart nginx
./scripts/graceful_flow_cancel_prefect_agent.sh && docker-compose -f docker-compose.prod.yml restart app prefect-agent

## DEV YML!
docker-compose -f docker-compose-dev.yml exec app postgres

docker-compose -f docker-compose-dev.yml down --rmi all --volumes --remove-orphans

### RESTART PREFECT_AGENT AFTER CODE CHANGES:
./scripts/graceful_flow_cancel_prefect_agent_dev.sh && docker-compose -f docker-compose-dev.yml restart prefect-agent



# migrations

## LOCAL passwords
psql postgresql://<DB_USER>:<DB_PASSWORD>@localhost:5432/workflow_service

psql postgresql://<DB_USER>:<DB_PASSWORD>@localhost:5432/postgres

POSTGRES_HOST=postgres
POSTGRES_PORT="5432"
MONGO_HOST=mongo
RABBITMQ_HOST=rabbitmq
REDIS_HOST=redis


postgresql://<PROD_DB_USER>:<PROD_DB_PASSWORD>@localhost:5432/postgres


# Port Forwarding

## Forward a local port to a remote port
# Syntax: ssh -i <key_file> -L <local_port>:<remote_host>:<remote_port> <ssh_host>
# Example: Forward local port 8000 to remote port 8000
ssh -i "~/.ssh/your-key.pem" ec2-user@<YOUR_SERVER_IP>

ssh -i "~/.ssh/your-key.pem" -L 4200:localhost:4200 ec2-user@<YOUR_SERVER_IP>

## Forward multiple ports (add multiple -L flags)
# Example: Forward local ports 8000, 5432, and 27017 to corresponding remote ports
ssh -i "~/.ssh/your-key.pem" -L 8000:localhost:8000 -L 5432:localhost:5432 -L 27017:localhost:27017 ec2-user@<YOUR_SERVER_IP>

## Forward to a specific service in docker-compose
# Example: Forward local port 5432 to postgres container port 5432
ssh -i "~/.ssh/your-key.pem" -L 5432:postgres:5432 ec2-user@<YOUR_SERVER_IP>

## Background port forwarding (add -N -f flags)
# -N: Do not execute a remote command (useful for port forwarding only)
# -f: Run in background
ssh -i "~/.ssh/your-key.pem" -N -f -L 8000:localhost:8000 ec2-user@<YOUR_SERVER_IP>

# IP address browsing
https://<YOUR_SERVER_IP>/docs


# Copy standalone client
yes | cp -rf standalone_test_client/* ../standalone_test_client/


# Disk Utils
```bash
df -h --total
sudo du -xh --max-depth=1 / | sort -rh | head -n20
```

### Totals on 9th Aug 2025:
```bash
[ec2-user@<YOUR_SERVER_HOSTNAME> stealth-backend]$ df -h --total
Filesystem        Size  Used Avail Use% Mounted on
devtmpfs          4.0M     0  4.0M   0% /dev
tmpfs              16G     0   16G   0% /dev/shm
tmpfs             6.2G  1.6M  6.2G   1% /run
/dev/nvme0n1p1   1000G  143G  858G  15% /
tmpfs              16G     0   16G   0% /tmp
/dev/nvme0n1p128   10M  1.3M  8.7M  13% /boot/efi
tmpfs             3.1G     0  3.1G   0% /run/user/1000
total             1.1T  143G  898G  14% -
```


# DANGER!! --- Docker pruning / cleanup --- DANGER!!

sudo docker-compose -f docker-compose.prod.yml down --volumes
~~ sudo docker-compose -f docker-compose.prod.yml down --volumes --remove-orphans ~~
~~ sudo docker volume prune --all -f~~ 

# **** Start HERE for PROD disk cleanup! ****

## Without stopping docker
docker volume prune -f

### BEST for cleanup!
```bash
docker image prune -f
docker image prune -a -f
docker builder prune -af
```
### AVOID in PROD
```bash
docker volume prune               # removes ALL unused volumes
docker system prune --volumes     # same, nukes unused volumes
docker compose down -v            # removes this project's volumes
```


~~ docker-compose -f docker-compose-dev.yml down --volumes --remove-orphans~~ 

# Docker health checks

docker stats

sudo docker-compose -f docker-compose.prod.yml ps


# RAM USAGE
# Run `docker stats` to see current container resource usage




# Memory profiling and optimization basics
```python
# import timing
# PYTHONPROFILEIMPORTTIME=1 | PYTHONPATH=$(pwd):$(pwd)/services poetry run python -X importtime services/workflow_service/services/test_clients/test_worker_job.py 2> importtime.log
# poetry run tuna importtime.log

# memory flamegraph
# PYTHONPATH=$(pwd):$(pwd)/services poetry run python -m memray run -o memray.bin services/workflow_service/services/test_clients/test_worker_job.py
# poetry run memray flamegraph memray.bin -o memray.html
```
