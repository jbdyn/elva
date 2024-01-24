# As a user, I want ...

- ... to share my files with my peers with no hassle
- ... to not resolve merge conflicts
- ... have a data backup
- ... to be able to rerun the data pipeline
- ... read what others have done
- ... access my files whereever I am within minimal steps


# Layout

- Y-CRDT is backbone of ELVA
- backend: background thread (networking, health check, syncing)
- frontend: requests over IPC by CLI, TUI (textual), or HTTPS (?)
- file watchers (multiple peers, with each peer having multiple connections, one per app with Y-CRDT)
- version control (text files): Git
- version control (non-text files): DVC (+no symlinks?), DataLad (-Windows?, -unlocking)
- reproducibility: declared pipelines with DVC (+super easy, +shell commands), Kedro (-complicated), Apache Airflow (-complicated), Luigi (-complicated), Prefect (-account), custom (-time)
- metadata management: MetaLad
- FAIR: GIN-G

# TUI

- file tree
- network/sync status
- chat
- history
- tasks/issues
