FROM node:20-slim AS build

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .

ARG VITE_TENANT_ID
ARG VITE_CLIENT_ID
ARG VITE_API_CLIENT_ID
ARG VITE_API_SCOPE
ARG VITE_API_BASE_URL

RUN npm run build

FROM node:20-slim
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY --from=build /app/server.js .
RUN npm init -y && npm install express@4

EXPOSE 8080
CMD ["node", "server.js"]
