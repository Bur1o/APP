-- init.sql
-- Скрипт инициализации базы данных AgroCultureDB

-- Создание таблицы предприятий
CREATE TABLE IF NOT EXISTS enterprises (
    enterprise_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    address TEXT,
    phone VARCHAR(20),
    email VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы участков (полей)
CREATE TABLE IF NOT EXISTS fields (
    field_id SERIAL PRIMARY KEY,
    enterprise_id INTEGER NOT NULL REFERENCES enterprises(enterprise_id) ON DELETE CASCADE,
    field_name VARCHAR(100) NOT NULL,
    area_hectares DECIMAL(10,2) NOT NULL CHECK (area_hectares > 0),
    soil_type VARCHAR(50),
    is_irrigated BOOLEAN DEFAULT FALSE,
    description TEXT,
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы культур
CREATE TABLE IF NOT EXISTS crops (
    crop_id SERIAL PRIMARY KEY,
    crop_name VARCHAR(100) NOT NULL,
    crop_type VARCHAR(50) NOT NULL,
    growing_season_days INTEGER CHECK (growing_season_days > 0),
    description TEXT,
    is_annual BOOLEAN DEFAULT TRUE,
    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы посевов
CREATE TABLE IF NOT EXISTS plantings (
    planting_id SERIAL PRIMARY KEY,
    field_id INTEGER NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    crop_id INTEGER NOT NULL REFERENCES crops(crop_id) ON DELETE CASCADE,
    planting_date DATE NOT NULL,
    expected_harvest_date DATE,
    seed_amount_kg DECIMAL(10,2) CHECK (seed_amount_kg >= 0),
    planting_method VARCHAR(50),
    notes TEXT,
    is_organic BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (expected_harvest_date IS NULL OR expected_harvest_date > planting_date)
);

-- Создание таблицы уборки урожая
CREATE TABLE IF NOT EXISTS harvests (
    harvest_id SERIAL PRIMARY KEY,
    planting_id INTEGER NOT NULL REFERENCES plantings(planting_id) ON DELETE CASCADE,
    harvest_date DATE NOT NULL,
    yield_kg DECIMAL(12,2) NOT NULL CHECK (yield_kg > 0),
    quality_grade VARCHAR(20),
    storage_location VARCHAR(100),
    notes TEXT,
    is_certified BOOLEAN DEFAULT FALSE,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы обработки полей
CREATE TABLE IF NOT EXISTS field_operations (
    operation_id SERIAL PRIMARY KEY,
    field_id INTEGER NOT NULL REFERENCES fields(field_id) ON DELETE CASCADE,
    operation_date DATE NOT NULL,
    operation_type VARCHAR(50) NOT NULL,
    description TEXT,
    fertilizer_amount_kg DECIMAL(10,2) CHECK (fertilizer_amount_kg >= 0),
    water_amount_liters DECIMAL(10,2) CHECK (water_amount_liters >= 0),
    cost DECIMAL(12,2) CHECK (cost >= 0),
    is_completed BOOLEAN DEFAULT TRUE,
    performed_by VARCHAR(100),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы сотрудников
CREATE TABLE IF NOT EXISTS employees (
    employee_id SERIAL PRIMARY KEY,
    enterprise_id INTEGER NOT NULL REFERENCES enterprises(enterprise_id) ON DELETE CASCADE,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    position VARCHAR(50),
    phone VARCHAR(20),
    email VARCHAR(100),
    hire_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    notes TEXT
);

-- Вставка тестовых данных о предприятиях
INSERT INTO enterprises (name, address, phone, email) VALUES
('Агрофирма "Рассвет"', 'Белгородская обл., с. Дубовое, ул. Полевая, 15', '+74722345678', 'rassvet@agro.ru'),
('Сельхозкооператив "Нива"', 'Воронежская обл., п. Ровное, ул. Центральная, 3', '+74732398765', 'niva@skh.ru'),
('КФХ "Золотой колос"', 'Курская обл., х. Степной, пер. Садовый, 7', '+74712456789', 'zkolos@farm.ru')
ON CONFLICT DO NOTHING;

-- Вставка тестовых данных о культурах
INSERT INTO crops (crop_name, crop_type, growing_season_days, description, is_annual) VALUES
('Пшеница озимая', 'Зерновые', 280, 'Сорт "Московская 39", высокая урожайность', TRUE),
('Подсолнечник', 'Масличные', 115, 'Гибрид "Ясон", масличное направление', TRUE),
('Кукуруза на зерно', 'Зерновые', 110, 'Гибрид "ДКС 3511", раннеспелый', TRUE),
('Ячмень яровой', 'Зерновые', 85, 'Сорт "Гелиос", пивоваренный', TRUE),
('Соя', 'Бобовые', 105, 'Сорт "Амулет", высокая белковость', TRUE),
('Люцерна', 'Кормовые', NULL, 'Многолетняя кормовая культура', FALSE)
ON CONFLICT DO NOTHING;

-- Вставка тестовых данных о полях
INSERT INTO fields (enterprise_id, field_name, area_hectares, soil_type, is_irrigated, description) VALUES
(1, 'Северное поле', 45.50, 'Чернозем', TRUE, 'Основное поле под зерновые'),
(1, 'Южное поле', 32.25, 'Супесь', FALSE, 'Под масличные культуры'),
(2, 'Центральный участок', 67.80, 'Чернозем', TRUE, 'Крупнейший участок'),
(2, 'Западный склон', 18.40, 'Суглинок', FALSE, 'Участок с уклоном'),
(3, 'Поле №1', 12.50, 'Песчаная', TRUE, 'Орошаемое поле'),
(3, 'Поле №2', 22.30, 'Супесь', FALSE, 'Суходольное поле')
ON CONFLICT DO NOTHING;

-- Вставка тестовых данных о сотрудниках
INSERT INTO employees (enterprise_id, first_name, last_name, position, phone, email, hire_date) VALUES
(1, 'Иван', 'Петров', 'Главный агроном', '+79161234567', 'i.petrov@rassvet.ru', '2020-03-15'),
(1, 'Мария', 'Сидорова', 'Бухгалтер', '+79169876543', 'm.sidorova@rassvet.ru', '2019-11-10'),
(2, 'Алексей', 'Кузнецов', 'Директор', '+79261234567', 'a.kuznetsov@niva.ru', '2018-05-20'),
(2, 'Ольга', 'Иванова', 'Агроном', '+79269876543', 'o.ivanova@niva.ru', '2021-02-28'),
(3, 'Сергей', 'Николаев', 'Фермер', '+79031234567', 's.nikolaev@zkolos.ru', '2022-04-01')
ON CONFLICT DO NOTHING;

-- Вставка тестовых данных о посевах
INSERT INTO plantings (field_id, crop_id, planting_date, expected_harvest_date, seed_amount_kg, planting_method, is_organic, notes) VALUES
(1, 1, '2024-09-15', '2025-07-20', 1365.00, 'Рядовой посев', FALSE, 'Норма высева 300 кг/га'),
(2, 2, '2024-05-10', '2024-09-05', 290.25, 'Пунктирный посев', FALSE, 'Междурядье 70 см'),
(3, 3, '2024-04-25', '2024-08-15', 542.40, 'Квадратно-гнездовой', TRUE, 'Органическое земледелие'),
(4, 4, '2024-04-05', '2024-07-10', 460.80, 'Рядовой посев', FALSE, 'Яровой ячмень'),
(5, 5, '2024-05-01', '2024-08-20', 375.00, 'Широкорядный посев', TRUE, 'Соя на зерно'),
(6, 6, '2023-08-20', NULL, 112.40, 'Разбросной посев', FALSE, 'Люцерна на сено')
ON CONFLICT DO NOTHING;

-- Вставка тестовых данных об уборке урожая
INSERT INTO harvests (planting_id, harvest_date, yield_kg, quality_grade, storage_location, is_certified, notes) VALUES
(1, '2024-07-25', 204750.00, 'Высший', 'Элеватор "Рассвет"', TRUE, 'Влажность 14%, клейковина 28%'),
(2, '2024-09-10', 80625.00, 'Первый', 'Склад масличных', FALSE, 'Масличность 48%'),
(4, '2024-07-15', 61020.00, 'Второй', 'Зерносклад кооператива', FALSE, 'Фуражный ячмень'),
(5, '2024-08-25', 18750.00, 'Высший', 'Склад бобовых', TRUE, 'Белок 38%')
ON CONFLICT DO NOTHING;

-- Вставка тестовых данных об обработке полей
INSERT INTO field_operations (field_id, operation_date, operation_type, description, fertilizer_amount_kg, water_amount_liters, cost, performed_by) VALUES
(1, '2024-09-01', 'Вспашка', 'Основная обработка почвы', NULL, NULL, 45000.00, 'Иван Петров'),
(1, '2024-09-10', 'Внесение удобрений', 'NPK 16:16:16', 2250.75, NULL, 67522.50, 'Иван Петров'),
(2, '2024-05-05', 'Культивация', 'Предпосевная обработка', NULL, NULL, 18500.00, 'Иван Петров'),
(3, '2024-04-20', 'Полив', 'Влагозарядковый полив', NULL, 1250000.00, 25000.00, 'Ольга Иванова'),
(5, '2024-06-15', 'Прополка', 'Механическая прополка сои', NULL, NULL, 15600.00, 'Сергей Николаев'),
(5, '2024-07-01', 'Обработка', 'Защита от вредителей', 85.50, 1500.00, 12450.00, 'Сергей Николаев')
ON CONFLICT DO NOTHING;
