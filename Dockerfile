FROM python:3.13-slim

# Install Node.js 20
RUN apt-get update && \
    apt-get install -y curl libxml2-dev libxslt1-dev gcc && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node dependencies (brightdata-mcp)
COPY package.json .
RUN npm install && ls -la node_modules/.bin/ && which node && node -v

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
