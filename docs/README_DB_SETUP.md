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
```

7. apply migration script

```bash
PYTHONPATH=$(pwd):$(pwd)/services poetry run alembic -c libs/src/db/alembic.ini upgrade head
```

8. (Only use this to reset Alembic's HEAD)

```bash
# <full postgress url>
psql postgresql://db_admin:db_admin_password@localhost/db_name
```

```sql
DROP TABLE alembic_version;
```

