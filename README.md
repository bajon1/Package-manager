# Packet-manager
Packet manager

## Testy

Zainstaluj zależności developerskie i uruchom testy z katalogu projektu:

```sh
uv sync --dev
uv run pytest
```

Testy znajdują się w katalogu `tests/`, w plikach `test_*.py`.

## Wczytywanie repozytorium

```python
from src.parser import load_repository

repository = load_repository("data/repo_10.json")
print(repository.package_names())
```

Niepoprawny plik powoduje `ValueError` z nazwą pliku i lokalizacją błędu.
Ostrzeżenia o wymaganiach bez pasujących wersji są wypisywane na standardowe wyjście błędów.
