# ResidueGuard | Digital Farm Management Portal

ResidueGuard is a digital farm management portal designed for livestock farmers. It enables active tracking of Maximum Residue Limits (MRL) and Antimicrobial Usage (AMU) to ensure food safety compliance and support veterinary drug stewardship.

---

## 🚀 Key Features

*   **Unified Telemetry Dashboard**: Real-time stats on Overall AMU Index ($mg / kg$), MRL Compliance Rate (%), active operations, and animals in withdrawal.
*   **Multi-Tenant Partitioning**: Individual users are completely isolated under a `tenant_id`. New registrations spawn a blank slate farm workspace.
*   **Live Countdown Timers**: Second-by-second countdown trackers showing remaining clearance times for animals currently under withdrawal.
*   **Residue Decay Simulator**: Dynamic line charts plotting exponential drug concentration clearance against safety MRL threshold lines.
*   **Stewardship Audit Logs**: High-detail logs showing veterinarian reference, dosage concentration, and exports for CSV/JSON auditing.
*   **Role-Based Access Control**:
    *   **Administrator**: Full write and operation access (registers animals, logs treatments, updates drug profiles).
    *   **Standard Operator**: Read-only access to metrics, logs, and charts.

---

## 🛠️ Tech Stack

*   **Frontend**: HTML5, CSS3 (Vanilla Dark Glassmorphism), JavaScript (Vanilla ES6)
*   **Backend**: Python Flask (REST API)
*   **Database**: SQLite (`farm.db`)
*   **Charts**: Chart.js (Loaded via CDN)

---

## 📦 Project Structure

```text
Farm-portal/
├── app.py                 # Flask server, REST controllers, session auth, and decay math
├── database.py            # SQLite schema initialization and mock seeding
├── farm.db                # SQLite database file (created on init)
├── requirements.txt       # Python package dependencies
├── templates/
│   └── index.html         # Main single-page layout (Login/Register and Portal views)
└── static/
    ├── css/
    │   └── style.css      # CSS styles, transitions, glows, and keyframe animations
    └── js/
        └── app.js         # API requests wrapper, timers loop, and Chart.js builders
```

---

## 🔧 Installation & Launch

### 1. Prerequisites
Ensure you have **Python 3** installed.

### 2. Install Dependencies
Navigate to the project root and install Flask:
```bash
pip install -r requirements.txt
```

### 3. Initialize the Database
Run the setup script to initialize the SQLite database and seed the default accounts:
```bash
python database.py
```

### 4. Run the Server
Launch the Flask development server:
```bash
python app.py
```
By default, the application will be active at **`http://127.0.0.1:5000`** in your web browser.

---

## 🔑 Demo Accounts

The database includes two default preseeded accounts sharing the default demo farm data:

| Role | Username | Password | Access Rights |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | Full Read & Write |
| **Standard Worker** | `employe` | `worker` | Read-Only View |

*Note: You can register a new account on the login screen. Self-registered users are assigned their own isolated, blank farm database with full Administrator rights over their own records.*
