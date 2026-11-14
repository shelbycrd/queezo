FROM nginx:1.28-alpine
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx/security-headers.conf /etc/nginx/queezo-security-headers.conf
COPY frontend/ /usr/share/nginx/html/
