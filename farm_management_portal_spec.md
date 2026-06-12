# Digital Farm Management Portal for MRL and AMU Monitoring

## Project Title

Digital Farm Management Portal for Monitoring Maximum Residue Limits (MRL) and Antimicrobial Usage (AMU) in Livestock

## Problem Statement

Livestock producers and regulators face growing challenges in ensuring food safety and animal welfare due to inadequate monitoring of antibiotic usage and chemical residue levels. Existing systems often lack centralized, real-time tracking of Maximum Residue Limits (MRL) and Antimicrobial Usage (AMU), leading to inconsistent compliance, delayed reporting, and increased risk of unsafe animal products entering the market.

This project seeks to develop a digital portal that enables farms to record, track, analyze, and report AMU and MRL data, ensuring compliance with regulatory standards while improving transparency and operational decision-making.

## Project Objectives

1. Create a centralized digital platform for recording livestock antimicrobial treatments and residue test results.
2. Provide automated monitoring of MRL compliance across different animal products and chemical classes.
3. Enable tracking of Antimicrobial Usage (AMU) metrics, including drug type, dosage, treatment date, and withdrawal periods.
4. Generate clear visual reports and alerts for farmers, veterinarians, and regulators.
5. Improve traceability of livestock treatment and testing history to support food safety audits.
6. Support data-driven decisions to reduce antimicrobial overuse and improve residue management practices.

## Model List

- User
- Farm
- Animal
- AntimicrobialTreatment
- ResidueTest
- ProductSample
- RegulationStandard
- Alert
- Report

## Data Models and Tables

### 1. `User`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| username | string | Login username |
| email | string | User email address |
| password_hash | string | Encrypted password |
| role | string | User role (farmer, veterinarian, regulator) |
| created_at | datetime | Account creation timestamp |
| updated_at | datetime | Last profile update timestamp |

### 2. `Farm`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| name | string | Farm name |
| location | string | Farm location or address |
| owner_id | integer | References `User` owner |
| size_acres | float | Farm area size |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

### 3. `Animal`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| farm_id | integer | References `Farm` |
| species | string | Animal species (e.g., cattle, poultry) |
| breed | string | Breed or type |
| identifier | string | Animal ID or herd tag |
| age_months | integer | Approximate age in months |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

### 4. `AntimicrobialTreatment`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| animal_id | integer | References `Animal` |
| farm_id | integer | References `Farm` |
| drug_name | string | Name of antimicrobial agent |
| dosage | string | Dosage and administration details |
| treatment_date | date | Date of treatment |
| duration_days | integer | Length of treatment |
| withdrawal_period_days | integer | Required withholding period |
| veterinarian | string | Responsible veterinarian name |
| notes | text | Additional treatment notes |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

### 5. `ResidueTest`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| sample_id | integer | References `ProductSample` |
| farm_id | integer | References `Farm` |
| test_date | date | Date sample was tested |
| compound | string | Chemical compound or drug tested |
| measured_value | float | Measured residue concentration |
| unit | string | Measurement unit (e.g., mg/kg) |
| mrl_value | float | Regulatory MRL threshold |
| result | string | Result status (pass/fail) |
| comments | text | Laboratory comments |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

### 6. `ProductSample`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| farm_id | integer | References `Farm` |
| animal_id | integer | References `Animal` |
| sample_type | string | Sample type (milk, meat, eggs, etc.) |
| collection_date | date | Date sample collected |
| source_location | string | Harvest or production location |
| status | string | Sample status |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

### 7. `RegulationStandard`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| jurisdiction | string | Regulatory region or agency |
| compound | string | Chemical compound or antimicrobial |
| product_type | string | Applicable product type |
| mrl_limit | float | Allowed maximum residue limit |
| unit | string | Measurement unit |
| effective_date | date | Date standard became effective |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

### 8. `Alert`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| farm_id | integer | References `Farm` |
| record_type | string | Triggering model type (treatment, test) |
| record_id | integer | Linked record identifier |
| alert_type | string | Alert category |
| severity | string | Severity level |
| message | string | Alert message |
| acknowledged | boolean | Whether alert is acknowledged |
| created_at | datetime | Alert creation timestamp |
| updated_at | datetime | Last update timestamp |

### 9. `Report`

| Field | Type | Description |
|---|---|---|
| id | integer | Unique identifier |
| farm_id | integer | References `Farm` |
| report_type | string | Report category (AMU summary, MRL compliance) |
| generated_at | datetime | Date/time generated |
| period_start | date | Report start date |
| period_end | date | Report end date |
| summary | text | Summary of findings |
| file_url | string | Link to generated report file |
| created_at | datetime | Record creation timestamp |
| updated_at | datetime | Last update timestamp |

## Usage Notes

- The portal should support user authentication with role-based access for farmers, veterinarians, and regulators.
- Data entry forms should capture treatment, testing, and sample information in a structured way.
- Dashboards should surface compliance status, MRL exceedances, and AMU trends.
- Alerts should notify users when residue tests exceed limits or withdrawal periods are breached.
