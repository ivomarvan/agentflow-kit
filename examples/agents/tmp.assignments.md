Zde jsou dvě zbývající varianty zadání pro demonstrační příklad orchestrace AI agentů.
(Varianta 1 — Smart Home — byla zpracována jako `examples/agents/06_smart_home_assistant.py`.)

---

## Varianta 2: Hlasový bankovní asistent a hlídač rozpočtu (FinTech)

### Kontext scénáře

Klient volá na infolinku své banky a chce rychle zjistit stav účtu, převést peníze nebo spočítat, zda si může dovolit nákup. Protože jde o peníze, každou operaci navrženou Workerem musí schválit přísný Judge z hlediska finanční logiky a limitů.

### Architektura grafu (4 vrcholy)

1. **`Call_Inbound_Router`**: Přijme přepis audia, provede základní entitní analýzu (identifikuje částky, měny, jména) a inicializuje stav sezení.
2. **`Transaction_Worker`**: (*Poháněn levnějším LLM*). Podle požadavku klienta volá bankovní nástroje. Sestavuje návrh transakce nebo odpovědi na finanční dotaz.
3. **`Compliance_Judge`**: (*Poháněn dražším LLM*). Kontroluje výstup z Workera. Ověřuje, zda transakce dává smysl (např. zda sedí měnová konverze, zda klient neposílá zápornou částku nebo nepřekračuje denní limity). Pokud Judge najde nesrovnalost, zamítne ji a pošle Workerovi instrukce k opravě.
4. **`Audio_Response_Composer`**: Převádí suchá finanční data a schválené transakce do empatického hlasového projevu (např. místo „Transakce ID 456 schválena“ řekne „V pořádku, peníze jsem vám právě odečetla z účtu“).

### Deterministické nástroje (4)

* `get_balance(account_type)` – Vrátí aktuální zůstatek na běžném/spořicím účtu.
* `convert_currency(amount, from_currency, to_currency)` – Provede matematický přepočet podle aktuálního kurzu.
* `check_daily_limits(amount)` – Vrátí `True/False`, zda požadovaná částka projde denním limitem.
* `log_pending_transaction(target_account, amount)` – Zanese transakci do dočasného registru před finálním odesláním.

---

## Varianta 3: Hlasový asistent pro firemní logistiku a nákup (Operations)

### Kontext scénáře

Skladník nebo terénní pracovník mluví do aplikace v telefonu a potřebuje objednat kurýra, zkontrolovat dostupnost dílů na skladě nebo přepočítat cenu dopravy pro zákazníka. Systém musí fungovat rychle, ale Judge hlídá firemní politiku a rozpočtová pravidla.

### Architektura grafu (5 vrcholů)

1. **`Audio_Input_Cleaner`**: Přijme text z hlasového vstupu, který může obsahovat ruchy z provozu (přeřeknutí, hluk na pozadí). Vyčistí text a extrahuje klíčová data (kódy produktů, adresy).
2. **`Logistics_Worker`**: (*Poháněn levnějším LLM*). Vyhledává informace v interních systémech pomocí nástrojů a sestavuje logistický plán (např. kalkulaci ceny nebo rezervaci materiálu).
3. **`Policy_Judge`**: (*Poháněn dražším LLM*). Kontroluje, zda plán neodporuje interním směrnicím (např. zda nákup nepřekračuje limit pro daného zaměstnance, nebo zda nebyl vybrán příliš drahý způsob dopravy). Pokud neprojde, vrací se s odůvodněním zpět Workerovi.
4. **`State_Consolidator`**: Spojí schválená data z předchozích kroků, finálně zafixuje stav v databázi a připraví čistá data pro expedici.
5. **`Voice_Brief_Generator`**: Zformuje velmi stručný, úderný report pro pracovníka do sluchátek (např. „Objednáno. Kurýr dorazí ve 14:00. Na skladě zbývá 5 kusů“).

### Deterministické nástroje (3)

* `check_stock(item_id)` – Vrátí počet kusů na skladě a jejich lokaci.
* `calculate_shipping_cost(weight_kg, distance_km)` – Vypočítá fixní cenu dopravy na základě zadaných parametrů.
* `get_user_permission_level(user_id)` – Vrátí finanční limit a oprávnění daného pracovníka.