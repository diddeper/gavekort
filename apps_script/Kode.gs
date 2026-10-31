/**
 * Gavekort – web app for activating and redeeming gift cards.
 *
 * Scanning a card's QR opens `<web app URL>?kode=<code>`. The page shows the card
 * and offers the next step: "Ikke solgt" → Aktiver → "Aktiv" → Løs inn → "Innløst".
 * Opening the page never changes anything; only the buttons do.
 *
 * Clip cards: column "Klipp" holds the number of treatments (empty = 1, an ordinary
 * card). Each Løs inn adds 1 to "Brukt"; the card stays "Aktiv" until all are used.
 * Every redemption is also appended to the "Logg" sheet.
 *
 * Access control (all three must pass):
 *   1. Deployment: execute as the user accessing, anyone with a Google account.
 *   2. The spreadsheet is shared only with the allowed accounts.
 *   3. Script property ALLOWED_EMAILS (comma-separated) is checked on every call.
 *
 * Script properties (Project Settings → Script properties):
 *   ALLOWED_EMAILS   e.g. "her@gmail.com,me@gmail.com"
 *   BOOKING_URL      shown to anyone else who scans a card
 *   VALIDITY_MONTHS  optional, default 12
 */

const SHEET_NAME = 'Gavekort';
const LOG_SHEET_NAME = 'Logg';
const LOG_HEADERS = ['Tidspunkt', 'Kode', 'Klipp', 'Innløst av'];
/** URL parameter with the card code. Never `c` or `sid`: Apps Script reserves them. */
const CODE_PARAM = 'kode';
const TIME_ZONE = 'Europe/Oslo';
const CODE_PATTERN = /^GK-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$/;

/** Column headers, in order. Must match SHEET_COLUMNS in src/gavekort/batch.py. */
const HEADERS = [
  'Kode', 'Type', 'Format', 'Status', 'Generert', 'Aktivert',
  'Utløper', 'Innløst', 'Aktivert av', 'Innløst av', 'Notat',
  'Klipp', 'Brukt',
];

/** 1-based column numbers, derived from HEADERS. */
const COL = Object.freeze({
  code: 1, type: 2, format: 3, status: 4, generated: 5, activated: 6,
  expires: 7, redeemed: 8, activatedBy: 9, redeemedBy: 10, note: 11,
  clips: 12, used: 13,
});

const STATUS = Object.freeze({
  notSold: 'Ikke solgt',
  active: 'Aktiv',
  redeemed: 'Innløst',
});

/**
 * @typedef {Object} CardView  Everything the page needs to render a card.
 * @property {'denied'|'unknown'|'card'} kind
 * @property {string} [code]
 * @property {string} [type]       "60" or "90"
 * @property {string} [status]     One of STATUS
 * @property {string} [activated]  Formatted date/time, or ""
 * @property {string} [expires]    Formatted date, or ""
 * @property {boolean} [expired]
 * @property {string} [redeemed]   Formatted date/time of the latest redemption, or ""
 * @property {string} [redeemedBy]
 * @property {number} [clips]      Treatments on the card, 1 for an ordinary card
 * @property {number} [used]       Treatments redeemed so far
 * @property {string} [bookingUrl] Only for kind "denied"
 * @property {string} [message]    Optional feedback after an action
 */

/**
 * Web app entry point. Renders the card page for `?kode=<code>`.
 * @param {GoogleAppsScript.Events.DoGet} e
 * @returns {GoogleAppsScript.HTML.HtmlOutput}
 */
function doGet(e) {
  const code = String((e && e.parameter && e.parameter[CODE_PARAM]) || '').trim().toUpperCase();
  const template = HtmlService.createTemplateFromFile('Side');
  template.initialState = JSON.stringify(viewFor_(code)).replace(/</g, '\\u003c');
  return template
    .evaluate()
    .setTitle('Gavekort')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/**
 * Mark a card as sold. Called from the page via google.script.run.
 * @param {string} code
 * @returns {CardView}
 */
function activate(code) {
  return transition_(code, STATUS.notSold, null, (sheet, row, now, email) => {
    const expires = new Date(now);
    expires.setMonth(expires.getMonth() + validityMonths_());
    sheet.getRange(row, COL.status).setValue(STATUS.active);
    sheet.getRange(row, COL.activated).setValue(now);
    sheet.getRange(row, COL.expires).setValue(expires);
    sheet.getRange(row, COL.activatedBy).setValue(email);
    return 'Gavekortet er aktivert.';
  });
}

/**
 * Use one treatment on a card. Called from the page via google.script.run.
 * The card becomes "Innløst" once every clip is used.
 * @param {string} code
 * @param {number} expectedUsed  The "Brukt" value the page showed. If it has changed
 *     since (a double tap, or another phone), nothing is redeemed.
 * @returns {CardView}
 */
function redeem(code, expectedUsed) {
  return transition_(code, STATUS.active, expectedUsed, (sheet, row, now, email) => {
    const card = cardView_(sheet, row);
    const used = card.used + 1;
    sheet.getRange(row, COL.used).setValue(used);
    sheet.getRange(row, COL.redeemed).setValue(now);
    sheet.getRange(row, COL.redeemedBy).setValue(email);
    if (used >= card.clips) {
      sheet.getRange(row, COL.status).setValue(STATUS.redeemed);
    }
    logSheet_(sheet.getParent()).appendRow([now, card.code, `${used} av ${card.clips}`, email]);
    if (card.clips === 1) return 'Gavekortet er løst inn.';
    const left = card.clips - used;
    return left > 0
      ? `Klipp ${used} av ${card.clips} løst inn. ${left} igjen.`
      : `Siste klipp (${used} av ${card.clips}) løst inn.`;
  });
}

/**
 * Create or tidy up the "Gavekort" sheet: headers, filter, validation, colours.
 * Run once from the Apps Script editor (select setupSheet → Run). Safe to re-run.
 */
function setupSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  const maxRows = sheet.getMaxRows();

  sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
  sheet.setFrozenRows(1);
  const filter = sheet.getFilter();
  if (filter && filter.getRange().getNumColumns() < HEADERS.length) {
    filter.remove(); // Created before columns were added: recreate it over all of them.
  }
  if (!sheet.getFilter()) {
    sheet.getRange(1, 1, maxRows, HEADERS.length).createFilter();
  }

  sheet.getRange(2, COL.code, maxRows - 1, 1).setFontFamily('Roboto Mono');
  sheet.getRange(2, COL.type, maxRows - 1, 1).setNumberFormat('@').setHorizontalAlignment('center');
  sheet.getRange(2, COL.generated, maxRows - 1, 2).setNumberFormat('yyyy-mm-dd hh:mm');
  sheet.getRange(2, COL.expires, maxRows - 1, 1).setNumberFormat('yyyy-mm-dd');
  sheet.getRange(2, COL.redeemed, maxRows - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm');
  sheet.getRange(2, COL.clips, maxRows - 1, 2).setNumberFormat('0').setHorizontalAlignment('center');

  const statusRange = sheet.getRange(2, COL.status, maxRows - 1, 1);
  statusRange.setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(Object.values(STATUS), true)
      .setAllowInvalid(false)
      .build());

  const colours = [
    [STATUS.notSold, '#EEEEEE', '#555555'],
    [STATUS.active, '#D9F2E3', '#1E6B3C'],
    [STATUS.redeemed, '#F8DADA', '#8A1F1F'],
  ];
  sheet.setConditionalFormatRules(colours.map(([text, bg, fg]) =>
    SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo(text)
      .setBackground(bg)
      .setFontColor(fg)
      .setRanges([statusRange])
      .build()));

  sheet.autoResizeColumns(1, HEADERS.length);

  const log = logSheet_(ss);
  log.getRange(2, 1, log.getMaxRows() - 1, 1).setNumberFormat('yyyy-mm-dd hh:mm');
  log.autoResizeColumns(1, LOG_HEADERS.length);
}

// ---------------------------------------------------------------------------
// Internals (trailing underscore = not callable from the page)
// ---------------------------------------------------------------------------

/**
 * Run a state change under a lock, after re-checking access and current state.
 * @param {string} code
 * @param {string} requiredStatus  The status the card must have for this action.
 * @param {?number} expectedUsed   If not null, "Brukt" must still have this value.
 * @param {function(GoogleAppsScript.Spreadsheet.Sheet, number, Date, string): string} apply
 *     Makes the change and returns the success message.
 * @returns {CardView}
 */
function transition_(code, requiredStatus, expectedUsed, apply) {
  const email = currentEmail_();
  if (!isAllowed_(email)) {
    return deniedView_();
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const found = findCard_(code);
    if (!found) {
      return { kind: 'unknown', code };
    }
    const card = cardView_(found.sheet, found.row);
    // Someone else (or a double tap) got there first: show the real state.
    if (card.status !== requiredStatus) {
      return Object.assign(card, { message: `Ingen endring: kortet har status «${card.status}».` });
    }
    if (expectedUsed !== null && Number(expectedUsed) !== card.used) {
      return Object.assign(card, {
        message: `Ingen endring: et klipp ble nettopp løst inn. Nå brukt ${card.used} av ${card.clips}.`,
      });
    }
    const message = apply(found.sheet, found.row, new Date(), email);
    SpreadsheetApp.flush();
    return Object.assign(cardView_(found.sheet, found.row), { message });
  } finally {
    lock.releaseLock();
  }
}

/**
 * Build the view for a scanned code, enforcing access first.
 * @param {string} code
 * @returns {CardView}
 */
function viewFor_(code) {
  if (!isAllowed_(currentEmail_())) {
    return deniedView_();
  }
  const found = findCard_(code);
  return found ? cardView_(found.sheet, found.row) : { kind: 'unknown', code };
}

/**
 * Locate a card's row by exact code match in column A.
 * @param {string} code
 * @returns {{sheet: GoogleAppsScript.Spreadsheet.Sheet, row: number}|null}
 */
function findCard_(code) {
  if (!CODE_PATTERN.test(code)) {
    return null;
  }
  let sheet;
  try {
    sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  } catch (err) {
    // Runs as the scanning user: fails if the spreadsheet isn't shared with them.
    throw new Error('Kontoen din har ikke tilgang til regnearket. Be eieren dele det med deg som redigerer.');
  }
  if (!sheet) {
    throw new Error(`Fant ikke arket «${SHEET_NAME}». Kjør setupSheet først.`);
  }
  const cell = sheet
    .getRange(2, COL.code, Math.max(sheet.getLastRow() - 1, 1), 1)
    .createTextFinder(code)
    .matchEntireCell(true)
    .findNext();
  return cell ? { sheet, row: cell.getRow() } : null;
}

/**
 * @param {GoogleAppsScript.Spreadsheet.Sheet} sheet
 * @param {number} row
 * @returns {CardView}
 */
function cardView_(sheet, row) {
  const values = sheet.getRange(row, 1, 1, HEADERS.length).getValues()[0];
  const at = (col) => values[col - 1];
  const expires = at(COL.expires);
  return {
    kind: 'card',
    code: String(at(COL.code)),
    type: String(at(COL.type)),
    status: String(at(COL.status)),
    activated: formatDate_(at(COL.activated), 'd. MMM yyyy HH:mm'),
    expires: formatDate_(expires, 'd. MMM yyyy'),
    expired: expires instanceof Date && expires.getTime() < Date.now(),
    redeemed: formatDate_(at(COL.redeemed), 'd. MMM yyyy HH:mm'),
    redeemedBy: String(at(COL.redeemedBy) || ''),
    clips: positiveInt_(at(COL.clips), 1),
    used: Math.max(parseInt(at(COL.used), 10) || 0, 0),
  };
}

/**
 * The "Logg" sheet, created with headers if missing.
 * @param {GoogleAppsScript.Spreadsheet.Spreadsheet} ss
 * @returns {GoogleAppsScript.Spreadsheet.Sheet}
 */
function logSheet_(ss) {
  let log = ss.getSheetByName(LOG_SHEET_NAME);
  if (!log) {
    log = ss.insertSheet(LOG_SHEET_NAME);
    log.getRange(1, 1, 1, LOG_HEADERS.length).setValues([LOG_HEADERS]).setFontWeight('bold');
    log.setFrozenRows(1);
  }
  return log;
}

/** @returns {CardView} */
function deniedView_() {
  return {
    kind: 'denied',
    bookingUrl: PropertiesService.getScriptProperties().getProperty('BOOKING_URL') || '',
  };
}

/** @returns {string} The scanning user's email, lower-cased, or "". */
function currentEmail_() {
  return (Session.getActiveUser().getEmail() || '').trim().toLowerCase();
}

/**
 * @param {string} email
 * @returns {boolean}
 */
function isAllowed_(email) {
  const allowed = (PropertiesService.getScriptProperties().getProperty('ALLOWED_EMAILS') || '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
  return email !== '' && allowed.includes(email);
}

/** @returns {number} */
function validityMonths_() {
  return positiveInt_(PropertiesService.getScriptProperties().getProperty('VALIDITY_MONTHS'), 12);
}

/**
 * @param {*} value  A cell or property value.
 * @param {number} fallback  Used when value is empty or not a positive integer.
 * @returns {number}
 */
function positiveInt_(value, fallback) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

/**
 * @param {*} value  A cell value; only Date instances are formatted.
 * @param {string} pattern
 * @returns {string}
 */
function formatDate_(value, pattern) {
  return value instanceof Date ? Utilities.formatDate(value, TIME_ZONE, pattern) : '';
}
