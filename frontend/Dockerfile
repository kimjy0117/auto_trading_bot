# ── Stage 1: Build ──────────────────────────────────────────────
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --prefer-offline

COPY . .
RUN npm run build

# ── Stage 2: Production (Nginx) ─────────────────────────────────
FROM nginx:1.27-alpine

# 보안: nginx 프로세스를 root 대신 nginx 유저로 실행
RUN chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx/conf.d

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

# nginx가 80번 포트에 바인딩할 수 있도록 권한 부여
RUN chown -R nginx:nginx /usr/share/nginx/html

EXPOSE 80

USER nginx
CMD ["nginx", "-g", "daemon off;"]
