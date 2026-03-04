FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json ./
RUN npm install

COPY . .
# Point API calls to the backend service
ENV VITE_API_BASE=http://backend:8000
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Forward /api requests to backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
