# Data Warehouse

Guardian Connector provides a secure, dedicated data store for each user, combining a PostgreSQL relational database and private file storage.

At a high level, the Guardian Connector data warehouse is designed around a simple idea: **user data should be stable, portable, and independent of any single application**. Files are treated as the primary source of truth, while databases and application-specific stores exist to make that data easier to query, visualize, and work with in day-to-day workflows. This separation allows applications to evolve, be upgraded, or even replaced without putting community data at risk, while ensuring that data remains accessible both inside and outside the platform.

## Data Warehouse Structure

### 📂 File-first approach

We prioritize storing data in file-based formats for flexibility and accessibility. Where possible, data is kept in durable, well-structured files and schemas (CSV, JSON, GeoJSON, GPX, KML) so that it remains portable and usable outside the platform.

Media content such as images, videos, and survey attachments is also stored in a dedicated file storage system.

Files are exposed to users through tools like [Filebrowser](https://docs.guardianconnector.net/reference/gc-toolkit/filebrowser/).

### 🗃️ Structured Data

In addition to being stored as user-accessible files, structured data is organized in a Postgres database called `warehouse`. This makes it easier for community organizations to query, visualize, and work with their data day to day using web applications like [Superset](https://docs.guardianconnector.net/reference/gc-toolkit/superset/) or [Guardian Connector Explorer](https://docs.guardianconnector.net/reference/gc-toolkit/gc-explorer/). 

Depending on the client and use case, structured data may also be stored as files such as SQLite databases, CSVs, GeoJSON, or other formats.

### 🔒 Access Control and Data Integrity

We maintain data integrity by isolating user-accessible data in a `persistent-storage/datalake` directory, which is exposed through Filebrowser. 

Other application-related files—such as SQLite databases or other structured data files read by applications, temporary files, and logs—are stored elsewhere within `persistent-storage/`. This separation protects the integrity and functionality of applications while ensuring users only have access to data they need.

### 🧠 Application Metastores (Internal)

Many Guardian Connector applications maintain their own internal “metastore” to track configuration, state, metadata, or job history required for the application to function.

These metastores are not part of the user data warehouse and are not exposed to users.

Examples include:
- Superset dashboards, charts, and user settings
- Windmill workflows, runs, and credentials
- Filebrowser metadata and permissions

Metastores are typically implemented as:
- Dedicated databases on the same Postgres server (for example, `superset_metastore`, `windmill`, or `guardianconnector`)
- Internal SQLite databases or files stored outside the exposed `persistent-storage/datalake` directory, or as Docker volume mounts on the host VM.

Docker volumes offer better performance for disk-intensive operations like SQLite databases and are backed up via VM backups, while network storage provides easier external access but may have higher latency and currently lacks automated backup in Azure deployments. At present, the choice of storage location is determined by the application and its requirements.

## 👉 Examples

### Filebrowser

[Filebrowser](https://docs.guardianconnector.net/reference/gc-toolkit/filebrowser/) has access to the `persistent-storage/datalake` directory and allows users to browse, upload, download, and share files within their Guardian Connector instance. It also uses its own SQLite database to store application metadata, currently stored as a persistent Docker volume on the VM.

### GC Explorer

[Guardian Connector Explorer](https://docs.guardianconnector.net/reference/gc-toolkit/gc-explorer/) reads data from the Postgres `warehouse` database and renders media files using [share link](https://docs.guardianconnector.net/reference/gc-toolkit/filebrowser/#generating-share-links) generated in  Filebrowser. It also uses its own metastore database on the same Postgres server, typically named `guardianconnector`.

### Superset

[Apache Superset](https://docs.guardianconnector.net/reference/gc-toolkit/superset/) reads data from the Postgres `warehouse` database and uses its own metastore database on the same Postgres server, typically named `superset_metastore`.

### Windmill

[Windmill](https://docs.guardianconnector.net/reference/gc-toolkit/gc-scripts-hub/) and uses its own metastore database on the same Postgres server, typically named `windmill`.

### GC Wildlife Explorer

[Guardian Connector Wildlife Explorer](https://github.com/conservationmetrics/gc-wildlife-explorer) reads data from a CSV file stored in the `persistent-storage/gc-wildlife` directory and renders media (such as camera trap photos or bioacoustic audio) from a specified subdirectory within `persistent-storage/datalake`.

On initialization, if no CSV file is found in `persistent-storage/gc-wildlife`, the application will attempt to locate the CSV in `persistent-storage/datalake` and copy it into place.