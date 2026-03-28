# Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

# Python backend
FROM python:3.12-slim
WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy backend code
COPY rnascope/ ./rnascope/

# Copy built frontend into static dir
COPY --from=frontend /app/web/dist ./static

# Create uploads dir
RUN mkdir -p /app/uploads

# Serve frontend from FastAPI
ENV RNASCOPE_UPLOAD_DIR=/app/uploads
ENV PORT=10000

EXPOSE 10000

CMD ["python", "-m", "uvicorn", "rnascope.api:api_app", "--host", "0.0.0.0", "--port", "10000"]
