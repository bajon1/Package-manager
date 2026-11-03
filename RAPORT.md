# Projekt 2 — manager pakietów

Autorzy: Piotr Matusiewicz, Dominik Mika. Numer grupy: **k = 16**.

## Uruchomienie i dane wejściowe

Python ≥3.13; polecenia PowerShell z katalogu projektu:

```sh
uv sync --dev
```

Żądania podaje się w pliku, po jednym w wierszu; puste wiersze i komentarze `#` są pomijane. Stan ma format `NAZWA WERSJA [manual]`. Pliki usuwania i aktualizacji zawierają same nazwy. `--state` wczytuje stan, a `--output` zapisuje wynik osobno. Dane `data/` odpowiadają `repos/k16/`; `examples/` zawiera przykłady prowadzącego.

## 4.2. Kodowanie bazy wiedzy

Dla każdej pary pakiet–wersja zmienna `x[p,v]` oznacza jej zainstalowanie.

- **A1:** co najwyżej jedna zmienna `x[p,v]` dla danego pakietu może być prawdziwa.
- **A2:** zainstalowana wersja wymusza spełnienie każdego wymagania; wewnątrz alternatywy wystarcza jeden pasujący pakiet.
- **A3:** zainstalowana wersja wyklucza wszystkie wersje pasujące do jej konfliktów.

Żądanie wymusza alternatywę pasujących wersji; brak pasujących wersji oznacza fałsz. Przykłady z `repo_example.json`:

```text
AtMost(x[lib,1.0], x[lib,1.5], x[lib,2.0], 1)
x[app,2.0] → x[lib,2.0] ∧ (x[util,1.0] ∨ x[util,2.0])
x[lib,2.0] → x[util,2.0]
x[legacy,1.0] → ¬x[util,2.0]
```

## 4.3, 6.1–6.2 i 8.1. Operacje i optymalizacja

Z3 minimalizuje kryteria leksykograficznie. Przestarzałość to pozycja wersji od najnowszej, od zera; dla zbioru jest sumowana.

| Operacja | Kolejność minimalizowanych kryteriów |
|---|---|
| Instalacja do pustego stanu — 4.3 | Przestarzałość pakietów żądanych; liczba pakietów; przestarzałość pozostałych pakietów. |
| Instalacja do istniejącego stanu — 6.1 | Usunięte pakiety; zmiany wersji pakietów zachowanych; przestarzałość nowych pakietów żądanych; liczba nowych pakietów; przestarzałość pozostałych nowych pakietów. |
| Usuwanie zbioru P — 6.2 | Usunięte pakiety ręczne spoza P; zmiany wersji pakietów zachowanych; nowe pakiety; usunięte pakiety. Z `autoremove` ostatnie kryterium zastępuje liczba wszystkich zainstalowanych pakietów. |
| Aktualizacja zbioru P — 8.1 | Przestarzałość P; usunięte pakiety; zmiany wersji zachowanych pakietów spoza P; nowe pakiety; przestarzałość wszystkich pakietów. |

Instalowane na żądanie pakiety stają się ręczne. Usuwanie wymusza nieobecność P. Aktualizacja zachowuje pakiety ręczne i P. Pozostałe oznaczenia ręczne/automatyczne są zachowywane.

### 4.3. Instalacja do pustego środowiska

Brak `--state` oznacza pusty stan. Polecenia odtwarzające pięć przykładów:

```powershell
Set-Content zadania.txt 'app' -Encoding ascii
uv run package-manager install zadania.txt --repo examples/repo_example.json
Set-Content zadania.txt 'tool' -Encoding ascii
uv run package-manager install zadania.txt --repo examples/repo_example.json
Set-Content zadania.txt @('app', 'tool') -Encoding ascii
uv run package-manager install zadania.txt --repo examples/repo_example.json
Set-Content zadania.txt @('app', 'legacy') -Encoding ascii
uv run package-manager install zadania.txt --repo examples/repo_example.json
uv run package-manager install examples/requests_example.txt --repo examples/repo_example.json
```

| Żądania | Stan wynikowy |
|---|---|
| `app` | `app 2.0`, `lib 2.0`, `util 2.0` |
| `tool` | `tool 1.1`, `lib 1.0`, `json-slow 1.0` |
| `app`, `tool` | `app 1.0`, `tool 1.1`, `lib 1.0`, `json-slow 1.0` |
| `app`, `legacy` | `app 1.0`, `legacy 1.0`, `lib 1.0` |
| `app==2.0`, `tool` | Brak rozwiązania. |

### 6.1–6.2 i 8.1. Operacje na istniejącym stanie

Każde polecenie zaczyna od oryginalnego `state_example.txt`:

```powershell
Set-Content zadania.txt 'app==2.0' -Encoding ascii
uv run package-manager install zadania.txt --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt
Set-Content usun.txt 'lib' -Encoding ascii
uv run package-manager remove usun.txt --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt
Set-Content usun.txt 'tool' -Encoding ascii
uv run package-manager remove usun.txt --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt --autoremove
uv run package-manager update --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt
```

Plik nazw podany po `update` ogranicza aktualizację do wskazanych pakietów; brak pliku oznacza wszystkie.

| Zapytanie | Zmiany |
|---|---|
| Instalacja `app==2.0` | `app 1.0 → 2.0`, `lib 1.0 → 2.0`, instalacja `util 2.0`, usunięcie `tool 1.1`. |
| Usunięcie `lib` | Usunięcie `lib 1.0`, `app 1.0`, `tool 1.1`. |
| Usunięcie `tool` z `autoremove` | Usunięcie `tool 1.1` i `json-slow 1.0`. |
| Aktualizacja wszystkich pakietów | `lib 1.0 → 1.5`, instalacja `util 2.0`. |

## 4.4. Weryfikacja stanu

Bez użycia solvera sprawdzane są istnienie wersji, zależności, konflikty i żądania. Weryfikacja zwraca wszystkie naruszenia i obejmuje każdy wynik przed zapisaniem. Wszystkie podane stany wynikowe przeszły weryfikację.

## 4.5. Eksperymenty grupy 16

Pomiary wykonano 2 listopada 2026 r. na Windows 11, Pythonie 3.13.16 i Z3 5.3.3. Polecenie odtwarzające eksperyment:

```sh
uv run python -m src.experiments --data data --group 16 --output tmp/wyniki45.json
```

| N | Wersje | Aksjomaty | Żądania | Pakiety | Przestarzałość | Budowa [s] | Rozwiązanie [s] | Weryfikacja |
|---:|---:|---:|---|---:|---:|---:|---:|---|
| 10 | 45 | 22 | `attrs`, `filelock`, `quartz-kit` | 4 | 2 | 0.007183 | 0.012233 | Bez naruszeń. |
| 30 | 202 | 149 | `uvicorn`, `typing-extensions`, `basalt-sdk` | 11 | 2 | 0.011753 | 0.045888 | Bez naruszeń. |
| 100 | 1284 | 1124 | `h2`, `tomli-umbra`, `nova-api` | — | — | 0.114124 | 0.082499 | Brak rozwiązania; brak stanu do weryfikacji. |
| 300 | 6636 | 5779 | `yarl`, `aiohttp-pebble`, `nova-cli` | 13 | 1 | 0.825887 | 3.251692 | Bez naruszeń. |
| 1000 | 21193 | 17477 | `uvicorn`, `certifi-yarrow`, `tundra-sdk` | 6 | 0 | 4.691203 | 5.700601 | Bez naruszeń. |

Czas budowy obejmuje wczytanie i walidację repozytorium oraz bazę wiedzy; czas rozwiązania — solver, odczyt modelu i obowiązkową walidację. Pełne wyniki: [results/group16.json](results/group16.json).

Czas budowy rósł z liczbą wersji i aksjomatów. Czas rozwiązania zależał również od struktury problemu: sprzeczność N = 100 wykryto szybciej niż znaleziono optimum dla N = 300 i 1000.

## 6.3. Wyjaśnienia braku rozwiązania

Śledzone są aksjomaty i żądania. Z rdzenia usuwa się zbędne elementy, aż usunięcie dowolnego pozostałego elementu daje spełnialny zestaw. Jest to minimalność przez zawieranie, nie najmniejsza liczba elementów.

```sh
uv run package-manager explain examples/requests_example.txt --repo examples/repo_example.json
uv run package-manager explain data/requests_100.txt --repo data/repo_100.json
```

### Przykład `app==2.0` i `tool`

Otrzymany rdzeń ma sześć elementów:

```text
x[app,2.0]
x[tool,1.0] ∨ x[tool,1.1]
x[app,2.0] → x[lib,2.0]
x[tool,1.0] → (x[lib,1.0] ∨ x[lib,1.5])
x[tool,1.1] → (x[lib,1.0] ∨ x[lib,1.5])
AtMost(x[lib,1.0], x[lib,1.5], x[lib,2.0], 1)
```

`app 2.0` wymaga `lib 2.0`, a obie wersje `tool` — starszej `lib`. A1 wyklucza ich współistnienie.

### Przypadek N = 100

Sprzeczność powoduje samo żądanie `nova-api`; `h2` i `tomli-umbra` nie należą do rdzenia. Rdzeń zawiera 43 elementy: żądanie, 28 zależności A2 i 14 warunków A1. Wymaganych kombinacji wersji `nova-x*` nie można spełnić przy ograniczeniu do jednej wersji pakietu. Pełne rdzenie obu przypadków: [results/six-point-examples.json](results/six-point-examples.json). Dla obu sprawdzono sprzeczność oraz spełnialność po usunięciu każdego elementu osobno.

## 6.4. Scenariusz losowych operacji

Scenariusz rozpoczyna się od pustego stanu i korzysta z `repo_200.json` grupy 16. Ziarno generatora: **2026**. Polecenie:

```sh
uv run python -m src.scenario --repo data/repo_200.json --group 16 --seed 2026 --steps 12 --output tmp/wyniki64.json
```

| Krok | Operacja | Pakiet | Autoremove | Liczba zmian | Pakiety (ręczne) | Czas [s] |
|---:|---|---|---|---:|---:|---:|
| 1 | Instalacja | `yarl-prism` | Nie | 4 | 4 (1) | 1.841631 |
| 2 | Usunięcie | `yarl-prism` | Nie | 1 | 3 (0) | 0.651842 |
| 3 | Usunięcie | `idna-prism` | Nie | 1 | 2 (0) | 0.623631 |
| 4 | Instalacja | `aiobotocore` | Nie | 17 | 18 (1) | 1.451499 |
| 5 | Usunięcie | `aiobotocore` | Nie | 1 | 17 (0) | 0.680793 |
| 6 | Usunięcie | `cffi` | Nie | 0 | 17 (0) | 0.693781 |
| 7 | Usunięcie | `jsonschema` | Tak | 17 | 0 (0) | 1.177127 |
| 8 | Usunięcie | `botocore-prism` | Tak | 0 | 0 (0) | 1.161534 |
| 9 | Usunięcie | `packaging-prism` | Tak | 0 | 0 (0) | 1.189288 |
| 10 | Instalacja | `aiohappyeyeballs-prism` | Nie | 1 | 1 (1) | 1.600209 |
| 11 | Instalacja | `tomli-garnet` | Nie | 1 | 2 (2) | 1.767265 |
| 12 | Usunięcie | `tomli-garnet` | Tak | 1 | 1 (1) | 1.254839 |

Każdy stan pośredni przeszedł weryfikację. Zmiany obejmują instalacje, usunięcia i zmiany wersji; czas obejmuje solver i jego obowiązkową walidację. Pełne stany: [results/random-group16.json](results/random-group16.json).

## 8.2. Konflikt aktualizacji i front Pareto

Dla stanu `a 1.0 manual`, `b 1.0 manual` najnowsze wersje osiągalne osobno to `a 2.0` i `b 2.0`. Nie można ich zainstalować jednocześnie.

```powershell
Set-Content stan-ab.txt @('a 1.0 manual', 'b 1.0 manual') -Encoding ascii
uv run package-manager update --repo examples/repo_example.json --state stan-ab.txt --output wynik-ab.txt
```

Minimalny rdzeń sprzeczności:

```text
x[a,2.0] → x[b,1.0]
AtMost(x[b,1.0], x[b,2.0], 1)
x[a,2.0]
x[b,2.0]
```

Przy zachowaniu obu pakietów ręcznych front Pareto składa się z:

| Stan | Przestarzałość a | Przestarzałość b |
|---|---:|---:|
| `a 2.0`, `b 1.0` | 0 | 1 |
| `a 1.1`, `b 2.0` | 1 | 0 |

Żaden punkt nie dominuje drugiego. Aktualizacja samego `a` daje `a 2.0`, `b 1.0` bez konfliktu:

```powershell
Set-Content aktualizuj.txt 'a' -Encoding ascii
uv run package-manager update aktualizuj.txt --repo examples/repo_example.json --state stan-ab.txt --output wynik-a.txt
```

Wyniki i weryfikacja: [results/eight-point-examples.json](results/eight-point-examples.json).

## Pytanie dodatkowe — NP-zupełność

Problem należy do NP, bo podany stan można zweryfikować w czasie wielomianowym. Redukcja z 3-SAT: zmiennej przypisujemy pakiet `Xi` o wersjach `0` i `1`, a klauzuli — pakiet `Cj` o trzech wersjach. Każda wersja `Cj` wymaga wersji `Xi` odpowiadającej jednemu literałowi: `==1` dla dodatniego, `==0` dla ujemnego. Żądamy wszystkich `Cj`. A1 zapewnia spójne wartości zmiennych, a wybrana wersja każdej klauzuli wskazuje prawdziwy literał; odwrotnie, każde spełniające wartościowanie daje poprawną instalację. Konstrukcja jest wielomianowa, więc problem jest NP-zupełny. W tej redukcji wystarczą wielowersyjność i ograniczenia `==`: problem pozostaje NP-zupełny także **bez konfliktów i bez alternatyw `|`**, ponieważ alternatywę zapewnia wybór wersji pakietu.
