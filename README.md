<!--
  Fibonacci — Clothing Warehouse Management System
  Repository: https://github.com/mmrezaqbi/Fibonacci
-->

<div align="center">

# 🧵 Fibonacci

### Clothing Warehouse Management System

A Django-powered inventory and warehouse management application for clothing businesses — built around product variants, color/size stock tracking, and auditable inventory movements.

<p>
  <a href="https://github.com/mmrezaqbi/Fibonacci"><img src="https://img.shields.io/badge/Project-Fibonacci-7c3aed?style=for-the-badge" alt="Fibonacci project"></a>
  <img src="https://img.shields.io/badge/Python-Django-092e20?style=for-the-badge&logo=django&logoColor=white" alt="Django">
  <img src="https://img.shields.io/badge/Database-SQLite-003b57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="MIT License"></a>
</p>

[Features](#-features) • [Tech Stack](#-tech-stack) • [Getting Started](#-getting-started) • [Usage](#-usage) • [Project Structure](#-project-structure) • [Security](#-security-notice)

</div>

---

## ✨ Overview

**Fibonacci** is a web-based warehouse and inventory management system designed for clothing shops and apparel warehouses.

Instead of treating every product as a single stock number, Fibonacci manages inventory at the **product variant** level — each combination of product, color, and size has its own SKU and stock quantity. Inventory changes are recorded as transactions, providing a history of stock activity.

The application includes a Persian (Farsi) interface and localized date handling for the Iranian calendar.

## 🚀 Features

### 📦 Product & Variant Management
- Create and manage clothing products.
- Store product details such as name, SKU, brand, category, gender, season, material, price, description, and image.
- Organize products by category.
- Define reusable colors and sizes.
- Generate product variants from selected color × size combinations.
- Assign a unique SKU to each variant and optionally store a barcode.
- Set a minimum-stock threshold for each variant.
- Activate or deactivate products and variants.

### 🧮 Inventory Tracking
- Track stock separately for each product color/size variant.
- Register incoming stock and outgoing stock.
- Prevent outgoing transactions from exceeding available stock.
- Update stock automatically when a transaction is recorded.
- Record the warehouse, quantity, transaction type, note, timestamp, and user who created the transaction.
- Keep stock transactions immutable after creation; corrections should be recorded as compensating transactions.
- Use database transactions to keep multi-line stock operations consistent.

> **Inventory model:** stock quantity is stored on each product variant. Transactions are associated with a warehouse, but the current implementation does not maintain a separate stock balance per warehouse.

### 📊 Dashboard
- View the number of active products.
- See total stock across active variants.
- Monitor low-stock variants.
- Review today's inventory transactions.
- Access recent stock activity.

### 🔎 Product Search & Filtering
- Search products by name, model SKU, brand, variant SKU, or barcode.
- Filter by category and gender.
- Filter products by stock status.
- Browse results with pagination.
- View product details, including color/size stock matrices and recent transactions.

### 📈 Reports & CSV Export
- Review inventory transaction history.
- Filter transactions by search term, date range, transaction type, and warehouse.
- View stock reports with category, gender, and stock-status filters.
- Export transaction and stock reports to CSV.
- Format CSV output for Persian/Excel compatibility.
- Accept Jalali (Persian) and Gregorian dates in report filters.

### 🛠️ Django Admin
- Manage products, categories, warehouses, colors, sizes, variants, and users.
- Inspect product stock matrices.
- Search and filter product variants.
- View stock transaction history.
- Prevent editing or deleting recorded inventory transactions through the admin interface.

### 👤 User Accounts
- Custom Django user model.
- User profile fields for phone number, country code, avatar, address, birthday, gender, and additional identity/profile information.
- Login-protected application pages.

## 🧰 Tech Stack

| Component | Technology |
|---|---|
| Backend | Python / Django |
| Database (default) | SQLite |
| Frontend | Django Templates, HTML, CSS, JavaScript |
| Static assets | CSS and JavaScript |
| Media | Django media files / uploaded product images |
| Localization | Persian (Farsi), `Asia/Tehran`, Jalali date utilities |
| Admin | Django Admin |

The project settings currently identify **Django 6.1.2** as the generation version. The repository does not currently include a dependency lockfile or `requirements.txt`; install a compatible Django version and Pillow for image handling.

## 🖥️ Getting Started

Follow these steps to run Fibonacci locally for development.

### Prerequisites

- Python **3.12 or newer** (use a Python version compatible with your installed Django release).
- `pip`
- Git

### 1. Clone the repository

```bash
git clone https://github.com/mmrezaqbi/Fibonacci.git
cd Fibonacci
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pyton -m pip install --upgrade pip
python -m pip install "Django==6.1.2" Pillow
```

> If your environment uses a different Django version, make sure it is compatible with the project and update the command accordingly. Add all project dependencies to a requirements.txt before sharing or deploying the application.

### 4. Apply database migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

The default configuration uses SQLite and creates the database file locally.

### 5. Create an administrator account

```bash
python manage.py createsuperuser
```

Follow the prompts to set your admin username and password.

### 6. Start the development server

```bash
python manage.py runserver
```

Open the application:

- **Application:** http://127.0.0.1:8000/
- **Django Admin:** http://127.0.0.1:8000/admin/

The development server is intended for local development only.

## 🗂️ Project Structure

```text
Fibonacci/
├── accounts/                 # Custom user model, authentication and account admin
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── admin.py
├── application/              # Main inventory and warehouse application
│   ├── models.py             # Products, variants, stock transactions, warehouses
│   ├── views.py              # Dashboard, product pages, stock movements
│   ├── forms.py              # Product and stock movement forms
│   ├── reports.py            # Stock and transaction reports / CSV exports
│   ├── admin.py              # Custom Django Admin configuration
│   ├── dates.py               # Jalali/Gregorian date parsing and formatting
│   ├── jalali.py              # Jalali calendar conversion utilities
│   └── urls.py
├── config/                    # Django project configuration
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
├── extensions/                # Shared date and utility helpers
├── templates/                 # Django HTML templates
├── static/                    # CSS and JavaScript assets
├── media/                     # Uploaded product and profile media
├── manage.py                  # Django management entry point
├── LICENSE                    # MIT license
└── README.md
```

## 🧭 Usage

### Initial setup

After creating your administrator account, open Django Admin and add the basic data needed by the inventory workflow:

1. **Categories** — organize your clothing products.
2. **Warehouses** — define the warehouse locations used on stock transactions.
3. **Colors** — add colors and, where applicable, a short color code and HEX value.
4. **Sizes** — define sizes and their display order.
5. **Products** — create products and configure their attributes and variants.

### Create a product

1. Open the product creation page.
2. Enter the product's name, SKU, category, brand, gender, season, material, price, and other available details.
3. Select one or more colors and sizes.
4. Set the minimum-stock threshold.
5. If entering initial stock, select a warehouse and fill in the quantities for the relevant color/size combinations.
6. Save the product.

The application creates the selected product variants and records initial stock as incoming inventory transactions.

### Register stock movements

- **Stock In:** select a product, choose a warehouse, enter quantities for the relevant variants, and submit.
- **Stock Out:** select a product and warehouse, enter outgoing quantities, and submit. The application validates stock availability before recording the movement.

Stock changes are recorded in the transaction history. Recorded transactions are designed to remain immutable.

### Review reports

Use the reports area to review inventory movements or stock levels. Apply available filters and export the resulting data as CSV when needed.

## 🧱 Core Data Model

The main inventory entities are:

| Model | Purpose |
|---|---|
| `Category` | Product classification |
| `Warehouse` | Warehouse/location metadata |
| `Color` | Reusable color definitions |
| `Size` | Reusable size definitions |
| `Product` | General clothing product information |
| `ProductVariant` | Product + color + size combination with its own SKU and stock |
| `StockTransaction` | Immutable incoming/outgoing stock movement record |
| `CustomUser` | Application user and profile information |
| `CountryCode` | International phone country codes |

### Stock transaction flow

```text
Product
  └── ProductVariant (color + size)
        ├── SKU / barcode
        ├── Current stock
        └── StockTransaction
              ├── IN  → increases variant stock
              └── OUT → decreases variant stock
```

Stock-out operations validate available quantities. Multi-line stock movement forms use database transactions so a failed line can roll back the complete operation.

## 🖥️ Configuration

Project configuration is located in:

- `config/settings.py` — Django settings, database, installed apps, locale, static/media configuration.
- `config/urls.py` — root URL outing.
- `application/urls.py` — inventory, product, movement, and report routes.
- `accounts/urls.py` — account routes.

### Database

SQLite is configured by default. For production, configure a supported production database and keep credentials outside source control.

### Static and media files

- Static files are served from `/static/`.
- Uploaded media is served from `/media/` in the current development configuration.
- Configure static and media storage appropriately for production deployment.

## 🔐 Security Notice

**This repository is currently configured for development, not production.** Before deploying it publicly:

- Replace the committed development Django `SECRET_KEY` and load the production secret from environment variables.
- Set `DEBUG = False`.
- Replace the wildcard `ALLOWED_HOSTS` setting with your actual hostnames.
- Configure HTTPS, secure cookies, CSRF trusted origins, and appropriate security headers.
- Configure production static/media serving and database credentials.
- Review user profile fields and access permissions, especially fields containing personal information.
- Do not commit real user data, uploaded private files, database files, or production secrets.

See the [Django deployment checklist](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/) before going live.

## 🧪 Tests

Run Django's test discovery with:

```bash
python manage.py test
```

The repository currently contains minimal test scaffolding. Add model, stock transaction, permissions, and report tests as the project evolves.

## 🛣️ Roadmap

Potential next steps for the project:

- [ ] Add a pinned `requirements.txt` and dependency management.
- [ ] Add automated tests for stock consistency and concurrent stock movements.
- [ ] Add warehouse-specific stock balances if multiple warehouses need independent inventory.
- [ ] Add role-based permissions for warehouse operators and managers.
- [ ] Add deployment configuration and environment-based settings.
- [ ] Add screenshots or a short demo GIF to showcase the interface.
- [ ] Add CI checks for formatting, linting, and tests.

## 🤝 Contributing

Contributions, bug reports, and feature suggestions are welcome.

1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature
   ```
3. Make your changes and add tests where appropriate.
4. Run the test suite:
   ```bash
   python manage.py test
   ```
5. Commit your changes and open a Pull Request.

For significant changes, open an issue first to discuss the proposed approach.

## 📄 License

Fibonacci is distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

## 👨‍💻 Author

**Mohamad Reza Qarebaqi**

- GitHub: [@mmrezaqbi](https://github.com/mmrezaqbi)
- Repository: [mmrezaqbi/Fibonacci](https://github.com/mmrezaqbi/Fibonacci)

---

<div align="center">

**Built with Django · Designed for clothing inventory workflows**

If Fibonacci is useful to you, consider giving the repository a ⭐

</div>
