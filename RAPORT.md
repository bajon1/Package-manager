# Projekt 2 — manager pakietów

Autorzy: Piotr Matusiewicz, Dominik Mika. Numer grupy: **k = 16**.

## Uruchomienie i dane wejściowe

Wymagany jest Python 3.13 lub nowszy. Z katalogu projektu:

```sh
uv sync --dev
uv run package-manager install examples/requests_example.txt --repo examples/repo_example.json --output wynik.txt
uv run pytest
```

Repozytorium JSON zawiera pakiety, ich wersje, zależności i konflikty. Nazwy są normalizowane, a wersje liczbowe porównywane jako ciągi liczb: `1.10 > 1.9` oraz `1.0 == 1.0.0`. Parser odrzuca błędną strukturę, nieznane pola, duplikaty i wymagania pakietu wobec siebie. Błędy składni JSON wskazują linię i kolumnę, pozostałe błędy — miejsce w dokumencie. Wymagania bez pasujących wersji powodują ostrzeżenie.

Plik żądań zawiera jedno wymaganie w wierszu; puste wiersze i komentarze `#` są pomijane. Żądania przekazuje się wyłącznie przez plik. Plik stanu zawiera `NAZWA WERSJA`, opcjonalnie z dopiskiem `manual`. Pliki usuwania i aktualizacji zawierają same nazwy pakietów. Przy aktualizacji brak pliku oznacza wszystkie zainstalowane pakiety.

Pliki w `examples/` pochodzą od prowadzącego. Dane w `data/` odpowiadają `repos/k16/` z udostępnionego archiwum; porównanie treści uwzględniało różnice końców linii.

```sh
uv run package-manager install zadania.txt --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt
uv run package-manager remove usun.txt --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt
uv run package-manager remove usun.txt --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt --autoremove
uv run package-manager update aktualizuj.txt --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt
uv run package-manager update --repo examples/repo_example.json --state examples/state_example.txt --output wynik.txt
uv run package-manager explain examples/requests_example.txt --repo examples/repo_example.json
```

`zadania.txt`, `usun.txt` i `aktualizuj.txt` oznaczają pliki przygotowane dla danego zapytania. `--state` wskazuje stan początkowy. `--output` zapisuje wynik osobno; bez tej opcji udana operacja aktualizuje podany plik stanu. Błąd lub brak rozwiązania nie zapisuje wyniku. Program wypisuje plan zmian, stan albo informację o braku rozwiązania. Wynik `unknown` solvera jest zgłaszany odrębnie.

## 4.2. Kodowanie bazy wiedzy

Dla każdej pary pakiet–wersja istnieje zmienna logiczna `x[p,v]`, prawdziwa wtedy, gdy wersja `v` pakietu `p` jest zainstalowana. `V(p)` oznacza wersje pakietu, a `M(r)` — pary pakiet–wersja spełniające wymaganie `r`.

- **A1:** co najwyżej jedna zmienna `x[p,v]` dla danego pakietu może być prawdziwa.
- **A2:** zainstalowana wersja wymusza spełnienie każdego wymagania; wewnątrz alternatywy wystarcza jeden pasujący pakiet.
- **A3:** zainstalowana wersja wyklucza wszystkie wersje pasujące do jej konfliktów.

```text
A1: AtMost({x[p,v] : v ∈ V(p)}, 1)
A2: x[p,v] → ∧ po grupach zależności C (∨ po r ∈ C (∨ po (q,w) ∈ M(r) x[q,w]))
A3: x[p,v] → ∧ po konfliktach r (∧ po (q,w) ∈ M(r) ¬x[q,w])
Żądanie r: ∨ po (q,w) ∈ M(r) x[q,w]
```

Pusta alternatywa jest fałszem, więc wersja z niespełnialnym wymaganiem nie może zostać zainstalowana. Aksjomaty mają etykiety opisujące pakiet, wersję i warunek.

Przykłady z `repo_example.json`:

```text
AtMost(x[lib,1.0], x[lib,1.5], x[lib,2.0], 1)
x[app,2.0] → x[lib,2.0] ∧ (x[util,1.0] ∨ x[util,2.0])
x[lib,2.0] → x[util,2.0]
x[tool,1.1] → (x[lib,1.0] ∨ x[lib,1.5])
                ∧ (x[json-fast,1.0] ∨ x[json-fast,2.0] ∨ x[json-slow,1.0])
x[legacy,1.0] → ¬x[util,2.0]
```

## 4.3, 6.1–6.2 i 8.1. Operacje i optymalizacja

Solver Z3 otrzymuje aksjomaty oraz twarde warunki zapytania. Kryteria są minimalizowane leksykograficznie: kryterium niższego priorytetu nie może pogorszyć wyniku wcześniejszego. Przestarzałość to pozycja wersji na liście od najnowszej, zaczynając od zera; dla zbioru sumowane są pozycje jego wersji.

| Operacja | Kolejność minimalizowanych kryteriów |
|---|---|
| Instalacja do pustego stanu — 4.3 | Przestarzałość pakietów żądanych; liczba pakietów; przestarzałość pozostałych pakietów. |
| Instalacja do istniejącego stanu — 6.1 | Usunięte pakiety; zmiany wersji pakietów zachowanych; przestarzałość nowych pakietów żądanych; liczba nowych pakietów; przestarzałość pozostałych nowych pakietów. |
| Usuwanie zbioru P — 6.2 | Usunięte pakiety ręczne spoza P; zmiany wersji pakietów zachowanych; nowe pakiety; usunięte pakiety. Z `autoremove` ostatnie kryterium zastępuje liczba wszystkich zainstalowanych pakietów. |
| Aktualizacja zbioru P — 8.1 | Przestarzałość P; usunięte pakiety; zmiany wersji zachowanych pakietów spoza P; nowe pakiety; przestarzałość wszystkich pakietów. |

Instalacja wymusza wszystkie żądania. Pakiety żądane stają się ręczne; pozostałe zachowane pakiety utrzymują wcześniejsze oznaczenia. Usuwanie wymusza nieobecność wszystkich pakietów z P, dopuszczając usunięcie lub zmianę wersji pakietów zależnych. Aktualizacja wymusza zachowanie pakietów ręcznych oraz P i nie zmienia oznaczeń automatycznych na ręczne.

Wyniki dla pustego stanu na przykładzie prowadzącego:

| Żądania | Stan wynikowy |
|---|---|
| `app` | `app 2.0`, `lib 2.0`, `util 2.0` |
| `tool` | `tool 1.1`, `lib 1.0`, `json-slow 1.0` |
| `app`, `tool` | `app 1.0`, `tool 1.1`, `lib 1.0`, `json-slow 1.0` |
| `app`, `legacy` | `app 1.0`, `legacy 1.0`, `lib 1.0` |
| `app==2.0`, `tool` | Brak rozwiązania. |

Wyniki operacji rozpoczynanych osobno od `state_example.txt`:

| Zapytanie | Zmiany |
|---|---|
| Instalacja `app==2.0` | `app 1.0 → 2.0`, `lib 1.0 → 2.0`, instalacja `util 2.0`, usunięcie `tool 1.1`. |
| Usunięcie `lib` | Usunięcie `lib 1.0`, `app 1.0`, `tool 1.1`. |
| Usunięcie `tool` z `autoremove` | Usunięcie `tool 1.1` i `json-slow 1.0`. |
| Aktualizacja wszystkich pakietów | `lib 1.0 → 1.5`, instalacja `util 2.0`. |

Każdy wynik przeszedł bezpośrednią weryfikację. Optymalność sprawdzono również przez wyliczenie wszystkich stanów małych repozytoriów, w tym 24 przypadków losowych z ziarnem 2026; porównywano wartości kryteriów, dopuszczając równorzędne rozwiązania.

## 4.4. Weryfikacja stanu

Weryfikator nie używa solvera. Sprawdza istnienie każdej zainstalowanej wersji w repozytorium, wszystkie grupy zależności, konflikty oraz opcjonalnie spełnienie żądań. Zwraca wszystkie naruszenia, a nie tylko pierwsze. Stan odczytany z modelu solvera jest weryfikowany przed zapisaniem; dla usuwania dodatkowo sprawdzana jest nieobecność P, a dla aktualizacji zachowanie pakietów chronionych.

## 4.5. Eksperymenty grupy 16

Pomiary wykonano 2 listopada 2026 r. na Windows 11, Pythonie 3.13.16 i Z3 5.3.3. Polecenie odtwarzające eksperyment:

```sh
uv run python -m src.experiments --data data --group 16 --output results/group16.json
```

| N | Wersje | Aksjomaty | Żądania | Pakiety | Przestarzałość | Budowa [s] | Rozwiązanie [s] | Weryfikacja |
|---:|---:|---:|---|---:|---:|---:|---:|---|
| 10 | 45 | 22 | `attrs`, `filelock`, `quartz-kit` | 4 | 2 | 0.007183 | 0.012233 | Bez naruszeń. |
| 30 | 202 | 149 | `uvicorn`, `typing-extensions`, `basalt-sdk` | 11 | 2 | 0.011753 | 0.045888 | Bez naruszeń. |
| 100 | 1284 | 1124 | `h2`, `tomli-umbra`, `nova-api` | — | — | 0.114124 | 0.082499 | Brak rozwiązania; brak stanu do weryfikacji. |
| 300 | 6636 | 5779 | `yarl`, `aiohttp-pebble`, `nova-cli` | 13 | 1 | 0.825887 | 3.251692 | Bez naruszeń. |
| 1000 | 21193 | 17477 | `uvicorn`, `certifi-yarrow`, `tundra-sdk` | 6 | 0 | 4.691203 | 5.700601 | Bez naruszeń. |

Czas budowy obejmuje wczytanie i walidację repozytorium oraz utworzenie bazy wiedzy. Czas rozwiązania obejmuje wywołanie instalacji, odczyt modelu i obowiązkową walidację wyniku. Dodatkowa kontrola zapisana w pliku wyników jest poza tym pomiarem. Pełne stany i dane pomiarowe: [results/group16.json](results/group16.json).

Czas budowy zwiększał się wraz z liczbą wersji i aksjomatów. Czas rozwiązania zależał także od struktury zależności i konieczności optymalizacji: wykrycie sprzeczności dla N = 100 było szybsze niż znalezienie optimum dla N = 300 i 1000. Sama liczba pakietów nie wyznacza więc czasu rozwiązania.

## 6.3. Wyjaśnienia braku rozwiązania

Aksjomaty i żądania są śledzone oddzielnymi etykietami. Z rdzenia sprzeczności usuwane są kolejno elementy, których pominięcie nadal daje sprzeczność. Wynik jest minimalny przez zawieranie: usunięcie dowolnego pozostałego elementu daje spełnialny zestaw. Nie zakłada się najmniejszej możliwej liczby elementów.

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

`app 2.0` wymaga `lib 2.0`, a każda dostępna wersja `tool` wymaga starszej `lib`. A1 nie pozwala zainstalować obu wersji biblioteki. Usunięcie każdego z sześciu elementów rdzenia osobno potwierdzono jako spełnialne.

### Przypadek N = 100

Jedynym niespełnialnym przypadkiem z 4.5 jest N = 100. Do rdzenia wchodzi samo żądanie `nova-api`; żądania `h2` i `tomli-umbra` nie są potrzebne do sprzeczności.

Rdzeń ma **43 elementy**: żądanie `A = x[nova-api,1.0]`, 14 warunków A1 i 28 zależności A2. Niech `Fi = x[nova-xi,1.0]`, a `Ti = x[nova-xi,2.0]`. Warunki A1 to `¬(Fi ∧ Ti)` dla `i ∈ {1,…,11,13,14,15}`. Każdy z poniższych wierszy C jest warunkiem zależności `A → C`:

```text
T6  ∨ F8  ∨ F4
T10 ∨ T3  ∨ F9
F6  ∨ F2  ∨ F3
F5  ∨ F15 ∨ F10
T3  ∨ T1  ∨ T4
F6  ∨ T14 ∨ T10
T5  ∨ F4  ∨ F2
T13 ∨ T11 ∨ F10
F2  ∨ T11 ∨ T3
T4  ∨ T10 ∨ F3
T9  ∨ F10 ∨ T13
T2  ∨ F10 ∨ T14
T3  ∨ F9  ∨ F13
F3  ∨ T7  ∨ T14
T3  ∨ T14 ∨ T15
F1  ∨ F11 ∨ T14
F8  ∨ F14 ∨ F13
F14 ∨ T4  ∨ F8
F9  ∨ F7  ∨ T8
F3  ∨ F2  ∨ F10
T3  ∨ T9  ∨ T2
T11 ∨ F7  ∨ T2
F11 ∨ F9  ∨ F14
T8  ∨ F14 ∨ F3
F8  ∨ F14 ∨ T7
T9  ∨ T8  ∨ F15
T15 ∨ T8  ∨ T9
T9  ∨ T10 ∨ F4
```

Żądanie wymusza wszystkie te alternatywy jednocześnie, ale nie da się ich spełnić bez naruszenia któregoś z warunków A1. Solver potwierdził sprzeczność rdzenia oraz spełnialność po usunięciu dowolnego z jego 43 elementów. Pełne etykiety obu rdzeni: [results/six-point-examples.json](results/six-point-examples.json).

## 6.4. Scenariusz losowych operacji

Scenariusz rozpoczyna się od pustego stanu i korzysta z `repo_200.json` grupy 16. Ziarno generatora: **2026**. Polecenie:

```sh
uv run python -m src.scenario --repo data/repo_200.json --group 16 --seed 2026 --steps 12 --output results/random-group16.json
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

W każdym kroku otrzymano stan bez naruszeń. Liczba zmian oznacza instalacje, usunięcia oraz podniesienia lub obniżenia wersji. Czasy obejmują operację solvera z jej obowiązkową walidacją. Operacje 6, 8 i 9 nie zmieniły stanu. W kroku 7 `autoremove` usunęło 17 pakietów automatycznych, mimo że wskazany `jsonschema` nie był zainstalowany: w tym momencie nie pozostał żaden pakiet ręczny wymagający ich zachowania.

Ziarno ustala wejścia operacji; czas i wybór pomiędzy równorzędnymi stanami mogą zależeć od środowiska solvera. Pełne zmiany i stany pośrednie: [results/random-group16.json](results/random-group16.json).

## 8.2. Konflikt aktualizacji i front Pareto

Dla stanu `a 1.0 manual`, `b 1.0 manual` najnowsze wersje osiągalne osobno to `a 2.0` i `b 2.0`. Nie można ich zainstalować jednocześnie. Otrzymany minimalny rdzeń zawiera:

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

Żaden punkt nie poprawia jednej współrzędnej bez pogorszenia drugiej. Stan `a 1.0`, `b 2.0` jest zdominowany przez `a 1.1`, `b 2.0`. W zapisanym uruchomieniu zwykła optymalizacja leksykograficzna wybrała drugi punkt; oba mają taką samą sumę przestarzałości. Aktualizacja samego `a` daje `a 2.0`, `b 1.0` bez konfliktu. Każdy zwrócony stan zweryfikowano. Wyniki: [results/eight-point-examples.json](results/eight-point-examples.json).

## 8.3. Dane PyPI

Zaimplementowano odczyt `requires_dist` i `requires_python`, wersje i wymagania PEP 440/508 przez bibliotekę `packaging`, filtrowanie wersji dla Pythona ze środowiska docelowego oraz ocenę znaczników według `meta.environment`. Extras są pomijane. Instalacja, usuwanie, aktualizacja, walidacja i wyjaśnienia korzystają z tego samego interfejsu repozytorium.

**Nie wykonano eksperymentu na wymaganym zbiorze 92 pakietów i 3330 wersji: w udostępnionych materiałach nie było `pypi_data.json`.** Brak zatem wyników i czasów tego scenariusza. Testy na małych danych potwierdzają działanie importera i scenariusza, ale nie zastępują wymaganego pomiaru. Program do jego uruchomienia:

```sh
uv run python -m src.pypi_scenario --repo pypi_data.json --output results/pypi-scenario.json
```
