FROM node:22-alpine
WORKDIR /app
# Resolve platform-specific optional packages inside the Linux image. A lockfile
# generated on macOS can omit Rollup's Linux native package (npm/cli#4828).
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
