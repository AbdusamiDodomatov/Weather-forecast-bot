# Используем официальный Python-образ
FROM python:3.11-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файлы проекта
COPY . .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Создаём пользователя, чтобы не запускать от root
RUN useradd -m botuser
USER botuser

# Запускаем бота
CMD ["python", "forecast.py"]
