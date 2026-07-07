-- Talking Rabbitt — MySQL schema
-- Matches backend/models.py exactly. Run this once, or let
-- database.init_db() auto-create tables on first app startup.

CREATE DATABASE IF NOT EXISTS talking_rabbitt
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE talking_rabbitt;

CREATE TABLE IF NOT EXISTS datasets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_name VARCHAR(255) NOT NULL,
    cache_path VARCHAR(500) NOT NULL,
    row_count INT DEFAULT 0,
    column_count INT DEFAULT 0,
    column_schema JSON,
    preprocessing_report JSON,
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS chat_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dataset_id INT NOT NULL,
    user_email VARCHAR(255) NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    tools_used JSON,
    chart_spec JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_chat_dataset (dataset_id),
    INDEX idx_chat_user (user_email),
    CONSTRAINT fk_chat_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_user FOREIGN KEY (user_email) REFERENCES user_table(email) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS reports (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dataset_id INT NOT NULL,
    report_type VARCHAR(50) DEFAULT 'executive_summary',
    content JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_report_dataset (dataset_id),
    CONSTRAINT fk_report_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS recommendations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dataset_id INT NOT NULL,
    category VARCHAR(100),
    title VARCHAR(255),
    reasoning TEXT,
    impact VARCHAR(20) DEFAULT 'medium',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_rec_dataset (dataset_id),
    CONSTRAINT fk_rec_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS forecasts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    dataset_id INT NOT NULL,
    metric VARCHAR(100),
    horizon_periods INT DEFAULT 6,
    model_used VARCHAR(50) DEFAULT 'linear_regression',
    predictions JSON NOT NULL,
    confidence FLOAT DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_forecast_dataset (dataset_id),
    CONSTRAINT fk_forecast_dataset FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_table (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_email (email)
) ENGINE=InnoDB;

