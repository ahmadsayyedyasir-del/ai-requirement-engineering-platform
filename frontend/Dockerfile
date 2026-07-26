# ── AI Requirement Engineering Platform — Frontend Dockerfile ─────────────────

# Build stage
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
# Use `npm install` because package-lock.json does not exist yet in the repo.
# npm install resolves all version ranges from package.json and installs them.
# Once Docker completes the first build, run this from your machine to capture
# the lockfile for future reproducible builds:
#   docker cp $(docker create ai-req-platform-frontend):/app/package-lock.json ./frontend/
# Then commit the lockfile and switch this line back to `npm ci`.
RUN npm install
COPY . .
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Production stage — Nginx serves the static bundle
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
