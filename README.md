# 🏭 SmartFactory API — Multi-Tenant IoT Platform

SmartFactory_API is a **multi-tenant IoT data management platform** built with **Django, PostgreSQL, and Docker**.  
Each customer runs in an **isolated tenant environment** with separate database, environment variables, and licensing controls.  

This setup enables full multi-customer deployment automation with a single script.

---

## 🚀 Features

- 🧩 **Multi-tenant setup automation** (`multi_tenant_setup.sh`)
- 🐳 **Dockerized architecture** for easy deployment
- 🔐 **License control** (trial and expiry support)
- 🧱 **Isolated PostgreSQL database per tenant**
- 🧑‍💻 **Auto-created Django admin user**
- ⚙️ **Extensible** for industrial IoT or general sensor data
- 📊 **IoT data models** for devices, sensors, and metrics
- 🌐 **Cross-platform**: works on macOS, Linux, and Windows (with Docker Desktop)

---

## 🧰 Prerequisites

Before running the setup, ensure you have:

| Tool | Version | Install Guide |
|------|----------|----------------|
| **Docker Engine / Desktop** | 20.10+ | [Install Docker](https://docs.docker.com/get-docker/) |
| **Docker Compose** | v2+ | Usually included in Docker Desktop |
| **Git** | any | [Install Git](https://git-scm.com/downloads) |
| **Bash** | default | (included on macOS/Linux; use Git Bash or WSL on Windows) |

---

## 🗂️ Project Structure

```
SmartFactory_API/
│
├── api/                     # Django app (models, views, admin, etc.)
├── iot_platform/            # Django project settings
├── Dockerfile               # Build instructions for Django app
├── docker-compose.yml       # Defines web + db services
├── multi_tenant_setup.sh    # Tenant setup automation script
├── requirements.txt         # Python dependencies
├── .env.template            # Template for base environment variables
└── README.md                # This documentation
```

---

## ⚙️ One-Time Setup

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/<your-username>/SmartFactory_API.git
cd SmartFactory_API
```

### 2️⃣ Make the setup script executable

```bash
chmod +x multi_tenant_setup.sh
```

---

## 🏗️ Create a New Tenant

Use the **multi-tenant setup script** to create a new customer environment.

```bash
./multi_tenant_setup.sh <customer_name> [license_days] [http_port]
```

### Example:

```bash
./multi_tenant_setup.sh acme 30 8010
```

✅ What this does:
1. Copies your SmartFactory_API codebase → `acme__iot/`
2. Creates `.env.acme_` with DB credentials, ports, and license info
3. Builds and starts Docker containers (`web` + `db`)
4. Runs Django migrations & static file collection
5. Creates default admin user:
   - **Username:** `admin`
   - **Password:** `SmartFactory@123`

---

## 🌐 Access the Tenant Admin Console

Once the setup completes, open:

👉 [http://localhost:8010/admin](http://localhost:8010/admin)

**Login Credentials:**
```
Username: admin
Password: SmartFactory@123
```

---

## 🧾 Example Output

```
✅ acme_ environment is ready!
🔑 License Key: b8db8590279ec5d37a292981723d7246
📅 Valid From: 2025-10-24  →  2025-11-23
🌐 URL: http://localhost:8010
```

---

## 🧩 Managing Tenants

### Stop a Tenant
```bash
docker compose -p acme__iot down -v
```

### View Logs
```bash
docker compose --env-file .env.acme_ -p acme__iot logs -f
```

### Recreate / Rebuild
```bash
./multi_tenant_setup.sh acme 30 8010
```

### Remove Completely
```bash
rm -rf acme__iot
```

---

## 💾 Database Access

Each tenant gets its own PostgreSQL instance and database:

| Variable | Description |
|-----------|-------------|
| `POSTGRES_DB` | Database name (e.g. `acme__db`) |
| `POSTGRES_USER` | Tenant DB user |
| `POSTGRES_PASSWORD` | Tenant DB password |
| `POSTGRES_PORT` | Randomized internal port between 5500–6500 |

You can connect using:

```bash
docker exec -it acme__iot-db-1 psql -U acme__user -d acme__db
```

---

## 🧿 Licensing System

Every tenant receives:
- `LICENSE_KEY`
- `LICENSE_START`
- `LICENSE_END`
- `LICENSE_SERVER_URL` (default: placeholder `https://license.smartfactory.com/verify`)

During setup, license verification runs automatically (SSL warnings are normal in local mode).

### Extending License Period
To extend a license, simply rerun the setup with a new duration:
```bash
./multi_tenant_setup.sh acme 60 8010
```

---

## 🧰 Windows Users

On Windows, run the same commands inside:

- **Git Bash**, or  
- **Windows Subsystem for Linux (WSL2)**

If Docker Desktop is installed, it will seamlessly integrate.

Example:
```bash
bash multi_tenant_setup.sh acme 30 8010
```

Then open `http://localhost:8010/admin` in your browser.

---

## 🔒 Security Recommendations

- Change the default password (`SmartFactory@123`) after first login.
- Use HTTPS reverse proxy (e.g., Nginx or Traefik) for production.
- Store `.env` files securely — they contain DB credentials and license keys.
- Rotate DB credentials periodically.

---

## 🧩 Useful Commands

| Command | Description |
|----------|-------------|
| `docker compose ps` | Show running containers |
| `docker compose down -v` | Stop and remove containers + volumes |
| `docker system prune -af` | Clean up unused Docker data |
| `docker compose logs -f` | Stream application logs |

---

## 📜 License

This project includes a **basic license control mechanism** (for demonstration).  
Production users should integrate a real licensing server and HTTPS certificate validation.

---

## 👨‍💻 Author

**Sameer Wadekar**  
Industrial IoT | Edge AI | Automation Systems
