# syntax=docker/dockerfile:1
#
# The web frontend from a gridworks-web-frontend checkout, which is the
# build context. Vite serves the dev app and proxies /api to the API
# on the pod's localhost:8000.
#
#     podman build -t localhost/beech-sim_frontend:latest -f frontend.Dockerfile \
#         --ignorefile frontend.Dockerfile.dockerignore \
#         ../../gridworks-web-frontend

FROM node:22-bookworm-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
