# Chương 4
# Xây dựng hệ thống hoàn chỉnh

## 4.1 Kiến trúc tổng thể

### 4.1.1 Mô hình hệ thống
Hệ thống được xây dựng theo kiến trúc microservices, mỗi service là một Django project độc lập (ngoại trừ ai-service).
- API Gateway (Nginx)
- user-service (Django)
- product-service (Django)
- cart-service (Django)
- order-service (Django)
- pay-service (Django)
- ship-service (Django)
- ai-behavior-service (FastAPI/Python)

*[Chèn ảnh: Sơ đồ kiến trúc tổng thể của hệ thống microservices]*

### 4.1.2 Nguyên tắc
- Mỗi service có database riêng (PostgreSQL cho Django, Neo4j cho AI)
- Giao tiếp qua REST API hoặc Message Broker (RabbitMQ)
- Không truy cập DB của service khác trực tiếp.

---

## 4.2 System Architecture

### 4.2.1 Overview
The proposed system, named ecom-final, is designed as a fully distributed microservice-based e-commerce platform. The architecture follows modern enterprise design principles, ensuring scalability, maintainability, and fault isolation. 

Each core business domain is implemented as an independent Django REST microservice, while an API Gateway is employed to manage request routing, authentication, and system-wide policies.

### 4.2.2 Microservice Architecture
The system consists of the following core services:
- **User Service:** Handles authentication, authorization, and user management.
- **Product Service:** Manages product catalog, categories, and inventory.
- **Order Service:** Processes customer orders and order lifecycle.
- **Payment Service:** Handles payment transactions and billing.
- **Ship/Notification Service:** Sends asynchronous notifications and delivery handling.

Each service is independently deployable and maintains its own database, following the principle of database-per-service.

### 4.2.3 API Gateway
An API Gateway layer is introduced as the single entry point for all client requests. The gateway is responsible for:
- Routing incoming requests to appropriate microservices
- Handling authentication using JSON Web Tokens (JWT)
- Enforcing rate limiting and security policies
- Logging and monitoring API usage

In this system, the API Gateway is implemented using **NGINX** as a reverse proxy.

### 4.2.4 Service Communication
The system adopts a hybrid communication strategy:
- **Synchronous communication:** RESTful APIs over HTTP for real-time operations (e.g., viewing carts, getting product details).
- **Asynchronous communication:** Message queues (RabbitMQ) for event-driven workflows (Saga Pattern).

For example, when an order is created, an event is published and consumed by the payment and notification services.

### 4.2.5 Containerization and Deployment
All services are containerized using Docker to ensure consistency across environments. The system is orchestrated using Docker Compose for development and can be extended to Kubernetes for production deployment.

### 4.2.6 System Structure
Cấu trúc thư mục mã nguồn thực tế của hệ thống (`bookstore-microservice`):
```text
ecom-final/
|-- nginx/ 
|   |-- nginx.conf       # (File Nginx Gateway Config - File then chốt định tuyến)
|-- auth-service/        # (Xử lý JWT Token)
|-- user-service/        # (Xử lý customer, staff, admin)
|-- product-service/     # (Xử lý các loại sản phẩm book, clothes...)
|-- cart-service/        # (Giỏ hàng)
|-- order-service/       # (Đơn hàng)
|-- pay-service/         # (Thanh toán)
|-- ship-service/        # (Giao hàng)
|-- ai-behavior-service/ # (Neo4j Knowledge Graph & Behavior)
|-- docker-compose.yml   # (File Orchestration toàn hệ thống)
```
*[Chèn ảnh: Hình 4.1: Microservice architecture of the ecom-final system - Vẽ dạng block diagram ánh xạ đúng thư mục ở trên]*

### 4.2.7 Design Principles
The proposed architecture adheres to the following principles:
- **Loose Coupling:** Services interact only through APIs or messaging systems.
- **High Cohesion:** Each service encapsulates a single business domain.
- **Scalability:** Services can be scaled independently.
- **Fault Isolation:** Failure in one service does not affect others.

### 4.2.8 Security Considerations
Security is enforced through:
- JWT-based authentication
- API Gateway validation (Header Authorization Propagation)
- Role-based access control (RBAC)

### 4.2.9 Discussion
Compared to monolithic architectures, the proposed microservice design significantly improves system flexibility and scalability. However, it introduces additional complexity in deployment and service coordination, which is mitigated through containerization and standardized communication protocols.

---

## 4.3 API Gateway (Nginx)

### 4.3.1 Vai trò
- Entry point cho toàn hệ thống (Cổng 80)
- Routing request đến đúng service theo Prefix (`/api/*`)
- Xử lý authentication gián tiếp thông qua việc pass Header Authorization.

### 4.3.2 Cấu hình mẫu
> **File:** `nginx/nginx.conf` (Đoạn từ dòng 63 đến dòng 85)
```nginx
location /api/product/ {
    proxy_pass http://product_service/;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_pass_header Authorization;
}

location /api/cart/ {
    proxy_pass http://cart_service/;
    proxy_set_header Host              $host;
    proxy_pass_header Authorization;
}
```

---

## 4.4 Authentication (JWT)

### 4.4.1 Cài đặt
> **File:** `auth-service/requirements.txt`
```text
djangorestframework-simplejwt==5.3.1
```

### 4.4.2 Cấu hình
> **File:** `auth-service/users/views.py` (Dòng 19 đến 30)
```python
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Add custom claims
        token['role'] = user.role
        token['username'] = user.username
        return token

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
```
Và được map vào API:
> **File:** `auth-service/users/urls.py` (Dòng 11)
```python
path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
```

### 4.4.3 Luồng
- User login (`auth-service`) → nhận Access Token & Refresh Token.
- Gửi token trong Authorization Header Bearer.
- Nginx proxy_pass header này tới các service. Các service nội bộ dùng JWT Verify độc lập với Public Key / Secret.

*[Chèn ảnh: Sơ đồ luồng cấp phát và xác thực JWT token (User -> Nginx -> Auth Service)]*

---

## 4.5 Giao tiếp giữa các Service

Hệ thống áp dụng chiến lược giao tiếp lai (hybrid): **đồng bộ** cho các nghiệp vụ cần kết quả ngay, **bất đồng bộ** qua RabbitMQ cho các luồng event-driven.

### 4.5.1 Giao tiếp đồng bộ — REST API

Dùng khi một service cần dữ liệu từ service khác ngay lập tức (ví dụ: order-service cần giá sản phẩm để tính tổng tiền):

> **File:** `order-service/app/views.py` (Dòng 52–57)
```python
# Gọi product-service để lấy thông tin sản phẩm phục vụ tính giá
try:
    books_res = requests.get("http://product-service:8000/books/")
    books = {str(b['id']): b for b in books_res.json()}
except Exception:
    books = {}   # Fallback: không crash nếu product-service lỗi
```

### 4.5.2 Giao tiếp bất đồng bộ — RabbitMQ (Message Queue)

Dùng cho các luồng nghiệp vụ dài (order → payment → shipping) theo **Saga Pattern** — mỗi service publish event, service tiếp theo lắng nghe và xử lý độc lập.

**Hàm tiện ích publish message:**

> **File:** `order-service/app/rabbitmq_utils.py` (Dòng 1–44)
```python
import pika, json

RABBITMQ_HOST = 'rabbitmq'

def get_connection():
    credentials = pika.PlainCredentials('guest', 'guest')
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        heartbeat=600,
        blocked_connection_timeout=300,
        credentials=credentials,
    )
    return pika.BlockingConnection(parameters)

def publish_message(queue_name, message):
    connection = get_connection()
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=queue_name,
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2),  # persistent
    )
    connection.close()
```

**Order Service publish lệnh thanh toán:**

> **File:** `order-service/app/views.py` (Dòng 111–120)
```python
payment_command = {
    "order_id": order.id,
    "payment_method_id": pay_id,
    "amount": float(total_price),
    "customer_address": address,
    "shipping_method_id": ship_id,
}
publish_message('payment_queue', payment_command)
```

**Pay Service consume và publish tiếp sang shipping:**

> **File:** `pay-service/app/management/commands/run_consumer.py` (Dòng 41–48)
```python
# Xử lý thanh toán thành công → kích hoạt Shipping
event = {
    "event_type": "PaymentReserved",
    "order_id": order_id,
    "customer_address": customer_address,
    "shipping_method_id": shipping_method_id,
}
publish_message('order_queue', event)
```

**Consumer lắng nghe queue (chạy như worker riêng biệt):**

> **File:** `order-service/app/management/commands/run_consumer.py` (Dòng 18–83)
```python
channel.queue_declare(queue='order_queue', durable=True)
channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='order_queue', on_message_callback=callback)
channel.start_consuming()
```

Các workers chạy song song cùng service trong docker-compose:
```yaml
# docker-compose.yml
order-worker:
  build: ./order-service
  command: python manage.py run_consumer   # lắng nghe order_queue

pay-worker:
  build: ./pay-service
  command: python manage.py run_consumer   # lắng nghe payment_queue

ship-worker:
  build: ./ship-service
  command: python manage.py run_consumer   # lắng nghe ship_queue
```

### 4.5.3 Best Practice
- **Timeout:** 60s cho Nginx proxy, 300s override cho AI service (xử lý nặng).
- **Retry/Fallback:** `try-except` bao quanh mọi REST call — service không crash khi dependency lỗi.
- **Durable queue:** `durable=True` + `delivery_mode=2` đảm bảo message không mất khi RabbitMQ restart.
- **Circuit breaker (nâng cao):** Có thể tích hợp thư viện `pybreaker` cho production.

---

## 4.6 Docker hóa hệ thống

### 4.6.1 Dockerfile (Ví dụ cấu trúc của user-service)
> **File:** `user-service/Dockerfile` (Dòng 1 đến 13)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DJANGO_SETTINGS_MODULE=config.settings.base
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
CMD ["sh", "-c", "python manage.py migrate --run-syncdb && python manage.py runserver 0.0.0.0:8000"]
```

### 4.6.2 docker-compose.yml
> **File:** `docker-compose.yml` (Trích đoạn dòng 123 đến 132 và các service expose nội bộ)
```yaml
services:
  nginx:
    build: ./nginx
    ports:
      - "80:80"
    depends_on:
      - api-gateway
      - user-service
      - product-service
  
  product-service:
    build: ./product-service
    expose:
      - "8000"
    volumes:
      - ./product-service:/app
```

---

## 4.7 Luồng hệ thống (End-to-End)

### 4.7.1 Use case: Mua hàng
1. User login qua `auth-service`
2. Xem sản phẩm từ `product-service`
3. Thêm vào giỏ hàng tại `cart-service`
4. Tạo order thông qua `order-service`
5. Thanh toán ở `pay-service`
6. Bàn giao giao hàng qua `ship-service`

*[Chèn ảnh: Biểu đồ BPMN hoặc Flowchart mô tả chu trình User mua hàng qua các Microservices]*

### 4.7.2 Sequence logic (Giao tiếp bất đồng bộ qua RabbitMQ / Saga Pattern)
**1. Order Service xuất lệnh vào Payment Queue:**
> **File:** `order-service/app/views.py` (Dòng 111 đến 120)
```python
# Tạo Command yêu cầu thanh toán
payment_command = {
    "order_id": order.id,
    "payment_method_id": pay_id,
    "amount": float(total_price),
    "customer_address": address,
    "shipping_method_id": ship_id,
}
# Quăng lệnh vào payment_queue
publish_message('payment_queue', payment_command)
```

**2. Payment Service xử lý thành công -> Đẩy sự kiện gọi Shipping:**
> **File:** `pay-service/app/management/commands/run_consumer.py` (Dòng 41 đến 48)
```python
# Payment.objects.create(order_id=order_id, amount=amount, status='SUCCESS')

# Báo cáo lại cho Nhạc trưởng (Order Queue) để kích hoạt Shipping
event = {
    "event_type": "PaymentReserved",
    "order_id": order_id,
    "customer_address": customer_address,
    "shipping_method_id": shipping_method_id
}
publish_message('order_queue', event)
```

*[Chèn ảnh: Sơ đồ Sequence Diagram cho Saga Pattern (Order -> RabbitMQ -> Payment -> RabbitMQ -> Order -> RabbitMQ -> Shipping)]*

---

## 4.8 Triển khai Kubernetes (Optional)

Dù môi trường local sử dụng Docker Compose, hệ thống đã chuẩn bị đầy đủ cấu hình Kubernetes cho môi trường Production. Toàn bộ 16 service đều có file `Deployment` và `Service` riêng trong thư mục `k8s/`, được sinh tự động từ `generate_k8s.py`. Images được public trên DockerHub tại `dockerhub.com/u/dunguyenquy`.

### 4.8.1 Deployment

Mỗi service có 1 file Deployment định nghĩa Pod template và resource limits:

> **File:** `k8s/nginx-deployment.yaml` (Dòng 1 đến 29)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  labels:
    app: nginx
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: dunguyenquy/nginx-gateway:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "500m"
```

### 4.8.2 Service

Mỗi service có 1 file Service kiểu `ClusterIP` để các Pod giao tiếp nội bộ trong cluster:

> **File:** `k8s/nginx-service.yaml` (Dòng 1 đến 15)
```yaml
apiVersion: v1
kind: Service
metadata:
  name: nginx
  labels:
    app: nginx
spec:
  type: ClusterIP
  selector:
    app: nginx
  ports:
    - port: 80
      targetPort: 80
      protocol: TCP
```

### 4.8.3 Quy trình deploy lên Kubernetes

**Bước 1 — Build và push image lên DockerHub:**
```bash
# Build tất cả services
docker compose build

# Tag và push từng service (ví dụ nginx và product-service)
docker tag bookstore-microservice-nginx dunguyenquy/nginx-gateway:latest
docker push dunguyenquy/nginx-gateway:latest

docker tag bookstore-microservice-product-service dunguyenquy/product-service:latest
docker push dunguyenquy/product-service:latest
# ... tương tự cho các service còn lại
```

> 📸 **[CHỤP ẢNH 1]:** Mở `https://hub.docker.com/u/dunguyenquy` trên trình duyệt
> → chụp màn hình danh sách repositories đã push (nginx-gateway, product-service, user-service...)

**Bước 2 — Apply toàn bộ cấu hình K8s:**
```bash
# Apply tất cả file trong thư mục k8s/
kubectl apply -f k8s/

# Kiểm tra trạng thái Pods
kubectl get pods

# Kiểm tra Services
kubectl get services
```

> 📸 **[CHỤP ẢNH 2]:** Chạy lệnh `kubectl get pods` trong terminal
> → chụp màn hình kết quả hiển thị tất cả pods ở trạng thái `Running`

> 📸 **[CHỤP ẢNH 3]:** Chạy lệnh `kubectl get services` trong terminal
> → chụp màn hình danh sách services với CLUSTER-IP tương ứng

---

## 4.9 Logging và Monitoring

Hệ thống sử dụng Docker Compose Profile `monitoring` để đóng gói toàn bộ stack giám sát — chỉ khởi động khi cần, không làm nặng môi trường phát triển thông thường.

### 4.9.1 Logging — ELK Stack

**Elasticsearch** lưu trữ log, **Kibana** trực quan hóa:

> **File:** `docker-compose.yml` (Dòng 304–324)
```yaml
elasticsearch:
  image: docker.elastic.co/elasticsearch/elasticsearch:8.11.1
  profiles: ["monitoring"]
  environment:
    - discovery.type=single-node
    - xpack.security.enabled=false
  ports:
    - "9200:9200"

kibana:
  image: docker.elastic.co/kibana/kibana:8.11.1
  profiles: ["monitoring"]
  ports:
    - "5601:5601"
  environment:
    - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
  depends_on:
    - elasticsearch
```

### 4.9.2 Monitoring — Prometheus + Grafana + cAdvisor

**cAdvisor** thu thập metrics từng container → **Prometheus** scrape và lưu → **Grafana** vẽ dashboard:

> **File:** `docker-compose.yml` (Dòng 268–302)
```yaml
prometheus:
  image: prom/prometheus:v2.45.0
  profiles: ["monitoring"]
  ports:
    - "9090:9090"
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

grafana:
  image: grafana/grafana:10.0.3
  profiles: ["monitoring"]
  ports:
    - "3000:3000"
  depends_on:
    - prometheus

cadvisor:
  image: gcr.io/cadvisor/cadvisor:v0.47.0
  profiles: ["monitoring"]
  ports:
    - "8080:8080"
```

Cấu hình Prometheus scrape cAdvisor mỗi 15 giây:

> **File:** `monitoring/prometheus.yml` (Dòng 1 đến 12)
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']
```

### 4.9.3 Quy trình khởi động và chụp ảnh

**Bước 1 — Khởi động monitoring stack:**
```bash
docker compose --profile monitoring up -d
```

**Bước 2 — Mở Grafana và cấu hình dashboard:**
```
Truy cập: http://localhost:3000
Username: admin
Password: admin
```

> 📸 **[CHỤP ẢNH 1]:** Sau khi đăng nhập Grafana
> → vào **Connections → Data Sources → Add data source → Prometheus**
> → nhập URL `http://prometheus:9090` → nhấn **Save & Test**
> → chụp màn hình thông báo "Data source is working"

> 📸 **[CHỤP ẢNH 2]:** Import dashboard có sẵn
> → vào **Dashboards → Import → nhập ID `193`** (Docker & System Monitoring)
> → chụp màn hình dashboard đang hiển thị CPU/RAM từng container

**Bước 3 — Mở Kibana xem log:**
```
Truy cập: http://localhost:5601
```

> 📸 **[CHỤP ẢNH 3]:** Trên Kibana
> → vào **Discover** → chụp màn hình giao diện log search
> (Nếu chưa có index, chụp màn hình trang chủ Kibana với logo ELK cũng được)

**Bước 4 — Xem Nginx access log trực tiếp (đơn giản nhất):**
```bash
docker logs bookstore-microservice-nginx-1 -f
```

> 📸 **[CHỤP ẢNH 4]:** Chụp terminal đang chạy lệnh trên khi có vài request đi qua
> → thấy log format: `GET /api/product/ 200 → product_service [0.05s]`

---

## 4.10 Đánh giá hệ thống

### 4.10.1 Hiệu năng
- Response time
- Throughput

### 4.10.2 Khả năng mở rộng
- Scale từng service (Scale out product-service hoặc order-service riêng biệt)
- Load balancing (Tích hợp trong nginx upstreams)

### 4.10.3 Ưu điểm
- Linh hoạt
- Dễ mở rộng

### 4.10.4 Nhược điểm
- Phức tạp triển khai
- Debug khó (Đòi hỏi tracing across services)

---

## 4.11 Bài tập thực hành
- Triển khai các service bằng Django
- Kết nối qua API (REST + RabbitMQ)
- Docker hóa hệ thống
- Test full flow mua hàng + kết quả tư vấn AI.

---

## 4.12 Checklist đánh giá
- [x] Có API Gateway (`nginx/nginx.conf`)
- [x] Có JWT Auth (`auth-service/users/views.py` & Header Propagation)
- [x] Có Docker chạy được (`docker-compose up -d --build`)
- [x] Có flow order → payment → shipping (`Saga Pattern` qua RabbitMQ)
