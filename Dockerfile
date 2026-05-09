FROM golang:1.26-bookworm AS builder

WORKDIR /src

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unzip && rm -rf /var/lib/apt/lists/*

# Install Bun for frontend build
RUN curl -fsSL https://bun.sh/install | bash
ENV BUN_INSTALL="/root/.bun"
ENV PATH="${BUN_INSTALL}/bin:${PATH}"

# Cache Go modules
COPY go.mod go.sum ./
RUN go mod download

# Cache frontend deps
COPY package.json bun.lock* ./
RUN bun install

# Copy source
COPY . .

# Build frontend
RUN bun run build.js

# Build Go binary (static, no CGo — pure Go SQLite)
RUN CGO_ENABLED=0 go build -ldflags "-s -w" -o /vibes ./cmd/vibes/


FROM scratch

COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /vibes /vibes

EXPOSE 8080

ENTRYPOINT ["/vibes"]
