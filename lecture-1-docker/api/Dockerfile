# --- стадия сборки: компилятор Go, в итоговый образ не попадает ---
FROM golang:1.22 AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download                  
COPY *.go ./
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /api .

# --- финальный образ: только статический бинарник ---
FROM scratch
COPY --from=build /api /api
USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["/api"]
