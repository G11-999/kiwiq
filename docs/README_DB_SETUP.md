## Setup

### Postgres - (Without Docker)

#### Brew installation
1. Download postgres
```bash
brew install postgresql
```
2. Start postgres
```bash
brew services start postgresql
```
#### Installer from postgres.org [X]

1. Download postgres installer from postgres.org
2. Install postgres
3. Add postgres to path via `.zshrc` and reload terminal

```bash
echo 'export PATH="/Library/PostgreSQL/17/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```


##### 4. Start postgres

```bash
sudo -u postgres pg_ctl -D /Library/PostgreSQL/17/data start
```

5. Login as superuser and enter postgres superuser password

```bash
sudo -u postgres psql
```

6. Create new admin user

```sql
CREATE ROLE db_admin WITH LOGIN SUPERUSER PASSWORD 'db_admin_password';
```

7. Login as new admin user and enter password

```bash
psql -U db_admin -d postgres
```

8. Create new database
```sql
CREATE DATABASE workflow_service;
```

`NOTE: Create prefect DB too, it should be same as $PREFECT_DB and different from *workflow_service* DB!`
```sql
CREATE DATABASE prefect_db;
```

`NOTE: Create separate Langgraph DB since during migrations, its created tables get dropped leading to loss of data! Make sure to update .env var DATABASE_URL_LANGGRAPH`
```sql
CREATE DATABASE langgraph_db;
```

Drop existing database

```sql
DROP DATABASE workflow_service;
```

```bash
psql -U db_admin -d workflow_service

SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

```

### SQLAlchemy, Alembic, Psycopg2, sqlmodel
NOTE: sqlmodel is a drop-in replacement for SQLAlchemy with pydantic features and typing.

1. Install SQLAlchemy and Alembic

```bash
poetry add sqlalchemy alembic psycopg2-binary sqlmodel
```

2. Setup DB URL in `.env`

```bash
DATABASE_URL="postgresql://db_admin:db_admin_password@localhost/db_name"
```

3. setup database.py to create db session using sqlmodel wrappers

4. INIT (first time) setup alembic to create migrations

```bash
poetry run alembic init alembic
```

modify alembic/env.py
```bash
target_metadata = SQLModel.metadata

# pass the created engine from database.py to alembic
# ...
connectable = engine
```

5. TL;DR: Import any new models to env.py and database/session.py both!

Create a new model inheriting from SQLModel from sqlmodel and import it into alembic's env.py.
Importing is important for alembic to know about the new model.
ALSO: import all created models into database.py to ensure they are loaded and sqlmodel metadata recognizes them during runtime!
TODO: find better fix!

5.b. Modify `alembic/script.py.mako` to import sqlmodel for alembic to work with sqlmodel

```python
import sqlmodel
```

5.c. Modify alembic.ini file to change script location (the path from root directory from which migration commands will be run)

```ini
script_location = libs/src/db/alembic
```

6. generate migration script

```bash
# migration #1
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Initial revision"

# migration #2
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Prefect RUN ID"

# migration #3
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Prefect RUN ID convert to comma separated list"

# migration #4
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add workflow name field for workflow runs"

# migration #5
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add workflow config override model and run tag field for annotating experiments"

# migration #6
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add Chat Thread model"

# migration #7
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add 'node_is_tool' in NodeTemplate"

# migration #8
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add tags in chat thread"

# migration #9
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Billing models"

# migration #10
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Make Billing model fields TZ aware"

# migration #11
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Make Billing model user / org fields nullable; add TZ to datetime fields in auth / workflow models"

# migration #12
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Make Billing model plan_id in subscription nullable"

# migration #13
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "change credits to float"

# migration #14
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Change stripe billing fields"

# migration #15
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "add external billing ID to Orgs"

# migration #16
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "remove stripe_customer_id from OrganizationSubscription"

# migration #17
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "add receipt field to credit purchase"

# migration #18
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "add stripe events model"

# migration #19
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "add primary billing email to Org"

# migration #20
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add LinkedIn Oauth model"

# migration #21
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add LinkedIn Oauth model cascade delete on user delete"

# migration #22
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add LinkedIn integration models"

# migration #23
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add proper relationship cascade for user / org delete, add is_active to org"

# migration #24
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "workflow run workflow_id SET NULL"

# migration #25
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "promotion code usage promo ID SET NULL constraint"

# migration #26
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add admin adjustment credit source type"

# migration #27
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add data job model"

# migration #28
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Assets and User Resume Metadata service"

# migration #29
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add parent workflow run ID field to WorkflowRun model"

# migration #29
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add input hash field to WorkflowRun model"

# migration #30
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add retry_count field in workflowrun"

# migration #30
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini revision --autogenerate -m "Add applied override tags field to workflow runs"


```

7. apply migration script

```bash
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini upgrade head
```

7.b. DOWNGRADE MIGRATION

```bash
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini downgrade -1
```

8. (Only use this to reset Alembic's HEAD)

```bash
# <full postgress url>
psql postgresql://db_admin:db_admin_password@localhost/workflow_service
```

```sql
DROP TABLE alembic_version;
```

9. DB reset DEBUGGING

for errors like below
```bash
FATAL:  could not write lock file "postmaster.pid": No space left on device

docker volume rm $(docker volume ls -q)
```

