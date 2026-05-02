FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build

# Next standalone server expects .next/static under .next/standalone/.next/static
RUN mkdir -p .next/standalone/.next && cp -r .next/static .next/standalone/.next/static

EXPOSE 3000
CMD ["node", ".next/standalone/server.js"]
