# Stage 1: Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install --legacy-peer-deps
COPY web/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.12-slim
WORKDIR /app

# Copy source code FIRST (hatchling needs it to resolve the package)
COPY pyproject.toml ./
COPY rnascope/ ./rnascope/

# Install (non-editable — production build)
RUN pip install --no-cache-dir .

# Copy built frontend
COPY --from=frontend /app/web/dist ./static

# Create uploads dir
RUN mkdir -p /app/uploads

ENV RNASCOPE_UPLOAD_DIR=/app/uploads
ENV PORT=10000

EXPOSE 10000

CMD ["python", "-m", "uvicorn", "rnascope.api:api_app", "--host", "0.0.0.0", "--port", "10000"]
