# Requirements

This artifact was tested on macOS with Docker Desktop. The verified reproduction path uses stored LLM outputs and does not require API credentials.

## Hardware

Recommended:

- 8 CPU cores or more
- 16 GB RAM or more
- 25 GB free disk space for Docker images, Maven dependencies, and reproduced outputs

Quick Start uses much less time and storage than the full RQ2/RQ3 repair runs.

## Software

Host environment used by the authors:

- Java: OpenJDK `20.0.2`
- Maven: Apache Maven `3.9.11`
- Python: `3.13.2`
- Docker: `28.4.0`
- Docker Compose: `v2.39.4-desktop.1`

The Maven project compiles with Java 8 source/target compatibility. ARepair repair runs inside Docker using Ubuntu 18.04, OpenJDK 8, Maven, and Python 3.

## Dependency Files

The artifact includes these dependency/configuration files:

- `pom.xml` for the Java evaluation harness
- `Dockerfile.arepair` for the ARepair container
- `docker-compose.arepair.yml` for Docker Compose execution
- `requirements.txt` for Python dependency documentation

No Python packages need to be installed for the verified reproduction path, which re-scores stored LLM outputs. Regenerating new LLM outputs from scratch is optional, outside the verified reproduction path, and would require a Gemini API key plus the Python Gemini SDK.

## Setup

From the artifact root:

```bash
mvn -q compile
docker compose -f docker-compose.arepair.yml build arepair
```

If your system uses the legacy Docker Compose binary, replace `docker compose` with `docker-compose`.

## Runtime Expectations

Approximate runtimes on the authors' development machine:

- `bash RQ1_Generation/run.sh --quick`: under a minute
- `bash RQ2_Validation/run.sh --quick`: a few minutes
- `bash RQ3_Repair/run.sh --quick`: a few minutes
- `bash RQ1_Generation/run.sh --full`: minutes
- `bash RQ2_Validation/run.sh --full`: several hours
- `bash RQ3_Repair/run.sh --full`: several hours

RQ2 and RQ3 full modes invoke ARepair in Docker and are the slowest stages.
