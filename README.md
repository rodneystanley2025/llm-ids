## Demo

### Run
docker compose up --build

### Open
- http://localhost:8000/
- http://localhost:8000/ui/sessions

### Try
1) Benign: should allow
2) Prompt-attack: should review/block
3) Dangerous request: should block

### Regression tests
make test
