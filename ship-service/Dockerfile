FROM python:3.10-slim

# Tắt cảnh báo dông dài và ép log hiển thị ngay lập tức
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Thư mục làm việc trong container
WORKDIR /app

# Copy và cài đặt thư viện trước để tận dụng cache của Docker
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào
COPY . /app/

# Mở port
EXPOSE 8000

# Lệnh khởi động server
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
