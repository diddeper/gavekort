# Gavekort

Gift cards for 60 and 90 min massages. Each card has a unique QR code, and the cards are tracked in a private Google Sheet.

- **Python** generates branded PDF cards (digital) and/or QR images (PNG/SVG for physical cards), plus a CSV to import into the sheet.
- **Google Sheets + Apps Script** tracks each card. Scanning a card's QR with the iPhone camera opens a small web app. It shows the card's status and offers one tap to **Aktiver** (sold) or **Løs inn** (redeem).

```
Ikke solgt ──Aktiver──▶ Aktiv ──Løs inn──▶ Innløst
(generated)           (sold, expires      (used)
                       in 12 months)
```

Opening the page never changes anything; only the buttons do, and each one asks you to confirm. So link previews, double taps and accidental scans are harmless. Expiry is counted from the activation date. An expired card shows a warning but can still be redeemed, at your discretion.

## Project layout

```
config.toml            Brand (colours, name, mark, booking link), card titles, web app URL
assets/mark.svg        Hands mark drawn in the corner of the PDF
assets/fonts/          Montserrat Light/Regular/Medium (SIL Open Font License, see OFL.txt), embedded in the PDFs
src/gavekort/
  config.py            Loads and validates config.toml
  codes.py             Unguessable, readable codes like GK-7F3K-9QXA
  qr.py                The single QR source: URL, PNG, SVG, vector matrix
  card.py              Draws the gift card PDF (148 x 93 mm, design "1c alt 3")
  batch.py             Generates a batch: files + batch.csv / import.csv
  cli.py               `gavekort generate` / `gavekort preview`
apps_script/
  Kode.gs              Web app: doGet, activate, redeem, setupSheet
  Side.html            Mobile page shown after scanning
  appsscript.json      Manifest: time zone, scopes, web app settings
tests/                 pytest suite
```

## Requirements

- [uv](https://docs.astral.sh/uv/). It installs Python 3.13 and all dependencies by itself.
- A Google account for each of you.

## One-time setup

Menu names are given in English with the Norwegian Google interface in parentheses.

### 1. Google Sheet and Apps Script

1. Create a new Google Sheet, e.g. "Gavekort".
2. Open **Extensions → Apps Script** (*Utvidelser → Apps Script*). Always open the script from *this* spreadsheet: the script belongs to the spreadsheet it was created from. Replace the contents of `Kode.gs` with `apps_script/Kode.gs`. Add an HTML file named exactly `Side` with the contents of `apps_script/Side.html` (the name must match `createTemplateFromFile('Side')` in `Kode.gs`).
3. Under **Project Settings** (*Prosjektinnstillinger*, ⚙️):
   - Tick *Show "appsscript.json" manifest file in editor*, then replace that file's contents with `apps_script/appsscript.json`.
   - Under **Script properties** (*Skriptegenskaper*), add:

     | Property | Value |
     |---|---|
     | `ALLOWED_EMAILS` | `her@gmail.com,you@gmail.com` |
     | `BOOKING_URL` | her booking page |
     | `VALIDITY_MONTHS` | optional, default `12` |

4. Save (Cmd+S). In the toolbar above the code, pick `setupSheet` in the function dropdown and click **Run** (*Kjør*). Approve the permissions: *Review permissions* → your account → *Advanced* → *Go to … (unsafe)* → *Allow* (*Gå gjennom tillatelser* → *Avansert* → *Gå til … (utrygt)* → *Tillat*). The warning appears because the script is your own, unverified app. This creates the `Gavekort` tab with headers, a filter, status colours and date formats.
5. **Deploy → New deployment → Web app** (*Distribuer → Ny distribusjon → Nettapp*):
   - *Execute as:* **User accessing the web app**
   - *Who has access:* **Anyone with Google account**

   Copy the URL that ends in `/exec`. If the URL you copy contains `/u/1/` or similar, remove that part: it only selects an account in your current browser.
6. Share the spreadsheet (as **Editor**) with the other person. Share it with nobody else.
7. Set up each phone (see [Adding a phone or a person](#adding-a-phone-or-a-person)).

### 2. Python

```sh
uv sync
```

Edit `config.toml`:

- `web_app_url`: the `/exec` URL from step 5. `generate` refuses to run without it.
- `validity_text`: the validity line printed on the card. Keep it in line with the `VALIDITY_MONTHS` script property.
- `[brand]`:
  - `background_color`, `text_color`: hex colours.
  - `name`, `tagline`: the large name and the small uppercase line under it. Leave either empty to drop it.
  - `mark`: single-colour SVG drawn large in the bottom-right corner, in `text_color`. Only straight-line paths (`M`, `L`, `H`, `V`, `Z`) are supported.
  - `booking_url`: where the booking line on the card links to.
  - `booking_text`: the clickable booking line, e.g. "Book time – trykk her" (printed in uppercase). Leave it empty to print a shortened URL instead, which is better for cards that will be printed.
  - `scan_text`: small caption under the QR, e.g. "Skannes ved oppmøte", so customers don't take the QR for a booking link. Leave it empty to drop it.
  - `font_light` / `font_regular` / `font_bold`: `.ttf` files (Montserrat Light / Regular / Medium by default). Light is used for the name and title, bold for labels, the code and the booking link.
  - `business_name`: only stored as the PDF's author; it is not printed on the card.
- `[cards.60]` / `[cards.90]`: card titles, used in the PDF metadata (title and code are not printed on the card; the sheet tracks them).

Check the design (this opens the PDF in Preview):

```sh
uv run gavekort preview --type 60
uv run gavekort preview --type 90
```

## Daily use

**Make a batch of digital cards (PDF):**

```sh
uv run gavekort generate --type 60 --count 20
```

**Make QR codes for physical cards.** SVG is vector, which is best for a print shop. PNG is about 700 px. `--label` prints the code under the QR:

```sh
uv run gavekort generate --type 90 --count 30 --format png,svg --label
```

Use `--format pdf,png,svg` to get both.

Each batch goes into its own folder, e.g. `output/2026-10-30_1312_60min/`, which contains:

- `pdf/` and/or `qr/`: the cards
- `batch.csv`: the batch with a header row, for reading (opens nicely in Numbers/Excel)
- `import.csv`: the same rows without a header, for importing into the sheet

**Import the batch into the sheet:** open the `Gavekort` tab, then **File → Import → Upload** (*Fil → Importer → Last opp*) `import.csv` → *Import location: **Append to current sheet*** (*Legg til i gjeldende ark*). Import `import.csv`, not `batch.csv`: the import has no "skip header" option, so the header in `batch.csv` would end up as an extra row in the sheet.

**Selling a card:** send the PDF, or hand over the physical card. Then scan it and tap **Aktiver (solgt) → Bekreft aktivering**.

**When the customer comes in:** scan the QR on their phone or card and tap **Løs inn → Bekreft innløsning**.

**Overview:** the sheet itself. Columns: `Kode | Type | Format | Status | Generert | Aktivert | Utløper | Innløst | Aktivert av | Innløst av | Notat`. Filter on Status or Type. Each change records the time and who made it. To undo a mistake, edit the row by hand (for example set Status back to `Aktiv` and clear `Innløst`/`Innløst av`). `Notat` is free text for your own notes.

**Test cards:** after testing, delete the test rows in the sheet and the test batch folder under `output/`.

## Adding a phone or a person

1. Add the person's Google email to the `ALLOWED_EMAILS` script property (comma-separated).
2. Share the spreadsheet with that email as **Editor**.
3. On their iPhone, in Safari, sign in to Google with **only** that account: go to google.com → profile picture → *Sign out of all accounts* (*Logg av alle kontoer*) → sign in again with just that one. With several accounts signed in, Google may pick the wrong one and show *"Beklager, filen kan ikke åpnes"*.
4. Open the `/exec` URL once and approve the permissions. Then scan a card: you should see its status and buttons. If you see the booking page instead, step 1 is missing; if you see *"Kontoen din har ikke tilgang til regnearket"*, step 2 is.

## Updating the script

When `Kode.gs`, `Side.html` or `appsscript.json` change in this repo:

1. In the Apps Script editor, replace the contents of each changed file and save. Keep the names: `Kode.gs`, `Side` and `appsscript.json`.
2. **Deploy → Manage deployments → ✏️ Edit → Version: New version → Deploy** (*Distribuer → Administrer distribusjoner → ✏️ → Versjon: Ny versjon → Distribuer*).
3. Scan a card to check.

Changes in `config.toml` or the Python code need no redeploy; they only affect newly generated cards.

## Security model

Only the two of you can see a card's status or change it. There are three independent checks:

1. **Google login.** The web app requires a signed-in Google account and runs *as that person*.
2. **Private sheet.** Because the script runs as the person scanning, it can only read the sheet if the sheet has been shared with that person.
3. **Allowlist.** Every page load and every button call checks the signed-in email against `ALLOWED_EMAILS` before it touches the sheet.

The codes have about 40 random bits, so they can't be guessed, and an unsold card can't be redeemed until one of you activates it.

**When a customer scans their own card**, Google first asks them to sign in and to approve the script's permissions. The script asks only for its own spreadsheet and the user's email address. If they go ahead, they see a neutral page with the booking link and nothing about the card. That consent screen is unavoidable with this setup, because the script has to run as the person scanning for checks 2 and 3 to work.

## ⚠️ Keep the web app URL stable

Every QR code you have printed contains the `/exec` URL. After you change the script, **update the existing deployment**: **Deploy → Manage deployments → ✏️ Edit → Version: New version → Deploy**. Never create a new deployment, or all existing cards stop working.

## Troubleshooting

| Symptom | Fix |
|---|---|
| *"Sorry, unable to open the file"* / *"Beklager, filen kan ikke åpnes"* | Usually several Google accounts signed in to the browser (a link containing `/u/1/` is a sign of this). Sign out of all accounts and sign in with only the allowlisted one. On iPhone, Chrome also picks up accounts from other Google apps. |
| The booking page is shown instead of the card | Your email is not in `ALLOWED_EMAILS`. |
| *"Kontoen din har ikke tilgang til regnearket"* / *"Du har ikke tillatelse til å se det forespurte dokumentet"* | The email is in `ALLOWED_EMAILS`, but the spreadsheet isn't shared with that exact Google account. Share it with that address as **Editor**. |
| *"Beklager, filen kan ikke åpnes"* only on card links, while the bare `/exec` URL works | The card URL uses a parameter Apps Script reserves (`c` or `sid`). Cards use `?kode=`; regenerate any old QR codes made with `?c=`. |
| "Ukjent gavekort" | The batch's `import.csv` hasn't been imported, or it was imported into a different tab than `Gavekort`. |
| "Fant ikke arket «Gavekort»" | The **tab** (bottom of the window, not the file name) must be named exactly `Gavekort`, with no trailing space. If it is, the script belongs to a different spreadsheet: open *Extensions → Apps Script* from the spreadsheet with the data and check that its deployment URL matches `web_app_url`. The error log is under *Executions* (*Utføringer*) in the editor. |
| `Konfigurasjonsfeil: web_app_url is empty` | Paste the `/exec` URL into `config.toml`. |

## Development

```sh
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
```

- mypy runs in strict mode.
- ruff enforces Google-style docstrings.
- Tests cover code generation, the QR outputs, PDF content and links, batch output and CSV, and config validation.
- The QR URL parameter is `kode`. Never use `c` or `sid`: Apps Script reserves them (a test guards this).
- The sheet columns are defined twice and must stay in sync: `SHEET_COLUMNS` in `src/gavekort/batch.py` and `HEADERS` in `apps_script/Kode.gs`.
