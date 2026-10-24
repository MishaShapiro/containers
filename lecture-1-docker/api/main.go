package main

import (
	"fmt"
	"net/http"
	"os"
	"strconv"
	"sync"
)

var (
	mu  sync.Mutex
	hog [][]byte
)

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintln(w, "ok")
	})

	// /eat?mb=N — выделить N МБ и держать. Пишем в каждую страницу, иначе ядро не выделит память реально
	http.HandleFunc("/eat", func(w http.ResponseWriter, r *http.Request) {
		mb, _ := strconv.Atoi(r.URL.Query().Get("mb"))
		if mb <= 0 {
			mb = 10
		}
		b := make([]byte, mb<<20)
		for i := 0; i < len(b); i += 4096 {
			b[i] = 1
		}
		mu.Lock()
		hog = append(hog, b)
		total := 0
		for _, h := range hog {
			total += len(h) >> 20
		}
		mu.Unlock()
		fmt.Fprintf(w, "holding %d MB\n", total)
	})

	// /burn — одно ядро в бесконечном цикле (каждый вызов добавляет ещё одно)
	http.HandleFunc("/burn", func(w http.ResponseWriter, r *http.Request) {
		go func() {
			x := 0
			for {
				x++
			}
		}()
		fmt.Fprintln(w, "burning one core")
	})

	// /info — кто я: помогает в Частях 2 и 5
	http.HandleFunc("/info", func(w http.ResponseWriter, r *http.Request) {
		host, _ := os.Hostname()
		fmt.Fprintf(w, "pid=%d uid=%d gid=%d hostname=%s\n", os.Getpid(), os.Getuid(), os.Getgid(), host)
	})

	fmt.Println("listening on :" + port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
// touch
