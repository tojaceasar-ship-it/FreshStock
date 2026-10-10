# AUDIT CHECKPOINT

## Cel, zakres i instrukcje

- Produkcyjna baza FreshStock ma zostać przywrócona do czystej postaci.
- Usunąć użytkowników, tenantów, subskrypcje, ustawienia sklepów i wszystkie pozostałe dane aplikacyjne.
- Zachować schemat bazy oraz tabelę wersji migracji `alembic_version`.
- Przed operacją wykonać pełną logiczną kopię danych i zweryfikować stan po operacji.

## Wersja i środowisko

- Repozytorium: `tojaceasar-ship-it/FreshStock`, gałąź `main`.
- Bazowy commit przed rozszerzeniem narzędzia: `a8a3501fd563b5c30e388d905db9684590967b0b`.
- Środowisko: produkcja Vercel + produkcyjna baza PostgreSQL Neon.
- Frontend: `https://freshstock-app.vercel.app`.
- API: `https://freshstock-api.vercel.app`.
- Operacja wykonana: 2026-10-10 03:36 UTC.

## Wykonane testy i dowody

- Guarded reset: `ALLOW_PRODUCTION_RESET=FRESHSTOCK_ALL_DATA` oraz `--all-data --execute`.
- Wynik operacji: `RESET_OK`.
- Niezależny dry-run po operacji: wszystkie 48 tabel danych mają licznik `0`; `alembic_version` ma licznik `1`.
- Kluczowe liczniki po operacji: `users=0`, `tenants=0`, `subscriptions=0`, `store_settings=0`, `onboarding_progress=0`, `tenant_stores=0`.
- API health: HTTP 200, `{"status":"ok","version":"1.0.0"}`.
- Frontend: HTTP 200.
- Stan inicjalizacji: `GET /api/auth/bootstrap-status` zwrócił HTTP 200 i `{"required":true}`.
- Kopia bezpośrednio przed pełnym resetem: `backend/.maintenance-backups/freshstock-production-before-reset-20261010T033643Z.json`.
- Rozmiar kopii: 367446 bajtów.
- SHA-256 kopii: `B2CF98DED19752A65C0F9CDD7784D47BC0A3F6FC395EAEFECC08787B863A77C6`.
- Wcześniejsza pełna kopia sprzed resetu operacyjnego: `backend/.maintenance-backups/freshstock-production-before-reset-20261010T030107Z.json`, SHA-256 `28B2C41E818A7417AFFAE360D474C53DD41F5F2294496B0D003C2A18705EDA4A`.

## Wykryte problemy i naprawy

- Pierwotny skrypt zachowywał tabele tożsamości i konfiguracji. Dodano jawny tryb `--all-data`.
- Tryb pełnego resetu ma odrębne potwierdzenie `FRESHSTOCK_ALL_DATA`, zachowuje wyłącznie `alembic_version`, tworzy kopię i weryfikuje liczniki po transakcji.

## Pozostałe scenariusze i blokady

- Brak blokad.
- Brak pozostałych scenariuszy dla żądanego czyszczenia bazy.

## Dokładny następny krok

- Zacommitować i wypchnąć rozszerzony skrypt oraz ten checkpoint do `main`, po czym potwierdzić czysty status repozytorium.
