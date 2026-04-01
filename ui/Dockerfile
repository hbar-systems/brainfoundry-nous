

# ui/Dockerfile
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ✅ CRITICAL: Next standalone server expects .next/static under .next/standalone/.next/static
RUN mkdir -p .next/standalone/.next && cp -r .next/static .next/standalone/.next/static

EXPOSE 3000
CMD ["node", ".next/standalone/server.js"]






# FROM node:18-alpine
# WORKDIR /app
# ENV NEXT_TELEMETRY_DISABLED=1
# RUN npm config set bin-links true
# COPY package.json ./
# RUN npm install
# COPY . .
# RUN npm run build
# EXPOSE 3000
# CMD ["npm", "start"]


# FROM node:18-alpine

# WORKDIR /app

# # Install dependencies first
# RUN npm install -g next@14.0.4 react@18.2.0 react-dom@18.2.0

# # Copy package files
# COPY package*.json ./

# # Install project dependencies
# RUN npm install --no-package-lock

# # Copy source files
# COPY . .

# # Try to build, but don't fail if it doesn't work
# RUN npm run build || echo "Build failed, will run in dev mode"

# EXPOSE 3000

# # Start in development mode if build failed
# CMD ["npm", "run", "dev"] 
